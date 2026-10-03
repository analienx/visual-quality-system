"""Candidate regression gates (criterion 16, WP-09).

A repair must change nothing it did not declare: untouched files stay
byte-identical, touched files differ only at declared edit paths (or
declared replace prefixes), page/visual IDs are preserved, and every
visual stays finite and in-canvas — neighbors included. Rerender
requirements name the pages that need fresh evidence; render
verification blocks until fresh manifests cover them, and never
fabricates coverage.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .recipes import affected_pages


def _diff_paths(before: Any, after: Any,
                prefix: tuple = ()) -> set[tuple]:
    """JSON path tuples where two documents differ (NaN equals NaN here)."""
    if isinstance(before, float) and isinstance(after, float):
        if math.isnan(before) and math.isnan(after):
            return set()
        return set() if before == after else {prefix}
    if isinstance(before, dict) and isinstance(after, dict):
        paths = set()
        for key in before.keys() | after.keys():
            if key not in before or key not in after:
                paths.add((*prefix, key))
            else:
                paths |= _diff_paths(before[key], after[key],
                                     (*prefix, key))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        paths = set()
        for index in range(max(len(before), len(after))):
            if index >= len(before) or index >= len(after):
                paths.add((*prefix, index))
            else:
                paths |= _diff_paths(before[index], after[index],
                                     (*prefix, index))
        return paths
    return set() if type(before) is type(after) and before == after \
        else {prefix}


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise _Unreadable(str(exc)) from exc


class _Unreadable(Exception):
    pass


def _inventory(report: Path) -> set[str]:
    return {path.relative_to(report).as_posix() for path in
            sorted(report.rglob("*")) if path.is_file()}


def _declared_for(edits: list[dict]) -> dict[str, dict[str, set]]:
    declared: dict[str, dict[str, set]] = {}
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise _Unreadable(f"edit {index} is not an object")
        target = edit.get("file")
        if not isinstance(target, str) or not target:
            raise _Unreadable(f"edit {index} has no file path")
        slot = declared.setdefault(target, {"exact": set(),
                                            "prefixes": set()})
        if edit.get("op") == "chart.replace":
            slot["prefixes"] |= {("visual", "visualType"),
                                 ("visual", "objects")}
        else:
            path = edit.get("path")
            if not isinstance(path, list):
                raise _Unreadable(f"edit {index} has no edit path")
            slot["exact"].add(tuple(path))
    return declared


def _inventories(original: Path, candidate: Path,
                 approved_removals: set[str]) -> list[dict]:
    problems = []
    try:
        before, after = _inventory(original), _inventory(candidate)
    except OSError as exc:
        return [{"rule": "report_unreadable", "detail": str(exc)}]
    for rel in sorted(after - before):
        problems.append({"rule": "file_added", "file": rel})
    for rel in sorted(before - after):
        parts = rel.split("/")
        approval = ""
        if parts[-1:] == ["visual.json"] and "visuals" in parts:
            at = parts.index("visuals")
            if 1 <= at and at + 1 < len(parts) - 1:
                approval = f"{parts[at - 1]}/{parts[at + 1]}"
        if approval and approval in approved_removals:
            continue
        problems.append({"rule": "file_removed", "file": rel})
    return problems


def _confinement(original: Path, candidate: Path,
                 edits: list[dict]) -> list[dict]:
    problems: list[dict] = []
    try:
        declared = _declared_for(edits)
    except _Unreadable as exc:
        return [{"rule": "edits_unreadable", "detail": str(exc)}]
    try:
        before_files = _inventory(original)
        after_files = _inventory(candidate)
    except OSError as exc:
        return [{"rule": "report_unreadable", "detail": str(exc)}]
    for rel in sorted(declared):
        if rel not in after_files:
            problems.append({"rule": "declared_target_missing", "file": rel})
    if problems:
        return problems
    common = before_files & after_files
    for rel in sorted(common):
        try:
            old_bytes = (original / rel).read_bytes()
            new_bytes = (candidate / rel).read_bytes()
        except OSError as exc:
            problems.append({"rule": "report_unreadable", "file": rel,
                             "detail": str(exc)})
            continue
        if rel not in declared:
            if old_bytes != new_bytes:
                problems.append({"rule": "undeclared_change", "file": rel})
            continue
        try:
            before_doc = json.loads(old_bytes.decode("utf-8-sig"))
            after_doc = json.loads(new_bytes.decode("utf-8-sig"))
        except ValueError:
            problems.append({"rule": "touched_file_unreadable", "file": rel})
            continue
        slot = declared[rel]
        for diff in sorted(_diff_paths(before_doc, after_doc),
                           key=repr):
            if diff in slot["exact"]:
                continue
            if any(diff[:len(prefix)] == prefix
                   for prefix in slot["prefixes"]):
                continue
            problems.append({"rule": "undeclared_change", "file": rel,
                             "path": list(diff)})
            if len(problems) >= 20:
                return problems
    return problems


def _page_order(pages_root: Path) -> list[str]:
    order = _load(pages_root / "pages.json")["pageOrder"]
    if not isinstance(order, list) or not all(
            isinstance(entry, str) for entry in order):
        raise _Unreadable("pageOrder is not a string list")
    return order


def _visual_ids(pages_root: Path, page_id: str) -> set[str]:
    visuals_root = pages_root / page_id / "visuals"
    if not visuals_root.is_dir():
        return set()
    try:
        return {child.name for child in visuals_root.iterdir()
                if (child / "visual.json").is_file()}
    except OSError as exc:
        raise _Unreadable(f"visuals of {page_id}: {exc}") from exc


def _identities(original: Path, candidate: Path,
                approved_removals: set[str]) -> list[dict]:
    """Page order and per-page visual IDs must match the original exactly.

    Owner-approved removals are "page/visual" pairs; anything else added
    or removed fails.
    """
    problems = []
    try:
        before = _page_order(original / "definition" / "pages")
        after = _page_order(candidate / "definition" / "pages")
    except (_Unreadable, KeyError, TypeError) as exc:
        return [{"rule": "report_unreadable",
                 "detail": f"pages.json: {exc}"}]
    if before != after:
        return [{"rule": "page_order_changed",
                 "expected": before, "actual": after}]
    pages_root = candidate / "definition" / "pages"
    for page_id in after:
        visuals_root = pages_root / page_id / "visuals"
        if not visuals_root.is_dir():
            problems.append({"rule": "page_visuals_missing",
                             "page": page_id})
            continue
        try:
            old_ids = _visual_ids(original / "definition" / "pages",
                                  page_id)
            new_ids = _visual_ids(pages_root, page_id)
        except _Unreadable as exc:
            problems.append({"rule": "report_unreadable",
                             "detail": str(exc)})
            continue
        excused = {entry.split("/", 1)[1]
                   for entry in approved_removals
                   if entry.startswith(page_id + "/")}
        removed = sorted(old_ids - new_ids - excused)
        added = sorted(new_ids - old_ids)
        if removed or added:
            problems.append({"rule": "visual_ids_changed", "page": page_id,
                             "removed": removed, "added": added})
    return problems


def _geometry(candidate: Path) -> list[dict]:
    """Every visual stays finite and inside its page canvas."""
    problems = []
    pages_root = candidate / "definition" / "pages"
    try:
        order = _load(pages_root / "pages.json")["pageOrder"]
    except (_Unreadable, KeyError, TypeError):
        return problems  # _identities reports the unreadable shape
    for page_id in order if isinstance(order, list) else []:
        if not isinstance(page_id, str):
            continue
        try:
            page = _load(pages_root / page_id / "page.json")
            width, height = page["width"], page["height"]
        except (_Unreadable, KeyError, TypeError):
            problems.append({"rule": "page_canvas_unreadable",
                             "page": page_id})
            continue
        if (isinstance(width, bool) or not isinstance(width, int)
                or isinstance(height, bool) or not isinstance(height, int)
                or width <= 0 or height <= 0):
            problems.append({"rule": "page_canvas_unreadable",
                             "page": page_id})
            continue
        visuals_root = pages_root / page_id / "visuals"
        if not visuals_root.is_dir():
            continue
        for visual_file in sorted(visuals_root.glob("*/visual.json")):
            visual_id = visual_file.parent.name
            try:
                position = _load(visual_file)["position"]
                values = [position[key] for key in
                          ("x", "y", "width", "height")]
            except (_Unreadable, KeyError, TypeError):
                problems.append({"rule": "visual_position_unreadable",
                                 "page": page_id, "visual": visual_id})
                continue
            if any(isinstance(value, bool)
                   or not isinstance(value, (int, float))
                   or not math.isfinite(value) for value in values):
                problems.append({"rule": "visual_position_nonfinite",
                                 "page": page_id, "visual": visual_id})
                continue
            x, y, w, h = values
            if min(x, y) < 0 or min(w, h) <= 0:
                problems.append({"rule": "visual_position_invalid",
                                 "page": page_id, "visual": visual_id})
            elif (x + w > width or y + h > height):
                problems.append({"rule": "visual_cropped_or_outside",
                                 "page": page_id, "visual": visual_id})
    return problems


def verify_candidate(original: str | Path, candidate: str | Path,
                     edits: list[dict],
                     approved_removals: set[str] | None = None) -> dict:
    """Pass only when the candidate differs solely by declared edits.

    approved_removals holds owner-approved "page/visual" pairs; global
    visual ids are not accepted.
    """
    original_path, candidate_path = Path(original), Path(candidate)
    approved = set(approved_removals or ())
    if not isinstance(edits, list):
        return {"verdict": "fail",
                "problems": [{"rule": "edits_unreadable",
                              "detail": "edits must be a list"}]}
    problems = _inventories(original_path, candidate_path, approved)
    problems += _confinement(original_path, candidate_path, edits)
    problems += _identities(original_path, candidate_path, approved)
    problems += _geometry(candidate_path)
    if problems:
        return {"verdict": "fail", "problems": problems[:20]}
    return {"verdict": "pass",
            "checks": ["inventory", "confinement", "identities", "geometry"]}


def rerender_requirements(operations: list[dict],
                          ordered_page_ids: list[str]) -> dict:
    """Pages needing fresh renders: affected + order neighbors (all if shared).

    Same-page neighbors ride along in their page's render; order-adjacent
    pages guard against cross-page template spillover. Shared theme or
    palette ops invalidate every page.
    """
    affected: list[str] = []
    shared = False
    reasons = []
    if not isinstance(operations, list):
        return {"verdict": "blocked",
                "reason": "repair operations required"}
    if not operations:
        return {"verdict": "blocked",
                "reason": "no operations; nothing requires a rerender"}
    if (not isinstance(ordered_page_ids, list) or not all(
            isinstance(entry, str) for entry in ordered_page_ids)):
        return {"verdict": "blocked", "reason": "page order required"}
    for index, op in enumerate(operations):
        try:
            result = affected_pages(op, ordered_page_ids)
        except (ValueError, TypeError, AttributeError) as exc:
            return {"verdict": "blocked",
                    "reason": f"operation {index} has no source binding",
                    "detail": str(exc)}
        shared = shared or result["shared"]
        reasons.append(result["reason"])
        for page in result["pages"]:
            if page not in affected:
                affected.append(page)
    unknown = [page for page in affected if page not in ordered_page_ids]
    if unknown:
        return {"verdict": "blocked", "reason": "unknown page in selector",
                "pages": unknown}
    if shared:
        pages = list(ordered_page_ids)
    else:
        pages = list(affected)
        for page in affected:
            if page in ordered_page_ids:
                at = ordered_page_ids.index(page)
                for neighbor in (at - 1, at + 1):
                    if 0 <= neighbor < len(ordered_page_ids):
                        candidate = ordered_page_ids[neighbor]
                        if candidate not in pages:
                            pages.append(candidate)
        pages.sort(key=ordered_page_ids.index
                   if all(page in ordered_page_ids for page in pages)
                   else repr)
    return {"verdict": "ready", "pages": pages, "shared": shared,
            "reasons": reasons}


def verify_renders(required_pages: list[str], manifests: list[dict],
                   candidate_digest: str) -> dict:
    """Pass only when fresh manifests cover every required page.

    A manifest counts for a page only when its source_sha256 equals the
    candidate digest and its page_images names the page. Malformed
    manifests are not evidence; missing pages block with exact names.
    Empty requirements or a missing digest block instead of passing
    vacuously. Malformed collections block with a reason; they never
    raise into the caller.
    """
    if not isinstance(required_pages, list):
        return {"verdict": "blocked",
                "reason": "required pages must be a list"}
    if not required_pages:
        return {"verdict": "blocked",
                "reason": "no pages required; refusing vacuous pass"}
    if not candidate_digest:
        return {"verdict": "blocked",
                "reason": "candidate digest required"}
    if not isinstance(manifests, list):
        return {"verdict": "blocked",
                "reason": "render manifests required"}
    covered: set[str] = set()
    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        if manifest.get("source_sha256") != candidate_digest:
            continue
        images = manifest.get("page_images")
        if not isinstance(images, dict):
            continue
        covered |= {page for page in required_pages if page in images}
    missing = [page for page in required_pages if page not in covered]
    if missing:
        return {"verdict": "blocked", "reason": "fresh complete renders "
                "required for affected pages and neighbors",
                "missing_pages": missing}
    return {"verdict": "pass", "pages": list(required_pages)}
