"""Typed repair-plan allowlist (WP-09 static half, issue #14).

Two-stage plan validation *before* any execution: every operation must be
allowlisted, model/DAX/RLS and intent changes need an explicit owner approval
id, the write target must be a disposable candidate (never the original
source), and a rollback recipe is mandatory. FIX-02 (shell/DAX smuggling),
FIX-08 (original overwrite), and DES-07 (intent change without approval) are
rejected here; live render, data, and regression gates belong downstream.
Criterion 11 additionally requires non-empty write targets, no
original/candidate overlap, per-operation write coverage, and link-escape
rejection (static lexical half here, realpath half in
validate_materialized_roots).
"""
from __future__ import annotations

import os
import posixpath
import re
from typing import Any

from .recipes import is_precision_str

ALLOWED_OPS: frozenset[str] = frozenset({
    "theme.set", "palette.assign", "typography.size", "axis.tick_format",
    "axis.title", "axis.precision", "label.format", "chart.resize",
    "spacing.adjust", "sort.set", "chart.replace",
})
MODEL_TARGETS: frozenset[str] = frozenset({"model", "dax", "rls", "dataset", "measure"})
SHELL_OPS: frozenset[str] = frozenset({"shell", "exec", "command", "run", "script"})


def _seps(path: str) -> str:
    return path.replace("\\", "/")


def _resolve(candidate_root: str, target: str) -> str:
    """Resolve a write target: absolute stays absolute, relative joins the root."""
    candidate = posixpath.normpath(_seps(candidate_root))
    cleaned = _seps(target)
    if posixpath.isabs(cleaned) or re.match(r"^[A-Za-z]:", cleaned) or cleaned.startswith("//"):
        return posixpath.normpath(cleaned)
    return posixpath.normpath(posixpath.join(candidate, cleaned))


def _inside(candidate_root: str, target: str) -> bool:
    """Strict containment: the target must be a file inside the root.

    The root directory itself (from empty, ".", or equivalent targets) is
    not a writable artifact and is rejected.
    """
    root = posixpath.normpath(_seps(candidate_root))
    resolved = _resolve(candidate_root, target)
    if resolved == root:
        return False
    return resolved.startswith(root.rstrip("/") + "/")


def _overlaps(first: str, second: str) -> bool:
    """Lexical root overlap: equal or nested in either direction."""
    left = posixpath.normpath(_seps(first)).rstrip("/") or "/"
    right = posixpath.normpath(_seps(second)).rstrip("/") or "/"
    return (left == right or left.startswith(right + "/")
            or right.startswith(left + "/"))


def normalize_targets(value: Any) -> list[str]:
    """String entries of a write-target declaration (non-strings dropped).

    A bare string coerces to one target here, but validate_plan rejects
    non-list write_targets up front; this is the executor's belt-and-
    braces normalization, not a second validation.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, str)]
    return []


def within_root(root_real: str, entry: str) -> bool:
    """Realpath containment: entry resolves at or under the real root."""
    target = os.path.normcase(os.path.realpath(entry))
    return target == root_real or target.startswith(root_real + os.sep)


def _leaf_terminal(path: object) -> str | None:
    """Terminal property after "properties" for leaf tails (T12 mirror).

    Mirrors recipes._bound_terminal without importing it, so
    validate-plan rejects malformed new precision before execution.
    """
    if not isinstance(path, list) or "properties" not in path:
        return None
    tail = path[path.index("properties") + 1:]
    if len(tail) == 4 and tail[1:] == ["expr", "Literal", "Value"]:
        return tail[0] if isinstance(tail[0], str) else None
    return None


def _touches_model(target: str) -> bool:
    """Case/whitespace-qualified match, including qualified refs like Dataset.T[col]."""
    norm = target.strip().casefold()
    delimiters = (".", "[", "(", " ", "/", ":")
    return any(norm == word or norm.startswith(word + mark)
               for word in MODEL_TARGETS for mark in delimiters)


def validate_plan(plan: dict[str, Any], original_path: str, candidate_root: str,
                 approved_semantic_change: str | None = None) -> list[dict[str, Any]]:
    """Validate a repair plan; empty list means it may proceed to execution."""
    issues: list[dict[str, Any]] = []
    if not isinstance(plan, dict):
        return [{"rule": "plan_not_an_object"}]
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        return [{"rule": "plan_has_no_operations"}]
    raw_targets = plan.get("write_targets")
    if not isinstance(raw_targets, list):
        return [{"rule": "plan_write_targets_not_a_list"}]
    declared_targets = normalize_targets(raw_targets)
    if not declared_targets:
        return [{"rule": "plan_has_no_write_targets"}]
    if _overlaps(original_path, candidate_root):
        issues.append({"rule": "roots_overlap",
                       "remediation": "Candidate and original roots must not "
                                      "overlap in either direction"})
    covered = {_resolve(candidate_root, target)
               for target in declared_targets}
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            issues.append({"rule": "operation_not_an_object", "index": index})
            continue
        op_type = op.get("type", "")
        if op_type in SHELL_OPS:
            issues.append({"rule": "plan_rejected_shell", "index": index, "type": op_type})
            continue
        if op_type not in ALLOWED_OPS:
            issues.append({"rule": "plan_rejected_unknown_op", "index": index,
                           "type": op_type})
            continue
        target = str(op.get("target", ""))
        if _touches_model(target) and not approved_semantic_change:
            issues.append({"rule": "dax_rls_unapproved", "index": index,
                           "remediation": "Declare an owner-approved semantic change id"})
            continue
        if op_type == "chart.replace" and not (
                op.get("identical_intent") is True or approved_semantic_change):
            issues.append({"rule": "intent_change_unapproved", "index": index})
        terminal = _leaf_terminal(op.get("path"))
        # T12: the bound property governs, never the op alias —
        # malformed new precision fails here, not just at apply.
        # The predicate is shared with bind so both gates agree
        # exactly (padded/unicode-digit strings fail cleanly).
        if (terminal in ("precision", "labelPrecision")
                and not is_precision_str(op.get("value"))):
            issues.append({"rule": "precision_value_invalid",
                           "index": index, "terminal": terminal,
                           "remediation": "Precision is a 0-15 string"})
        writes = op.get("writes")
        if writes is not None:
            for entry in normalize_targets(writes):
                if _resolve(candidate_root, entry) not in covered:
                    issues.append({"rule": "operation_write_mismatch",
                                   "index": index, "target": entry,
                                   "remediation": "Declare every operation "
                                                  "write in write_targets"})
            if not isinstance(writes, list) or not all(
                    isinstance(entry, str) for entry in writes):
                issues.append({"rule": "operation_write_mismatch",
                               "index": index,
                               "remediation": "writes must be a list of paths"})
    original = posixpath.normpath(_seps(original_path))
    for target in plan.get("write_targets", []):
        if not isinstance(target, str) or not _inside(candidate_root, target):
            issues.append({"rule": "write_guard_violation", "target": target,
                           "remediation": "Write only inside the disposable candidate root"})
        elif _resolve(candidate_root, target) == original:
            issues.append({"rule": "write_guard_violation", "target": target,
                           "remediation": "The original source is read-only"})
    if plan.get("removed_ids") and not approved_semantic_change:
        issues.append({"rule": "id_not_preserved", "removed": plan.get("removed_ids")})
    if not plan.get("rollback"):
        issues.append({"rule": "missing_rollback"})
    return issues


def _has_link(path: str) -> bool:
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    return bool(isjunction is not None and isjunction(path))


def _nlink(path: str) -> int | None:
    """Hardlink count of a file; None when it cannot be stated."""
    try:
        return os.stat(path).st_nlink
    except OSError:
        return None


def validate_materialized_roots(original_path: str,
                                candidate_root: str) -> list[dict[str, Any]]:
    """Realpath half of criterion 11 on existing roots; [] means proceed.

    Rejects realpath overlap (catches case/alias tricks the lexical check
    cannot see) and any link or hardlink inside either root. Detection is per-entry
    realpath containment, which is version-independent: it catches
    symlinks, junctions, and alias tricks on every supported Python,
    including junctions on 3.11 where os.path.isjunction is missing.
    Inside-pointing junctions are invisible on 3.11 (no API exists) but
    cannot escape; directory loops are refused via visited-realpath
    tracking. Walk errors fail closed as roots_unreadable.
    """
    issues: list[dict[str, Any]] = []
    for label, root in (("original", original_path),
                        ("candidate", candidate_root)):
        if not os.path.isdir(root):
            issues.append({"rule": "roots_not_materialized", "root": label,
                           "path": root})
    if issues:
        return issues
    real_original = os.path.realpath(original_path)
    real_candidate = os.path.realpath(candidate_root)
    if (real_original == real_candidate
            or real_original.startswith(real_candidate + os.sep)
            or real_candidate.startswith(real_original + os.sep)):
        issues.append({"rule": "roots_overlap",
                       "remediation": "Candidate and original roots must not "
                                      "overlap after link resolution"})
        return issues
    for label, root in (("original", original_path),
                        ("candidate", candidate_root)):
        root_real = os.path.normcase(os.path.realpath(root))
        failures: list[OSError] = []

        def _on_error(exc: OSError,
                      _sink: list[OSError] = failures) -> None:
            _sink.append(exc)

        seen: set[str] = {root_real}
        walker = os.walk(root, followlinks=False, onerror=_on_error)
        for current, dirs, files in walker:
            for name in (*dirs, *files):
                full = os.path.join(current, name)
                if _has_link(full) or not within_root(root_real, full):
                    issues.append({"rule": "link_escape", "root": label,
                                   "path": full,
                                   "remediation": "Remove links from "
                                                  "repair roots"})
                    return issues
                if os.path.isfile(full):
                    links = _nlink(full)
                    if links is None:
                        issues.append({"rule": "roots_unreadable",
                                       "root": label, "path": full})
                        return issues
                    if links > 1:
                        issues.append({"rule": "link_escape",
                                       "root": label, "path": full,
                                       "remediation": "Remove hardlinks "
                                                      "from repair roots"})
                        return issues
            for name in list(dirs):
                marker = os.path.normcase(os.path.realpath(
                    os.path.join(current, name)))
                if marker in seen:
                    issues.append({"rule": "link_escape", "root": label,
                                   "path": os.path.join(current, name),
                                   "remediation": "Remove directory loops "
                                                  "from repair roots"})
                    return issues
                seen.add(marker)
        if failures:
            issues.append({"rule": "roots_unreadable", "root": label,
                           "detail": str(failures[0])})
            return issues
    return issues


def rollback_ok(before_digest: str, after_rollback_digest: str) -> dict:
    """Pass only when rollback restores the exact input hash."""
    if not before_digest or not after_rollback_digest:
        return {"rule": "rollback_unverifiable", "status": "blocked"}
    if before_digest == after_rollback_digest:
        return {"rule": "rollback_restored", "status": "pass"}
    return {"rule": "rollback_mismatch", "status": "fail"}
