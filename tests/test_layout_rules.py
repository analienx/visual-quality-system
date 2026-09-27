"""Rule tests: layout geometry (LAY-01/02) and map labels (CHT-03)."""
from pathlib import Path

from vqs.design_rules import chart_map_location_labels, layout_no_visual_overlap, layout_visuals_within_page


def _box(page, visual, x, y, width, height):
    return {"page": page, "visual": visual, "x": x, "y": y,
            "width": width, "height": height}


def test_overlap_partial_and_nested_fail() -> None:
    result = layout_no_visual_overlap([
        _box("P1", "a", 0, 0, 100, 100),
        _box("P1", "b", 50, 50, 100, 100),
        _box("P1", "c", 10, 10, 20, 20)])
    assert result["status"] == "fail"
    kinds = {(c["visuals"][0], c["visuals"][1]) for c in
             result["evidence"]["conflicts"]}
    assert kinds == {("a", "b"), ("a", "c")}
    assert result["evidence"]["conflicts"][0]["overlap"] == {
        "x": 50.0, "y": 50.0, "width": 50.0, "height": 50.0}


def test_edge_touch_and_cross_page_pass() -> None:
    result = layout_no_visual_overlap([
        _box("P1", "a", 0, 0, 100, 100),
        _box("P1", "b", 100, 0, 100, 100),
        _box("P2", "c", 0, 0, 100, 100)])
    assert result["status"] == "pass"
    assert result["evidence"]["pairs_compared"] == 1
    assert layout_no_visual_overlap([])["status"] == "unknown"
    assert layout_no_visual_overlap([{"page": "P1"}])["status"] == "unknown"


def test_bounds_overflow_fails() -> None:
    result = layout_visuals_within_page([
        {"page": "P1", "width": 1280, "height": 720, "visuals": [
            {"visual": "ok", "x": 0, "y": 0, "width": 100, "height": 100},
            {"visual": "wide", "x": 1200, "y": 0, "width": 200, "height": 100},
            {"visual": "neg", "x": -5, "y": 0, "width": 50, "height": 50}]}])
    assert result["status"] == "fail"
    assert [c["visual"] for c in result["evidence"]["conflicts"]] == [
        "wide", "neg"]


def test_bounds_missing_size_unknown() -> None:
    result = layout_visuals_within_page([
        {"page": "P1", "width": None, "height": None, "visuals": [
            {"visual": "a", "x": 0, "y": 0, "width": 10, "height": 10}]}])
    assert result["status"] == "unknown"
    assert layout_visuals_within_page([])["status"] == "unknown"


def test_map_labels_shown_or_heatmap_pass() -> None:
    shown = chart_map_location_labels([{
        "page": "P1", "visual": "m", "labels_shown": True, "heatmap": False}])
    assert shown["status"] == "pass"
    heat = chart_map_location_labels([{
        "page": "P1", "visual": "m", "labels_shown": False, "heatmap": True}])
    assert heat["status"] == "pass"
    bare = chart_map_location_labels([{
        "page": "P1", "visual": "m", "labels_shown": False, "heatmap": False}])
    assert bare["status"] == "fail"
    assert bare["evidence"]["conflicts"] == [{"kind": "unlabeled_map",
                                              "page": "P1", "visual": "m"}]
    assert chart_map_location_labels([])["status"] == "unknown"


def test_pipeline_runs_layout_and_label_rules(tmp_path: Path) -> None:
    from vqs.pipeline import run_check
    facts = {"rules": {
        "layout.no_visual_overlap": {"visuals": [
            _box("P1", "a", 0, 0, 10, 10)]},
        "chart.map_location_labels": {"maps": [
            {"page": "P1", "visual": "m", "labels_shown": True,
             "heatmap": False}]}}}
    result = run_check(facts, tmp_path, run_id="layout-pipeline")
    assert result["verdict"] == "pass"
    assert {f["check"] for f in result["findings"]} == {
        "layout.no_visual_overlap", "chart.map_location_labels"}
