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
    assert sunny["dataColors"][0] in {"#B65B0A", "#F7941E"}
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


def test_conditional_status_duplicates_are_detected_in_category_chart(
        tmp_path: Path) -> None:
    """Previous target-chart bug: multiple categories evaluate to same red."""
    out = tmp_path / "conditional"
    apply_theme(SOURCE, "light",
                load_palette("light", None, "organic-palette"), out)
    report = out / SOURCE.name
    file = (report / "definition/pages/Executive_overview/visuals/"
            "cd368855f0cc75592aed/visual.json")
    obj = json.loads(file.read_text(encoding="utf-8"))
    target = obj["visual"]["objects"]["dataPoint"]
    target[1]["properties"]["fill"]["solid"]["color"]["expr"] = {
        "Conditional": {"Cases": [
            {"Condition": {"Comparison": {"ComparisonKind": 3,
                "Left": {"Measure": {"Expression": {"SourceRef": {
                    "Entity": "Fact Sales"}}, "Property": "Reporting Year GM %"}},
                "Right": {"Literal": {"Value": "0.35D"}}}},
             "Value": {"Literal": {"Value": "'#BE123C'"}}}]}}
    target[1]["selector"] = {
        "data": [{"dataViewWildcard": {"matchingOption": 1}}]}
    obj["visual"]["objects"]["dataPoint"] = target[:2]
    file.write_text(json.dumps(obj), encoding="utf-8")
    failures = [f for f in audit(str(report))["findings"]
                if f["rule"] == "color.category_conditional_shared_status"]
    assert len(failures) == 1
    assert failures[0]["importance"] == "high"
    assert failures[0]["visual_ids"] == ["cd368855f0cc75592aed"]


def test_five_category_near_collision_previous_40_threshold_is_rejected(
        tmp_path: Path) -> None:
    """Old 40/9 rule passed this blue/beige pair despite visible closeness."""
    from vqs.series_readability import distance
    first, second = "#88A4CD", "#C2B093"
    assert 40 <= distance(first, second) < 45
    dest = tmp_path / "near"
    apply_theme(SOURCE, "dark", load_palette("dark", None, "graphite-red"), dest)
    report = dest / SOURCE.name
    file = (report / "definition/pages/Products_brands/visuals/"
            "6eef7fa2804207db6a94/visual.json")
    obj = json.loads(file.read_text(encoding="utf-8"))
    entries = obj["visual"]["objects"]["dataPoint"]
    for entry, shade in zip(entries[1:3], (first, second)):
        entry["properties"]["fill"]["solid"]["color"]["expr"] = {
            "Literal": {"Value": "'" + shade + "'"}}
    file.write_text(json.dumps(obj), encoding="utf-8")
    findings = [x for x in audit(str(report))["findings"]
                if x["rule"] == "color.category_series_collision"
                and x["visual_ids"] == ["6eef7fa2804207db6a94"]]
    assert len(findings) == 1
    assert any(set(x["colors"]) == {first, second}
               for x in findings[0]["evidence"]["colliding_pairs"])
