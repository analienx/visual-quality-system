"""Compact decision-facing projection of an otherwise sealed VQS run.

Never modifies verdict, approval or evidence. Full machine-readable
envelopes and run manifests remain available for audits.
"""
from __future__ import annotations

import hashlib
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


def _answered_ids(result: dict[str, Any]) -> set[str]:
    """Decision ids the owner has actually answered in this run."""
    out: set[str] = set()
    for item in result.get("owner_decisions") or []:
        if isinstance(item, dict) and isinstance(item.get("decision_id"), str):
            out.add(item["decision_id"])
    return out


def _is_echo(question: Any, answered: set[str]) -> bool:
    """True only for a question whose own id is already answered.

    Answers are partial by design: `vqs.repair.decisions` resolves only
    the entries an owner supplied and leaves the rest open, so a run can
    carry one answer and four open questions. A question is expendable
    only when *its* id is answered -- never because some other question
    in the same run was.
    """
    return (isinstance(question, dict)
            and isinstance(question.get("decision_id"), str)
            and question["decision_id"] in answered)


def _unanswered_count(result: dict[str, Any]) -> int:
    answered = _answered_ids(result)
    return sum(1 for q in (result.get("needs_review") or [])
               if not _is_echo(q, answered))


# Scalars the terminal overflow form may give up, in order, when its own
# metadata does not fit. `candidate` lives under the run, and `run_dir` is
# the retrieval pointer, so it is surrendered last and only as a digest.
_OVERFLOW_OPTIONAL = ("evidence", "candidate", "decision_source_sha256",
                      "source_sha256", "candidate_status")


def _path_stand_in(value: Any) -> Any:
    """Identify a path too long to quote, without quoting it."""
    if not isinstance(value, str) or not value:
        return value
    raw = value.encode("utf-8", "surrogatepass")
    return {"omitted": "too long for the compact budget",
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _overflow(result: dict[str, Any], budget: int,
              reason: str | None = None) -> dict[str, Any]:
    """Refuse to be answered from: mandatory content exceeds the budget.

    The terminal form is itself measured. Long `run_dir` / `candidate`
    paths and this function's own explanatory text can exceed the budget
    even with every optional list already empty, so optional scalars are
    surrendered in a fixed order and the retrieval pointer degrades to a
    digest rather than silently blowing the limit it advertises.
    """
    pending = _unanswered_count(result)
    required = _compact_bytes(result)
    if reason is None:
        reason = (f"{pending} unanswered owner decision(s) exceed the "
                  f"{budget}-byte compact budget on their own, and owner "
                  "questions are never truncated"
                  if pending else
                  f"mandatory result metadata exceeds the {budget}-byte "
                  "compact budget even with every optional list empty")
    out = {key: result.get(key) for key in (
        "tool", "verdict", "outcome", "run_id", "run_dir",
        "decision_source_sha256", "candidate", "candidate_status",
        "promotion_performed", "acceptance")}
    # No partial questions: a subset would invite an answer based on less
    # than the owner decision actually covers.
    out["needs_review"] = []
    out["compact_overflow"] = {
        "reason": reason,
        "owner_decisions_pending": pending,
        "budget_bytes": budget,
        "required_bytes": required,
        "next_action": ("read the full result before answering: re-run with "
                        "`--report-out <file>`, or read the sealed envelope "
                        "in run_dir. Do not answer from this output"),
    }
    out["evidence"] = result.get("evidence")
    # Bound this object too. Verdict, outcome, acceptance and
    # promotion_performed are never surrendered: they are how a reader
    # knows the run is still awaiting review.
    for key in _OVERFLOW_OPTIONAL:
        if _compact_bytes(out) <= budget:
            return out
        if out.get(key) is not None:
            out[key] = None
            out["compact_overflow"]["omitted_fields"] = [
                *out["compact_overflow"].get("omitted_fields", []), key]
    if _compact_bytes(out) > budget:
        out["run_dir"] = _path_stand_in(out.get("run_dir"))
        out["compact_overflow"]["next_action"] = (
            "the run directory path is itself too long to print here; "
            "recover it from the run id with `--report-out <file>`. "
            "Do not answer from this output")
    if _compact_bytes(out) > budget:
        # Last resort: a fixed-shape refusal that cannot itself overflow.
        return {"tool": result.get("tool"),
                "verdict": result.get("verdict", "blocked"),
                "outcome": result.get("outcome"),
                "promotion_performed": result.get("promotion_performed"),
                "acceptance": result.get("acceptance"),
                "needs_review": [],
                "compact_overflow": {
                    "reason": "this run cannot be represented within the "
                              f"{budget}-byte compact budget at all",
                    "owner_decisions_pending": pending,
                    "budget_bytes": budget,
                    "required_bytes": required,
                    "next_action": ("read the full result with "
                                    "`--report-out <file>`. Do not answer "
                                    "from this output")}}
    return out


def _trim_order(result: dict[str, Any]) -> tuple[str, ...]:
    """Fields to give up, in order, least decision-critical first.

    ``needs_review`` carries the questions an owner must answer. An
    *answered* question is a pure echo of an answer the owner already
    holds in their answers file, so it is more expendable than anything
    describing the run's current state. An *unanswered* question is
    mandatory and is never dropped, however many of its siblings were
    answered -- so this list appears here only when it holds echoes, and
    only those entries are ever given up (see ``_trim_list``).

    ``regressions`` sits between the two groups: it is a safety signal
    rather than guidance, so it outranks the diagnostics, but it is not
    part of the decision record.
    """
    answered = _answered_ids(result)
    echoes = any(_is_echo(q, answered)
                 for q in (result.get("needs_review") or []))
    middle = _DIAGNOSTICS + ("regressions",)
    if echoes:
        return ("needs_review",) + middle + _DECISION_RECORD
    return middle + _DECISION_RECORD


def _without(values: list[Any], dropped: set[int]) -> list[Any]:
    """``values`` minus the dropped indices, order preserved."""
    return [value for index, value in enumerate(values) if index not in dropped]


def _droppable(key: str, values: list[Any],
               result: dict[str, Any]) -> list[int]:
    """Indices of entries this key may surrender, in list order.

    Every entry of an ordinary list is expendable. ``needs_review`` is
    not an ordinary list: only the questions the owner has already
    answered may go, so an unanswered question survives regardless of
    how many of its siblings were answered.
    """
    if key != "needs_review":
        return list(range(len(values)))
    answered = _answered_ids(result)
    return [i for i, question in enumerate(values)
            if _is_echo(question, answered)]


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
        removable = _droppable(key, original, result)
        if not removable:
            continue
        dropped: set[int] = set()
        # Bound the work on pathological input before refining one by one.
        pending = list(reversed(removable))
        if len(removable) > _PRETRIM:
            dropped.update(removable[_PRETRIM:])
            pending = list(reversed(removable[:_PRETRIM]))
            trimmed[key] = _without(original, dropped)
            omitted[key] = len(dropped)
        for index in pending:
            if _compact_bytes(trimmed) <= budget:
                break
            dropped.add(index)
            trimmed[key] = _without(original, dropped)
            omitted[key] = len(dropped)
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
