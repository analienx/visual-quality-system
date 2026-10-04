"""F12 RED: triple-backtick TMDL expression blocks must parse verbatim.

extract_objects joins triple-double-quote spans, not actual
triple-backtick blocks, so flush-left DAX inside backticks is
discarded while the gate reports complete coverage and acyclicity.
M2 parses actual blocks verbatim (or blocks unsupported/unclosed
syntax): ordinary indented and backtick-delimited versions of a
cyclic expression must produce identical graphs.
"""
from pathlib import Path

import pytest

from vqs.data.tmdl import extract_objects
from vqs.powerbi.cycles import check_model


def _model(root: Path, files: dict[str, str]) -> str:
    model = root / "M.SemanticModel"
    for rel, text in files.items():
        target = model / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return str(model)


PLAIN_CYCLE = ("table T\n"
               "\tmeasure A = IF('T'[B] = 1, 1, 0)\n"
               "\tmeasure B = IF('T'[A] = 1, 1, 0)\n")

BACKTICK_CYCLE = ("table T\n"
                  "\tmeasure A = ```\n"
                  "IF('T'[B] = 1, 1, 0)\n"
                  "\t```\n"
                  "\tmeasure B = ```\n"
                  "IF('T'[A] = 1, 1, 0)\n"
                  "\t```\n")


def _cycle_nodes(result: dict) -> set[frozenset[str]]:
    return {frozenset(cycle) for cycle in result["dax_cycles"]}


def test_f12_backtick_cycle_matches_plain_cycle(tmp_path: Path) -> None:
    """RED: backtick-delimited and plain cyclic graphs must be identical."""
    plain = check_model(_model(tmp_path / "plain", {"tables/T.tmdl": PLAIN_CYCLE}))
    assert plain["acyclic"] is False
    ticked = check_model(_model(tmp_path / "ticked", {"tables/T.tmdl": BACKTICK_CYCLE}))
    assert ticked["acyclic"] is False
    assert _cycle_nodes(ticked) == _cycle_nodes(plain)


def test_f12_unclosed_backtick_blocks(tmp_path: Path) -> None:
    """RED: an unclosed backtick block must issue or block, never vanish."""
    text = "table T\n\tmeasure A = ```\nIF('T'[B] = 1, 1, 0)\n"
    issues = extract_objects(text)["issues"]
    model = _model(tmp_path, {"tables/T.tmdl": text})
    try:
        check_model(model)
        blocked = False
    except OSError:
        blocked = True
    assert issues != [] or blocked
