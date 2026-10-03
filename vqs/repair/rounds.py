"""Bounded repair rounds (WP-09, §E): at most three attempts per cluster.

Each round applies one plan variant to a fresh candidate and asks the
caller's verifier for a verdict plus a defect fingerprint. Unchanged
fingerprints, failed invariants, and verifier errors stop the cluster
immediately; anything half-applied is removed, never kept. Rounds retry
with the next caller-supplied variant — never by inventing edits.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable

from .execute import apply_plan

MAX_ROUNDS = 3


def run_rounds(plan_variants: list[dict], original: str,
               candidate_base: str,
               verify: Callable[[str], dict],
               max_rounds: int = MAX_ROUNDS) -> dict:
    """Try plan variants in order; return the first verified repair."""
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) \
            or not 1 <= max_rounds <= MAX_ROUNDS:
        raise ValueError(f"max_rounds must be 1-{MAX_ROUNDS}")
    if not plan_variants:
        return {"verdict": "stopped", "reason": "no plan variants supplied",
                "records": []}
    try:
        baseline = verify(original)
    except Exception as exc:  # noqa: BLE001 - verifier failure stops round one
        return {"verdict": "stopped", "reason": "verifier error on original",
                "detail": f"{type(exc).__name__}: {exc}", "records": []}
    baseline_print = baseline.get("fingerprint", "")
    if not baseline.get("ok", False) and not baseline_print:
        return {"verdict": "stopped",
                "reason": "defect fingerprint missing", "records": []}
    records: list[dict] = []
    for number, plan in enumerate(plan_variants[:max_rounds], start=1):
        candidate = f"{candidate_base}-round{number}"
        applied = apply_plan(plan, original, candidate)
        if applied["verdict"] != "applied":
            records.append({"round": number, "candidate": candidate,
                            "applied": applied})
            return {"verdict": "stopped",
                    "reason": "plan application blocked",
                    "records": records}
        try:
            result = verify(candidate)
        except Exception as exc:  # noqa: BLE001 - verifier failure stops
            shutil.rmtree(candidate, ignore_errors=True)
            records.append({"round": number, "candidate": candidate,
                            "applied": applied})
            return {"verdict": "stopped", "reason": "verifier error",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "records": records}
        fingerprint = result.get("fingerprint", "")
        record = {"round": number, "candidate": candidate,
                  "applied": applied, "verify": result}
        records.append(record)
        if result.get("ok"):
            return {"verdict": "repaired", "candidate": candidate,
                    "rounds": number, "records": records}
        if result.get("failed_invariants"):
            shutil.rmtree(candidate, ignore_errors=True)
            return {"verdict": "stopped",
                    "reason": "failed invariants; candidate restored",
                    "records": records}
        if not fingerprint:
            shutil.rmtree(candidate, ignore_errors=True)
            return {"verdict": "stopped",
                    "reason": "defect fingerprint missing; candidate restored",
                    "records": records}
        if fingerprint == baseline_print:
            shutil.rmtree(candidate, ignore_errors=True)
            return {"verdict": "stopped",
                    "reason": "defect fingerprint unchanged; "
                              "candidate restored",
                    "records": records}
        shutil.rmtree(candidate, ignore_errors=True)
    return {"verdict": "stopped", "reason": "rounds exhausted",
            "records": records}
