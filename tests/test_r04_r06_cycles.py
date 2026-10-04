"""R04-R06 RED: honest TMDL/M grammar coverage and lexical cycle graphs.

Extractor issues must reach check_model coverage (block, never
acyclic-pass); TMDL keywords are case-insensitive; repeated
quoted M identifiers share one identity; per-query let names
shadow shared queries. Every failing test here is red on the
pre-R3 gate and green after the fix; controls pass throughout.
"""
from pathlib import Path

import pytest

from vqs.data.tmdl import extract_objects
from vqs.powerbi.cycles import check_model, m_edges, within_let_cycles


def _model(root: Path, files: dict[str, str]) -> str:
    model = root / "M.SemanticModel"
    for rel, text in files.items():
        target = model / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return str(model)


def test_orphan_declaration_blocks_model(tmp_path: Path) -> None:
    """RED R04: a dropped orphan declaration narrows the graph: block."""
    text = "\tmeasure Lost = 1\ntable T\n\tmeasure B = 2\n"
    assert any(issue["rule"] == "orphan_declaration"
               for issue in extract_objects(text)["issues"])
    with pytest.raises(OSError):
        check_model(_model(tmp_path, {"tables/T.tmdl": text}))


def test_unclosed_backtick_blocks_model(tmp_path: Path) -> None:
    """RED R04: an unclosed backtick fence blocks, never parses through."""
    text = "table T\n\tmeasure A = ```\nIF('T'[B] = 1, 1, 0)\n"
    with pytest.raises(OSError):
        check_model(_model(tmp_path, {"tables/T.tmdl": text}))


def test_uppercase_declarations_match_lowercase(tmp_path: Path) -> None:
    """RED R04: TABLE/MEASURE parse exactly like table/measure."""
    lower = "table T\n\tmeasure A = IF('T'[B] = 1, 1, 0)\n\tmeasure B = 2\n"
    upper = "TABLE T\n\tMEASURE A = IF('T'[B] = 1, 1, 0)\n\tMEASURE B = 2\n"
    assert extract_objects(upper)["tables"] == extract_objects(lower)["tables"]
    assert check_model(_model(tmp_path / "u", {"tables/T.tmdl": upper})) == \
        check_model(_model(tmp_path / "l", {"tables/T.tmdl": lower}))


def test_quoted_let_cycle_detected() -> None:
    """RED R05: repeated quoted identifiers share one identity."""
    cycles = within_let_cycles(
        'let #"a x" = #"b x", #"b x" = #"a x" in #"a x"')
    assert {frozenset(cycle) for cycle in cycles} == {frozenset({"a x", "b x"})}


def test_bare_and_quoted_cycles_agree() -> None:
    """Bare passes now (control); quoted must agree after the fix."""
    bare = within_let_cycles("let a = b, b = a in a")
    assert {frozenset(cycle) for cycle in bare} == {frozenset({"a", "b"})}
    quoted = within_let_cycles('let #"a" = #"b", #"b" = #"a" in #"a"')
    assert {frozenset(cycle) for cycle in quoted} == {frozenset({"a", "b"})}


def test_acyclic_let_stays_acyclic() -> None:
    """Control: a genuine DAG reports no cycle."""
    assert within_let_cycles("let a = 1, b = a in b") == []


def test_let_binding_shadows_shared_query() -> None:
    """RED R06: local `let Q` is not a global Q->Q cycle."""
    assert m_edges({"Q": "let Q = 1 in Q"}) == {"Q": set()}


def test_shared_query_recursion_detected() -> None:
    """Control: real cross-query recursion still reports edges."""
    edges = m_edges({"A": "B + 1", "B": "A + 1"})
    assert edges == {"A": {"B"}, "B": {"A"}}
