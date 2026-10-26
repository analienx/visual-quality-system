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


def local_semantic_model(project: Path, report: Path, wrapper: Path) -> tuple[Path | None, str]:
    """Follow the *declared* PBIR byPath model, never guess an unrelated model."""
    reference = report / "definition.pbir"
    if reference.is_symlink():
        raise ValueError("report dataset reference is symlinked")
    if not reference.is_file():
        legacy = project / (wrapper.stem + ".SemanticModel")
        return (legacy if legacy.is_dir() else None), "legacy_unverified_reference"
    try:
        info = json.loads(reference.read_text(encoding="utf-8-sig"))
        dataset = info["datasetReference"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("report dataset reference unreadable") from exc
    if not isinstance(dataset, dict):
        raise TypeError("report dataset reference is not an object")
    if "byConnection" in dataset and "byPath" not in dataset:
        return None, "byConnection_not_locally_verified"
    path = dataset.get("byPath")
    if not isinstance(path, dict) or not isinstance(path.get("path"), str):
        raise TypeError("local dataset reference missing byPath")
    value = path["path"].replace("\\", "/")
    if not value.strip() or value.startswith("/") or ":" in value:
        raise ValueError("invalid or absolute byPath dataset reference")
    target = report.joinpath(*value.split("/"))
    if target.is_symlink():
        raise ValueError("dataset byPath is symlinked")
    try:
        resolved = target.resolve(strict=True)
        parent = project.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("local byPath semantic model missing") from exc
    if resolved.parent != parent or not resolved.is_dir() or not resolved.name.endswith(".SemanticModel"):
        raise ValueError("dataset byPath escapes project or is not a semantic-model directory")
    return resolved, "byPath_source_checked"


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
    except (OSError, ValueError, TypeError) as exc:
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
    # Bind the semantic *definition*, not the volatile ABF/cache generated
    # when Desktop refreshes the model. Only byPath/local models are covered.
    try:
        model, model_reference = local_semantic_model(wrapper.parent, report, wrapper)
    except (OSError, ValueError, TypeError) as exc:
        return block(str(exc))
    sources = [wrapper, *report.rglob("*")]
    has_local_model = model is not None
    if has_local_model:
        if model.is_symlink():
            return block("local semantic model is symlinked")
        sources.extend(model.rglob("*"))
    if any(x.is_symlink() for x in sources):
        return block("PBIR or semantic source contains symlinks")
    source_files = []
    for x in sources:
        if not x.is_file():
            continue
        if has_local_model and x.is_relative_to(model):
            relative = x.relative_to(model)
            if ".pbi" in relative.parts or relative.name == ".platform":
                continue
        source_files.append(x)
    if not source_files:
        return block("PBIR source has no files")
    try:
        latest = max(x.stat().st_mtime for x in source_files)
    except OSError:
        return block("PBIR/model source modification times unreadable")
    if latest > created + 1:
        return block("PBIR/model source modified after the Desktop process started")
    evidence.update({
        "status": "pass", "loaded_file_attested": True,
        "reason": "OS launch path, sole Bridge registered report, PID, saved state "
                  "and source file age agree",
        "source_report": str(report.resolve()), "launch_wrapper": str(wrapper.resolve()),
        "desktop_create_time": created, "latest_source_mtime": latest,
        "local_model_definition_checked": has_local_model,
        "local_model_reference": model_reference,
        "source_file_count": len(source_files),
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
    except (OSError, ValueError, TypeError) as exc:
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
