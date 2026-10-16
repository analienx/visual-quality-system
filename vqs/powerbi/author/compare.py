"""Read-only paired Microsoft PBIR diagnostics on an exact declared candidate delta.

No normalization, warning waiver, original write, screenshot authority or release
approval. Compare *both* reports with the same pinned Microsoft CLI, and separate
inherited failures from newly introduced failures.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from ...pbir import source_digest
from ...repair.preview import _inventory
from . import mscli

Runner = Callable[..., dict[str, Any]]


def _normalize(lines: list[str], project: Path) -> list[str]:
    """Remove only the project-root prefix; preserve file paths and message."""
    prefix = str(project.resolve()).replace("\\", "/").casefold().rstrip("/")
    return sorted(
        line.replace("\\", "/").casefold().replace(prefix + "/", "<project>/")
        for line in lines
    )


def _diagnostics(value: Any, project: Path) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("status") not in ("valid", "invalid"):
        raise ValueError("Microsoft CLI did not return a complete validation")
    errors, warnings = value.get("errors"), value.get("warnings")
    full = value.get("diagnostics_full")
    if full is not None:
        if not isinstance(full, dict):
            raise TypeError("Microsoft full diagnostics malformed")
        errors, warnings = full.get("errors"), full.get("warnings")
    if not isinstance(errors, list) or not isinstance(warnings, list):
        raise TypeError("Microsoft diagnostic arrays missing")
    if (any(not isinstance(z, str) or not z for z in errors + warnings)
            or value.get("errorCount") != len(errors)
            or value.get("warningCount") != len(warnings)):
        raise ValueError("Microsoft diagnostics truncated or malformed")
    # Older validators provide only 300-character summaries. Never compare
    # them if capped, because differing absolute path lengths can masquerade
    # as introduced diagnostics even when underlying messages are identical.
    if full is None and any(len(z) >= 300 for z in errors + warnings):
        raise ValueError("Microsoft diagnostic truncated; full evidence required")
    if full is not None and any(len(z) > 4200 for z in errors + warnings):
        raise ValueError("Microsoft full diagnostic exceeds safe bound")
    if ((value["status"] == "valid" and errors)
            or (value["status"] == "invalid" and not errors)):
        raise ValueError("Microsoft validation status/count contradiction")
    return {
        "status": value["status"],
        "errors": _normalize(errors, project),
        "warnings": _normalize(warnings, project),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def compare_authoring(
    baseline_report: str | Path,
    candidate_report: str | Path,
    declared_visual_files: list[str],
    *,
    runner: Runner | None = None,
    tool: str | None = None,
) -> dict[str, Any]:
    """Compare authorized visual delta + Microsoft diagnostics, never certify release.

    Baseline and candidate are distinct *same-named* .Report folders, each in
    its own project root. Only declared exact PBIR visual files may differ.
    A diagnostic PASS means 'no newly introduced CLI issues', *not* that the
    source or repaired report passed Microsoft's validation.
    """
    baseline = Path(baseline_report).resolve()
    candidate = Path(candidate_report).resolve()
    if (baseline == candidate or baseline in candidate.parents
            or candidate in baseline.parents or baseline.name != candidate.name
            or baseline.suffix.casefold() != ".report"):
        raise ValueError("require distinct, same-named non-overlapping .Report folders")
    if not declared_visual_files or len(set(declared_visual_files)) != len(declared_visual_files):
        raise ValueError("declare at least one unique visual file")
    authorized = set(declared_visual_files)
    for entry in authorized:
        path = Path(entry)
        parts = path.parts
        if (path.is_absolute() or ".." in parts or len(parts) != 6
                or parts[:2] != ("definition", "pages")
                or parts[3] != "visuals" or parts[-1] != "visual.json"):
            raise ValueError(f"not an exact PBIR visual file: {entry!r}")
    # The Microsoft CLI also examines the sibling .pbip project shortcut.
    # Equal .Report file inventories alone cannot prove equal validation inputs.
    before_pbip = baseline.with_suffix(".pbip")
    after_pbip = candidate.with_suffix(".pbip")
    if before_pbip.exists() != after_pbip.exists():
        raise ValueError("baseline/candidate PBIP shortcut presence differs")
    if (before_pbip.exists()
            and (before_pbip.is_symlink() or after_pbip.is_symlink()
                 or not before_pbip.is_file() or not after_pbip.is_file()
                 or sha256(before_pbip.read_bytes()).digest() !=
                 sha256(after_pbip.read_bytes()).digest())):
        raise ValueError("baseline/candidate PBIP shortcuts differ")
    before_files = _inventory(baseline)
    after_files = _inventory(candidate)
    if set(before_files) != set(after_files):
        raise ValueError("source and candidate file inventories differ")
    changed = {name for name in before_files if before_files[name] != after_files[name]}
    if changed != authorized:
        raise ValueError(f"unexpected/missing candidate mutation: {sorted(changed ^ authorized)}")
    if runner is None:
        observed = mscli.probe()
        if not observed.get("available") or not isinstance(observed.get("path"), str):
            raise ValueError("pinned Microsoft validator unavailable")
        active_runner = mscli.validate
        executable = observed["path"]
        version = observed.get("version")
    else:
        active_runner = runner
        executable = tool or "<injected-test-validator>"
        version = None

    import inspect
    # VQS's validator supports the pinned tool parameter; injected ports do too.
    # Never invoke an unpinned fallback when that parameter is absent.
    if "tool" not in inspect.signature(active_runner).parameters:
        raise ValueError("validator cannot accept a pinned executable")

    earlier = _diagnostics(active_runner(baseline, tool=executable), baseline.parent)
    later = _diagnostics(active_runner(candidate, tool=executable), candidate.parent)
    error_delta = Counter(later["errors"]) - Counter(earlier["errors"])
    warning_delta = Counter(later["warnings"]) - Counter(earlier["warnings"])
    cleared_errors = Counter(earlier["errors"]) - Counter(later["errors"])
    cleared_warnings = Counter(earlier["warnings"]) - Counter(later["warnings"])
    def expanded(entries: Counter[str]) -> list[str]:
        return sorted(entries.elements())

    new_errors = expanded(error_delta)
    new_warnings = expanded(warning_delta)
    return {
        "contract": "vqs.authoring-paired-diagnostics/1",
        "status": "compared",
        "comparison": ("introduced_diagnostics" if new_errors or new_warnings
                       else "no_new_diagnostics"),
        "release_verdict": "blocked",
        "release_reason": "paired Microsoft diagnostics and file identity are not "
                          "Desktop, semantic, interaction or release acceptance",
        "baseline_report_sha256": source_digest(baseline),
        "candidate_report_sha256": source_digest(candidate),
        "declared_changed_files": sorted(changed),
        "microsoft_tool": executable,
        "microsoft_version": version,
        "baseline": earlier,
        "candidate": later,
        "new_errors": new_errors,
        "new_warnings": new_warnings,
        "cleared_errors": expanded(cleared_errors),
        "cleared_warnings": expanded(cleared_warnings),
        "baseline_warnings_still_block_production": bool(later["warnings"]),
        "visual_runtime": "NOT_RUN",
        "semantic_answer_parity": "NOT_RUN",
    }
