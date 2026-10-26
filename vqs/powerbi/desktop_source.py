"""Fail-closed read-only identity attestation for an already-open Desktop PBIP.

An OS process command line alone proves which project was *launched*, not
which report is currently loaded. Require agreement from the Desktop Bridge
host registry, saved state, process age and current report file timestamps.
This is G0 source evidence, not visual G2 or interaction G4 approval.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA = "vqs.desktop-loaded-source-attestation/1"


def _same_path(left: str, right: Path) -> bool:
    if not isinstance(left, str) or not left.strip():
        return False
    try:
        lhs = os.path.normcase(str(Path(left).resolve(strict=True)))
        rhs = os.path.normcase(str(right.resolve(strict=True)))
        return lhs == rhs
    except (OSError, ValueError, RuntimeError):
        return False


def project_artifacts(project: Path) -> tuple[Path, Path]:
    """Resolve exactly one physical PBIP wrapper and its matching .Report."""
    project = Path(project)
    if not project.is_dir() or project.is_symlink():
        raise ValueError("PBIP project directory missing or symlinked")
    wrappers = list(project.glob("*.pbip"))
    if len(wrappers) != 1:
        raise ValueError("project must contain exactly one PBIP wrapper")
    wrapper = wrappers[0]
    report = project / (wrapper.stem + ".Report")
    if (not wrapper.is_file() or not report.is_dir()
            or wrapper.is_symlink() or report.is_symlink()):
        raise ValueError("matching local PBIP/Report pair missing or symlinked")
    return wrapper, report


def assess(
    project: Path, pid: int, process: Mapping[str, Any],
    preview: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure, externally testable verification; never infer missing evidence."""
    evidence: dict[str, Any] = {
        "schema": SCHEMA, "desktop_pid": pid, "loaded_file_attested": False,
        "status": "blocked", "reason": "missing source/host identity",
    }

    def block(reason: str) -> dict[str, Any]:
        evidence["reason"] = reason
        return evidence

    if type(pid) is not int or pid <= 0:
        return block("invalid Desktop process ID")
    if not isinstance(process, Mapping) or not isinstance(preview, Mapping):
        return block("missing OS process or Desktop preview registry evidence")
    try:
        wrapper, report = project_artifacts(project)
    except (OSError, ValueError) as exc:
        return block(str(exc))
    if process.get("pid") != pid or str(process.get("name", "")).lower() != "pbidesktop.exe":
        return block("Desktop PID missing or process executable mismatch")
    args = process.get("cmdline")
    if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
        return block("OS Desktop command line unavailable")
    opened = [a for a in args[1:] if a.lower().endswith(".pbip")]
    if len(opened) != 1 or not _same_path(opened[0], wrapper):
        return block("launched PBIP differs from the source project or is ambiguous")
    created = process.get("create_time")
    if type(created) not in (int, float) or created <= 0:
        return block("OS process creation timestamp missing")
    data = preview.get("data")
    if not isinstance(data, Mapping) or data.get("state") != "ready":
        return block("Desktop Bridge is not in ready state")
    details = data.get("details")
    if not isinstance(details, Mapping) or type(details.get("hasUnsavedChanges")) is not bool:
        return block("Desktop Bridge saved-state flag missing")
    if details["hasUnsavedChanges"]:
        return block("Desktop currently has unsaved changes")
    reports = data.get("reports")
    if not isinstance(reports, list) or len(reports) != 1:
        return block("Desktop Bridge report registry is missing or ambiguous")
    host = reports[0]
    if not isinstance(host, Mapping) or str(host.get("hostInstanceId")) != str(pid):
        return block("Desktop Bridge host PID differs from OS PID")
    if not _same_path(host.get("folder"), report):
        return block("Desktop Bridge loaded report folder differs from source")
    sources = [wrapper, *report.rglob("*")]
    if any(x.is_symlink() for x in sources):
        return block("PBIR source contains symlinks")
    source_files = [x for x in sources if x.is_file()]
    if not source_files:
        return block("PBIR source has no files")
    try:
        latest = max(x.stat().st_mtime for x in source_files)
    except OSError:
        return block("PBIR source modification times unreadable")
    if latest > created + 1:
        return block("PBIR source modified after the Desktop process started")
    evidence.update({
        "status": "pass", "loaded_file_attested": True,
        "reason": "OS launch path, sole Bridge registered report, PID, saved state "
                  "and source file age agree",
        "source_report": str(report.resolve()), "launch_wrapper": str(wrapper.resolve()),
        "desktop_create_time": created, "latest_source_mtime": latest,
    })
    return evidence


def collect(project: Path, pid: int) -> dict[str, Any]:
    """Collect real OS + Bridge metadata, never mutate or refresh the Desktop."""
    if os.name != "nt":
        return {"schema": SCHEMA, "status": "blocked",
                "desktop_pid": pid, "loaded_file_attested": False,
                "reason": "live Desktop identity requires Windows"}
    try:
        import psutil  # Optional Windows-host diagnostic; core stays dependency-free.
        active = psutil.Process(pid)
        process = {"pid": active.pid, "name": active.name(),
                   "cmdline": active.cmdline(), "create_time": active.create_time()}
    except (ImportError, OSError, ValueError) as exc:
        return {"schema": SCHEMA, "status": "blocked",
                "desktop_pid": pid, "loaded_file_attested": False,
                "reason": f"OS process inventory unavailable: {type(exc).__name__}"}
    # Refuse a different PBIP before contacting the Bridge at all. This
    # protects other open user instances and avoids reporting their status.
    try:
        wrapper, _ = project_artifacts(project)
    except (OSError, ValueError) as exc:
        return {"schema": SCHEMA, "status": "blocked", "desktop_pid": pid,
                "loaded_file_attested": False, "reason": str(exc)}
    cmdline = process.get("cmdline", [])
    launched = ([x for x in cmdline[1:] if isinstance(x, str)
                 and x.lower().endswith(".pbip")]
                if isinstance(cmdline, list) else [])
    if (process["name"].lower() != "pbidesktop.exe" or len(launched) != 1
            or not _same_path(launched[0], wrapper)):
        return {"schema": SCHEMA, "status": "blocked",
                "desktop_pid": pid, "loaded_file_attested": False,
                "reason": "OS process does not own exactly the requested PBIP"}
    cli = shutil.which("powerbi-report-author")
    if cli is None:
        return {"schema": SCHEMA, "status": "blocked",
                "desktop_pid": pid, "loaded_file_attested": False,
                "reason": "pinned Microsoft report authoring CLI unavailable"}
    try:
        result = subprocess.run(
            [cli, "preview", str(wrapper), "--host", "desktop", "--status"],
            capture_output=True, text=True, timeout=40, check=False,
        )
        if result.returncode:
            raise ValueError("Desktop preview status returned nonzero")
        preview = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"schema": SCHEMA, "status": "blocked",
                "desktop_pid": pid, "loaded_file_attested": False,
                "reason": "Desktop Bridge status unavailable or malformed"}
    return assess(project, pid, process, preview)
