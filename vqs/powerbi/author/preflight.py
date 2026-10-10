"""Read-only Microsoft authoring preflight, before any report candidate is created.

The official skill is executable guidance, NOT an alternative mutation engine.
The approved source-worktree skill and actual CLI must both match their lock
when Microsoft validation is selected. Missing/invalid capability blocks
rather than falling back to a different validator mid-repair.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import adapter

PREFLIGHT_VERSION = "vqs.authoring-preflight/1"


def _approved_skill() -> tuple[dict[str, Any], dict[str, Any]]:
    """Use the pinned verifier bundled inside VQS, never external Python."""
    from . import skill_attest

    return skill_attest.check()


def check(
    policy: str, *,
    prober: Callable[[], dict[str, Any]] | None = None,
    approved_checker: Callable[[], tuple[dict[str, Any], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe, evidence-ready authoring capability decision.

    Direct mode is an explicit static-only authorization, not Microsoft
    validity. Legacy auto without CLI retains an explicitly marked native-only
    path for backwards compatibility; neither supports Desktop/release claims.
    """
    result: dict[str, Any] = {
        "contract": PREFLIGHT_VERSION,
        "policy": policy,
        "status": "blocked",
        "validation_provider": "unselected",
        "mutation_engine": "vqs_typed",
        "assurance": "none",
    }
    if policy not in adapter.POLICIES:
        result["reason"] = f"unknown authoring policy: {policy!r}"
        return result
    try:
        probe = (adapter.probe if prober is None else prober)()
        if not isinstance(probe, dict):
            raise TypeError("CLI probe was not an object")
        selection = adapter.select(policy, probe)
    except (OSError, ValueError, TypeError) as exc:
        result["reason"] = f"authoring selection unavailable: {exc}"
        return result
    result["validation_provider"] = selection["backend"]
    result["probe"] = probe
    if selection["backend"] == "direct":
        result.update(
            status="pass",
            assurance="native_static_only",
            reason=("explicit native validation only" if policy == "direct"
                    else "legacy auto: Microsoft tool unavailable; no Microsoft validation"),
        )
        return result
    try:
        skill, cli = (approved_checker or _approved_skill)()
        if not isinstance(skill, dict) or not isinstance(cli, dict):
            raise TypeError("approved checker must return skill and CLI records")
    except Exception as exc:  # noqa: BLE001 - fail-closed external port
        result["reason"] = f"approved toolchain check crashed: {type(exc).__name__}: {exc}"
        return result
    result["skill"] = skill
    result["cli"] = cli
    if skill.get("status") != "pass" or cli.get("status") != "pass":
        result["reason"] = "Microsoft authoring requires approved skill and pinned CLI"
        return result
    if (not probe.get("available")
            or probe.get("version") != cli.get("version")
            or Path(str(probe.get("path") or "")).resolve()
            != Path(str(cli.get("path") or "")).resolve()):
        result["reason"] = "Microsoft CLI probe differs from approved executable/version"
        return result
    if (not isinstance(skill.get("snapshot"), dict)
            or not isinstance(skill["snapshot"].get("sha256"), str)
            or len(skill["snapshot"]["sha256"]) != 64):
        result["reason"] = "approved Microsoft skill has no full snapshot digest"
        return result
    result.update(status="pass", assurance="microsoft_structural_only",
                  reason="approved Microsoft skill and CLI attested before mutation")
    try:
        json.dumps(result, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        result.update(status="blocked", reason="unsealable toolchain attestation")
    return result
