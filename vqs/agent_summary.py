"""Compact decision-facing projection of an otherwise sealed VQS run.

Never modifies verdict, approval or evidence. Full machine-readable
envelopes and run manifests remain available for audits.
"""
from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any


def _changes(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Plain list of the edits in the verified candidate (what changed)."""
    plan = envelope.get("plan")
    ops = plan.get("operations") if isinstance(plan, dict) else None
    out = []
    for op in ops if isinstance(ops, list) else []:
        if not isinstance(op, dict):
            continue
        selector = op.get("selector") if isinstance(op.get("selector"), dict) else {}
        path = op.get("path") if isinstance(op.get("path"), list) else []
        named = [str(step) for step in path
                 if isinstance(step, str) and step not in (
                     "visual", "objects", "visualContainerObjects", "properties",
                     "expr", "Literal", "Value")]
        out.append({"page": selector.get("page"), "visual": selector.get("visual"),
                    "property": ".".join(named) or None, "op": op.get("type"),
                    "from": op.get("old"), "to": op.get("value")})
    return out


def _shell_quote(value: str, *, windows: bool) -> str:
    """Quote one literal argument for the documented shell on this host."""
    if windows:
        # PowerShell treats these five characters as single-quote delimiters.
        # Doubling each preserves its literal value inside a verbatim string.
        # This also prevents smart quotes from ending the argument early.
        quotes = "'\u2018\u2019\u201a\u201b"
        return "'" + value.translate({ord(char): char * 2 for char in quotes}) + "'"
    return shlex.quote(value)


def _adopt(envelope: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any] | None:
    """The one owner step that applies a verified candidate to the original."""
    if (summary.get("candidate_status") or {}).get("status") != "verified":
        return None
    repair = (summary.get("child_runs") or {}).get("repair") or {}
    run_id, run_dir = repair.get("run_id"), envelope.get("run_dir")
    if not isinstance(run_id, str) or not isinstance(run_dir, str):
        return None
    root = str(Path(run_dir).parent)
    # The owner runs this after their explicit decision. POSIX shlex
    # quoting is not PowerShell quoting, especially around apostrophes.
    # The MCP form needs no shell quoting at all.
    windows = os.name == "nt"
    shell = "PowerShell" if windows else "a POSIX shell"
    return {
        "command": (f"vqs promote --run-root {_shell_quote(root, windows=windows)} "
                    f"--run-id {_shell_quote(run_id, windows=windows)} "
                    '--owner-approval "<who: why>" --scope static'),
        "mcp": {"tool": "vqs_promote", "run_root": root, "run_id": run_id,
                "scope": "static"},
        "note": (f"Run the command in {shell}. Owner decision only: replaces "
                 "the original report with the "
                 "verified candidate after re-checking both digests; the "
                 "original is kept as <report>.vqs-backup. Static scope is "
                 "not native Desktop, G2/G4 or G6 acceptance"),
    }


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
        "needs_review": needs_review,
        "decision_source_sha256": triage.get("decision_source_sha256"),
        "waived": summary.get("waived_findings") or [],
        "owner_decisions": (summary.get("owner_decisions") or {}).get("answered", []),
        "regressions": summary.get("new_regressions") or [],
        "candidate": (summary.get("candidate_status") or {}).get("candidate"),
        "changes": _changes(envelope),
        "adopt": _adopt(envelope, summary),
        "candidate_status": (summary.get("candidate_status") or {}).get("status"),
        "promotion_performed": False if not summary else
            bool((summary.get("repair_triage") or {}).get("promotion_performed")),
        "acceptance": bool(summary.get("acceptance")),
        "blocked_reasons": (envelope.get("blocked_reasons") or [])[:12],
        "next_actions": (envelope.get("next_actions") or [])[:8],
        "evidence": ("Sealed stage ledger available in run_dir; the returned envelope is not "
                     "sealed there. Never infer native approval from static checks"),
    }
