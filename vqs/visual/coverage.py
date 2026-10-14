"""Explicit specialist dispatch coverage: skipped checks are never PASS."""
from __future__ import annotations

from typing import Any

VERSION = "vqs.visual-coverage/1"


def coverage_index(graphs: list[dict[str, Any]],
                   signals: list[dict[str, Any]],
                   *, specialists: frozenset[str] = frozenset({
                       "page_scan", "kpi_clipping", "table_matrix_overflow",
                       "map_geo_labels", "slicer_filter",
                       "cartesian_legend_axes", "decomposition_tree",
                       "geometry_collision",
                   })) -> dict[str, Any]:
    """Declare task applicability, not reviewed status or model verdict."""
    selected = {(s["page_id"], s["visual_id"], s["specialist"])
                for report in signals for s in report.get("signals", [])}
    rows = []
    for graph in graphs:
        page = graph["page_id"]
        rows.append({
            "page_id": page, "visual_id": None,
            "specialist": "page_scan", "status": "planned_not_executed",
        })
        for visual in graph["nodes"]:
            vid = visual["visual_id"]
            for specialist in sorted(specialists - {"page_scan"}):
                applies = (page, vid, specialist) in selected
                rows.append({
                    "page_id": page, "visual_id": vid,
                    "specialist": specialist,
                    "status": ("planned_not_executed" if applies
                               else "not_applicable_to_type_or_geometry"),
                })
    return {"schema": VERSION, "coverage": rows}
