"""Cycle-gate tests: synthetic TMDL with known loops and clean controls."""
import json
import os
from pathlib import Path

import pytest

from vqs.powerbi.cycles import check_model

FIXTURES = Path(__file__).parent / "fixtures"
LOOPY = str(FIXTURES / "cycle_model")
CLEAN = str(FIXTURES / "clean_model")


def test_dax_cycle_reports_both_measures() -> None:
    result = check_model(LOOPY)
    assert result["acyclic"] is False
    # B references [a] lowercase: DAX matching is case-insensitive.
    # LoopSelf references itself: self-loops are cycles, not skipped.
    assert result["dax_cycles"] == [
        ["measure:Loop.A", "measure:Loop.B", "measure:Loop.A"],
        ["measure:Loop.LoopSelf", "measure:Loop.LoopSelf"]]
    assert all("Clean" not in node for cycle in result["dax_cycles"]
               for node in cycle)


def test_m_query_cycle_found() -> None:
    result = check_model(LOOPY)
    assert result["m_cycles"] == [["Q1", "Q2", "Q1"],
                                  ["SelfQ", "SelfQ"]]
    assert result["m_queries"] == 8


def test_m_string_literal_is_not_a_reference() -> None:
    from vqs.powerbi.cycles import m_edges, m_queries
    edges = m_edges(m_queries(LOOPY))
    assert edges["Solo"] == set(), edges["Solo"]


def test_m_prefix_names_do_not_collide() -> None:
    from vqs.powerbi.cycles import m_edges, m_queries
    edges = m_edges(m_queries(LOOPY))
    assert edges["Q1"] == {"Q2", "Q10"}, edges["Q1"]
    assert edges["Q10"] == set(), edges["Q10"]


def test_within_let_cycle_names_query() -> None:
    result = check_model(LOOPY)
    assert result["let_cycles"] == [
        {"query": "Loopy", "cycle": ["a", "b", "a"]}]


def test_clean_model_is_acyclic() -> None:
    result = check_model(CLEAN)
    assert result == {"model_dir": CLEAN, "tables": 1,
                      "dax_objects": 2, "m_queries": 1,
                      "dax_cycles": [], "m_cycles": [], "let_cycles": [],
                      "acyclic": True,
                      "coverage": {
                          "parsed": [os.path.join(CLEAN, "tables",
                                                  "Clean.tmdl")],
                          "skipped": [], "unparsed": [],
                          "extract_issues": [],
                          "complete": True}}


def test_missing_model_dir_raises() -> None:
    with pytest.raises(OSError):
        check_model(str(FIXTURES / "absent"))


def test_cycles_command_exit_codes(capsys) -> None:
    from vqs.cli import main as vqs_main
    assert vqs_main(["cycles", LOOPY]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["acyclic"] is False
    assert vqs_main(["cycles", CLEAN]) == 0
    assert vqs_main(["cycles", str(FIXTURES / "absent")]) == 2

def test_single_line_let_shapes() -> None:
    from vqs.powerbi.cycles import within_let_cycles
    # Acyclic single-line let: no spurious self-cycle (was [['a','a']]).
    assert within_let_cycles("let a = 1, b = a + 1 in b") == []
    # True single-line 2-cycle keeps its shape (was [['a','a']]).
    assert within_let_cycles("let a = b, b = a in a") == [["a", "b", "a"]]
    # "in" inside literals/comments cannot truncate scope.
    assert within_let_cycles(
        'let a = "x in y" /* in, b = a */, b = 1 in b') == []
    assert within_let_cycles("let a = 1 // in, b = a\n in a") == []
    assert "OneLine" not in [c.get("query")
                             for c in check_model(LOOPY)["let_cycles"]]


def test_quoted_identifier_edges() -> None:
    from vqs.powerbi.cycles import m_edges
    assert m_edges({"Q": 'x = #"My Query"', "My Query": "1"}) == {
        "Q": {"My Query"}, "My Query": set()}
    assert m_edges({"Q": 'x = #"Q" + 1'}) == {"Q": {"Q"}}


def test_dax_strings_ignored_and_dotted_names_exact() -> None:
    from vqs.powerbi.cycles import dax_objects
    nodes = dax_objects(LOOPY)
    assert ("measure", "Loop", "A.B") in nodes
    result = check_model(LOOPY)
    assert result["dax_cycles"] == [
        ["measure:Loop.A", "measure:Loop.B", "measure:Loop.A"],
        ["measure:Loop.LoopSelf", "measure:Loop.LoopSelf"]]


def test_empty_model_warns_on_stderr(tmp_path, capsys) -> None:
    from vqs.cli import main as vqs_main
    assert vqs_main(["cycles", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["acyclic"] is True
    assert "nothing to check" in captured.err
