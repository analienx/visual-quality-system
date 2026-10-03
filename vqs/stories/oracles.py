"""Minimal question/answer oracles (WP-10, issue #15, offline subset).

A repair preserves the answer to the same scoped question. Scope equality is
checked on a stable digest of filters, role, period, and measure — an
apparently equal answer under a different scope can never pass (DES-09), and
a question with no known measure, date, or target needs clarification instead
of a fabricated claim (DES-08). Scope equality alone never proves answer
preservation (criterion 14): the answer rows themselves must match. No model
query or render is performed here.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any


def scope_digest(filters: dict[str, str] | None, role: str = "",
                 period: str = "", measure: str = "") -> str:
    """Stable digest of an answer scope; empty scope digests honestly, not equally."""
    canonical = json.dumps(
        {"filters": filters or {}, "role": role, "period": period, "measure": measure},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def oracle_matches(oracle_scope: str, run_scope: str) -> dict:
    """Pass only when the run reproduced the oracle under the identical scope."""
    if not oracle_scope or not run_scope:
        return {"verdict": "blocked", "reason": "Both oracle and run scopes required"}
    if oracle_scope == run_scope:
        return {"verdict": "pass", "scope": run_scope}
    return {"verdict": "fail", "reason": "Answer scope differs from the oracle scope",
            "oracle": oracle_scope, "run": run_scope}


def ambiguity_check(question: str | None, known_measures: Sequence[str] | None,
                    known_targets: Sequence[str] | None = None) -> dict:
    """Decide whether a question is answerable from known model context.

    Returns ``answerable`` only when the question names a known measure.
    Anything else returns ``needs_clarification`` — never a fabricated
    trend, target, or causal claim.
    """
    if not question or not question.strip():
        return {"verdict": "blocked", "reason": "A question is required"}
    measures = list(known_measures or [])
    targets = list(known_targets or [])
    lowered = question.lower()
    if not any(measure.lower() in lowered for measure in measures):
        return {"verdict": "needs_clarification",
                "reason": "Question names no known measure; do not invent one"}
    mentions_target = any(target.lower() in lowered for target in targets)
    if "target" in lowered and not mentions_target:
        return {"verdict": "needs_clarification",
                "reason": "Question implies a target with no target evidence"}
    return {"verdict": "answerable", "question": question}
def _cell_equal(want: Any, got: Any, absolute: float,
                relative: float) -> bool:
    """One answer cell: exact, except declared numeric tolerance."""
    if isinstance(want, bool) or isinstance(got, bool):
        return (isinstance(want, bool) and isinstance(got, bool)
                and want == got)
    if isinstance(want, (int, float)) and isinstance(got, (int, float)):
        if not math.isfinite(want) or not math.isfinite(got):
            return False
        if absolute <= 0 and relative <= 0:
            return want == got
        spread = abs(want - got)
        return spread <= absolute + relative * max(abs(want), abs(got))
    return type(want) is type(got) and want == got


def _row_key(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)


def answer_rows_preserved(expected: Sequence[dict] | None,
                          actual: Sequence[dict] | None,
                          tolerance: dict | None = None,
                          ordered: bool = False) -> dict:
    """Pass only when actual answer rows preserve the expected rows.

    Empty or missing rows on either side BLOCK (no answer evidence),
    they never pass. tolerance optionally declares {"absolute": float,
    "relative": float} applied to int/float cells; every other cell must
    be exactly equal. Unordered (default) compares as multisets; ordered
    compares positionally (rankings, top-N answers).
    """
    declared: dict[str, Any] = dict(tolerance or {})
    absolute = declared.get("absolute", 0)
    relative = declared.get("relative", 0)
    for name, value in (("absolute", absolute), ("relative", relative)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            return {"verdict": "blocked",
                    "reason": f"tolerance declaration invalid: {name!r}"}
    if expected is None or actual is None:
        return {"verdict": "blocked",
                "reason": "answer evidence required on both sides"}
    if not isinstance(expected, list) or not isinstance(actual, list):
        return {"verdict": "blocked",
                "reason": "answer rows must be a list of objects"}
    if not expected or not actual:
        return {"verdict": "blocked",
                "reason": "no answer rows; equal scopes prove nothing"}
    if any(not isinstance(row, dict) for row in (*expected, *actual)):
        return {"verdict": "blocked",
                "reason": "answer rows must be a list of objects"}
    if len(expected) != len(actual):
        return {"verdict": "fail",
                "reason": "answer row count changed",
                "expected_rows": len(expected), "actual_rows": len(actual)}
    pairs = (zip(expected, actual, strict=True) if ordered
             else zip(sorted(expected, key=_row_key),
                      sorted(actual, key=_row_key), strict=True))
    for index, (want_row, got_row) in enumerate(pairs):
        if set(want_row) != set(got_row):
            return {"verdict": "fail",
                    "reason": "answer shape changed",
                    "row": index,
                    "expected_columns": sorted(want_row),
                    "actual_columns": sorted(got_row)}
        for column in want_row:
            want, got = want_row[column], got_row[column]
            if isinstance(want, float) and math.isnan(want):
                return {"verdict": "blocked",
                        "reason": "non-finite answer cell",
                        "row": index, "column": column}
            if isinstance(got, float) and math.isnan(got):
                return {"verdict": "blocked",
                        "reason": "non-finite answer cell",
                        "row": index, "column": column}
            if not _cell_equal(want, got, float(absolute),
                               float(relative)):
                return {"verdict": "fail",
                        "reason": "repair changed answers",
                        "row": index, "column": column,
                        "expected": want, "actual": got}
    return {"verdict": "pass", "rows": len(expected), "ordered": ordered,
            "tolerance": {"absolute": absolute, "relative": relative}}
