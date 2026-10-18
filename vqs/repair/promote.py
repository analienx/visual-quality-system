"""Owner-controlled promotion mechanics (P0-U4 file swap + rollback).

Promotion never overwrites silently: the original tree is preserved by
rename (no copy window), the candidate is copied into a staging sibling
first, every digest is re-verified at each step, and the sealed
promotion record carries a machine-actionable rollback plan. Any
failure before the first rename leaves the original untouched; a
failure between the two renames raises with the exact partial state
(backup path + staging path) instead of pretending nothing happened.
"""
from __future__ import annotations

import os
import shutil
from typing import Any


class PromoteError(OSError):
    """Promotion refused or interrupted; ``state`` names the exact fallout."""

    def __init__(self, message: str,
                 state: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.state = dict(state or {})


def _real(path: str) -> str:
    return os.path.realpath(path)


def _copy_tree(source: str, dest: str) -> None:
    try:
        shutil.copytree(source, dest, symlinks=False)
    except OSError as exc:
        raise PromoteError(f"cannot stage candidate copy: {exc}",
                           {"staging": dest}) from exc


def swap_original_with_candidate(*, original: str, candidate: str,
                                 backup_dir: str,
                                 precondition_digest: str,
                                 candidate_digest: str) -> dict[str, str]:
    """Rename-swap the candidate onto the original; backup preserves bytes.

    Steps: copy candidate -> staging sibling; verify staging digest;
    rename original -> backup_dir (must not exist); verify backup digest
    equals the precondition; rename staging -> original; verify the final
    digest. Returns paths + digests for the sealed record.
    """
    from .execute import RepairError, tree_digest

    original_real = _real(original)
    candidate_real = _real(candidate)
    backup_real = os.path.abspath(backup_dir)
    if original_real == candidate_real:
        raise PromoteError("original and candidate resolve to the same tree; "
                           "refusing self-promotion")
    if not os.path.isdir(original_real):
        raise PromoteError(f"original report is not a directory: {original}")
    if not os.path.isdir(candidate_real):
        raise PromoteError(f"candidate report is not a directory: {candidate}")
    if os.path.lexists(backup_real):
        raise PromoteError("backup path exists; refusing to overwrite it: "
                           f"{backup_dir}")
    staging = os.path.join(os.path.dirname(original_real),
                           ".vqs-promote-staging")
    if os.path.lexists(staging):
        raise PromoteError("staging path exists; a previous promotion may "
                           f"be incomplete: {staging}")
    _copy_tree(candidate_real, staging)
    try:
        staged_digest = tree_digest(staging)
    except RepairError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise PromoteError(f"staged candidate unreadable: {exc}",
                           {"staging": staging}) from exc
    if staged_digest != candidate_digest:
        shutil.rmtree(staging, ignore_errors=True)
        raise PromoteError("staged candidate digest differs from the sealed "
                           f"candidate: {staged_digest} != {candidate_digest}",
                           {"staging": staging})
    try:
        os.rename(original_real, backup_real)
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise PromoteError(f"cannot preserve original at backup: {exc}",
                           {"staging": staging}) from exc
    try:
        backup_digest = tree_digest(backup_real)
    except RepairError as exc:
        raise PromoteError(f"backup unreadable after preserve: {exc}",
                           {"state": "original-at-backup",
                            "backup": backup_real,
                            "staging": staging}) from exc
    if backup_digest != precondition_digest:
        raise PromoteError("backup digest differs from the promotion "
                           f"precondition: {backup_digest} != "
                           f"{precondition_digest}",
                           {"state": "original-at-backup",
                            "backup": backup_real,
                            "staging": staging})
    try:
        os.rename(staging, original_real)
    except OSError as exc:
        raise PromoteError(f"cannot place candidate at original: {exc}",
                           {"state": "original-at-backup",
                            "backup": backup_real,
                            "staging": staging}) from exc
    try:
        final_digest = tree_digest(original_real)
    except RepairError as exc:
        raise PromoteError(f"promoted original unreadable: {exc}",
                           {"state": "candidate-at-original-unreadable",
                            "backup": backup_real,
                            "original": original_real}) from exc
    if final_digest != candidate_digest:
        raise PromoteError("promoted original digest differs from the "
                           f"sealed candidate: {final_digest} != "
                           f"{candidate_digest}",
                           {"state": "candidate-at-original-mismatch",
                            "backup": backup_real,
                            "original": original_real})
    return {"backup": backup_real, "backup_digest": backup_digest,
            "final": original_real, "final_digest": final_digest}


def rollback_promotion(*, original: str, backup_dir: str,
                       precondition_digest: str) -> dict[str, str]:
    """Reverse a sealed promotion: backup returns to the original path.

    Refuses when the backup digest no longer matches the sealed
    precondition (rolling back to unknown bytes is worse than no
    rollback) or when the original path is occupied by non-promotion
    content — both checked by digest, never by name.
    """
    from .execute import RepairError, tree_digest

    original_real = _real(original)
    backup_real = os.path.abspath(backup_dir)
    if not os.path.isdir(backup_real):
        raise PromoteError("rollback backup is not a directory: "
                           f"{backup_dir}")
    try:
        backup_digest = tree_digest(backup_real)
    except RepairError as exc:
        raise PromoteError(f"rollback backup unreadable: {exc}",
                           {"backup": backup_real}) from exc
    if backup_digest != precondition_digest:
        raise PromoteError("rollback backup differs from the sealed "
                           f"precondition: {backup_digest} != "
                           f"{precondition_digest}",
                           {"backup": backup_real})
    retired = original_real + ".vqs-retired"
    if os.path.lexists(original_real):
        if os.path.lexists(retired):
            raise PromoteError("rollback retired path exists; refusing: "
                               f"{retired}")
        try:
            os.rename(original_real, retired)
        except OSError as exc:
            raise PromoteError(f"cannot retire promoted tree: {exc}",
                               {"original": original_real}) from exc
    try:
        os.rename(backup_real, original_real)
    except OSError as exc:
        raise PromoteError(f"cannot restore backup to original: {exc}",
                           {"state": "promoted-at-retired" if os.path.lexists(
                               retired) else "backup-intact",
                            "backup": backup_real,
                            "retired": retired}) from exc
    try:
        restored = tree_digest(original_real)
    except RepairError as exc:
        raise PromoteError(f"restored original unreadable: {exc}",
                           {"original": original_real}) from exc
    if restored != precondition_digest:
        raise PromoteError("restored original digest differs from the "
                           f"sealed precondition: {restored}",
                           {"original": original_real})
    return {"original": original_real, "digest": restored,
            "retired": retired if os.path.lexists(retired) else ""}
