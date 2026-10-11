"""Versioned report-writing assurance policy. Portable is not production."""
from __future__ import annotations

from typing import Any

CONTRACT = "vqs.writer-policy/1"
LEVELS = ("portable", "production")


def authorize(level: str, preflight: dict[str, Any], *,
              allow_warnings: bool = False) -> dict[str, Any]:
    """Require real Microsoft validation for explicitly production-scoped work.

    This guard runs before any repair run, staging directory or candidate.
    Portable mode exists for offline fixtures and visibly lacks production
    authority. Blanket warning approval is never production authority.
    """
    result = {"contract": CONTRACT, "requested": level,
              "status": "blocked", "reason": ""}
    if level not in LEVELS:
        result["reason"] = "authoring_assurance must be portable or production"
    elif not isinstance(allow_warnings, bool):
        result["reason"] = "authoring_allow_warnings must be boolean"
    elif preflight.get("status") != "pass":
        result["reason"] = "approved authoring preflight unavailable"
    elif level == "production" and (
            preflight.get("validation_provider") != "microsoft"
            or preflight.get("assurance") != "microsoft_structural_only"):
        result["reason"] = "production repair requires approved Microsoft structural validation"
    elif level == "production" and allow_warnings:
        result["reason"] = (
            "blanket authoring warning waiver forbidden for production; "
            "per-diagnostic reviewed exceptions are not yet supported")
    else:
        result["status"] = "pass"
        result["reason"] = (
            "production requires Microsoft validation and blocks all warnings"
            if level == "production"
            else "portable-only validation: no production or release approval")
    return result
