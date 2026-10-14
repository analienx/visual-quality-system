"""Spatial layout graph and routing: deterministic candidates, never invented FAIL."""
from __future__ import annotations

import copy

import pytest

from vqs.visual.coverage import coverage_index
from vqs.visual.layout_graph import page_graph
from vqs.visual.regions import RegionError
from vqs.visual.risk import route_signals


def _page():
    return {
        "id": "p1", "canvas": [1280, 720],
        "visuals": [
            {"visual_id": "sales", "visual_type": "card",
             "position": {"x": 24, "y": 104, "width": 296, "height": 96, "z": 1}},
            {"visual_id": "customer-matrix", "visual_type": "pivotTable",
             "position": {"x": 856, "y": 468, "width": 400, "height": 228, "z": 2}},
            {"visual_id": "geo", "visual_type": "map",
             "position": {"x": 648, "y": 216, "width": 608, "height": 236, "z": 3}},
        ],
    }


def test_type_routes_refer_to_real_exact_visual_ids():
    graph = page_graph(_page())
    risk = route_signals(graph)
    signals = {(s["visual_id"], s["specialist"]) for s in risk["signals"]}
    assert ("sales", "kpi_clipping") in signals
    assert ("customer-matrix", "table_matrix_overflow") in signals
    assert ("geo", "map_geo_labels") in signals
    assert not any(s.get("state") == "fail" for s in risk["signals"])
    assert graph["nodes"][0]["visual_type"] == "card"


def test_graph_positive_intersection_not_quality_fail():
    page = _page()
    page["visuals"][0]["position"]["x"] = 840
    page["visuals"][0]["position"]["y"] = 470
    graph = page_graph(page)
    overlaps = [e for e in graph["edges"]
                if e["relation"] == "bounding_boxes_intersect"]
    assert len(overlaps) == 1
    overlap = overlaps[0]
    assert overlap["intersection_pbir"]["overlap_area"] > 0
    assert overlap["render_occlusion"] == "unknown_requires_pixels"
    signals = route_signals(graph)["signals"]
    hazards = [s for s in signals if s["specialist"] == "geometry_collision"]
    assert len(hazards) == 1
    assert hazards[0]["state"] == "suspect_requires_pixels"
    assert "intentional layering" in hazards[0]["unknowns"]


def test_proximity_edge_is_not_a_collision():
    page = {
        "id": "p1", "canvas": [1280, 720],
        "visuals": [
            {"visual_id": "one", "visual_type": "card",
             "position": {"x": 10, "y": 10, "width": 100, "height": 100}},
            {"visual_id": "two", "visual_type": "card",
             "position": {"x": 115, "y": 10, "width": 100, "height": 100}},
        ],
    }
    graph = page_graph(page, proximity_pbir=8)
    assert [e["relation"] for e in graph["edges"]] == ["within_context_distance"]
    assert not any(s["specialist"] == "geometry_collision"
                   for s in route_signals(graph)["signals"])


@pytest.mark.parametrize("change", ["duplicate", "unknown", "invalid", "outside"])
def test_bad_inventory_refused_without_graph(change):
    page = _page()
    if change == "duplicate":
        page["visuals"][1]["visual_id"] = "sales"
    elif change == "unknown":
        del page["visuals"][0]["visual_id"]
    elif change == "invalid":
        page["visuals"][0]["position"]["width"] = -1
    else:
        page["visuals"][0]["position"]["x"] = 1220
    with pytest.raises(RegionError):
        page_graph(page)


def test_unknown_z_uses_unknown_not_inferred_order():
    page = _page()
    page["visuals"][0]["position"]["x"] = 840
    page["visuals"][0]["position"]["y"] = 470
    page["visuals"][0]["position"].pop("z")
    edges = page_graph(page)["edges"]
    assert edges[0]["layering"] == "z_order_unknown"


def test_fractional_coords_kept_when_computing_intersections():
    page = _page()
    page["visuals"][0]["position"].update({
        "x": 840.5, "y": 470.125, "width": 296.0,
    })
    graph = page_graph(page)
    e = [e for e in graph["edges"]
         if e["relation"] == "bounding_boxes_intersect"]
    assert len(e) == 1
    assert e[0]["intersection_pbir"]["x"] == 856.0


def test_unselected_checks_never_pass_in_coverage_ledger():
    graph = page_graph(_page())
    risks = route_signals(graph)
    ledger = coverage_index([graph], [risks])
    assert ledger["schema"] == "vqs.visual-coverage/1"
    assert all(r["status"] in {
        "planned_not_executed", "not_applicable_to_type_or_geometry"
    } for r in ledger["coverage"])
    by_key = {(r["visual_id"], r["specialist"]): r["status"]
              for r in ledger["coverage"]}
    assert by_key[("sales", "kpi_clipping")] == "planned_not_executed"
    assert by_key[("sales", "map_geo_labels")] == "not_applicable_to_type_or_geometry"
    assert by_key[(None, "page_scan")] == "planned_not_executed"


def test_synthetic_inventory_does_not_mutate_source():
    page = _page()
    snapshot = copy.deepcopy(page)
    risk = route_signals(page_graph(page))
    assert risk["schema"] == "vqs.visual-risk/1"
    assert page == snapshot


def test_out_of_range_proximity_blocks():
    with pytest.raises(RegionError, match="proximity"):
        page_graph(_page(), proximity_pbir=-1)
