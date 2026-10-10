"""Microsoft powerbi-report-author subprocess port; structured JSON contract.

The public-preview CLI emits a JSON envelope with data.result or error. Never
infer success or warnings from substring scans over minified JSON. Every
malformed/mismatched response blocks; only candidate files are validated.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

TOOL_NAME = "powerbi-report-author"
PACKAGE_NAME = "@microsoft/powerbi-report-authoring-cli"
PROBE_ARGS = ("--version",)
PROBE_TIMEOUT = 60
RAW_TAIL_LIMIT = 8192
DIAGNOSTIC_LINE_LIMIT = 50


def _run(argv: list[str], timeout: int) -> dict[str, Any]:
    """Return command output; Windows npm CMD shims need guarded fallback."""
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "", "note": "timeout"}
    except (OSError, subprocess.SubprocessError):
        try:
            command = subprocess.list2cmdline(argv)
            if re.search(r'[&|^<>%!$;\r\n]', command):
                return {"returncode": None, "stdout": "", "stderr": "",
                        "note": "launch refused: metacharacters"}
            completed = subprocess.run(
                command, capture_output=True, text=True,
                timeout=timeout, check=False, shell=True)
        except subprocess.TimeoutExpired:
            return {"returncode": None, "stdout": "", "stderr": "", "note": "timeout"}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"returncode": None, "stdout": "", "stderr": "",
                    "note": f"launch failed: {exc}"}
    return {"returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "", "note": None}


def probe(tool: str = TOOL_NAME, timeout: int = PROBE_TIMEOUT) -> dict[str, Any]:
    """Record real semantic version, not the first --help line."""
    try:
        path = shutil.which(tool)
    except Exception:  # noqa: BLE001
        path = None
    record: dict[str, Any] = {
        "tool": tool, "package": PACKAGE_NAME, "available": False,
        "path": path, "version": None,
        "probe_command": [tool, *PROBE_ARGS],
        "returncode": None, "note": None}
    if path is None:
        record["note"] = "not on PATH"
        return record
    result = _run([path, *PROBE_ARGS], timeout)
    record["returncode"] = result["returncode"]
    version = result["stdout"].strip()
    if result["returncode"] != 0 or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        record["note"] = result["note"] or "version probe failed or returned non-semver"
        return record
    record["available"] = True
    record["version"] = version
    return record


def _structured(stdout: str, returncode: int) -> dict[str, Any]:
    """Interpret documented JSON validation envelope and reconcile exit code."""
    try:
        obj = json.loads(stdout)
    except (ValueError, TypeError):
        return {"status": "error", "note": "CLI stdout is not a JSON envelope",
                "errors": [], "warnings": [], "result": None}
    if not isinstance(obj, dict):
        return {"status": "error", "note": "CLI envelope is not an object",
                "errors": [], "warnings": [], "result": None}
    if "error" in obj:
        error = obj["error"]
        return {"status": "error", "note": (
            error.get("message", "CLI error envelope")
            if isinstance(error, dict) else "malformed CLI error envelope"),
            "errors": [], "warnings": [], "result": None}
    data = obj.get("data")
    if not isinstance(data, dict):
        return {"status": "error", "note": "CLI envelope missing data object",
                "errors": [], "warnings": [], "result": None}
    result = data.get("result")
    errors_count = data.get("errorCount")
    warnings_count = data.get("warningCount")
    if (result not in {"succeeded", "succeededWithWarnings", "failed"}
            or type(errors_count) is not int or errors_count < 0
            or type(warnings_count) is not int or warnings_count < 0):
        return {"status": "error", "note": "invalid result/errorCount/warningCount",
                "errors": [], "warnings": [], "result": result}
    diagnostics = data.get("diagnostics", {})
    if not isinstance(diagnostics, dict):
        return {"status": "error", "note": "diagnostics is not an object",
                "errors": [], "warnings": [], "result": result}
    errors: list[str] = []
    warnings: list[str] = []
    seen_errors = 0
    seen_warnings = 0
    for code, group in diagnostics.items():
        if not isinstance(group, dict) or group.get("severity") not in {"error", "warning"}:
            return {"status": "error", "note": "malformed diagnostics group",
                    "errors": [], "warnings": [], "result": result}
        items = group.get("items")
        if not isinstance(items, list):
            return {"status": "error", "note": "malformed diagnostics items",
                    "errors": [], "warnings": [], "result": result}
        target = errors if group["severity"] == "error" else warnings
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("message"), str):
                return {"status": "error", "note": "malformed diagnostic item",
                        "errors": [], "warnings": [], "result": result}
            target.append(f"{code}: {item['message']}"[:300])
            if group["severity"] == "error":
                seen_errors += 1
            else:
                seen_warnings += 1
    if (seen_errors != errors_count or seen_warnings != warnings_count
            or (result == "succeeded" and (errors_count or warnings_count))
            or (result == "succeededWithWarnings" and (not warnings_count or errors_count))
            or (result == "failed" and not errors_count)
            or ((returncode == 0) != (result != "failed"))):
        return {"status": "error", "note": "CLI result/count/exit mismatch",
                "errors": errors[:DIAGNOSTIC_LINE_LIMIT],
                "warnings": warnings[:DIAGNOSTIC_LINE_LIMIT], "result": result}
    return {"status": "invalid" if result == "failed" else "valid",
            "note": None, "errors": errors[:DIAGNOSTIC_LINE_LIMIT],
            "warnings": warnings[:DIAGNOSTIC_LINE_LIMIT], "result": result,
            "errorCount": errors_count, "warningCount": warnings_count}


def validate(report_dir: str | Path, timeout: int = 300,
             tool: str = TOOL_NAME) -> dict[str, Any]:
    """Run validate on a candidate and keep the structured result and raw tail."""
    record: dict[str, Any] = {
        "tool": tool, "package": PACKAGE_NAME,
        "command": [tool, "validate", str(report_dir)],
        "status": "error", "returncode": None, "errors": [],
        "warnings": [], "raw_tail": "", "note": None}
    try:
        path = shutil.which(tool)
    except Exception:  # noqa: BLE001
        path = None
    if path is None:
        record.update(status="missing", note="not on PATH")
        return record
    result = _run([path, "validate", str(report_dir)], timeout)
    record["returncode"] = result["returncode"]
    combined = result["stdout"] + ("\n" + result["stderr"] if result["stderr"] else "")
    record["raw_tail"] = combined[-RAW_TAIL_LIMIT:]
    if result["returncode"] is None:
        record.update(status="timeout" if result["note"] == "timeout" else "error",
                      note=result["note"])
        return record
    record.update(_structured(result["stdout"], result["returncode"]))
    return record
