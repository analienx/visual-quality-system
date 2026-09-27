"""Capability reporter: what is installed, never a setup step.

`vqs doctor` prints presence/version evidence for the external Power BI
tools VQS interoperates with. It installs, downloads, patches, and
modifies nothing; every check degrades to ``unknown`` instead of
failing. Exit code is always 0: this command reports, it does not gate.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any


def _version(executable: str, *args: str, timeout: int = 30) -> str | None:
    """Best-effort ``--version`` probe; None when anything goes wrong."""
    try:
        completed = subprocess.run(
            [executable, *args], capture_output=True, text=True,
            timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        try:  # Windows .CMD shims (npm globals) need a shell to launch.
            command = subprocess.list2cmdline([executable, *args])
            if re.search(r'[&|^<>%!`$;\r\n]', command):
                return None
            completed = subprocess.run(
                command, capture_output=True,
                text=True, timeout=timeout, check=False, shell=True)
        except (OSError, subprocess.SubprocessError):
            return None
    if completed.returncode != 0:
        return None
    line = (completed.stdout + completed.stderr).strip().splitlines()
    return line[0][:120] if line else None


def _tool(name: str, *version_args: str) -> dict[str, Any]:
    path = shutil.which(name)
    if path is None:
        return {"name": name, "status": "missing", "path": None,
                "version": None}
    version = _version(path, *version_args) if version_args else None
    return {"name": name, "status": "present", "path": path,
            "version": version if version is not None else "unknown"}


def _desktop_process() -> dict[str, Any]:
    """Count running PBIDesktop processes (Windows tasklist only)."""
    if os.name != "nt":
        return {"status": "unknown", "count": None,
                "reason": "process scan is Windows-only"}
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq PBIDesktop.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"status": "unknown", "count": None,
                "reason": "tasklist unavailable"}
    if completed.returncode != 0:
        return {"status": "unknown", "count": None,
                "reason": f"tasklist exited {completed.returncode}"}
    rows = [line for line in completed.stdout.splitlines()
            if "PBIDesktop.exe" in line]
    return {"status": "running" if rows else "not_running",
            "count": len(rows)}


def _adomd() -> dict[str, Any]:
    """Report ADOMD discoverability; informational only, never required.

    VQS itself has no ADOMD dependency. Only ``pbir model`` and
    ``pbir validate --fields`` need the client library, and pbir
    discovers it from DAX Studio / Tabular Editor installs or the
    ``PBIR_ADOMD_DIR`` override.
    """
    override = os.environ.get("PBIR_ADOMD_DIR")
    bases = [os.environ.get("ProgramFiles", ""),
             os.environ.get("ProgramFiles(x86)", "")]
    candidates = ["DAX Studio", "Tabular Editor 3",
                  os.path.join("Microsoft Power BI Desktop", "bin")]
    found = [os.path.join(base, leaf) for base in bases for leaf in candidates
             if base and os.path.isfile(
                 os.path.join(base, leaf,
                              "Microsoft.AnalysisServices.AdomdClient.dll"))]
    return {"status": "informational", "required_by_vqs": False,
            "pbir_adomd_dir": override,
            "known_installs": [path for path in found]}


def report() -> dict[str, Any]:
    """Collect every capability check into one JSON-serializable report."""
    pbir = _tool("pbir", "--version")
    bridge = _tool("powerbi-desktop", "--version")
    mcp = _tool("powerbi-modeling-mcp")
    mcp["note"] = ("Presence only: live model connectivity is proven "
                   "per run via connection_operations ListLocalInstances.")
    return {"status": "ok",
            "checks": {"pbir": pbir, "desktop_bridge": bridge,
                       "modeling_mcp": mcp,
                       "desktop_process": _desktop_process(),
                       "adomd": _adomd()}}
