"""Proof of an actual Windows native Save, without overriding read-only attestation.

A save operation is allowed ONLY on an explicit disposable PBIP within scratch.
The producer never changes PBIR/semantic files directly or touches other windows.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from vqs.powerbi.desktop_native_provenance import (
    SCHEMA,
    metadata_source,
    snapshot,
    verify,
)
from vqs.powerbi.desktop_source import (
    _same_path,
    local_semantic_model,
    project_artifacts,
)


def _bridge_state(project: Path, pid: int) -> bool:
    cli = shutil.which("powerbi-report-author")
    if cli is None:
        raise ValueError("Microsoft authoring CLI is unavailable")
    wrapper, report = project_artifacts(project)
    result = subprocess.run(
        [cli, "preview", str(wrapper), "--host", "desktop", "--status"],
        capture_output=True, text=True, timeout=45, check=False,
    )
    if result.returncode:
        raise ValueError("Desktop Bridge status failed")
    data = json.loads(result.stdout)["data"]
    reports = data.get("reports")
    if (data.get("state") != "ready" or not isinstance(reports, list)
            or len(reports) != 1 or str(reports[0].get("hostInstanceId")) != str(pid)
            or not _same_path(reports[0].get("folder"), report)):
        raise ValueError("Desktop Bridge registry has wrong PID/report or is not ready")
    dirty = data.get("details", {}).get("hasUnsavedChanges")
    if type(dirty) is not bool:
        raise ValueError("Desktop has no trustworthy saved-state flag")
    return dirty


def _os_process(project: Path, pid: int) -> float:
    if os.name != "nt":
        raise ValueError("native save requires Windows")
    if type(pid) is not int or pid <= 0:
        raise ValueError("invalid Desktop PID")
    try:
        import psutil  # type: ignore[import-untyped]
        proc = psutil.Process(pid)
        command = proc.cmdline()
        if (proc.name().lower() != "pbidesktop.exe"
                or len([c for c in command[1:] if c.lower().endswith(".pbip")]) != 1
                or not _same_path(command[-1], project_artifacts(project)[0])):
            raise ValueError("OS process does not own exactly this PBIP")
        return proc.create_time()
    except (ImportError, OSError) as exc:
        raise ValueError("OS Desktop process unavailable") from exc


def save_and_witness(
    project: Path, pid: int, *, disposable_root: Path,
    invoke: Any = None,
    bridge: Any = None,
) -> dict[str, Any]:
    """Execute once on a disposable candidate; return verified source receipt.

    Optional callbacks are narrowly intended for adversarial unit-test fakes.
    """
    project = project.resolve(strict=True)
    private = disposable_root.resolve(strict=True)
    if project == private or not project.is_relative_to(private):
        raise ValueError("native Save requires explicit disposable child directory")
    wrapper, report = project_artifacts(project)
    model, reference = local_semantic_model(project, report, wrapper)
    if reference != "byPath_source_checked" or model is None:
        raise ValueError("native Save requires local byPath semantic source")
    created = _os_process(project, pid)
    read_bridge = bridge if bridge is not None else _bridge_state
    if read_bridge(project, pid) is not True:
        raise ValueError("expected one ready unsaved disposable Desktop candidate")
    pre = snapshot(project)
    original_metadata = metadata_source(project)
    if any(float(entry["mtime_ns"]) / 1e9 > created + 1 for entry in pre.values()):
        raise ValueError("source already changed after launch before native Save")
    ps_script = (Path(__file__).resolve().parents[2]
                 / "scripts" / "windows" / "desktop_native_save_uia.ps1")
    if not ps_script.is_file():
        raise ValueError("native UIA save adapter missing")
    if invoke is None:
        shell = shutil.which("powershell.exe")
        if not shell:
            raise ValueError("native Windows UIA command unavailable")
        operation = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-File", str(ps_script),
             "-DesktopProcessId", str(pid), "-ExpectedPbip", str(wrapper),
             "-DisposableRoot", str(private)],
            capture_output=True, text=True, check=False, timeout=40,
            encoding="utf-8-sig",
        )
        if operation.returncode:
            raise ValueError("native Save button refused or failed: "
                             + operation.stderr[-500:])
        control = json.loads(operation.stdout)
    else:
        control = invoke(pid, str(wrapper), str(private))
    if not isinstance(control, dict):
        raise TypeError("no native UIA Save control receipt")
    if control.get("schema") != "vqs.native-desktop-save-ui-control/1":
        raise ValueError("UIA control proof schema missing")
    start = control.get("action_epoch")
    if type(start) not in (int, float):
        raise ValueError("native Save action time invalid")
    for _ in range(20):
        # Native Save briefly drops Desktop Bridge readiness during a model/
        # report flush. Retry status reads only: NEVER invoke Save twice.
        try:
            saved_now = read_bridge(project, pid) is False
        except (OSError, ValueError, KeyError, TypeError):
            saved_now = False
        if saved_now:
            break
        time.sleep(.75)
    else:
        raise ValueError("Desktop never confirmed saved state after native Save")
    end = time.time()
    time.sleep(.6)
    after = snapshot(project)
    metadata_after = metadata_source(project)
    if snapshot(project) != after or read_bridge(project, pid) is not False:
        raise ValueError("source/Bridge not stable after native Save")
    if _os_process(project, pid) != created:
        raise ValueError("Desktop PID recycled during native Save")
    witness: dict[str, Any] = {
        "schema": SCHEMA,
        "desktop_pid": pid,
        "pbip": str(wrapper.resolve()),
        "report": str(report.resolve()),
        "model": str(model.resolve()),
        "process_created": created,
        "native_save_control": {
            "method": control.get("method"),
            "automation_id": control.get("automation_id"),
            "button": control.get("button"),
            "window": control.get("window"),
            "pid": control.get("pid"),
        },
        "save_start_epoch": start,
        "saved_observed_epoch": end,
        "unsaved_before": True,
        "unsaved_after": False,
        "manifest_before": pre,
        "manifest_after": after,
        "metadata_before": original_metadata,
        "metadata_after": metadata_after,
        "independent_g2_g4_g6": "blocked",
    }
    passed, reason, detail = verify(project, pid, created, witness)
    witness["native_saved_source_verified"] = passed
    witness["verification_reason"] = reason
    witness["verification_details"] = detail
    return witness
