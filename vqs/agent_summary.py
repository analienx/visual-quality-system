"""Compact decision-facing projection of an otherwise sealed VQS run.

Never modifies verdict, approval or evidence. Full machine-readable
envelopes and run manifests remain available for audits.
"""
from __future__ import annotations

from typing import Any


def summarize(envelope: dict[str, Any]) -> dict[str, Any]:
    summary = envelope.get("summary") or {}
    triage = summary.get("repair_triage") or {}
    decisions = triage.get("decisions") or []
    # Each owner decision is an answerable question: an agent shows the
    # options to the owner once, then re-runs with --decisions.
    needs_review = [
        {key: x[key] for key in ("decision_id", "check", "question", "reason",
                                 "cohort", "pair", "page", "visual")
         if x.get(key) is not None}
        | ({"options": [{"id": o.get("id"), "label": o.get("label"),
                         "effect": o.get("effect")}
                        for o in x.get("options", []) if isinstance(o, dict)]}
           if isinstance(x.get("options"), list) else {})
        for x in decisions if x.get("status") == "needs_owner_decision"
    ]
    remaining = summary.get("remaining_findings") or []
    return {
        "tool": envelope.get("tool"),
        "verdict": envelope.get("verdict", "blocked"),
        "outcome": summary.get("outcome"),
        "run_id": envelope.get("run_id"),
        "run_dir": envelope.get("run_dir"),
        "source_sha256": (envelope.get("provenance") or {}).get("source_sha256"),
        "fixed": summary.get("resolved_findings") or [],
        "remaining": remaining,
        "needs_review": needs_review[:12],
        "decision_source_sha256": triage.get("decision_source_sha256"),
        "waived": summary.get("waived_findings") or [],
        "owner_decisions": (summary.get("owner_decisions") or {}).get("answered", []),
        "regressions": summary.get("new_regressions") or [],
        "candidate": (summary.get("candidate_status") or {}).get("candidate"),
        "candidate_status": (summary.get("candidate_status") or {}).get("status"),
        "promotion_performed": False if not summary else
            bool((summary.get("repair_triage") or {}).get("promotion_performed")),
        "acceptance": bool(summary.get("acceptance")),
        "blocked_reasons": (envelope.get("blocked_reasons") or [])[:12],
        "next_actions": (envelope.get("next_actions") or [])[:8],
        "evidence": "Full sealed envelope available in run_dir; never infer native approval from static checks",
    }
