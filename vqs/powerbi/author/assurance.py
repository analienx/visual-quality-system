"""Versioned truth contract for typed mutations and validation assurances.

PBIR source mutation is always done by the VQS typed repair engine.
A *validator* only inspects the resulting candidate, never writes it.
Structural success is not live Desktop, data, visual or release success.
"""
from __future__ import annotations

from typing import Any

CONTRACT = "vqs.authoring-assurance/1"
ASSURANCE = ("microsoft_structural_only", "native_static_only")
PROVIDERS = {"microsoft": "microsoft_cli", "direct": "native_static"}


def compose(preflight: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Create truthful, JSON-safe after-mutation evidence; never upgrade scope."""
    selected = preflight.get("validation_provider")
    backend = result.get("backend")
    record = result.get("record")
    validation = record.get("validation") if isinstance(record, dict) else None
    structural = "not_run"
    verdict = result.get("verdict", "blocked")
    if selected not in PROVIDERS or backend != selected:
        verdict = "blocked"
    elif selected == "microsoft":
        status = validation.get("status") if isinstance(validation, dict) else None
        if verdict == "pass" and status == "valid":
            structural = "pass"
        elif status == "invalid":
            structural = "fail"
        else:
            structural = "blocked"
    return {
        "contract": CONTRACT,
        "mutation_engine": "vqs_typed",
        "validation_provider": PROVIDERS.get(selected, "unverified"),
        "preflight_assurance": preflight.get("assurance", "none"),
        "execution_verdict": verdict,
        "structural_validation": structural,
        "rendered_desktop": "not_run",
        "data_semantics": "not_run",
        "independent_visual_review": "not_run",
        "release_acceptance": "not_run",
    }
