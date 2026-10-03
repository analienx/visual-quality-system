"""Actual answer comparison for repairs (criteria 14/16, WP-09/WP-10).

A repair preserves the answer to the same scoped question. Scope digests
must match AND the answer rows themselves must match; equal scopes with
missing, empty, or differing rows never pass. An optional oracle row set
checks baseline validity first: when the original does not reproduce the
oracle, any repair verdict would be meaningless, so the gate blocks.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vqs.stories.oracles import answer_rows_preserved, oracle_matches


def answers_preserved(scope_before: str, scope_after: str,
                      rows_before: Sequence[dict] | None,
                      rows_after: Sequence[dict] | None,
                      tolerance: dict | None = None,
                      ordered: bool = False,
                      oracle_rows: Sequence[dict] | None = None) -> dict:
    """Pass only when the candidate reproduces the original scoped answer."""
    scope = oracle_matches(scope_before, scope_after)
    if scope["verdict"] != "pass":
        return {"verdict": scope["verdict"],
                "reason": scope.get("reason", "answer scope drifted"),
                "scope": scope}
    if oracle_rows is not None:
        baseline = answer_rows_preserved(oracle_rows, rows_before,
                                         tolerance, ordered)
        if baseline["verdict"] != "pass":
            return {"verdict": "blocked",
                    "reason": "original does not reproduce the oracle; "
                              "repair verdict would be meaningless",
                    "scope": scope, "baseline": baseline}
    rows = answer_rows_preserved(rows_before, rows_after, tolerance, ordered)
    if rows["verdict"] != "pass":
        return {"verdict": rows["verdict"],
                "reason": rows.get("reason", "repair changed answers"),
                "scope": scope, "rows": rows}
    return {"verdict": "pass", "scope": scope, "rows": rows}


def collect_answers(query: Any, questions: Sequence[dict]) -> dict:
    """Run scoped oracle questions through a query port (duck-typed).

    The port needs ``query_scoped(dax, scope)`` returning {"rows": [...],
    "context": {...}} (the modeling-port shape); each question needs
    {"id", "dax", "scope"}. Any port failure blocks that question —
    missing evidence never passes.
    """
    answers: dict[str, Any] = {}
    for position, question in enumerate(questions):
        if not isinstance(question, dict):
            answers[f"question-{position}"] = {
                "verdict": "blocked", "reason": "malformed oracle question"}
            continue
        qid = str(question.get("id", f"question-{position}"))
        try:
            result = query.query_scoped(str(question.get("dax", "")),
                                        question.get("scope", {}))
        except Exception as exc:  # noqa: BLE001 - any port failure blocks
            answers[qid] = {"verdict": "blocked",
                            "reason": f"scoped query failed: {exc}"}
            continue
        if not isinstance(result, dict) or not isinstance(
                result.get("rows"), list):
            answers[qid] = {"verdict": "blocked",
                            "reason": "query port returned no rows list"}
            continue
        answers[qid] = {"verdict": "observed", "rows": result["rows"],
                        "context": result.get("context", {})}
    return answers
