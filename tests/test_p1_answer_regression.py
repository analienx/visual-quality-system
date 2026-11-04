"""P1 items 30-31: live answer regression under identical scope.

Item 30 folds the existing Modeling MCP answer collection into the
coordinator for baseline/candidate under identical scope: the baseline
persists the query/scope/result evidence per question and the
regression stage re-asks the identical scoped query. Item 31 keeps
non-empty filters/period fail-closed with the exact blocker.
"""
import json
from pathlib import Path
from typing import Any

import pytest

from vqs import coordinator as coord


class _FakePort:
    """Modeling query port double; records every scoped call."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, Any]] = []

    def query_scoped(self, dax: str, scope: Any) -> dict:
        self.calls.append((dax, scope))
        return {"rows": [dict(row) for row in self.rows],
                "context": {"dax": dax}}


def _record(entries: list) -> Any:
    def append(entry: dict) -> dict:
        entries.append(entry)
        return entry
    return append


def _params(questions: list) -> dict:
    return {"dax_questions": questions, "runtime": True,
            "live_answers": True, "modeling": None}


def _connect(port: _FakePort) -> Any:
    def fake(params: dict) -> tuple:
        return port, False, {"launcher": "fake-modeling"}
    return fake


def _question(qid: str, dax: str = "EVALUATE 'X'",
              scope: Any = None) -> dict:
    return {"id": qid, "dax": dax,
            "scope": {} if scope is None else scope}


def test_filters_and_period_stay_fail_closed() -> None:
    supported, held = coord._unsupported_scope_answers([
        _question("ok"),
        _question("filtered", scope={"filters": ["Dim[Year]=2024"]}),
        _question("ranged", scope={"period": "YTD"}),
        {"id": "broken"},
    ])
    assert [entry["id"] for entry in supported] == ["ok"]
    blocked = {entry["id"]: entry["reason"] for entry in held}
    assert "fail-closed until supported" in blocked["filtered"]
    assert "fail-closed until supported" in blocked["ranged"]
    assert "DAX string" in blocked["broken"]


def test_collect_echoes_query_and_scope() -> None:
    port = _FakePort([{"a": 1}])
    result = coord._answers_collect(
        [_question("q1", "EVALUATE 'Q1'")], port)
    assert result["verdict"] == "pass"
    entry = result["questions"]["q1"]
    assert entry["verdict"] == "observed"
    assert entry["dax"] == "EVALUATE 'Q1'"
    assert entry["scope"] == {}
    assert entry["rows"] == [{"a": 1}]


def test_held_filters_block_collection_with_exact_blocker() -> None:
    port = _FakePort([{"a": 1}])
    result = coord._answers_collect(
        [_question("held", scope={"filters": ["Dim[Year]=2024"]})], port)
    assert result["verdict"] == "blocked"
    assert "held" in result["reason"]
    assert ("fail-closed until supported"
            in result["questions"]["held"]["reason"])
    assert port.calls == []


def test_baseline_does_not_query_without_source_bound_evidence(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable query port is not proof it owns the selected report."""
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "modeling_present", lambda: True)
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    questions = [_question("revenue", "EVALUATE 'Revenue'")]
    entries: list = []
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    first = coord._answers_baseline(
        _params(questions), _record(entries), {}, {}, run_dir)
    assert first["status"] == "blocked"
    assert "source-bound" in first["reason"]
    assert not (run_dir / "answers-baseline.json").exists()
    assert port.calls == []


def test_regression_never_queries_an_unbound_legacy_baseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _FakePort([{"total": 43}])
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    path = tmp_path / "answers-baseline.json"
    path.write_text(json.dumps({"questions": {"revenue": {
        "verdict": "observed", "dax": "EVALUATE 'Revenue'", "scope": {},
        "rows": [{"total": 42}]}}}), encoding="utf-8")
    result = coord._answer_regression({}, {"answers_path": str(path)}, tmp_path)
    assert result["status"] == "blocked"
    assert "binding" in result["reason"]
    assert port.calls == []


def test_empty_question_collection_is_blocked():
    port = _FakePort([{"a": 1}])
    result = coord._answers_collect([], port)
    assert result["verdict"] == "blocked"
    assert port.calls == []


def test_unbound_prior_baseline_is_never_reused(tmp_path, monkeypatch):
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "modeling_present", lambda: True)
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    monkeypatch.setattr(coord, "_adoptable", lambda *_args: True)
    prior = {"answers_baseline": {"stage": "answers_baseline", "status": "pass"}}
    result = coord._answers_baseline(_params([_question("revenue")]),
                                     _record([]), prior, {}, tmp_path)
    assert result["status"] == "blocked"
    assert port.calls == []


def test_regression_blocked_without_readable_baseline(
        tmp_path: Path) -> None:
    missing = coord._answer_regression(
        {}, {"answers_path": str(tmp_path / "absent.json")}, tmp_path)
    assert missing["status"] == "blocked"
    assert "unreadable" in missing["reason"]


def test_empty_baseline_questions_never_pass(tmp_path, monkeypatch):
    path = tmp_path / "answers-baseline.json"
    path.write_text(json.dumps({"questions": {}}), encoding="utf-8")
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    result = coord._answer_regression({}, {"answers_path": str(path)}, tmp_path)
    assert result["status"] == "blocked"
    assert port.calls == []


@pytest.mark.parametrize("document", [
    [],
    {"questions": []},
    {"questions": {"q": []}},
    {"questions": {"q": {"verdict": "observed", "dax": "EVALUATE ROW('x', 1)",
                         "scope": [], "rows": [{"x": 1}]}}},
    {"questions": {"q": {"verdict": "observed", "dax": "EVALUATE ROW('x', 1)",
                         "scope": {}, "rows": []}}},
])
def test_malformed_legacy_answer_document_blocks_without_query(tmp_path, monkeypatch, document):
    path = tmp_path / "answers-baseline.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    result = coord._answer_regression({}, {"answers_path": str(path)}, tmp_path)
    assert result["status"] == "blocked"
    assert port.calls == []


def test_incomplete_baseline_questions_are_not_silently_dropped(tmp_path, monkeypatch):
    path = tmp_path / "answers-baseline.json"
    path.write_text(json.dumps({"questions": {
        "valid": {"verdict": "observed", "dax": "EVALUATE ROW('x', 42)",
                  "scope": {}, "rows": [{"total": 42}]},
        "missing": {"verdict": "blocked", "reason": "no data"}}}), encoding="utf-8")
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    result = coord._answer_regression({}, {"answers_path": str(path)}, tmp_path)
    assert result["status"] == "blocked"
    assert port.calls == []


def test_equal_rows_with_different_model_context_never_pass(tmp_path, monkeypatch):
    path = tmp_path / "answers-baseline.json"
    path.write_text(json.dumps({"questions": {"revenue": {
        "verdict": "observed", "dax": "EVALUATE ROW('x', 42)", "scope": {},
        "rows": [{"total": 42}], "context": {"model": "baseline-model"}}}}),
        encoding="utf-8")

    class DifferentModel(_FakePort):
        def query_scoped(self, dax, scope):
            self.calls.append((dax, scope))
            return {"rows": [{"total": 42}], "context": {"model": "different-model"}}

    port = DifferentModel([{"total": 42}])
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    result = coord._answer_regression({}, {"answers_path": str(path)}, tmp_path)
    assert result["status"] == "blocked"
    assert port.calls == []


def _verify_fixture(tmp_path, monkeypatch, *, ready):
    """Exercise the real stage sequence with in-memory synthetic ports."""
    from vqs import pipeline

    monkeypatch.setattr(pipeline, "verify_candidate", lambda **_kwargs: {"verdict": "pass"})
    monkeypatch.setattr(pipeline, "review_report",
                        lambda **_kwargs: {"verdict": "pass", "findings": []})
    monkeypatch.setattr(coord, "_finish",
                        lambda _dir, _rid, entries, *_args: {"stages": entries})
    stages = [coord._stage("repair", "pass")]
    state = {"adopted": {}, "repair_id": "synthetic-repair", "ready": ready,
             "candidate": "synthetic-candidate", "answers_path": "legacy.json"}
    params = {"mode": "repair", "runtime": True, "scope": "desktop",
              "run_root": str(tmp_path), "report_dir": "synthetic-original", "pid": 123}
    return stages, state, params


def test_denied_desktop_permission_never_opens_candidate(tmp_path, monkeypatch):
    from vqs.repair import runtime

    stages, state, params = _verify_fixture(tmp_path, monkeypatch, ready=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("permission denial must prevent Desktop/model access")

    monkeypatch.setattr(runtime, "LocalBridgePort", forbidden)
    monkeypatch.setattr(coord, "_answer_regression", forbidden)
    monkeypatch.setattr(coord, "_capture_stage", forbidden)
    result = coord._verify_sequence(tmp_path, "permission-denied", stages,
                                    state, {}, _record(stages), params)
    stages = {stage["stage"]: stage for stage in result["stages"]}
    assert stages["verify"]["status"] == "pass"
    assert stages["candidate_reload"]["status"] == "blocked"
    assert stages["answer_regression"]["status"] == "blocked"
    assert stages["recapture"]["status"] == "blocked"


def test_failed_reload_prevents_answer_query_and_recapture(tmp_path, monkeypatch):
    from vqs.repair import runtime

    stages, state, params = _verify_fixture(tmp_path, monkeypatch, ready=True)
    stages.append(coord._stage("candidate_reload", "pass", evidence={"pid": 123}))

    def refused_bridge():
        raise runtime.BridgeUnavailable("synthetic reload failure")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("failed reload must prevent answer queries")

    monkeypatch.setattr(runtime, "LocalBridgePort", refused_bridge)
    monkeypatch.setattr(coord, "_answer_regression", forbidden)
    monkeypatch.setattr(coord, "_capture_stage", forbidden)
    result = coord._verify_sequence(tmp_path, "reload-failed", stages,
                                    state, {}, _record(stages), params)
    stages = {stage["stage"]: stage for stage in result["stages"]}
    assert stages["verify"]["status"] == "pass"
    assert stages["candidate_reload"]["status"] == "blocked"
    assert stages["answer_regression"]["status"] == "blocked"
    assert stages["recapture"]["status"] == "blocked"


@pytest.mark.parametrize("pid", [None, True, 0, -1, "123", [], {}])
def test_reload_pass_needs_a_positive_integer_pid(pid):
    stages = [coord._stage("candidate_reload", "pass", evidence={"pid": pid})]
    assert coord._candidate_reload_pid(stages) is None


def test_reload_precondition_accepts_current_bound_pid_only():
    stages = [coord._stage("candidate_reload", "blocked"),
              coord._stage("candidate_reload", "pass", evidence={"pid": 123})]
    assert coord._candidate_reload_pid(stages) == 123


def test_recapture_uses_newly_opened_candidate_pid(tmp_path, monkeypatch):
    from vqs.repair import runtime

    stages, state, params = _verify_fixture(tmp_path, monkeypatch, ready=True)
    params["pid"] = None
    monkeypatch.setattr(runtime, "LocalBridgePort", lambda: object())
    monkeypatch.setattr(coord, "_candidate_source_sha256", lambda _state: "a" * 64)
    monkeypatch.setattr(runtime, "open_candidate_instance",
                        lambda *_args, **_kwargs: {"instance": {"pid": 456}})
    monkeypatch.setattr(runtime, "reload_instance", lambda _port, instance: instance)
    monkeypatch.setattr(coord, "_answer_regression",
                        lambda *_args: coord._stage("answer_regression", "blocked"))
    monkeypatch.setattr(coord, "_handoff_stage",
                        lambda *_args: coord._stage("handoff", "blocked"))
    called = []

    def capture(name, report, _renders, pid, record, *_args, **kwargs):
        called.append((name, report, pid, kwargs.get("owned_candidate")))
        return record(coord._stage(name, "pass"))

    monkeypatch.setattr(coord, "_capture_stage", capture)
    result = coord._verify_sequence(tmp_path, "run-owned", stages,
                                    state, {}, _record(stages), params)
    assert {stage["stage"]: stage for stage in result["stages"]}["recapture"]["status"] == "pass"
    assert called == [("recapture", "synthetic-candidate", 456, True)]
