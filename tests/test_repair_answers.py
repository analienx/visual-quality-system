"""Answer-preservation tests (criteria 14/16): rows, scopes, tolerance.

Equal scope digests without matching answer rows never pass; changed
answers fail; port failures and empty evidence block.
"""

from vqs.repair.answers import answers_preserved, collect_answers
from vqs.stories import scope_digest
from vqs.stories.oracles import answer_rows_preserved

ROWS = [{"city": "Paris", "revenue": 100}, {"city": "Lima", "revenue": 50}]


def test_identical_rows_pass_unordered() -> None:
    verdict = answer_rows_preserved(ROWS, [dict(r) for r in reversed(ROWS)])
    assert verdict["verdict"] == "pass"
    assert verdict["rows"] == 2


def test_changed_cell_fails_with_location() -> None:
    changed = [dict(ROWS[0]), {"city": "Lima", "revenue": 51}]
    verdict = answer_rows_preserved(ROWS, changed)
    assert verdict["verdict"] == "fail"
    assert verdict["reason"] == "repair changed answers"
    assert verdict["column"] == "revenue"


def test_row_count_and_shape_change_fail() -> None:
    verdict = answer_rows_preserved(ROWS, ROWS[:1])
    assert verdict["verdict"] == "fail"
    assert verdict["reason"] == "answer row count changed"
    verdict = answer_rows_preserved(ROWS, [{"city": "Paris"}] * 2)
    assert verdict["verdict"] == "fail"
    assert verdict["reason"] == "answer shape changed"


def test_empty_or_missing_rows_block_never_pass() -> None:
    for expected, actual in (([], ROWS), (ROWS, []), ([], []),
                             (None, ROWS), (ROWS, None),
                             ("rows", ROWS), (ROWS, [{"ok": 1}, "bad"])):
        verdict = answer_rows_preserved(expected, actual)  # type: ignore[arg-type]
        assert verdict["verdict"] == "blocked", (expected, actual)


def test_tolerance_applies_to_numbers_only() -> None:
    close = [{"city": "Paris", "revenue": 100.05},
             {"city": "Lima", "revenue": 50.0}]
    exact = answer_rows_preserved(ROWS, close)
    assert exact["verdict"] == "fail"
    looser = answer_rows_preserved(ROWS, close, {"absolute": 0.1})
    assert looser["verdict"] == "pass"
    renamed = [{"city": "Parish", "revenue": 100.05},
               {"city": "Lima", "revenue": 50.0}]
    assert answer_rows_preserved(ROWS, renamed,
                                 {"absolute": 99})["verdict"] == "fail"
    assert answer_rows_preserved(ROWS, ROWS,
                                 {"absolute": -1})["verdict"] == "blocked"
    assert answer_rows_preserved(ROWS, ROWS,
                                 {"absolute": "much"})["verdict"] == "blocked"


def test_ordered_comparison_is_positional() -> None:
    verdict = answer_rows_preserved(ROWS, list(reversed(ROWS)), ordered=True)
    assert verdict["verdict"] == "fail"
    verdict = answer_rows_preserved(ROWS, [dict(r) for r in ROWS],
                                    ordered=True)
    assert verdict["verdict"] == "pass"


def test_bool_and_type_strictness() -> None:
    assert answer_rows_preserved([{"ok": True}],
                                 [{"ok": 1}])["verdict"] == "fail"
    assert answer_rows_preserved([{"n": 1}],
                                 [{"n": "1"}])["verdict"] == "fail"
    assert answer_rows_preserved([{"n": float("nan")}],
                                 [{"n": float("nan")}])["verdict"] == "blocked"


def test_malformed_tolerance_blocks_without_raise() -> None:
    for bad in ("x", 5, ["absolute"], 3.5, True):
        verdict = answer_rows_preserved(ROWS, ROWS, bad)  # type: ignore[arg-type]
        assert verdict["verdict"] == "blocked", bad
        assert "must be an object" in verdict["reason"]


def test_infinities_block_like_nan() -> None:
    assert answer_rows_preserved([{"n": float("inf")}],
                                 [{"n": float("inf")}])["verdict"] == "blocked"
    assert answer_rows_preserved([{"n": 1}],
                                 [{"n": float("inf")}])["verdict"] == "blocked"


def test_scope_drift_and_baseline_block_or_fail() -> None:
    scope = scope_digest({"Year": "2024"}, measure="Revenue")
    other = scope_digest({"Year": "2023"}, measure="Revenue")
    assert answers_preserved(scope, scope, ROWS, ROWS)["verdict"] == "pass"
    drifted = answers_preserved(scope, other, ROWS, ROWS)
    assert drifted["verdict"] == "fail"
    assert "scope" in drifted["reason"]
    assert answers_preserved("", scope, ROWS, ROWS)["verdict"] == "blocked"
    changed = answers_preserved(scope, scope, ROWS, ROWS[:1])
    assert changed["verdict"] == "fail"
    assert changed["rows"]["reason"] == "answer row count changed"
    bad_baseline = answers_preserved(scope, scope, ROWS, ROWS,
                                     oracle_rows=ROWS[:1])
    assert bad_baseline["verdict"] == "blocked"
    assert "oracle" in bad_baseline["reason"]


class _Port:
    def __init__(self, script):
        self.script = script

    def query_scoped(self, dax, scope):
        outcome = self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_collect_answers_blocks_port_failures() -> None:
    port = _Port([{"rows": ROWS, "context": {"scope": "s"}},
                  ValueError("boom"), {"rows": "nope"}])
    questions = [{"id": "q1", "dax": "E1", "scope": {}},
                 {"id": "q2", "dax": "E2", "scope": {}},
                 {"id": "q3", "dax": "E3", "scope": {}}]
    answers = collect_answers(port, questions)
    assert answers["q1"]["verdict"] == "observed"
    assert answers["q1"]["rows"] == ROWS
    assert answers["q2"]["verdict"] == "blocked"
    assert "boom" in answers["q2"]["reason"]
    assert answers["q3"]["verdict"] == "blocked"


def test_collect_answers_blocks_malformed_questions() -> None:
    port = _Port([{"rows": ROWS, "context": {}}])
    answers = collect_answers(port, ["not-a-question",
                                     {"id": "q1", "dax": "E1", "scope": {}}])
    assert answers["question-0"]["verdict"] == "blocked"
    assert answers["q1"]["verdict"] == "observed"


def test_criterion14_equal_scopes_without_rows_never_pass() -> None:
    scope = scope_digest({"Year": "2024"}, measure="Revenue")
    verdict = answers_preserved(scope, scope, [], [])
    assert verdict["verdict"] == "blocked"
    verdict = answers_preserved(scope, scope, None, None)
    assert verdict["verdict"] == "blocked"
