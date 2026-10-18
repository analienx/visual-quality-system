"""T03: nested let fragments must not hide or invent cycles.

Routes: m_edges/within_let_cycles/check_model plus the installed
`vqs cycles` entry point (exit 2 = blocked, never a wrong graph).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs.powerbi.cycles import (
    ModelingError,
    check_model,
    find_cycles,
    m_edges,
    within_let_cycles,
)

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")


def _model(root: Path, expressions: str) -> Path:
    model = root / "M.Model"
    (model / "tables").mkdir(parents=True, exist_ok=True)
    (model / "expressions.tmdl").write_text(expressions, encoding="utf-8")
    (model / "tables" / "T.tmdl").write_text("table T\n", encoding="utf-8")
    return model


def test_hidden_local_loop_blocked() -> None:
    """T03 case 1: nested let hides root bindings -> block, never acyclic."""
    code = "let a = b, x = (let c = 1 in c), b = a in a"
    with pytest.raises(ModelingError, match="nested let"):
        within_let_cycles(code)


def test_hidden_local_loop_model_blocked(tmp_path: Path) -> None:
    """T03 case 1 through check_model: the gate blocks, not passes."""
    model = _model(tmp_path,
                   "expression Q = let a = b, x = (let c = 1 in c), "
                   "b = a in a\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


@needs_vqs
def test_installed_cycles_hidden_loop_exit_2(tmp_path: Path) -> None:
    """T03 case 1 installed: exit 2 with reason, no traceback verdict."""
    model = _model(tmp_path,
                   "expression Q = let a = b, x = (let c = 1 in c), "
                   "b = a in a\n")
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout)["status"] == "blocked"


def test_false_global_loop_passes() -> None:
    """T03 case 2: root binding B shadows global B -> no invented cycle."""
    queries = {"A": "let x = (let y = 1 in y), B = 1 in B", "B": "A"}
    assert m_edges(queries) == {"A": set(), "B": {"A"}}
    assert find_cycles(m_edges(queries)) == []


def test_false_global_loop_model_blocked(tmp_path: Path) -> None:
    """T03 case 2 through check_model: explicitly blocked (nested bindings
    exceed let-cycle analysis), never a false cycle. The m_edges graph
    itself is correctly acyclic (see test_false_global_loop_passes)."""
    model = _model(tmp_path,
                   "expression A = let x = (let y = 1 in y), B = 1 in B\n"
                   "expression B = A\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


@needs_vqs
def test_installed_cycles_nested_shadow_exit_2(tmp_path: Path) -> None:
    """T03 case 2 installed: explicitly blocked exit 2, no false cycle."""
    model = _model(tmp_path,
                   "expression A = let x = (let y = 1 in y), B = 1 in B\n"
                   "expression B = A\n")
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout)["status"] == "blocked"


def test_nonleading_nested_bindings_no_false_edge() -> None:
    """T03: nested scope split across fragment+rest still masks B."""
    queries = {"Q": "f(let x = (let y = 1 in y), B = 1 in B)",
               "B": "1"}
    assert m_edges(queries) == {"Q": set(), "B": set()}


def test_root_cycle_without_nesting_detected(tmp_path: Path) -> None:
    """T03 control: plain root a<->b loop still detected (exit 1)."""
    assert within_let_cycles("let a = b, b = a in a") == [["a", "b", "a"]]
    model = _model(tmp_path, "expression Q = let a = b, b = a in a\n")
    report = check_model(str(model))
    assert report["acyclic"] is False
    assert report["let_cycles"] != []


def test_local_global_same_name_cycle_detected(tmp_path: Path) -> None:
    """T03 control: outer B stays global, so A<->B is a real cycle."""
    queries = {"A": "B + (let B = 1 in B)", "B": "A"}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]
    model = _model(tmp_path,
                   "expression A = B + (let B = 1 in B)\n"
                   "expression B = A\n")
    assert check_model(str(model))["acyclic"] is False


def test_genuine_acyclic_nesting_passes(tmp_path: Path) -> None:
    """T03 control: sequential nesting with no loop stays acyclic."""
    assert m_edges({"Q": "(let b = 2 in b) + 1"}) == {"Q": set()}
    assert within_let_cycles("(let b = 2 in b) + 1") == []
    model = _model(tmp_path, "expression Q = (let b = 2 in b) + 1\n")
    assert check_model(str(model))["acyclic"] is True


def test_deep_nesting_blocked() -> None:
    """T03: three-level nesting in bindings blocks, never mis-resolves."""
    code = "let a = (let b = (let c = 1 in c) in b) in a"
    with pytest.raises(ModelingError, match="beyond supported depth"):
        m_edges({"Q": code})
    with pytest.raises(ModelingError, match="nested let"):
        within_let_cycles(code)


def test_trailing_outer_ref_after_nested_let_detected() -> None:
    """T03: trailing global B past the nested scope end stays an edge."""
    queries = {"A": "(let B = (let C = 1 in C) in B) + B", "B": "A"}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]


def test_trailing_outer_ref_model_blocked(tmp_path: Path) -> None:
    """T03: trailing-outer shape blocks at the gate (nested bindings)."""
    model = _model(tmp_path,
                   "expression A = (let B = (let C = 1 in C) in B) + B\n"
                   "expression B = A\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


@needs_vqs
def test_installed_cycles_trailing_outer_exit_2(tmp_path: Path) -> None:
    """T03 installed: trailing-outer shape blocks exit 2, no wrong graph."""
    model = _model(tmp_path,
                   "expression A = (let B = (let C = 1 in C) in B) + B\n"
                   "expression B = A\n")
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout)["status"] == "blocked"


def test_fragment_outer_ref_detected() -> None:
    """T03: a global ref inside the fragment resolves outward, not masked."""
    queries = {"A": "(let C = B + (let D = 1 in D) in C)", "B": "A"}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]


def test_middle_closed_later_segment_outer_ref_detected() -> None:
    """T03: past a delimited scope end, later refs are outer edges."""
    queries = {"A": "(let B = (let C = 1 in C) in B) + "
                    "(let D = B in D)",
               "B": "A"}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]


def test_unclosed_middle_later_ref_blocked() -> None:
    """T03: middle-scope name past an undelimited end blocks, not guesses."""
    code = ("X + (let B = (let C = 1 in C) in B + "
            "let D = B in D)")
    with pytest.raises(ModelingError, match="cannot be delimited"):
        m_edges({"A": code, "X": "1", "B": "1"})


def test_sibling_deeper_lets_trailing_outer_detected() -> None:
    """T03/B1: middle `in` in a later rest still delimits the tail."""
    queries = {"A": "(let x = (let y = 1 in y) + (let z = 1 in z), "
                    "B = 1 in B) + B",
               "B": "A"}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]


def test_sibling_deeper_lets_model_blocked(tmp_path: Path) -> None:
    """T03/B1 through check_model: the gate blocks nested bindings."""
    model = _model(tmp_path,
                   "expression A = (let x = (let y = 1 in y) + "
                   "(let z = 1 in z), B = 1 in B) + B\n"
                   "expression B = A\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


def test_enclosing_binding_in_deeper_scope_masked() -> None:
    """T03/B2: enclosing middle binding inside a deeper let is inner."""
    queries = {"A": "(let B = 1, x = (let D = B in D) in x)", "B": "A"}
    assert m_edges(queries) == {"A": set(), "B": {"A"}}
    assert find_cycles(m_edges(queries)) == []


def test_enclosing_binding_model_blocked(tmp_path: Path) -> None:
    """T03/B2 through check_model: explicitly blocked, never a cycle."""
    model = _model(tmp_path,
                   "expression A = (let B = 1, x = (let D = B in D) "
                   "in x)\n"
                   "expression B = A\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


def test_same_scope_sibling_in_fragment_masked() -> None:
    """T03/B3: later same-scope sibling in the fragment is inner."""
    queries = {"A": "(let x = B + (let y = 1 in y), B = 1 in B)",
               "B": "A"}
    assert m_edges(queries) == {"A": set(), "B": {"A"}}
    assert find_cycles(m_edges(queries)) == []


def test_same_scope_sibling_model_blocked(tmp_path: Path) -> None:
    """T03/B3 through check_model: explicitly blocked, never a cycle."""
    model = _model(tmp_path,
                   "expression A = (let x = B + (let y = 1 in y), "
                   "B = 1 in B)\n"
                   "expression B = A\n")
    with pytest.raises(ModelingError, match="nested let"):
        check_model(str(model))


def test_swallowed_middle_in_resolves() -> None:
    """T03: middle `in` inside an undelimited body still masks inner."""
    code = "Q + (let B = let C = 1 in C + 0 in B)"
    assert m_edges({"A": code, "Q": "1"}) == {"A": {"Q"}, "Q": set()}


def test_truncated_middle_scope_blocked() -> None:
    """T03: middle scope with no `in` anywhere blocks, never guesses."""
    code = "X + (let B = (let C = 1 in C) + B)"
    with pytest.raises(ModelingError, match="cannot be delimited"):
        m_edges({"A": code, "X": "1", "B": "1"})
