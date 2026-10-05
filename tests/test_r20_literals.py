"""R20 RED: precision range on real PBIR string literals.

QueryLiteralExpression.Value is a string: 'banana' and '99999'
must be rejected for axis.precision while legal '0'-'15' binds;
old and new are both validated. All red pre-R3, green after.
"""
import pytest

from vqs.repair.recipes import RecipeError, bind_leaf

PATH = ["visual", "objects", "labels", "properties", "precision",
        "expr", "Literal", "Value"]


def _doc(old: object) -> dict:
    return {"visual": {"objects": {"labels": {"properties": {
        "precision": {"expr": {"Literal": {"Value": old}}}}}}}}


def _op(value: object) -> dict:
    return {"type": "axis.precision",
            "selector": {"page": "P1", "visual": "v1"},
            "path": list(PATH), "value": value}


def test_banana_precision_rejected() -> None:
    """RED R20: a non-numeric precision string must not bind."""
    with pytest.raises(RecipeError, match="precision"):
        bind_leaf(_op("banana"), _doc("1"))


def test_out_of_range_precision_rejected() -> None:
    """RED R20: '99999' is outside integer 0-15."""
    with pytest.raises(RecipeError, match="precision"):
        bind_leaf(_op("99999"), _doc("1"))


def test_malformed_old_precision_rejected() -> None:
    """RED R20: the bound old value is validated too."""
    with pytest.raises(RecipeError, match="precision"):
        bind_leaf(_op("2"), _doc("banana"))


def test_legal_precision_binds() -> None:
    """Control: '2' for '1' binds with the recorded old/new."""
    bound = bind_leaf(_op("2"), _doc("1"))
    assert (bound["old"], bound["new"]) == ("1", "2")


def test_raw_number_old_precision_rejected() -> None:
    """T12/S17: a raw JSON number old literal blocks at bind."""
    with pytest.raises(RecipeError, match="old precision"):
        bind_leaf(_op(1), _doc(1))


def test_padded_precision_rejected() -> None:
    """T12: '007' is not canonical and must not bind."""
    with pytest.raises(RecipeError, match="precision"):
        bind_leaf(_op("007"), _doc("1"))


def test_unicode_digit_precision_rejected() -> None:
    """T12: non-ASCII digits are not precision literals."""
    with pytest.raises(RecipeError, match="precision"):
        bind_leaf(_op("²"), _doc("1"))
