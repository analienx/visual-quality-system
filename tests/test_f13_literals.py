"""F13 RED: DAX strings/comments must not create reference edges.

dax_edges runs qualified-reference matching before string/comment
cleaning, so `A.X="'B'[Y]"; B.Y='A'[X]` incorrectly cycles, and
comments do the same. M2 lexes literals/comments without destroying
genuine quoted table identifiers, then extracts references: the same
token inside and outside a literal/comment must yield different edge
sets.
"""
from pathlib import Path

from vqs.powerbi.cycles import check_model, dax_edges


def _model(root: Path, files: dict[str, str]) -> str:
    model = root / "M.SemanticModel"
    for rel, text in files.items():
        target = model / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return str(model)


def _objects(m1: str) -> dict:
    return {("measure", "T", "M1"): m1,
            ("measure", "T", "M2"): "'B'[C]",
            ("measure", "B", "C"): "1"}


def test_f13_string_token_adds_no_edge() -> None:
    """RED: a qualified ref inside a string literal adds no edge."""
    edges = dax_edges(_objects("\"'B'[C]\""))
    assert edges[("measure", "T", "M1")] == set()
    assert edges[("measure", "T", "M2")] == {("measure", "B", "C")}


def test_f13_line_comment_token_adds_no_edge() -> None:
    """RED: a qualified ref inside a // comment adds no edge."""
    edges = dax_edges(_objects("// 'B'[C]\n1"))
    assert edges[("measure", "T", "M1")] == set()


def test_f13_block_comment_token_adds_no_edge() -> None:
    """RED: a qualified ref inside a /* */ comment adds no edge."""
    edges = dax_edges(_objects("/* 'B'[C] */ 1"))
    assert edges[("measure", "T", "M1")] == set()


def test_f13_string_only_cross_refs_stay_acyclic(tmp_path: Path) -> None:
    """RED: the finding's string-only cross-reference pair is acyclic."""
    model = _model(tmp_path, {
        "tables/A.tmdl": "table A\n\tmeasure X = \"'B'[Y]\"\n",
        "tables/B.tmdl": "table B\n\tmeasure Y = \"'A'[X]\"\n"})
    result = check_model(model)
    assert result["acyclic"] is True
    assert result["dax_cycles"] == []


def test_f13_genuine_qualified_cycle_control(tmp_path: Path) -> None:
    """Control (passes now): real qualified cross-refs still cycle."""
    model = _model(tmp_path, {
        "tables/A.tmdl": "table A\n\tmeasure X = 'B'[Y] + 1\n",
        "tables/B.tmdl": "table B\n\tmeasure Y = 'A'[X] + 1\n"})
    result = check_model(model)
    assert result["acyclic"] is False
    assert result["dax_cycles"] != []
