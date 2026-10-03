"""Typed initial repair recipes (WP-09, §E).

Each allowlisted operation binds an exact component (page/visual
selector), property path, value, precondition, and affected pages before
anything is written. Scalar replacements are type-preserving: the new
value must share the existing value's JSON type, so a repair can never
silently change a string encoding into a number or reshape a container.
Only sort.set may introduce a container, and only chart.replace (via a
vetted template) may change a visual's type.
"""
from __future__ import annotations

import math
import re
from typing import Any

_SIZE_RE = re.compile(r"(\d{1,3})D")
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
_BAD_CONTROLS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

LEAF_OPS = frozenset({"typography.size", "axis.tick_format", "axis.title",
                      "axis.precision", "label.format", "theme.set",
                      "palette.assign"})
GEOMETRY_OPS = frozenset({"chart.resize", "spacing.adjust"})


class RecipeError(ValueError):
    """An operation is not a well-formed typed recipe application."""


def _require_selector(op: dict) -> tuple[str, str]:
    selector = op.get("selector")
    if not isinstance(selector, dict):
        raise RecipeError("op lacks source binding: selector {page, visual}")
    page, visual = selector.get("page"), selector.get("visual")
    if (not isinstance(page, str) or not page
            or not isinstance(visual, str) or not visual):
        raise RecipeError("op lacks source binding: selector {page, visual}")
    return page, visual


def _walk(doc: Any, path: list) -> Any:
    node = doc
    for step in path:
        if isinstance(node, dict) and step in node or (isinstance(node, list) and isinstance(step, int)
                and 0 <= step < len(node)):
            node = node[step]
        else:
            raise RecipeError(f"precondition failed: path {path!r} missing")
    return node


def _check_string(op_type: str, value: str) -> None:
    if not value or len(value) > 500 or _BAD_CONTROLS_RE.search(value):
        raise RecipeError(f"{op_type}: string value rejected "
                          "(empty, too long, or control characters)")
    if op_type == "typography.size":
        match = _SIZE_RE.fullmatch(value)
        if match is None or not 6 <= int(match.group(1)) <= 96:
            raise RecipeError("typography.size: value must look like 'ND' "
                              f"(6D-96D), not {value!r}")
    if op_type == "palette.assign" and _COLOR_RE.fullmatch(value) is None:
        raise RecipeError(f"palette.assign: value must be #RRGGBB, "
                          f"not {value!r}")


def _check_number(op_type: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipeError(f"{op_type}: numeric value required")
    if not math.isfinite(value):
        raise RecipeError(f"{op_type}: non-finite number rejected")
    if op_type == "axis.precision" and (
            isinstance(value, float) or not 0 <= value <= 15):
        raise RecipeError("axis.precision: integer 0-15 required")


def _same_json_type(old: Any, new: Any) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool)
    return type(old) is type(new) or (
        isinstance(old, (int, float)) and isinstance(new, (int, float)))


def bind_leaf(op: dict, visual_doc: dict) -> dict:
    """Bind a scalar property replacement; old and new share a JSON type."""
    op_type = str(op.get("type", ""))
    page, visual = _require_selector(op)
    path = op.get("path")
    if (not isinstance(path, list) or len(path) < 2
            or path[0] != "visual" or path[1] not in (
                "objects", "visualContainerObjects")):
        raise RecipeError(f"{op_type}: path must address visual.objects* "
                          f"or visual.visualContainerObjects*, not {path!r}")
    old = _walk(visual_doc, path)
    if old is None or isinstance(old, (dict, list)):
        raise RecipeError(f"{op_type}: path {path!r} is not a scalar leaf")
    new = op.get("value", None if "value" in op else ...)
    if new is ...:
        raise RecipeError(f"{op_type}: missing value")
    if not _same_json_type(old, new):
        raise RecipeError(f"{op_type}: value type {type(new).__name__} "
                          f"would replace {type(old).__name__}")
    if isinstance(new, str):
        _check_string(op_type, new)
    elif isinstance(new, (int, float)) and not isinstance(new, bool):
        if not math.isfinite(new):
            raise RecipeError(f"{op_type}: non-finite number rejected")
        if op_type == "axis.precision":
            _check_number(op_type, new)
    elif not isinstance(new, bool):
        raise RecipeError(f"{op_type}: value type {type(new).__name__} "
                          f"would replace {type(old).__name__}")
    return {"page": page, "visual": visual, "path": list(path),
            "old": old, "new": new}


def bind_geometry(op: dict, visual_doc: dict,
                  canvas: tuple[int, int]) -> dict:
    """Bind a position change; the result must stay finite and in-canvas."""
    op_type = str(op.get("type", ""))
    page, visual = _require_selector(op)
    path = op.get("path")
    want = ("width", "height") if op_type == "chart.resize" else ("x", "y")
    if not isinstance(path, list) or len(path) != 2 or path[0] != "position" \
            or path[1] not in want:
        raise RecipeError(f"{op_type}: path must be ['position', "
                          f"{'/'.join(want)}], not {path!r}")
    position = visual_doc.get("position")
    if not isinstance(position, dict):
        raise RecipeError(f"{op_type}: visual has no position object")
    old = position.get(path[1])
    if (not isinstance(old, (int, float)) or isinstance(old, bool)
            or not math.isfinite(old)):
        raise RecipeError(f"{op_type}: existing {path[1]} is not finite")
    new = op.get("value", None if "value" in op else ...)
    if (new is ... or isinstance(new, bool)
            or not isinstance(new, (int, float)) or not math.isfinite(new)):
        raise RecipeError(f"{op_type}: finite numeric value required")
    merged = dict(position)
    merged[path[1]] = new
    try:
        x, y = float(merged["x"]), float(merged["y"])
        width, height = float(merged["width"]), float(merged["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RecipeError(f"{op_type}: position lacks finite x/y/w/h") from exc
    if min(x, y) < 0 or min(width, height) <= 0:
        raise RecipeError(f"{op_type}: position must stay non-negative "
                          "with positive size")
    if x + width > canvas[0] or y + height > canvas[1]:
        raise RecipeError(f"{op_type}: visual would leave the canvas")
    return {"page": page, "visual": visual, "path": list(path),
            "old": old, "new": new}


def _finite_deep(value: Any, depth: int = 0) -> None:
    if depth > 6:
        raise RecipeError("sort.set: value nests too deep")
    if isinstance(value, float) and not math.isfinite(value):
        raise RecipeError("sort.set: non-finite number rejected")
    if isinstance(value, dict):
        if len(value) > 50:
            raise RecipeError("sort.set: value object too large")
        for entry in value.values():
            _finite_deep(entry, depth + 1)
    elif isinstance(value, list):
        if len(value) > 200:
            raise RecipeError("sort.set: value array too large")
        for entry in value:
            _finite_deep(entry, depth + 1)


def bind_sort(op: dict, visual_doc: dict) -> dict:
    """Bind a sortDefinition replacement (the one allowed container write)."""
    page, visual = _require_selector(op)
    path = op.get("path")
    if path != ["visual", "query", "sortDefinition"]:
        raise RecipeError("sort.set: path must be "
                          "['visual', 'query', 'sortDefinition']")
    query = visual_doc.get("visual", {}).get("query")
    if not isinstance(query, dict):
        raise RecipeError("sort.set: visual has no query to sort")
    new = op.get("value", None if "value" in op else ...)
    if new is ... or not isinstance(new, dict):
        raise RecipeError("sort.set: value must be a JSON object")
    _finite_deep(new)
    return {"page": page, "visual": visual, "path": list(path),
            "old": query.get("sortDefinition"), "new": new}


def bind_replace(op: dict) -> dict:
    """Bind a chart.replace to its vetted template reference (shape only).

    Template resolution, binding verification, and the identical-intent
    gate happen in the executor; this only proves the reference shape.
    """
    page, visual = _require_selector(op)
    template = op.get("template")
    if not isinstance(template, dict):
        raise RecipeError("chart.replace: template {name, version} required")
    name, version = template.get("name"), template.get("version")
    if (not isinstance(name, str) or not name
            or not isinstance(version, str) or not version):
        raise RecipeError("chart.replace: template {name, version} required")
    return {"page": page, "visual": visual, "template": name,
            "version": version}


def bind_operation(op: dict, visual_doc: dict | None,
                   canvas: tuple[int, int] = (0, 0)) -> dict:
    """Bind any typed op; RecipeError names the exact violated rule."""
    if not isinstance(op, dict):
        raise RecipeError("operation must be an object")
    op_type = op.get("type", "")
    if op_type in LEAF_OPS:
        if not isinstance(visual_doc, dict):
            raise RecipeError(f"{op_type}: visual document required")
        return {"op": op_type, **bind_leaf(op, visual_doc)}
    if op_type in GEOMETRY_OPS:
        if not isinstance(visual_doc, dict):
            raise RecipeError(f"{op_type}: visual document required")
        return {"op": op_type, **bind_geometry(op, visual_doc, canvas)}
    if op_type == "sort.set":
        if not isinstance(visual_doc, dict):
            raise RecipeError("sort.set: visual document required")
        return {"op": op_type, **bind_sort(op, visual_doc)}
    if op_type == "chart.replace":
        return {"op": op_type, **bind_replace(op)}
    raise RecipeError(f"unknown operation type: {op_type!r}")


def affected_pages(op: dict, all_page_ids: list[str]) -> dict:
    """Pages invalidated by one op; theme/palette ops invalidate everything.

    Shared presentation properties may affect every page, so those ops
    conservatively require a full rerender; all other typed ops affect
    only their bound page.
    """
    page, _ = _require_selector(op)
    if op.get("type") in ("theme.set", "palette.assign"):
        return {"pages": list(all_page_ids), "shared": True,
                "reason": "shared presentation change invalidates all pages"}
    return {"pages": [page], "shared": False, "reason": "bound page only"}
