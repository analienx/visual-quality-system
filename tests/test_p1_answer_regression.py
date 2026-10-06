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


def _params(port: _FakePort, questions: list) -> dict:
    return {"dax_questions": questions, "runtime": True,
            "live_answers": True, "modeling": None,
            "_fake_port": port}


def _connect(port: _FakePort) -> Any:
    def fake(params: dict) -> tuple:
        assert params["_fake_port"] is port
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


def test_baseline_then_regression_identical_scope(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 30: the regression re-asks the baseline's exact scoped query."""
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "modeling_present", lambda: True)
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    questions = [_question("revenue", "EVALUATE 'Revenue'")]
    entries: list = []
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    first = coord._answers_baseline(
        _params(port, questions), _record(entries), {}, {}, run_dir)
    assert first["status"] == "pass"
    persisted = json.loads((run_dir / "answers-baseline.json").read_text(
        encoding="utf-8"))
    assert persisted["questions"]["revenue"]["dax"] == "EVALUATE 'Revenue'"
    assert persisted["questions"]["revenue"]["scope"] == {}
    assert persisted["questions"]["revenue"]["rows"] == [{"total": 42}]
    second = coord._answer_regression(
        {}, {"answers_path": str(run_dir / "answers-baseline.json")},
        run_dir)
    assert second["status"] == "pass"
    assert [call[0] for call in port.calls] == ["EVALUATE 'Revenue'"] * 2
    assert len(port.calls) == 2


def test_regression_fails_on_changed_rows(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    port = _FakePort([{"total": 42}])
    monkeypatch.setattr(coord, "modeling_present", lambda: True)
    monkeypatch.setattr(coord, "_connect_modeling", _connect(port))
    entries: list = []
    run_dir = tmp_path / "runs"
    run_dir.mkdir()
    coord._answers_baseline(
        _params(port, [_question("revenue")]), _record(entries),
        {}, {}, run_dir)
    port.rows = [{"total": 43}]
    failed = coord._answer_regression(
        {}, {"answers_path": str(run_dir / "answers-baseline.json")},
        run_dir)
    assert failed["status"] == "fail"
    assert "revenue" in failed["reason"]


def test_regression_blocked_without_readable_baseline(
        tmp_path: Path) -> None:
    missing = coord._answer_regression(
        {}, {"answers_path": str(tmp_path / "absent.json")}, tmp_path)
    assert missing["status"] == "blocked"
    assert "unreadable" in missing["reason"]
