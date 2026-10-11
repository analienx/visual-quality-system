"""Read-only report and model identity checks around Microsoft validation."""
from __future__ import annotations

from typing import Any


def snapshot(original: str, candidate: str,
             original_sha: str | None, candidate_sha: str | None,
             model_pin: dict[str, Any] | None) -> dict[str, Any]:
    """Require the exact typed-applied report and model bytes, never mutating.

    The same check is made before launching a validator and immediately
    afterwards. A concurrent saver can no longer turn an old CLI verdict
    into an approval of an edited candidate.
    """
    from ...pipeline import _sealed_model_problems
    from ...repair.execute import tree_digest

    record: dict[str, Any] = {
        "contract": "vqs.validation-snapshot/1",
        "status": "blocked", "original_sha256": None,
        "candidate_sha256": None, "problems": [],
    }
    try:
        record["original_sha256"] = tree_digest(original)
        record["candidate_sha256"] = tree_digest(candidate)
        if record["original_sha256"] != original_sha:
            record["problems"].append("original report changed since typed apply")
        if record["candidate_sha256"] != candidate_sha:
            record["problems"].append("candidate report changed since typed apply")
        record["problems"].extend(
            str(problem.get("rule", "model identity unavailable"))
            for problem in _sealed_model_problems(model_pin, original, candidate))
    except Exception as exc:  # noqa: BLE001 - filesystem/model failures block
        record["problems"].append(
            f"validation snapshot unavailable: {type(exc).__name__}: {exc}")
    if not record["problems"]:
        record["status"] = "pass"
    return record
