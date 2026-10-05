"""Backend selection + Microsoft validation adjudication (R6-E07).

Policies: ``auto`` (Microsoft when probed available, else the direct
writer — the selection is recorded, so never silent), ``microsoft``
(explicit; any tool/validation failure blocks or fails, never falls
back), ``direct`` (explicit recorded fallback to the typed isolated
candidate-file writer). ``run_backend`` never raises: runner crashes
are recorded as blocked evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .mscli import TOOL_NAME, probe, validate

POLICIES = ("auto", "microsoft", "direct")

LIMITS = ("Microsoft schema validation only: a valid candidate is "
          "structurally sound PBIR, never Desktop fidelity, render "
          "approval, or data correctness.")

Runner = Callable[..., dict[str, Any]]
Prober = Callable[..., dict[str, Any]]


def select(policy: str, probe_result: dict[str, Any]) -> dict[str, str]:
    """Choose the backend for a validated policy; fail fast otherwise."""
    if policy not in POLICIES:
        raise ValueError(f"unknown authoring policy: {policy!r}")
    if policy == "direct":
        return {"backend": "direct", "policy": policy,
                "reason": "explicit direct fallback selected"}
    if policy == "microsoft":
        return {"backend": "microsoft", "policy": policy,
                "reason": "explicit Microsoft validation selected"}
    if probe_result.get("available") is True:
        return {"backend": "microsoft", "policy": policy,
                "reason": "tool probed available"}
    return {"backend": "direct", "policy": policy,
            "reason": "tool unavailable; explicit recorded fallback"}


def direct_record(policy: str, probe_result: dict[str, Any]) -> dict[str, Any]:
    """Authoring record for the direct typed-writer backend."""
    return {"backend": "direct", "policy": policy,
            "reason": ("explicit direct fallback selected"
                       if policy == "direct"
                       else "tool unavailable; explicit recorded fallback"),
            "tool": None, "version": None,
            "probe": dict(probe_result), "commands": [],
            "validation": None, "limits": LIMITS}


def _microsoft_record(probe_result: dict[str, Any], policy: str,
                      validation: dict[str, Any]) -> dict[str, Any]:
    return {"backend": "microsoft", "policy": policy,
            "reason": "explicit Microsoft validation selected"
                      if policy == "microsoft" else "tool probed available",
            "tool": TOOL_NAME,
            "version": probe_result.get("version"),
            "probe": dict(probe_result),
            "commands": [validation.get("command", [])],
            "validation": dict(validation), "limits": LIMITS}


def run_backend(candidate: str | Path, *, policy: str = "auto",
                timeout: int = 300, allow_warnings: bool = False,
                prober: Prober = probe,
                runner: Runner = validate) -> dict[str, Any]:
    """Select the backend and validate the candidate; never raises.

    Returns backend/policy/verdict/reason/record. Microsoft verdicts:
    valid maps to pass (warnings block unless explicitly allowed and
    are always recorded verbatim); invalid maps to fail; missing,
    timeout, error, or runner crashes map to blocked. A Microsoft
    failure never silently falls back to direct.
    """
    try:
        probe_result = prober()
    except Exception as exc:
        probe_result = {"tool": TOOL_NAME, "available": False,
                        "path": None, "version": None,
                        "note": f"probe raised: {exc}"}
    try:
        selection = select(policy, probe_result)
    except ValueError as exc:
        record = direct_record("auto", probe_result)
        record["reason"] = str(exc)
        return {"backend": "direct", "policy": policy,
                "verdict": "blocked", "reason": str(exc),
                "record": record}
    if selection["backend"] == "direct":
        record = direct_record(policy, probe_result)
        return {"backend": "direct", "policy": policy,
                "verdict": "pass", "reason": record["reason"],
                "record": record}
    try:
        validation = runner(candidate, timeout=timeout)
    except Exception as exc:
        validation = {"tool": TOOL_NAME, "command": [TOOL_NAME],
                      "status": "error", "returncode": None,
                      "errors": [], "warnings": [], "raw_tail": "",
                      "note": f"runner raised: {exc}"}
    if not isinstance(validation, dict):
        validation = {"tool": TOOL_NAME, "command": [TOOL_NAME],
                      "status": "error", "returncode": None,
                      "errors": [], "warnings": [], "raw_tail": "",
                      "note": "runner returned malformed output"}
    record = _microsoft_record(probe_result, policy, validation)
    status = validation.get("status")
    warnings = validation.get("warnings") or []
    if status == "valid" and (not warnings or allow_warnings):
        return {"backend": "microsoft", "policy": policy,
                "verdict": "pass",
                "reason": ("Microsoft validation passed"
                           + (" with explicitly allowed warnings"
                              if warnings else "")),
                "record": record}
    if status == "valid":
        return {"backend": "microsoft", "policy": policy,
                "verdict": "blocked",
                "reason": "authoring_warnings_require_review",
                "record": record}
    if status == "invalid":
        return {"backend": "microsoft", "policy": policy,
                "verdict": "fail",
                "reason": ("Microsoft validation rejected the candidate: "
                           + (validation.get("note") or "see validation")),
                "record": record}
    detail = validation.get("note") or f"status {status}"
    return {"backend": "microsoft", "policy": policy,
            "verdict": "blocked",
            "reason": f"Microsoft validation unavailable: {detail}",
            "record": record}
