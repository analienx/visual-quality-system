"""Source-level assigned category colors: exact names, rendered-theme IDs, hard failures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vqs.premium import audit
from vqs.theme import apply_theme, load_palette

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "examples/contoso-retail/Contoso Retail.Report"


def _collisions(report: Path) -> list[dict]:
    return [x for x in audit(str(report))["findings"]
            if x["rule"] == "color.category_series_collision"]


def test_existing_organic_exposes_named_category_collision(tmp_path: Path) -> None:
    """Mutation deliberately reproduces the actual historic duplicate-bar bug."""
    palette = load_palette("light", None, "organic-palette")
    result = tmp_path / "candidate"
    apply_theme(SOURCE, "light", palette, result)
    report = result / SOURCE.name
    assert _collisions(report) == []
    file = (report / "definition/pages/Markets_drivers/visuals/"
            "c1d2e3f40516273849ab/visual.json")
    obj = json.loads(file.read_text(encoding="utf-8"))
    data = obj["visual"]["objects"]["dataPoint"]
    # Change *Sports & Outdoors* to exactly the Electronics color. The palette
    # itself remains perfectly valid; earlier VQS checks failed to catch this.
    data[3]["properties"]["fill"]["solid"]["color"]["expr"][
        "ThemeDataColor"]["ColorId"] = data[1]["properties"]["fill"][
            "solid"]["color"]["expr"]["ThemeDataColor"]["ColorId"]
    file.write_text(json.dumps(obj), encoding="utf-8")
    collisions = _collisions(report)
    assert len(collisions) == 1
    issue = collisions[0]
    assert issue["page_id"] == "Markets_drivers"
    assert issue["visual_ids"] == ["c1d2e3f40516273849ab"]
    assert issue["importance"] == "high"
    assert issue["evidence"]["colliding_pairs"][0]["categories"] == [
        "Electronics", "Sports & Outdoors"]
    assert issue["evidence"]["colliding_pairs"][0]["normal_delta_e76"] == 0


@pytest.mark.parametrize("slug", ("organic-palette", "sunny-palette",
                                  "graphite-red", "indigo-ember",
                                  "petrol-gold"))
@pytest.mark.parametrize("mode", ("light", "dark"))
def test_featured_theme_actual_categories_clear_gate(
        tmp_path: Path, slug: str, mode: str) -> None:
    report_path = tmp_path / (slug+"-"+mode)
    apply_theme(SOURCE, mode, load_palette(mode, None, slug), report_path)
    assert _collisions(report_path / SOURCE.name) == []


@pytest.mark.parametrize("mode", ("light", "dark"))
def test_brand_inspired_primary_color_roles_remain_recognizable(
        mode: str) -> None:
    organic = load_palette(mode, None, "organic-palette")
    sunny = load_palette(mode, None, "sunny-palette")
    assert organic["dataColors"][0] in {"#1B4298", "#F47A9A"}
    assert sunny["dataColors"][0] in {"#B65B0A", "#FFB14F"}
    # Organic retains blue/pink/green/sky-blue vocabulary; Sunny's
    # orange and complementary neutrals remain separate from analytics colors.
    assert organic["dataColors"][1] != organic["dataColors"][2]
    assert sunny["dataColors"][1] != sunny["dataColors"][2]


def test_uniform_wildcard_fill_is_flagged_but_business_rule_is_not(
        tmp_path: Path) -> None:
    """Unscoped Retail/Online shared blue is detected in actual PBIR."""
    palette = load_palette("light", None, "sunny-palette")
    dest = tmp_path / "wildcard"
    apply_theme(SOURCE, "light", palette, dest)
    report = dest / SOURCE.name
    original_findings = audit(str(report))["findings"]
    assert not any(f["rule"] == "color.category_wildcard_shared_fill"
                   for f in original_findings)
    file = (report/"definition/pages/Markets_drivers/visuals/"
            "channel-mix-bar/visual.json")
    doc = json.loads(file.read_text(encoding="utf-8"))
    scoped = doc["visual"]["objects"]["dataPoint"][1]
    scoped["selector"] = {
        "data": [{"dataViewWildcard": {"matchingOption": 1}}]}
    doc["visual"]["objects"]["dataPoint"] = [scoped]
    file.write_text(json.dumps(doc), encoding="utf-8")
    risks = [f for f in audit(str(report))["findings"]
             if f["rule"] == "color.category_wildcard_shared_fill"]
    assert len(risks) == 1
    assert risks[0]["page_id"] == "Markets_drivers"
    assert risks[0]["visual_ids"] == ["channel-mix-bar"]
    assert risks[0]["evidence"]["categoryDistinctness"] == (
        "not explicitly guaranteed")
