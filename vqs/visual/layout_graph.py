"""Read-only PBIR spatial graph for targeted visual QA evidence.

Rectangular intersection is an inspection hint, NEVER proof of unwanted
occlusion: PBIR containers may intentionally layer or hide visuals.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .regions import RegionError, _rect

GRAPH_VERSION = "vqs.visual-layout/1"


def _num(value: float) -> Fraction:
    return Fraction(str(value))


def _touch(a: dict, b: dict, distance: int) -> bool:
    ax, ay = _num(a["x"]), _num(a["y"])
    bx, by = _num(b["x"]), _num(b["y"])
    return (ax <= bx + _num(b["width"]) + distance
            and bx <= ax + _num(a["width"]) + distance
            and ay <= by + _num(b["height"]) + distance
            and by <= ay + _num(a["height"]) + distance)


def _intersection(a: dict, b: dict) -> dict | None:
    left = max(_num(a["x"]), _num(b["x"]))
    top = max(_num(a["y"]), _num(b["y"]))
    right = min(_num(a["x"]) + _num(a["width"]),
                _num(b["x"]) + _num(b["width"]))
    bottom = min(_num(a["y"]) + _num(a["height"]),
                 _num(b["y"]) + _num(b["height"]))
    if right <= left or bottom <= top:
        return None
    return {
        "x": float(left), "y": float(top),
        "width": float(right - left), "height": float(bottom - top),
        "overlap_area": float((right - left) * (bottom - top)),
    }


def page_graph(page: dict[str, Any], *, proximity_pbir: int = 24
               ) -> dict[str, Any]:
    """Build deterministic graph; reject bad positions rather than guess."""
    if (not isinstance(page, dict) or not isinstance(page.get("id"), str)
            or not isinstance(page.get("canvas"), list)
            or len(page["canvas"]) != 2):
        raise RegionError("page graph requires a real PBIR page and canvas")
    if type(proximity_pbir) is not int or not 0 <= proximity_pbir <= 256:
        raise RegionError("invalid PBIR proximity radius")
    page_id = page["id"]
    width, height = page["canvas"]
    if (any(type(n) is not int or n <= 0 for n in (width, height))
            or not isinstance(page.get("visuals"), list)):
        raise RegionError("page graph canvas or visual inventory invalid")
    nodes: list[dict] = []
    seen: set[str] = set()
    for v in page["visuals"]:
        if not isinstance(v, dict):
            raise RegionError("invalid PBIR visual")
        vid = v.get("visual_id")
        if not isinstance(vid, str) or not vid or vid in seen:
            raise RegionError("missing or duplicate PBIR visual ID")
        seen.add(vid)
        rect = _rect(v.get("position"), width, height)
        z = v.get("position", {}).get("z")
        nodes.append({
            "page_id": page_id,
            "visual_id": vid,
            "visual_type": v.get("visual_type"),
            "rect_pbir": rect,
            "z_order": z if isinstance(z, (int, float)) and not isinstance(z, bool)
            else None,
        })
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i+1:]:
            intersection = _intersection(a["rect_pbir"], b["rect_pbir"])
            if intersection:
                if a["z_order"] is None or b["z_order"] is None:
                    layer = "z_order_unknown"
                elif a["z_order"] == b["z_order"]:
                    layer = "z_order_tied"
                else:
                    layer = ("first_above_second" if a["z_order"] > b["z_order"]
                             else "second_above_first")
                edges.append({
                    "from_visual_id": a["visual_id"],
                    "to_visual_id": b["visual_id"],
                    "relation": "bounding_boxes_intersect",
                    "intersection_pbir": intersection,
                    "layering": layer,
                    "render_occlusion": "unknown_requires_pixels",
                })
            elif _touch(a["rect_pbir"], b["rect_pbir"], proximity_pbir):
                edges.append({
                    "from_visual_id": a["visual_id"],
                    "to_visual_id": b["visual_id"],
                    "relation": "within_context_distance",
                    "render_occlusion": "not_established",
                })
    return {
        "schema": GRAPH_VERSION,
        "page_id": page_id,
        "canvas_pbir": list(page["canvas"]),
        "proximity_pbir": proximity_pbir,
        "nodes": nodes,
        "edges": edges,
    }
