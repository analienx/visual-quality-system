"""Deterministic safe plan synthesis (P0-U1).

Reads sealed findings plus caller facts whose digest matches the sealed
run, and emits typed candidate operations only for findings VQS can bind
safely:

- geometry overlap (``layout.no_visual_overlap``): move one visual by the
  exact overlap extent on a single axis, verified in-canvas and
  overlap-free against the measured page geometry;
- outside-page geometry (``layout.visuals_within_page``): clamp the proven
  out-of-bounds axis back inside the measured canvas;
- explicit leaf bindings: an ``axis.*``/``label.format``/``theme.set``/
  ``palette.assign``/``typography.size`` edit whose page, visual, property
  path, old literal and new literal are all proven in the sealed finding
  detail (old/new actually known, never guessed).

Everything else becomes ``needs_owner_decision`` / ``unsupported`` with an
exact reason. Pure function: no IO, no live sources, deterministic order.
Repair re-validates every emitted op before touching the filesystem.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .allowlist import validate_plan
from .recipes import (
    LEAF_OPS,
    RecipeError,
    affected_pages,
    is_precision_str,
    validate_leaf_path,
)

PLAN_SCHEMA_VERSION = "vqs.plan/1"

_ROLLBACK_RECIPE = "re-materialize from original"

_SIZE_RE = re.compile(r"(\d{1,3})D")
_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
_BAD_CONTROLS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_OVERLAP_CHECK = "layout.no_visual_overlap"
_WITHIN_CHECK = "layout.visuals_within_page"

# An overlap covering more than half of the moved visual is a stacking or
# redesign decision, not a nudge: the owner chooses which visual moves.
_LARGE_OVERLAP_FRACTION = 0.5


def _is_num(value: Any) -> bool:
    """Finite JSON number (bools are never coordinates)."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _safe_segment(value: Any) -> bool:
    """Mirror the executor's selector rules so emitted plans bind there."""
    return (isinstance(value, str) and bool(value) and value == value.strip()
            and not value.startswith(".") and "/" not in value
            and "\\" not in value and ":" not in value and ".." not in value)


def _visual_rel(page: str, visual: str) -> str | None:
    """Candidate-relative visual path, or None when IDs are unsafe."""
    if not (_safe_segment(page) and _safe_segment(visual)):
        return None
    return f"definition/pages/{page}/visuals/{visual}/visual.json"


def _as_int(old: Any, value: float) -> Any:
    """Keep PBIR integer shapes integer when the move is integral."""
    if isinstance(old, int) and float(value).is_integer():
        return int(value)
    return value


def _positive_overlap(first: dict, second: dict) -> dict | None:
    """Positive-area intersection of two rects, or None (edge-touch passes)."""
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["width"], second["x"] + second["width"])
    bottom = min(first["y"] + first["height"], second["y"] + second["height"])
    if right > left and bottom > top:
        return {"x": left, "y": top, "width": right - left,
                "height": bottom - top}
    return None


def _in_canvas(rect: dict, canvas: tuple) -> bool:
    """Rect fully inside the measured canvas (edges may touch)."""
    return (rect["x"] >= 0 and rect["y"] >= 0
            and rect["x"] + rect["width"] <= canvas[0]
            and rect["y"] + rect["height"] <= canvas[1])


def _geometry_index(facts: Any) -> tuple[dict, dict, str | None]:
    """Index measured rects and canvases from sealed facts.

    Returns ``(rects, canvases, issue)``; ``issue`` names the missing
    binding when facts carry no usable geometry at all.
    """
    if not isinstance(facts, dict):
        return {}, {}, ("missing source binding: geometry synthesis needs "
                        "the sealed facts (pass --facts)")
    rules = facts.get("rules")
    if not isinstance(rules, dict):
        return {}, {}, "missing source binding: facts carry no rules"
    rects: dict[tuple[str, str], dict] = {}
    entry = rules.get(_OVERLAP_CHECK)
    if isinstance(entry, dict) and isinstance(entry.get("visuals"), list):
        for item in entry["visuals"]:
            if not (isinstance(item, dict)
                    and isinstance(item.get("page"), str)
                    and isinstance(item.get("visual"), str)):
                continue
            coords = {key: item.get(key)
                      for key in ("x", "y", "width", "height")}
            if (not all(_is_num(coords[key]) for key in coords)
                    or coords["width"] <= 0 or coords["height"] <= 0):
                continue
            zed = item.get("z", 0.0)
            rects[(item["page"], item["visual"])] = {
                **coords, "z": zed if _is_num(zed) else 0.0}
    canvases: dict[str, tuple] = {}
    within = rules.get(_WITHIN_CHECK)
    if isinstance(within, dict) and isinstance(within.get("pages"), list):
        for page in within["pages"]:
            if not (isinstance(page, dict)
                    and isinstance(page.get("page"), str)):
                continue
            width, height = page.get("width"), page.get("height")
            if (_is_num(width) and _is_num(height)
                    and width > 0 and height > 0):
                canvases[page["page"]] = (width, height)
    if not rects and not canvases:
        return {}, {}, ("missing source binding: sealed facts carry no "
                        "measured geometry")
    return rects, canvases, None


def _decision(check: str, status: str, reason: str,
              page: str | None = None,
              visual: str | None = None) -> dict:
    record: dict[str, Any] = {"check": check, "status": status,
                              "reason": reason}
    if page is not None:
        record["page"] = page
    if visual is not None:
        record["visual"] = visual
    return record


def _candidate(check: str, page: str, visual: str, op: dict, old: Any,
               new: Any, rel: str, affected: list[str], rationale: str,
               confidence: str, safety: str, autofix: str) -> dict:
    return {"check": check, "status": "candidate", "page": page,
            "visual": visual, "op": op["type"], "path": list(op["path"]),
            "old": old, "new": new, "operation": op,
            "write_targets": [rel], "affected_pages": list(affected),
            "rationale": rationale, "confidence": confidence,
            "safety": safety, "autofix_reason": autofix}


def _clear_of(rect: dict, page: str, tracked: dict,
              mover: tuple[str, str], canvas: tuple) -> bool:
    """A moved rect stays in-canvas and overlaps no page neighbor."""
    if not _in_canvas(rect, canvas):
        return False
    for key, other in sorted(tracked.items()):
        if key[0] != page or key == mover:
            continue
        if _positive_overlap(rect, other) is not None:
            return False
    return True


def _plan_overlap_conflict(check: str, conflict: dict, canvases: dict,
                           tracked: dict, planned: dict,
                           all_pages: list[str]
                           ) -> tuple[list[dict], list[dict]]:
    """Synthesize one overlap conflict; ([candidates], [decisions])."""
    pair = conflict.get("visuals") if isinstance(conflict, dict) else None
    page = conflict.get("page") if isinstance(conflict, dict) else None
    overlap = conflict.get("overlap") if isinstance(conflict, dict) else None
    if (not isinstance(page, str) or not isinstance(pair, list)
            or len(pair) != 2 or not all(isinstance(name, str)
                                         for name in pair)
            or not isinstance(overlap, dict)):
        return [], [_decision(check, "unsupported",
                              "unsupported: overlap conflict is not a "
                              "page/visual-pair/overlap-rect object")]
    first, second = sorted(pair)
    rel = _visual_rel(page, second)
    if rel is None:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: unsafe page/visual "
                              "segment", page, second)]
    if (page, first) not in tracked or (page, second) not in tracked:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: sealed facts carry "
                              "no measured rect for the overlapping pair",
                              page, second)]
    canvas = canvases.get(page)
    if canvas is None:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: no measurable page "
                              "canvas for the overlapping pair",
                              page, second)]
    dims = {key: overlap.get(key)
            for key in ("x", "y", "width", "height")}
    if (not all(_is_num(dims[key]) for key in dims)
            or dims["width"] <= 0 or dims["height"] <= 0):
        return [], [_decision(check, "unsupported",
                              "unsupported: overlap rect is not a "
                              "positive-area rect", page, second)]
    mover = tracked[(page, second)]
    current = _positive_overlap(tracked[(page, first)], mover)
    if current is None:
        return [], [_decision(check, "covered_by_candidate",
                              "already resolved by an earlier candidate "
                              "move on this page", page, second)]
    area = mover["width"] * mover["height"]
    if area > 0 and dims["width"] * dims["height"] > (
            _LARGE_OVERLAP_FRACTION * area):
        return [], [_decision(check, "needs_owner_decision",
                              "large ambiguous overlap: covers more than "
                              "half of the moved visual; the owner chooses "
                              "which visual moves", page, second)]
    mover_key = (page, second)
    attempts = sorted((("x", dims["width"]), ("y", dims["height"])),
                      key=lambda item: (item[1], item[0]))
    for axis, extent in attempts:
        key = (page, second, axis)
        old = mover[axis]
        new = _as_int(old, old + extent)
        placed = dict(mover)
        placed[axis] = new
        if key in planned:
            if planned[key] == new:
                return [], [_decision(
                    check, "covered_by_candidate",
                    "identical move already planned", page, second)]
            return [], [_decision(
                check, "needs_owner_decision",
                "conflicting plans: this visual already has a different "
                f"planned {axis} move from an earlier finding",
                page, second)]
        if _clear_of(placed, page, tracked, mover_key, canvas):
            op = {"type": "spacing.adjust",
                  "selector": {"page": page, "visual": second},
                  "target": "visual", "path": ["position", axis],
                  "old": old, "value": new, "writes": [rel]}
            planned[key] = new
            tracked[mover_key] = placed
            affected = affected_pages(
                {"type": "spacing.adjust",
                 "selector": {"page": page, "visual": second}}, all_pages)
            rationale = (
                f"move {page}/{second} {axis} {old} -> {new} "
                f"(overlap {dims['width']}x{dims['height']} at "
                f"{dims['x']},{dims['y']}); {first} stays fixed; "
                "single-axis minimal shift, edge-touch passes the rule")
            return [_candidate(
                check, page, second, op, old, new, rel,
                affected["pages"], rationale, "high",
                "geometry-stays-in-canvas",
                "verified in-canvas and overlap-free against every "
                "measured page neighbor")], []
    return [], [_decision(check, "needs_owner_decision",
                          "no free slot: neither single-axis shift stays "
                          "in-canvas and overlap-free", page, second)]


def _plan_within_conflict(check: str, conflict: dict, tracked: dict,
                          canvases: dict, planned: dict,
                          all_pages: list[str]
                          ) -> tuple[list[dict], list[dict]]:
    """Clamp one outside-page visual back inside its measured canvas."""
    page = conflict.get("page") if isinstance(conflict, dict) else None
    visual = conflict.get("visual") if isinstance(conflict, dict) else None
    rect = conflict.get("rect") if isinstance(conflict, dict) else None
    size = conflict.get("page_size") if isinstance(conflict, dict) else None
    if (not isinstance(page, str) or not isinstance(visual, str)
            or not isinstance(rect, dict) or not isinstance(size, dict)):
        return [], [_decision(check, "unsupported",
                              "unsupported: outside-page conflict is not "
                              "a page/visual/rect/page-size object")]
    rel = _visual_rel(page, visual)
    if rel is None:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: unsafe page/visual "
                              "segment", page, visual)]
    width, height = size.get("width"), size.get("height")
    if not (_is_num(width) and _is_num(height)
            and width > 0 and height > 0):
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: no measurable page "
                              "canvas for the outside visual",
                              page, visual)]
    coords = {key: rect.get(key) for key in ("x", "y", "width", "height")}
    if (not all(_is_num(coords[key]) for key in coords)
            or coords["width"] <= 0 or coords["height"] <= 0):
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: no measured rect "
                              "for the outside visual", page, visual)]
    if coords["width"] > width or coords["height"] > height:
        return [], [_decision(check, "needs_owner_decision",
                              "no free slot: visual is larger than the "
                              "page canvas", page, visual)]
    desired = {"x": min(max(0, coords["x"]), width - coords["width"]),
               "y": min(max(0, coords["y"]), height - coords["height"])}
    current = tracked.get((page, visual))
    base = current if current is not None else coords
    moves = [(axis, base[axis], _as_int(base[axis], desired[axis]))
             for axis in ("x", "y") if desired[axis] != base[axis]]
    if not moves:
        return [], [_decision(check, "covered_by_candidate",
                              "visual already inside the canvas",
                              page, visual)]
    for axis, _old, want in moves:
        key = (page, visual, axis)
        if key in planned and planned[key] != want:
            return [], [_decision(
                check, "needs_owner_decision",
                "conflicting plans: this visual already has a different "
                f"planned {axis} move from an earlier finding",
                page, visual)]
    if all(planned.get((page, visual, axis)) == want
           for axis, _old, want in moves):
        return [], [_decision(check, "covered_by_candidate",
                              "identical clamp already planned",
                              page, visual)]
    clamped = {"x": desired["x"], "y": desired["y"],
               "width": coords["width"], "height": coords["height"]}
    if not _clear_of(clamped, page, tracked, (page, visual),
                     (width, height)):
        return [], [_decision(check, "needs_owner_decision",
                              "no free slot: clamping inside the canvas "
                              "would overlap a measured neighbor",
                              page, visual)]
    candidates = []
    if current is None:
        current = dict(coords)
        tracked[(page, visual)] = current
    for axis, old, want in moves:
        op = {"type": "spacing.adjust",
              "selector": {"page": page, "visual": visual},
              "target": "visual", "path": ["position", axis],
              "old": old, "value": want, "writes": [rel]}
        planned[(page, visual, axis)] = want
        current = dict(current)
        current[axis] = want
        tracked[(page, visual)] = current
        affected = affected_pages(
            {"type": "spacing.adjust",
             "selector": {"page": page, "visual": visual}}, all_pages)
        candidates.append(_candidate(
            check, page, visual, op, old, want, rel, affected["pages"],
            f"clamp {page}/{visual} {axis} {old} -> {want} inside "
            f"{width}x{height}; the rule fails exactly this edge",
            "high", "geometry-stays-in-canvas",
            "clamped coordinate is inside the measured canvas by "
            "construction"))
    return candidates, []


def _check_leaf_string(op_type: str, old: Any, new: Any) -> str | None:
    """Validate string operands; None means both may be written."""
    for side, value in (("old", old), ("new", new)):
        if (not isinstance(value, str) or not value or len(value) > 500
                or _BAD_CONTROLS_RE.search(value)):
            return (f"{side} value is not a plain non-empty string "
                    "(empty, too long, or control characters)")
    if op_type == "typography.size":
        for side, value in (("old", old), ("new", new)):
            match = _SIZE_RE.fullmatch(value)
            if match is None or not 6 <= int(match.group(1)) <= 96:
                return (f"{side} size must look like 'ND' (6D-96D), "
                        f"not {value!r}")
    if op_type == "palette.assign" and _COLOR_RE.fullmatch(new) is None:
        return f"new color must be #RRGGBB, not {new!r}"
    return None


def _plan_leaf_binding(check: str, binding: Any, all_pages: list[str]
                         ) -> tuple[list[dict], list[dict]]:
    """Synthesize one explicit leaf binding with proven old/new literals."""
    if not isinstance(binding, dict):
        return [], [_decision(check, "needs_owner_decision",
                              "unknown inherited default: no proven "
                              "old/new binding; effective values need "
                              "render evidence, never guesses")]
    op_type = binding.get("op")
    page, visual = binding.get("page"), binding.get("visual")
    path = binding.get("path")
    old = binding.get("old")
    new = binding.get("new", None)
    if op_type not in LEAF_OPS:
        reason = (f"unsupported: leaf op {op_type!r} is not a supported "
                  "cosmetic recipe")
        if isinstance(page, str):
            return [], [_decision(check, "unsupported", reason,
                                  page,
                                  visual if isinstance(visual, str)
                                  else None)]
        return [], [_decision(check, "unsupported", reason)]
    if not (_safe_segment(page) and _safe_segment(visual)):
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: unsafe page/visual "
                              "segment")]
    rel = _visual_rel(page, visual)
    assert rel is not None
    if not isinstance(path, list) or len(path) < 2:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: leaf path is not a "
                              "visual objects path", page, visual)]
    try:
        validate_leaf_path(op_type, path)
    except RecipeError as exc:
        return [], [_decision(check, "needs_owner_decision",
                              f"missing source binding: {exc}",
                              page, visual)]
    if isinstance(old, bool) or isinstance(new, bool):
        same = isinstance(old, bool) and isinstance(new, bool)
    else:
        same = type(old) is type(new) or (
            isinstance(old, (int, float)) and isinstance(new, (int, float)))
    if not same:
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: old/new JSON types "
                              "differ; the recipe is type-preserving",
                              page, visual)]
    terminal = (path[path.index("properties") + 1]
                if "properties" in path else None)
    if terminal in ("precision", "labelPrecision"):
        if not is_precision_str(old) or not is_precision_str(new):
            return [], [_decision(
                check, "needs_owner_decision",
                "missing source binding: precision literals must be "
                "strings '0'-'15'", page, visual)]
    elif isinstance(new, str):
        problem = _check_leaf_string(op_type, old, new)
        if problem is not None:
            return [], [_decision(check, "needs_owner_decision",
                                  f"missing source binding: {problem}",
                                  page, visual)]
    elif isinstance(new, float) and not math.isfinite(new):
        return [], [_decision(check, "needs_owner_decision",
                              "missing source binding: non-finite number "
                              "rejected", page, visual)]
    op = {"type": op_type, "selector": {"page": page, "visual": visual},
          "target": "visual", "path": list(path), "old": old,
          "value": new, "writes": [rel]}
    affected = affected_pages(
        {"type": op_type,
         "selector": {"page": page, "visual": visual}}, all_pages)
    return [_candidate(
        check, page, visual, op, old, new, rel, affected["pages"],
        f"set {page}/{visual} {terminal or path[-1]} {old!r} -> {new!r}; "
        "both literals are proven in the sealed finding detail and the "
        "recipe is type-preserving; repair re-validates the precondition "
        "before writing",
        "medium", "leaf-type-preserving",
        "old and new share a JSON type and the terminal is inside "
        "this recipe")], []


def _finding_conflicts(item: dict) -> list[dict]:
    """Rule conflicts from a sealed finding, sorted deterministically."""
    detail = item.get("detail")
    evidence = detail.get("evidence") if isinstance(detail, dict) else None
    conflicts = (evidence.get("conflicts")
                 if isinstance(evidence, dict) else None)
    if not isinstance(conflicts, list):
        return []
    ordered = [entry for entry in conflicts if isinstance(entry, dict)]
    ordered.sort(key=lambda entry: (
        str(entry.get("page", "")),
        [str(name) for name in entry.get("visuals", [])]
        if isinstance(entry.get("visuals"), list)
        else [str(entry.get("visual", ""))]))
    return ordered


def _finding_binding(item: dict) -> Any:
    """Explicit leaf binding from a sealed finding, if the emitter proved one."""
    detail = item.get("detail")
    evidence = detail.get("evidence") if isinstance(detail, dict) else None
    if isinstance(evidence, dict) and "binding" in evidence:
        return evidence["binding"]
    return None


def synthesize_plan(findings: Any, facts: Any, *,
                    source_run_id: str | None = None,
                    source_sha256: str | None = None,
                    facts_sha256: str | None = None) -> dict[str, Any]:
    """Triage sealed findings into candidates, decisions, and a plan.

    Only ``fail``/``blocked`` findings are considered; anything that
    cannot be bound exactly becomes ``needs_owner_decision`` or
    ``unsupported``. Never raises on bad input.
    """
    candidates: list[dict] = []
    decisions: list[dict] = []
    if not isinstance(findings, list):
        return {"plan": None, "candidates": candidates,
                "decisions": [_decision("?", "unsupported",
                                        "unsupported: sealed findings are "
                                        "not a list")]}
    try:
        rects, canvases, geometry_issue = _geometry_index(facts)
    except (TypeError, ValueError, AttributeError, KeyError):
        rects, canvases, geometry_issue = {}, {}, (
            "missing source binding: sealed facts are unreadable")
    tracked = {key: dict(rect) for key, rect in rects.items()}
    planned: dict[tuple[str, str, str], Any] = {}
    all_pages = sorted({*canvases, *[key[0] for key in rects]})
    for item in findings:
        if not isinstance(item, dict):
            decisions.append(_decision("?", "unsupported",
                                       "unsupported: finding is not "
                                       "an object"))
            continue
        check = item.get("check", "?")
        status = item.get("status")
        if status not in ("fail", "blocked"):
            continue
        if not isinstance(check, str):
            decisions.append(_decision("?", "unsupported",
                                       "unsupported: finding check is not "
                                       "a string"))
            continue
        try:
            if check == _OVERLAP_CHECK:
                conflicts = _finding_conflicts(item)
                if not conflicts:
                    decisions.append(_decision(
                        check, "needs_owner_decision",
                        "missing source binding: overlap finding carries "
                        "no proven conflicts", None, None))
                    continue
                if geometry_issue is not None:
                    for conflict in conflicts:
                        pair = conflict.get("visuals")
                        second = (sorted(pair)[1] if isinstance(pair, list)
                                  and len(pair) == 2
                                  and all(isinstance(name, str)
                                          for name in pair) else None)
                        decisions.append(_decision(
                            check, "needs_owner_decision", geometry_issue,
                            str(conflict.get("page"))
                            if isinstance(conflict.get("page"), str)
                            else None, second))
                    continue
                for conflict in conflicts:
                    made, held = _plan_overlap_conflict(
                        check, conflict, canvases, tracked, planned,
                        all_pages or [str(conflict.get("page", ""))])
                    candidates.extend(made)
                    decisions.extend(held)
            elif check == _WITHIN_CHECK:
                conflicts = _finding_conflicts(item)
                if not conflicts:
                    decisions.append(_decision(
                        check, "needs_owner_decision",
                        "missing source binding: outside-page finding "
                        "carries no proven conflicts"))
                    continue
                for conflict in conflicts:
                    made, held = _plan_within_conflict(
                        check, conflict, tracked, canvases, planned,
                        all_pages or [str(conflict.get("page", ""))])
                    candidates.extend(made)
                    decisions.extend(held)
            elif _finding_binding(item) is not None:
                made, held = _plan_leaf_binding(
                    check, _finding_binding(item),
                    all_pages or ["unknown"])
                candidates.extend(made)
                decisions.extend(held)
            elif check.startswith(("coverage:", "oracle:", "document:",
                                       "model:")):
                decisions.append(_decision(
                    check, "unsupported",
                    f"unsupported: no synthesizer for {check}"))
            else:
                decisions.append(_decision(
                    check, "needs_owner_decision",
                    "needs_owner_decision: no safe automatic fix; the "
                    "owner authors a plan (unknown inherited defaults, "
                    "ambiguous layout, and semantic findings are never "
                    "guessed)"))
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            decisions.append(_decision(
                check if isinstance(check, str) else "?", "unsupported",
                f"unsupported: unusable finding shape "
                f"({type(exc).__name__})"))
    seen: dict[tuple[str, tuple[str, ...]], Any] = {}
    unique: list[dict] = []
    for record in candidates:
        operation = record["operation"]
        key = (operation["writes"][0], tuple(operation["path"]))
        if key in seen:
            if seen[key] != operation["value"]:
                decisions.append(_decision(
                    record["check"], "needs_owner_decision",
                    "duplicate target edits: two candidates write "
                    "different values to the same path; the owner "
                    "arbitrates", record["page"], record["visual"]))
                unique = [entry for entry in unique
                          if (entry["operation"]["writes"][0],
                              tuple(entry["operation"]["path"])) != key]
            else:
                decisions.append(_decision(
                    record["check"], "covered_by_candidate",
                    "identical edit already planned",
                    record["page"], record["visual"]))
            continue
        seen[key] = operation["value"]
        unique.append(record)
    candidates = unique
    if not candidates:
        return {"plan": None, "candidates": candidates,
                "decisions": decisions}
    operations = [dict(record["operation"]) for record in candidates]
    targets = sorted({target for record in candidates
                      for target in record["write_targets"]})
    pages = sorted({page for record in candidates
                    for page in record["affected_pages"]})
    checks = sorted({record["check"] for record in candidates})
    plan = {"schema_version": PLAN_SCHEMA_VERSION,
            "source_run_id": source_run_id,
            "source_sha256": source_sha256,
            "facts_sha256": facts_sha256,
            "operations": operations, "write_targets": targets,
            "rollback": _ROLLBACK_RECIPE,
            "affected_pages": pages, "finding_checks": checks}
    issues = validate_plan(plan, "__vqs_original__", "__vqs_candidate__")
    if issues:
        for record in candidates:
            decisions.append(_decision(
                record["check"], "needs_owner_decision",
                "internal plan failed self-validation; no plan emitted",
                record["page"], record["visual"]))
        return {"plan": None, "candidates": [],
                "decisions": decisions}
    return {"plan": plan, "candidates": candidates,
            "decisions": decisions}
