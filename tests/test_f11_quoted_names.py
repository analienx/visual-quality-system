"""F11 RED: '=' inside legal quoted TMDL names must not split declarations.

extract_objects uses rest.partition('='), so `measure 'A=B' = [Y]`
becomes the wrong name/expression and can hide the return edge of
`Y=[A=B]`. M2 parses the delimiter outside quoted identifiers with
apostrophe escaping; inventory, binding, and cycles stay exact for
measures and calculated columns.
"""
from pathlib import Path

from vqs.data.tmdl import check_bindings, extract_objects, inventory_model
from vqs.powerbi.cycles import check_model


def _model(root: Path, files: dict[str, str]) -> str:
    model = root / "M.SemanticModel"
    for rel, text in files.items():
        target = model / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return str(model)


def test_f11_quoted_equals_measure_inventory() -> None:
    """RED: quoted measure name keeps its '='; body is the DAX."""
    extracted = extract_objects("table T\n\tmeasure 'A=B' = [Y]\n")
    assert extracted["tables"]["T"]["measures"] == {"A=B": "[Y]"}


def test_f11_quoted_equals_column_inventory() -> None:
    """RED: quoted calculated-column name keeps its '='."""
    extracted = extract_objects("table T\n\tcolumn 'C=D' = [Y] + 1\n")
    assert extracted["tables"]["T"]["columns"] == {"C=D": "[Y] + 1"}


def test_f11_apostrophe_escaping_control() -> None:
    """Control (passes now): doubled apostrophes already unescape."""
    extracted = extract_objects("table T\n\tmeasure 'O''Brien' = [X]\n")
    assert extracted["tables"]["T"]["measures"] == {"O'Brien": "[X]"}


def test_f11_quoted_equals_cycle_found(tmp_path: Path) -> None:
    """RED: the return edge of Y=[A=B] must close the cycle."""
    model = _model(tmp_path, {"tables/T.tmdl":
                              "table T\n"
                              "\tmeasure 'A=B' = [Y]\n"
                              "\tmeasure Y = [A=B]\n"})
    result = check_model(model)
    assert result["acyclic"] is False
    assert result["dax_cycles"] != []


def test_f11_quoted_equals_binding_resolves(tmp_path: Path) -> None:
    """RED: queryRef to a quoted '=' measure must resolve."""
    model = _model(tmp_path, {"tables/T.tmdl":
                              "table T\n\tmeasure 'A=B' = [Y]\n"})
    inventory = inventory_model(model)
    findings = check_bindings([{"query_ref": "T.A=B"}], inventory)
    assert findings == [{"rule": "binding_resolved", "status": "pass",
                         "query_ref": "T.A=B"}]
