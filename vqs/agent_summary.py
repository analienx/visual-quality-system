"""Compact decision-facing projection of an otherwise sealed VQS run.

Never modifies verdict, approval or evidence. Full machine-readable
envelopes and run manifests remain available for audits.
"""
from __future__ import annotations

import json
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


# The compact result is what an agent reads into its context, so it has a
# hard byte budget. Owner questions and their options are mandatory: an
# "omitted" count alone would leave an owner answering without the basis
# for the answer, so they are never trimmed. Optional diagnostics are
# trimmed instead, deterministically, and what went is reported.
COMPACT_BUDGET_BYTES = 6000

# Restatable guidance: generated advice and findings that the sealed run
# still carries in full, so these go first. ``next_actions`` is derived
# wholly from the rest of the result, which makes it the cheapest loss.
_DIAGNOSTICS: tuple[str, ...] = ("next_actions", "remaining", "blocked_reasons")
# What the repair actually achieved and what the owner decided. ``fixed``
# and ``changes`` are the result, not commentary on it -- an agent reads
# them to report what the run did -- so they are given up last.
_DECISION_RECORD: tuple[str, ...] = (
    "owner_decisions", "waived", "changes", "fixed",
)
# Bound the work on pathological input before refining entry by entry.
_PRETRIM = 200


def _compact_bytes(result: dict[str, Any]) -> int:
    """Bytes the CLI actually writes: the serialized form plus its newline.

    Measured in encoded UTF-8, not characters, so non-ASCII text is
    budgeted at its real cost, and measured *with* any omission metadata
    already attached so recording a trim cannot push the result over.
    """
    return len(json.dumps(result, indent=2, ensure_ascii=False,
                          default=str).encode("utf-8")) + 1


def _overflow(result: dict[str, Any], budget: int) -> dict[str, Any]:
    """Refuse to be answered from: mandatory content exceeds the budget."""
    pending = result.get("needs_review") or []
    out = {key: result.get(key) for key in (
        "tool", "verdict", "outcome", "run_id", "run_dir",
        "decision_source_sha256", "candidate", "candidate_status",
        "promotion_performed", "acceptance")}
    # No partial questions: a subset would invite an answer based on less
    # than the owner decision actually covers.
    out["needs_review"] = []
    out["compact_overflow"] = {
        "reason": (f"{len(pending)} owner decision(s) exceed the "
                   f"{budget}-byte compact budget on their own, and owner "
                   "questions are never truncated"),
        "owner_decisions_pending": len(pending),
        "budget_bytes": budget,
        "required_bytes": _compact_bytes(result),
        "next_action": ("read the full result before answering: re-run with "
                        "`--report-out <file>`, or read the sealed envelope "
                        "in run_dir. Do not answer from this output"),
    }
    out["evidence"] = result.get("evidence")
    return out


def _trim_order(result: dict[str, Any]) -> tuple[str, ...]:
    """Fields to give up, in order, least decision-critical first.

    ``needs_review`` carries the questions an owner must answer, so while
    any decision is unanswered it is mandatory and never appears here.
    Once answered, those same questions are a pure echo of answers the
    owner already holds in their answers file, which makes them more
    expendable than anything describing the run's current state -- so on
    an answered run they are given up before the diagnostics.

    ``regressions`` sits between the two groups: it is a safety signal
    rather than guidance, so it outranks the diagnostics, but it is not
    part of the decision record.
    """
    answered = bool(result.get("owner_decisions"))
    middle = _DIAGNOSTICS + ("regressions",)
    if answered:
        return ("needs_review",) + middle + _DECISION_RECORD
    return middle + _DECISION_RECORD


def _fit_budget(result: dict[str, Any],
                budget: int = COMPACT_BUDGET_BYTES) -> dict[str, Any]:
    """Keep the printed result within ``budget`` encoded bytes."""
    if _compact_bytes(result) <= budget:
        return result
    omitted: dict[str, int] = {}
    trimmed = dict(result)
    trimmed["omitted"] = omitted
    for key in _trim_order(result):
        original = result.get(key)
        if not isinstance(original, list) or not original:
            continue
        values = list(original)
        if len(values) > _PRETRIM:
            values = values[:_PRETRIM]
            trimmed[key] = values
            omitted[key] = len(original) - len(values)
        while _compact_bytes(trimmed) > budget and values:
            values = values[:-1]
            trimmed[key] = values
            omitted[key] = len(original) - len(values)
        if not values:
            # An empty list carries nothing; drop the key and keep the count.
            trimmed[key] = []
        if _compact_bytes(trimmed) <= budget:
            return trimmed
    if _compact_bytes(trimmed) <= budget:
        return trimmed
    return _overflow(result, budget)


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
    return _fit_budget({
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
    })
