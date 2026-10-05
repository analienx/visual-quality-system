"""Subprocess port for Microsoft's powerbi-report-author CLI (R6-E07).

Only two surfaces are executed: the presence probe (documented
``--help``; ``--version`` is undocumented for this CLI) and
``validate <path>`` on a candidate report directory. Nothing else is
invoked — no preview/scaffold/pack, no Desktop/service contact.

Every function is total: nothing raises, and every outcome —
including timeouts and unparseable output — is recorded for the
caller to adjudicate. Diagnostics parsing is best-effort over the
retained raw tail; the exit status is the verdict signal.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

TOOL_NAME = "powerbi-report-author"
PROBE_ARGS = ("--help",)
PROBE_TIMEOUT = 60
RAW_TAIL_LIMIT = 8192
DIAGNOSTIC_LINE_LIMIT = 50


def _run(argv: list[str], timeout: int) -> dict[str, Any]:
    """Shim-tolerant subprocess run; never raises.

    Returns returncode (None on timeout/launch failure), captured
    output, and a note. Windows .CMD shims (npm globals) need a
    shell to launch; metacharacter-bearing commands refuse.
    """
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "",
                "note": "timeout"}
    except (OSError, subprocess.SubprocessError):
        try:
            command = subprocess.list2cmdline(argv)
            if re.search(r'[&|^<>%!`$;\r\n]', command):
                return {"returncode": None, "stdout": "", "stderr": "",
                        "note": "launch refused: metacharacters"}
            completed = subprocess.run(
                command, capture_output=True, text=True,
                timeout=timeout, check=False, shell=True)
        except subprocess.TimeoutExpired:
            return {"returncode": None, "stdout": "", "stderr": "",
                    "note": "timeout"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"returncode": None, "stdout": "", "stderr": "",
                    "note": f"launch failed: {exc}"}
    return {"returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "", "note": None}


def probe(tool: str = TOOL_NAME,
          timeout: int = PROBE_TIMEOUT) -> dict[str, Any]:
    """Presence/version probe; never raises.

    Available means on-PATH plus a zero-exit documented ``--help``.
    The version is a best-effort first line, else ``"unknown"``.
    """
    try:
        path = shutil.which(tool)
    except Exception:  # noqa: BLE001 - lookup crash means missing
        path = None
    record: dict[str, Any] = {
        "tool": tool, "available": False, "path": path, "version": None,
        "probe_command": [tool, *PROBE_ARGS], "returncode": None,
        "note": None}
    if path is None:
        record["note"] = "not on PATH"
        return record
    try:
        result = _run([path, *PROBE_ARGS], timeout)
    except Exception as exc:  # noqa: BLE001 - probe crash degrades
        record["note"] = f"probe failed: {exc}"
        return record
    record["returncode"] = result["returncode"]
    if result["returncode"] != 0:
        record["note"] = (result["note"]
                          or f"--help exited {result['returncode']}")
        return record
    combined = result["stdout"] + "\n" + result["stderr"]
    first = next((line.strip() for line in combined.splitlines()
                  if line.strip()), "")
    record["available"] = True
    record["version"] = first[:120] if first else "unknown"
    return record


def _diagnostics(combined: str, marker: str) -> list[str]:
    return [line[:300] for line in
            (entry.strip() for entry in combined.splitlines())
            if line and marker in line.lower()][:DIAGNOSTIC_LINE_LIMIT]


def validate(report_dir: str | Path, timeout: int = 300,
             tool: str = TOOL_NAME) -> dict[str, Any]:
    """Run ``validate <path>`` on a candidate report dir; never raises.

    Status is valid (exit 0), invalid (the tool rejected the
    candidate), error (launch/output failure), timeout, or missing.
    Errors/warnings are best-effort marker scans over the retained
    raw tail; callers adjudicate warnings by explicit policy.
    """
    record: dict[str, Any] = {
        "tool": tool, "command": [tool, "validate", str(report_dir)],
        "status": "error", "returncode": None, "errors": [],
        "warnings": [], "raw_tail": "", "note": None}
    try:
        path = shutil.which(tool)
    except Exception:  # noqa: BLE001 - lookup crash means missing
        path = None
    if path is None:
        record.update(status="missing", note="not on PATH")
        return record
    try:
        result = _run([path, "validate", str(report_dir)], timeout)
    except Exception as exc:  # noqa: BLE001 - launch crash degrades
        record["note"] = f"validation failed: {exc}"
        return record
    record["returncode"] = result["returncode"]
    combined = result["stdout"]
    if result["stderr"]:
        combined += ("\n" if combined else "") + result["stderr"]
    record["raw_tail"] = combined[-RAW_TAIL_LIMIT:]
    if result["returncode"] is None:
        record["status"] = ("timeout" if result["note"] == "timeout"
                            else "error")
        record["note"] = result["note"]
        return record
    record["errors"] = _diagnostics(combined, "error")
    record["warnings"] = _diagnostics(combined, "warning")
    if result["returncode"] != 0:
        record["status"] = "invalid"
        record["note"] = f"validate exited {result['returncode']}"
    else:
        record["status"] = "valid"
    return record
