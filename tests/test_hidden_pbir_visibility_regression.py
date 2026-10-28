"""Regression: explicitly hidden native PBIR visuals are not visible overlaps.

The native Contoso Markets screenshot shows only the Sales movement and
delivery charts. An earlier invisible decomposition tree occupies their
geometry but is deliberately hidden by source-level isHidden:true.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from vqs.design_rules import layout_no_visual_overlap
from vqs.powerbi.insights import page_insights
from vqs.powerbi.measure import measure_report

REPORT = (Path(__file__).resolve().parents[1] / "examples" /
          "contoso-retail" / "Contoso Retail.Report")
HIDDEN_ID = "a1b2c3d4e5f60718293a"
PAGE = "Markets_drivers"
HIDDEN_VISUAL = Path("definition/pages") / PAGE / "visuals" / HIDDEN_ID / "visual.json"


def _conflicts(report: Path) -> list[dict]:
    facts = measure_report(str(report))
    return layout_no_visual_overlap(
        facts["rules"]["layout.no_visual_overlap"]["visuals"]
    )["evidence"]["conflicts"]


def test_real_contoso_hidden_tree_kept_in_inventory_but_not_overlap():
    manifest = page_insights(str(REPORT))
    assert manifest["coverage"]["parsed_pages"] == 5
    assert manifest["coverage"]["parsed_visuals"] == 54
    visible = manifest["layout"]
    assert len(visible) == 53
    assert not [v for v in visible if v["visual"] == HIDDEN_ID]
    page = next(p for p in manifest["pages"] if p["page"] == PAGE)
    hidden = next(v for v in page["visuals"] if v["visual"] == HIDDEN_ID)
    assert hidden["is_hidden"] is True
    assert hidden["type"] == "decompositionTreeVisual"
    assert _conflicts(REPORT) == []


def test_only_explicit_boolean_true_authorizes_hidden_exclusion(tmp_path):
    target = tmp_path / "Contoso Retail.Report"
    shutil.copytree(REPORT, target)
    p = target / HIDDEN_VISUAL
    original = p.read_bytes()

    assert _conflicts(target) == []
    doc = json.loads(p.read_text(encoding="utf8"))
    assert doc["isHidden"] is True

    doc["isHidden"] = False
    p.write_text(json.dumps(doc), encoding="utf8")
    visible_conflicts = _conflicts(target)
    assert len(visible_conflicts) == 2
    assert all(HIDDEN_ID in c["visuals"] for c in visible_conflicts)

    doc.pop("isHidden")
    p.write_text(json.dumps(doc), encoding="utf8")
    assert len(_conflicts(target)) == 2

    doc["isHidden"] = "true"
    p.write_text(json.dumps(doc), encoding="utf8")
    assert len(_conflicts(target)) == 2

    doc["isHidden"] = True
    p.write_text(json.dumps(doc), encoding="utf8")
    assert _conflicts(target) == []
    assert (REPORT / HIDDEN_VISUAL).read_bytes() == original


def test_hidden_query_bindings_still_audited():
    facts = measure_report(str(REPORT))
    bindings = facts["models"][0]["bindings"]
    # Hidden does not grant a free pass for incorrect/unknown model refs.
    assert any(b["visual"] == HIDDEN_ID for b in bindings)
    page = next(p for p in facts["insights"]["pages"] if p["page"] == PAGE)
    assert sum(v.get("is_hidden") is True for v in page["visuals"]) == 1


def test_hidden_text_is_not_visible_contrast_but_stays_in_source(tmp_path):
    from vqs.powerbi.measure import measure_report

    mini = (Path(__file__).resolve().parent / "powerbi" /
            "fixtures" / "mini_report")
    target = tmp_path / "Hidden.Report"
    shutil.copytree(mini, target)
    original = mini / "definition/pages/P1/visuals/titlebox/visual.json"
    visual = target / "definition/pages/P1/visuals/titlebox/visual.json"
    doc = json.loads(visual.read_text(encoding="utf8"))
    assert "isHidden" not in doc
    doc["isHidden"] = True
    visual.write_text(json.dumps(doc), encoding="utf8")
    facts = measure_report(str(target))
    contrast = facts["rules"].get("typography.text_contrast", {})
    assert not [item for item in contrast.get("readings", [])
                if item["visual"] == "titlebox"]
    assert original.is_file()
