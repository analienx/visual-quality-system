"""Atomic candidate application (WP-09 execution half).

Two stages, no shortcuts: the plan validates (allowlist) before anything
is copied, and every operation binds (recipes) before anything is
written. The candidate root must be fresh; the original is never
modified (verified by digest after the run). Any failure restores the
candidate snapshot and blocks with the exact op index and reason.
chart.replace needs a vetted registered template plus identical intent
or an owner approval; nothing else may change a visual's type or query.
Every write lands in a visual.json under the candidate report tree: the
executor physically cannot touch model files, so broader DAX/model
mutation stays a later separately authorized capability even when a plan
carries an owner approval id.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .allowlist import validate_materialized_roots, validate_plan
from .recipes import RecipeError, affected_pages, bind_operation
from .templates import TemplateError, get_template, verify_bindings


class RepairError(OSError):
    """Candidate materialization or application failed; nothing applied."""


def tree_digest(report: str | Path) -> str:
    """Fingerprint a report tree relative to its own root.

    Unlike source_digest (which binds the report's parent path and
    sibling models), this compares original and candidate CONTENT across
    different roots: identical trees digest identically wherever they
    live. Any link inside refuses instead of hashing through it.
    """
    root = Path(report)
    digest = hashlib.sha256()
    try:
        entries = sorted(root.rglob("*"))
    except OSError as exc:
        raise RepairError(f"cannot walk {root}: {exc}") from exc
    for path in entries:
        if path.is_symlink():
            raise RepairError(f"link inside repair tree: {path}")
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            try:
                digest.update(path.read_bytes())
            except OSError as exc:
                raise RepairError(f"cannot read {path}: {exc}") from exc
            digest.update(b"\0")
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RepairError(f"cannot read {path}: {exc}") from exc


def _write_json(path: Path, doc: Any) -> None:
    try:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        raise RepairError(f"cannot write {path}: {exc}") from exc


def materialize_candidate(original: str, candidate_root: str) -> dict:
    """Copy the original report into a fresh candidate root (links refuse)."""
    if not os.path.isdir(original):
        raise RepairError(f"original report is not a directory: {original}")
    if os.path.lexists(candidate_root):
        raise RepairError("candidate root exists; use a fresh path: "
                          f"{candidate_root}")
    try:
        os.makedirs(candidate_root)
    except OSError as exc:
        raise RepairError(f"cannot create candidate root: {exc}") from exc
    try:
        root_issues = validate_materialized_roots(original, candidate_root)
        if root_issues:
            raise RepairError(f"repair roots rejected: {root_issues[0]}")
        count = 0
        for current, _dirs, files in os.walk(original, followlinks=False):
            for name in files:
                source = os.path.join(current, name)
                if os.path.islink(source):
                    raise RepairError(f"original contains a link: {source}")
                rel = os.path.relpath(source, original)
                target = os.path.join(candidate_root, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(source, target)
                count += 1
    except Exception:
        shutil.rmtree(candidate_root, ignore_errors=True)
        raise
    return {"original": os.path.realpath(original),
            "candidate": os.path.realpath(candidate_root), "files": count,
            "digest": tree_digest(candidate_root)}


def _visual_file(candidate: Path, page: str, visual: str) -> Path:
    return (candidate / "definition" / "pages" / page / "visuals" / visual
            / "visual.json")


def _canvas_of(candidate: Path, page: str) -> tuple[int, int]:
    page_doc = _read_json(candidate / "definition" / "pages" / page
                          / "page.json")
    width, height = page_doc.get("width"), page_doc.get("height")
    if (not isinstance(width, int) or not isinstance(height, int)
            or width <= 0 or height <= 0):
        raise RepairError(f"page {page} has no positive integer canvas")
    return width, height


def _set_path(doc: dict, path: list, value: Any) -> None:
    node = doc
    for step in path[:-1]:
        node = node[step] if isinstance(node, dict) else node[int(step)]
    last = path[-1]
    if isinstance(node, dict):
        node[last] = value
    else:
        node[int(last)] = value


def _unified_patch(rel: str, before: bytes, after: bytes) -> str:
    before_lines = before.decode("utf-8-sig").splitlines()
    after_lines = after.decode("utf-8-sig").splitlines()
    return "\n".join(difflib.unified_diff(
        before_lines, after_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}",
        lineterm=""))


def apply_plan(plan: dict, original: str, candidate_root: str,
               approved_semantic_change: str | None = None) -> dict:
    """Validate, materialize, and apply a plan; blocked restores, never half."""
    plan_issues = validate_plan(plan, original, candidate_root,
                                approved_semantic_change)
    if plan_issues:
        return {"verdict": "blocked", "stage": "validate",
                "issues": plan_issues}
    try:
        materialize_candidate(original, candidate_root)
    except RepairError as exc:
        return {"verdict": "blocked", "stage": "materialize",
                "reason": str(exc)}
    candidate = Path(candidate_root)
    operations = plan.get("operations", [])
    snapshot: dict[str, bytes] = {}
    edits: list[dict[str, Any]] = []
    pages: list[str] = []
    try:
        from vqs.pbir import report_context
        info = report_context(candidate)
        all_pages = [page["id"] for page in info["pages"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        shutil.rmtree(candidate_root, ignore_errors=True)
        return {"verdict": "blocked", "stage": "materialize",
                "reason": f"candidate report unreadable: {exc}"}
    covered = set()
    for entry in plan.get("write_targets", []):
        target = str(entry)
        absolute = target if os.path.isabs(target) else os.path.join(
            candidate_root, target)
        covered.add(os.path.realpath(absolute))
    for index, op in enumerate(operations):
        try:
            edits.append(_apply_op(op, candidate, all_pages,
                                   approved_semantic_change, snapshot,
                                   covered))
        except (RecipeError, TemplateError, RepairError) as exc:
            shutil.rmtree(candidate_root, ignore_errors=True)
            return {"verdict": "blocked", "stage": "apply", "index": index,
                    "reason": f"{type(exc).__name__}: {exc}"}
    for edit in edits:
        for page in edit["affected"]["pages"]:
            if page not in pages:
                pages.append(page)
    try:
        before_digest = tree_digest(original)
        after_digest = tree_digest(candidate)
        if before_digest == after_digest:
            raise RepairError("candidate digest unchanged; no edit landed")
    except RepairError as exc:
        shutil.rmtree(candidate_root, ignore_errors=True)
        return {"verdict": "blocked", "stage": "digest",
                "reason": str(exc)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        shutil.rmtree(candidate_root, ignore_errors=True)
        return {"verdict": "blocked", "stage": "digest",
                "reason": f"cannot re-read reports: {exc}"}
    patch = {rel: _unified_patch(rel, before,
                                 (candidate / rel).read_bytes())
             for rel, before in snapshot.items()}
    return {"verdict": "applied", "candidate": str(candidate),
            "before": before_digest, "after": after_digest,
            "edits": edits, "patch": patch, "affected_pages": pages}


def _apply_op(op: dict, candidate: Path, all_pages: list[str],
              approved: str | None, snapshot: dict[str, bytes],
              covered: set[str]) -> dict:
    from vqs.pbir import report_context

    selector = op.get("selector", {})
    page = selector.get("page", "")
    visual = selector.get("visual", "")
    target_file = _visual_file(candidate, page, visual)
    try:
        rel = target_file.relative_to(candidate).as_posix()
    except ValueError as exc:
        raise RepairError(f"selector escapes the candidate: {page}/{visual}"
                          ) from exc
    if os.path.realpath(target_file) not in covered:
        raise RepairError(f"derived write is not a declared write target: "
                          f"{rel}")
    if not target_file.is_file():
        raise RepairError(f"bound visual file missing: {rel}")
    if rel not in snapshot:
        snapshot[rel] = target_file.read_bytes()
    visual_doc = _read_json(target_file)
    canvas = _canvas_of(candidate, page)
    if op.get("type") == "chart.replace":
        return _apply_replace(op, visual_doc, target_file, rel, candidate,
                              all_pages, approved)
    binding = bind_operation(op, visual_doc, canvas)
    _set_path(visual_doc, binding["path"], binding["new"])
    _write_json(target_file, visual_doc)
    binding["file"] = rel
    binding["affected"] = affected_pages(op, all_pages)
    info_pages = {page["id"] for page in report_context(candidate)["pages"]}
    if page not in info_pages:
        raise RepairError(f"bound page {page} left the page order")
    return binding


def _apply_replace(op: dict, visual_doc: dict, target_file: Path, rel: str,
                   candidate: Path, all_pages: list[str],
                   approved: str | None) -> dict:
    from vqs.pbir import report_context

    binding = bind_operation(op, None)
    if not (op.get("identical_intent") is True or approved):
        raise RepairError("chart.replace needs identical_intent or an "
                          "owner-approved semantic change id")
    template = get_template(binding["template"], binding["version"])
    query = visual_doc.get("visual", {}).get("query", {})
    roles = query.get("queryState", {}) if isinstance(query, dict) else {}
    bindings = {name: spec.get("projections", [])
                for name, spec in roles.items()
                if isinstance(spec, dict)}
    missing = verify_bindings(template, bindings)
    if missing:
        raise RepairError("template bindings unverified on target visual: "
                          + ", ".join(missing))
    new_visual = dict(visual_doc.get("visual", {}))
    new_visual["visualType"] = template["visual_type"]
    new_visual["objects"] = template["body"]["visual"].get("objects", {})
    visual_doc["visual"] = new_visual
    _write_json(target_file, visual_doc)
    info = report_context(candidate)
    if binding["page"] not in {page["id"] for page in info["pages"]}:
        raise RepairError("bound page left the page order")
    return {**binding, "file": rel,
            "affected": affected_pages(op, all_pages)}


def rollback_candidate(original: str, candidate_root: str,
                       before_digest: str) -> dict:
    """Rollback an applied candidate by re-materializing from the original.

    The candidate is disposable: rollback removes it and copies the
    original again, then proves the restore with rollback_ok against the
    recorded before digest.
    """
    from .allowlist import rollback_ok

    shutil.rmtree(candidate_root, ignore_errors=True)
    try:
        staged = materialize_candidate(original, candidate_root)
    except RepairError as exc:
        return {"rule": "rollback_unverifiable", "status": "blocked",
                "reason": str(exc)}
    after = tree_digest(candidate_root)
    verdict = rollback_ok(before_digest, after)
    return {**verdict, "candidate": staged["candidate"]}
