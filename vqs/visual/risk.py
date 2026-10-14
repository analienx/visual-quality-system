"""Deterministic evidence-only routing signals, never visual quality verdicts."""
from __future__ import annotations

from typing import Any

RISK_VERSION = "vqs.visual-risk/1"
CARD = frozenset({"card", "multirowcard", "kpi", "newcard"})
TABLE = frozenset({"pivottable", "table", "matrix"})
MAP = frozenset({"map", "filledmap", "azuremap", "arcgismap", "shapeMap".casefold()})
SLICER = frozenset({"slicer"})
AXES = ("barchart", "columnchart", "linechart", "areachart",
        "waterfallchart", "scatterchart", "combochart")


def route_signals(graph: dict[str, Any]) -> dict[str, Any]:
    """Produce inspection priorities solely from proven visual types/geometry.

    Neither a visual type nor a bounding-box intersection is a visual FAIL.
    This stage cannot claim effective typography, visible scrolling or
    clipping; it only chooses which pixels a specialist should inspect.
    """
    page = graph["page_id"]
    signals = []
    for n in graph["nodes"]:
        vid = n["visual_id"]
        typ = n.get("visual_type")
        kind = typ.casefold() if isinstance(typ, str) else ""
        dispatch = []
        reasons = []
        if kind in CARD:
            dispatch.append("kpi_clipping")
            reasons.append("PBIR identifies a KPI/card family visual")
        if kind in TABLE:
            dispatch.append("table_matrix_overflow")
            reasons.append("PBIR identifies a table or matrix")
        if kind in MAP:
            dispatch.append("map_geo_labels")
            reasons.append("PBIR identifies a map visual")
        if kind in SLICER:
            dispatch.append("slicer_filter")
            reasons.append("PBIR identifies a slicer")
        if any(t in kind for t in AXES):
            dispatch.append("cartesian_legend_axes")
            reasons.append("PBIR identifies an axis-oriented chart")
        if kind in ("decompositiontreevisual", "decompositiontree"):
            dispatch.append("decomposition_tree")
            reasons.append("PBIR identifies a decomposition tree")
        if not dispatch:
            dispatch.append("page_scan")
            reasons.append("covered by whole-page scan; subtype-specific review unavailable")
        for specialist in dispatch:
            signals.append({
                "risk_id": f"route:{page}:{vid}:{specialist}",
                "page_id": page,
                "visual_id": vid,
                "visual_type": typ,
                "specialist": specialist,
                "evidence": reasons,
                "unknowns": ["actual rendered defect", "effective theme formatting"],
                "state": "inspection_candidate_not_finding",
            })
    for e in graph["edges"]:
        if e["relation"] == "bounding_boxes_intersect":
            signals.append({
                "risk_id": f"geometry:{page}:{e['from_visual_id']}:{e['to_visual_id']}",
                "page_id": page,
                "visual_id": e["from_visual_id"],
                "related_visual_id": e["to_visual_id"],
                "specialist": "geometry_collision",
                "evidence": ["PBIR visual bounding rectangles have positive intersection"],
                "intersection_pbir": e["intersection_pbir"],
                "unknowns": ["visibility", "transparency", "intentional layering",
                             "actual rendered occlusion"],
                "state": "suspect_requires_pixels",
            })
    return {"schema": RISK_VERSION, "page_id": page, "signals": signals}
