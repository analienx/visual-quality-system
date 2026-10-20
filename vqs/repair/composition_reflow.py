"""Constrained, source-measured repairs for a four-KPI/two-panel PBIR layout.

Only the *measured* ``layout.composition`` signature is supported.  This is a
small exact projection onto explicit grid constraints, rather than a general
purpose dashboard redesign: preserve the KPI column anchors, match the two
detail-column edges, cap a four-card row at 15% of canvas height, and keep the
existing card-to-panel/stacked-panel vertical gutters.  Reject ambiguous or
unsafe layouts; a candidate still needs native render and data checks.

Every suggested edit is a preconditioned, allowlisted scalar replacement.
The module deliberately never opens or writes a report file.
"""
from __future__ import annotations

import copy
import itertools
import math
from typing import Any

from vqs.design_rules import layout_composition

_RECT = ("x", "y", "width", "height")
_KPI_TYPES = frozenset({"card", "cardvisual", "kpi", "multirowcard"})
_NON_PANEL_TYPES = _KPI_TYPES | {"slicer", "textbox"}
_MAX_KPI_CANVAS_FRACTION = 0.15
_EPS = 0.01


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _safe_id(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and not value.startswith(".") and ".." not in value
            and not any(char in value for char in ("/", "\\", ":")))


def _rect(value: Any) -> dict | None:
    if (not isinstance(value, dict)
            or not all(_finite(value.get(k)) for k in _RECT)
            or value["width"] <= 0 or value["height"] <= 0):
        return None
    return {k: value[k] for k in _RECT}


def _overlap_area(a: dict, b: dict) -> float:
    width = (min(a["x"] + a["width"], b["x"] + b["width"])
             - max(a["x"], b["x"]))
    height = (min(a["y"] + a["height"], b["y"] + b["height"])
              - max(a["y"], b["y"]))
    return max(0, width) * max(0, height)


def _kind(visual: dict) -> str:
    value = visual.get("type")
    return value.casefold() if isinstance(value, str) else ""


def _as_original_type(old: float, new: float) -> int | float:
    if type(old) is int and float(new).is_integer():
        return int(new)
    return float(new)


def _issue(page: str, reason: str) -> dict:
    return {"page": page, "reason": reason}


def _page_edits(page: dict, defects: list[dict]) -> tuple[list[dict], list[dict]]:
    pid = page["page"]
    width, height = page["width"], page["height"]
    visuals = page["visuals"]
    observed: dict[str, dict] = {}
    original: dict[str, dict] = {}
    if not (_finite(width) and _finite(height) and width > 0 and height > 0):
        return [], [_issue(pid, "missing finite page dimensions")]
    for visual in visuals:
        if not isinstance(visual, dict) or not _safe_id(visual.get("visual")):
            return [], [_issue(pid, "unidentified visual prevents collision proof")]
        vid = visual["visual"]
        coords = _rect(visual.get("position"))
        if vid in observed or coords is None:
            return [], [_issue(pid, "duplicate ID or unmeasured visual prevents collision proof")]
        observed[vid] = visual
        original[vid] = coords

    updated = copy.deepcopy(original)
    explanations: dict[tuple[str, str], str] = {}
    held: list[dict] = []

    # Independently proved redundant captions: the field header remains visible
    # and the container title's explicit old=true becomes false.
    for defect in defects:
        if defect.get("kind") != "redundant_slicer_caption":
            continue
        vid = defect.get("visual")
        visual = observed.get(vid)
        if visual is None or _kind(visual) != "slicer":
            held.append(_issue(pid, "redundant caption has no native slicer binding"))
            continue
        explanations[(vid, "slicer_title_shown")] = (
            "explicit redundant container title; retain the field header and query")

    # Find the exactly identified same-row quartet.  Do not infer another
    # dashboard's intent from proximity or a suggestive visual ID.
    crowding = [d for d in defects if d.get("kind") == "kpi_row_crowding"]
    drift = [d for d in defects if d.get("kind") == "kpi_detail_grid_drift"]
    if not (crowding or drift):
        return _edits(page, original, updated, explanations), held
    if len(crowding) > 1 or len(drift) > 1:
        return _edits(page, original, updated, explanations), [
            *held, _issue(pid, "multiple KPI rows need an explicit layout contract")]
    if drift:
        ids = drift[0].get("cards")
    else:
        oversized = {c.get("visual") for c in crowding[0].get("cards", [])}
        matching = []
        for visual in observed.values():
            vid = visual["visual"]
            if _kind(visual) not in _KPI_TYPES:
                continue
            top = original[vid]["y"]
            row = sorted((name for name, item in observed.items()
                          if _kind(item) in _KPI_TYPES
                          and abs(original[name]["y"] - top) <= 2),
                         key=lambda name: original[name]["x"])
            if len(row) == 4 and oversized.issubset(row) and row not in matching:
                matching.append(row)
        ids = matching[0] if len(matching) == 1 else None
    if (not isinstance(ids, list) or len(ids) != 4
            or len(set(ids)) != 4 or not all(vid in observed for vid in ids)):
        return _edits(page, original, updated, explanations), [
            *held, _issue(pid, "cannot uniquely bind four KPI cards")]
    cards = sorted(ids, key=lambda vid: original[vid]["x"])
    top = original[cards[0]]["y"]
    heights = [original[vid]["height"] for vid in cards]
    if any(_kind(observed[vid]) not in _KPI_TYPES
           or abs(original[vid]["y"] - top) > 2 for vid in cards):
        return _edits(page, original, updated, explanations), [
            *held, _issue(pid, "KPI row baselines are not consistent")]
    if any(original[a]["x"] + original[a]["width"] + 4 > original[b]["x"]
           for a, b in itertools.pairwise(cards)):
        return _edits(page, original, updated, explanations), [
            *held, _issue(pid, "KPI card order/gutters are not safely identifiable")]

    max_height = math.floor(height * _MAX_KPI_CANVAS_FRACTION)
    if max_height < 40:
        return _edits(page, original, updated, explanations), [
            *held, _issue(pid, "canvas too short for an accessible KPI tile")]
    even_row = max(heights) - min(heights) <= 2
    shrink = max(0, max(heights) - max_height) if crowding and even_row else 0
    if crowding:
        for vid in cards:
            if original[vid]["height"] > max_height:
                updated[vid]["height"] = _as_original_type(
                    original[vid]["height"], max_height)
                explanations[(vid, "height")] = (
                    "cap the four-card KPI row at 15% of canvas height")

    # The two large panels, when identified by the detector, are projected to
    # the existing 2+2 KPI pair anchors.  Keep downstream panels in the same
    # inferred column and preserve their current vertical stacking gutters.
    panels: list[str] = []
    if drift:
        panel_ids = drift[0].get("detail_panels")
        if (not isinstance(panel_ids, list) or len(panel_ids) != 2
                or len(set(panel_ids)) != 2
                or not all(vid in observed for vid in panel_ids)):
            return _edits(page, original, original, explanations), [
                *held, _issue(pid, "cannot bind exactly two detail panels")]
        panels = sorted(panel_ids, key=lambda vid: original[vid]["x"])
    elif shrink:
        after_cards = max(original[vid]["y"] + original[vid]["height"]
                          for vid in cards)
        lower = [vid for vid, visual in observed.items()
                 if _kind(visual) not in _NON_PANEL_TYPES
                 and original[vid]["y"] >= after_cards]
        if lower:
            first_top = min(original[vid]["y"] for vid in lower)
            first_panels = sorted((vid for vid in lower
                                   if abs(original[vid]["y"] - first_top) <= 2),
                                  key=lambda vid: original[vid]["x"])
            if (len(first_panels) == 2
                    and abs(original[first_panels[0]]["width"]
                            - original[first_panels[1]]["width"]) <= .08 * width):
                panels = first_panels

    descendants: set[str] = set(panels)
    if panels:
        for base in panels:
            r = original[base]
            for vid, visual in observed.items():
                if (vid == base or _kind(visual) in _NON_PANEL_TYPES
                        or vid in panels):
                    continue
                child = original[vid]
                if (abs(child["x"] - r["x"]) <= 2
                        and abs(child["width"] - r["width"]) <= 2
                        and child["y"] >= r["y"] + r["height"]
                        and child["y"] - (r["y"] + r["height"]) <= 32):
                    descendants.add(vid)
        if drift:
            anchors = ((original[cards[0]]["x"],
                        original[cards[1]]["x"] + original[cards[1]]["width"]),
                       (original[cards[2]]["x"],
                        original[cards[3]]["x"] + original[cards[3]]["width"]))
            for base, (left, right) in zip(panels, anchors):
                for vid in sorted(descendants):
                    if vid == base or (abs(original[vid]["x"] - original[base]["x"]) <= 2
                                       and abs(original[vid]["width"]
                                               - original[base]["width"]) <= 2):
                        updated[vid]["x"] = _as_original_type(original[vid]["x"], left)
                        updated[vid]["width"] = _as_original_type(
                            original[vid]["width"], right - left)
                        explanations[(vid, "x")] = "align panel start with its KPI pair"
                        explanations[(vid, "width")] = "align panel end with its KPI pair"
        if shrink:
            for vid in sorted(descendants):
                updated[vid]["y"] = _as_original_type(
                    original[vid]["y"], original[vid]["y"] - shrink)
                explanations[(vid, "y")] = (
                    "preserve existing KPI-to-panel and stacked-panel gutters")

    # Hard invariants: in-canvas and no newly intersecting visual pair.  An
    # existing intentional annotation overlay is not itself a veto, but the
    # repair must never create a new overlap or grow an existing overlap.
    for vid, rect in updated.items():
        if (rect["x"] < 0 or rect["y"] < 0 or rect["width"] <= 0
                or rect["height"] <= 0 or rect["x"] + rect["width"] > width + _EPS
                or rect["y"] + rect["height"] > height + _EPS):
            return _edits(page, original, original, explanations), [
                *held, _issue(pid, "proposed grid would leave the canvas")]
    names = sorted(original)
    for index, a in enumerate(names):
        for b in names[index + 1:]:
            if (_overlap_area(updated[a], updated[b])
                    > _overlap_area(original[a], original[b]) + _EPS):
                return _edits(page, original, original, explanations), [
                    *held, _issue(pid, f"proposed grid would increase overlap {a}/{b}")]

    return _edits(page, original, updated, explanations), held


def _edits(page: dict, before: dict, after: dict,
           explanations: dict[tuple[str, str], str]) -> list[dict]:
    pid = page["page"]
    output = []
    for (vid, axis), reason in sorted(explanations.items()):
        if axis == "slicer_title_shown":
            output.append({"page": pid, "visual": vid, "op": "theme.set",
                           "path": ["visual", "visualContainerObjects", "title", 0,
                                    "properties", "show", "expr", "Literal", "Value"],
                           "old": "true", "new": "false", "reason": reason})
        elif axis in _RECT and vid in before and before[vid][axis] != after[vid][axis]:
            output.append({"page": pid, "visual": vid,
                           "op": "spacing.adjust" if axis in ("x", "y")
                           else "chart.resize", "path": ["position", axis],
                           "old": before[vid][axis], "new": after[vid][axis],
                           "reason": reason})
    # An intermediate property write also has to be in-canvas. Moving left
    # permits widening; narrowing first permits moving right. This avoids
    # transient invalid PBIR even when the combined final rect is valid.
    priority = {"height": 0, "y": 1, "x": 2, "width": 3, "Value": 4}

    def order(edit: dict) -> tuple:
        axis = edit["path"][-1]
        if axis in ("x", "width") and after[edit["visual"]]["x"] > before[edit["visual"]]["x"]:
            return edit["visual"], 2 if axis == "width" else 3
        return edit["visual"], priority.get(axis, 5)

    output.sort(key=order)
    return output


def solve_composition(pages: Any) -> tuple[list[dict], list[dict]]:
    """Return deterministic typed edits and explicit unresolved decisions.

    The *current* static rule is recomputed against measured facts, not copied
    from an untrusted finding payload.  An absent/clean observation is never
    a mandate to redesign the report.
    """
    if not isinstance(pages, list):
        return [], [{"reason": "source has no measured composition pages"}]
    verdict = layout_composition(pages)
    if verdict["status"] != "fail":
        return [], ([{"reason": "composition observations are unproved"}]
                    if verdict["status"] == "unknown" else [])
    defects = verdict["evidence"]["findings"]
    results: list[dict] = []
    blocked: list[dict] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("page"), str):
            blocked.append({"reason": "unidentified composition page"})
            continue
        local = [entry for entry in defects if entry.get("page") == page["page"]]
        if local:
            made, held = _page_edits(page, local)
            results.extend(made)
            blocked.extend(held)
    return results, blocked
