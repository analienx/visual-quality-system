"""Regression: map label checks must not mistake Shape Map for a bubble map."""
import json
import shutil
from pathlib import Path

from vqs.design_rules import chart_map_location_labels
from vqs.powerbi.insights import _label_facts
from vqs.powerbi.measure import measure_report

SOURCE = Path(__file__).parent / "powerbi" / "fixtures" / "insight_report"


def test_shape_map_choropleth_does_not_require_bubble_labels():
    result = chart_map_location_labels([
        {"page": "P", "visual": "countries", "type": "shapeMap",
         "labels_shown": False, "heatmap": False}])
    assert result["status"] == "unknown"
    assert result["evidence"]["not_applicable"][0]["type"] == "shapemap"
    assert result["evidence"]["conflicts"] == []


def test_explicit_unlabelled_bubble_still_fails():
    failed = chart_map_location_labels([
        {"page": "P", "visual": "places", "type": "map",
         "labels_shown": False, "heatmap": False}])
    assert failed["status"] == "fail"
    assert failed["evidence"]["checked"] == 1
    assert failed["evidence"]["conflicts"][0]["visual"] == "places"


def test_inherited_or_ambiguous_bubble_labels_are_unknown():
    missing = _label_facts({"objects": {}})
    assert missing == {"labels_shown": None, "heatmap": False}
    result = chart_map_location_labels([
        {"page": "P", "visual": "places", "type": "map", **missing}])
    assert result["status"] == "unknown"
    assert result["evidence"]["unresolved"]


def test_explicit_disabled_heatmap_does_not_excuse_hidden_labels():
    raw = {"categoryLabels": [{"properties": {"show": {"expr": {
        "Literal": {"Value": "false"}}}}}],
           "heatMap": [{"properties": {"show": {"expr": {
               "Literal": {"Value": "false"}}}}}]}
    facts = _label_facts({"objects": raw})
    assert facts == {"labels_shown": False, "heatmap": False}
    assert chart_map_location_labels([
        {"page": "P", "visual": "map", "type": "map", **facts}
    ])["status"] == "fail"


def test_measure_does_not_emit_bubble_policy_for_shape_maps(tmp_path):
    report = tmp_path / "sample.Report"
    shutil.copytree(SOURCE, report)
    for visual in ("mapvis", "lostmap"):
        page = "P1" if visual == "mapvis" else "P2"
        path = report / "definition" / "pages" / page / "visuals" / visual / "visual.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["visual"]["visualType"] = "shapeMap"
        path.write_text(json.dumps(payload), encoding="utf-8")
    rules = measure_report(str(report))["rules"]
    assert "chart.map_location_binding" in rules
    assert "chart.map_location_labels" not in rules
