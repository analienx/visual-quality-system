"""S04-S05: lexical let scoping, case-equivalent extraction, declaration accounting.

S04: a nested let binds only its own body (outer shared-name
references stay global); unbalanced scopes block structured.
S05: EXPRESSION/PARTITION extraction is case-equivalent and every
declared query/partition is accounted for (dropped declarations
block instead of passing narrowed). CLI exit codes go through the
installed entry point.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs.powerbi.cycles import find_cycles, m_edges, m_queries

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")


def _model(root: Path, expressions: str = "",
           tables: dict[str, str] | None = None) -> Path:
    model = root / "M.Model"
    (model / "tables").mkdir(parents=True, exist_ok=True)
    if expressions:
        (model / "expressions.tmdl").write_text(expressions,
                                                encoding="utf-8")
    for name, text in (tables or {}).items():
        (model / "tables" / name).write_text(text, encoding="utf-8")
    return model


def test_nested_let_free_global_cycle_detected() -> None:
    """S04: outer B stays global, so the A<->B loop is detected."""
    queries = {"A": "B + (let B = 1 in B)", "B": "A"}
    assert m_edges(queries) == {"A": {"B"}, "B": {"A"}}
    assert find_cycles(m_edges(queries)) == [["A", "B", "A"]]


def test_root_shadow_stays_acyclic() -> None:
    """S04 positive: leading-let bindings are local throughout."""
    assert m_edges({"Q": "let Q = 1 in Q"}) == {"Q": set()}


def test_trailing_outer_reference_stays_global() -> None:
    """S04: text after a nested body belongs to the ancestor scope."""
    queries = {"A": "f(let D = 1 in D) + B", "B": "1"}
    assert m_edges(queries) == {"A": {"B"}, "B": set()}


def test_unbalanced_nested_body_blocked() -> None:
    """S04: indelimitable scope raises instead of mis-resolving."""
    from vqs.powerbi.cycles import ModelingError
    with pytest.raises(ModelingError, match="unbalanced"):
        m_edges({"A": "f(let B = 1 in (B"})


def test_uppercase_expression_cycle_detected(tmp_path: Path) -> None:
    """S05: EXPRESSION declarations extract case-equivalently."""
    model = _model(tmp_path, "EXPRESSION A = B\nEXPRESSION B = A\n",
                   {"T.tmdl": "table T\n"})
    assert set(m_queries(str(model))) == {"A", "B"}
    assert find_cycles(m_edges(m_queries(str(model)))) == [["A", "B", "A"]]


def test_uppercase_partition_extracted(tmp_path: Path) -> None:
    """S05: PARTITION declarations extract case-equivalently."""
    model = _model(tmp_path, "",
                   {"T.tmdl": "table T\n\tPARTITION P1 = M\n\tmode: import\n"})
    assert m_queries(str(model)) == {"T|P1": "\n"}


def test_unextractable_expression_blocks(tmp_path: Path) -> None:
    """S05: a declaration the extractor drops blocks coverage."""
    from vqs.powerbi.cycles import check_model
    model = _model(tmp_path, "expression NoEquals\n",
                   {"T.tmdl": "table T\n"})
    with pytest.raises(OSError, match="unextracted_expression"):
        check_model(str(model))


def test_non_m_partition_blocks(tmp_path: Path) -> None:
    """S05: non-m partition kinds are unsupported and block."""
    from vqs.powerbi.cycles import check_model
    model = _model(tmp_path, "",
                   {"T.tmdl": "table T\n\tpartition P1 = dataSource\n"})
    with pytest.raises(OSError, match="unextracted_partition"):
        check_model(str(model))


@needs_vqs
def test_installed_cycles_uppercase_loop_exit_1(tmp_path: Path) -> None:
    """S05+C02: installed cycles reports the uppercase loop (exit 1)."""
    model = _model(tmp_path, "EXPRESSION A = B\nEXPRESSION B = A\n",
                   {"T.tmdl": "table T\n"})
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 1, completed.stderr
    assert json.loads(completed.stdout)["m_cycles"] == [["A", "B", "A"]]


@needs_vqs
def test_installed_cycles_shadow_exit_0(tmp_path: Path) -> None:
    """S04+C02 positive: installed cycles passes root shadowing."""
    model = _model(tmp_path, "expression Q = let Q = 1 in Q\n",
                   {"T.tmdl": "table T\n"})
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["acyclic"] is True


@needs_vqs
def test_installed_cycles_unbalanced_exit_2(tmp_path: Path) -> None:
    """S04+C02: indelimitable scope is blocked exit 2, no traceback."""
    model = _model(tmp_path, "expression A = f(let B = 1 in (B\n",
                   {"T.tmdl": "table T\n"})
    completed = subprocess.run([VQS_BIN, "cycles", str(model)],
                               capture_output=True, text=True, timeout=120,
                               check=False)
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout)["status"] == "blocked"
    assert "Traceback" not in (completed.stderr + completed.stdout)
