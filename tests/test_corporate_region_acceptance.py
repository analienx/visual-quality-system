"""Native region G4 proof must reject false UIA or DAX matches."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from vqs.powerbi.corporate_region_acceptance import run, validate_step


@pytest.fixture
def example(tmp_path: Path):
    pbip = tmp_path / "Corporate Spend.pbip"
    pbip.write_text("{}", encoding="utf8")
    record = {
        "schema": "vqs.native-corporate-region-uia/1",
        "pid": 88,
        "pbip": str(pbip.resolve()),
        "control_name": "Sales Region",
        "before": "Europe",
        "target": "Latin America",
        "observed": "Latin America ",
        "action": "TogglePattern + ExpandCollapsePattern.Collapse",
        "selected_target": True,
        "other_region_unselected": True,
        "variance_pct_ui": -13.08,
    }
    model = {"Europe": 0.0678, "Latin America": -0.1308}
    return pbip, record, model


def test_real_native_card_matches_only_selected_region(example):
    pbip, receipt, values = example
    result = validate_step(
        receipt, values, expected="Latin America", prior="Europe",
        pid=88, pbip=pbip,
    )
    assert result["native_value_committed"]
    assert result["rendered_kpi_matches_independent_dax"]
    assert result["different_from_other_region"]


@pytest.mark.parametrize(("path", "value"), [
    ("pid", 89),
    ("pbip", "C:/different.pbip"),
    ("control_name", "Other Slicer"),
    ("before", "Latin America"),
    ("observed", "Europe"),
    ("target", "Europe"),
    ("action", "InvokePattern"),
    ("selected_target", False),
    ("other_region_unselected", False),
    ("variance_pct_ui", 6.78),
    ("variance_pct_ui", float("nan")),
    ("schema", "untrusted"),
])
def test_native_receipts_fail_closed(example, path, value):
    pbip, receipt, values = example
    damaged = copy.deepcopy(receipt)
    damaged[path] = value
    with pytest.raises(ValueError):
        validate_step(
            damaged, values, expected="Latin America", prior="Europe",
            pid=88, pbip=pbip,
        )


def test_missing_or_indistinguishable_dax_blocks(example):
    pbip, receipt, values = example
    for fake in (
        {"Europe": values["Europe"]},
        {"Europe": values["Latin America"], "Latin America": values["Latin America"]},
        {"Europe": 0.0678, "Latin America": 0.0},
        {"Europe": float("nan"), "Latin America": -0.1308},
    ):
        with pytest.raises(ValueError):
            validate_step(receipt, fake, expected="Latin America",
                          prior="Europe", pid=88, pbip=pbip)


@pytest.mark.parametrize("wrappers", [0, 2])
def test_run_requires_exactly_one_pbip_before_any_native_action(
        tmp_path: Path, wrappers: int) -> None:
    """No/ambiguous wrappers fail as ValueError (a blocked receipt), never
    StopIteration or an arbitrary first-glob pick."""
    for index in range(wrappers):
        (tmp_path / f"R{index}.pbip").write_text("{}", encoding="utf8")
    with pytest.raises(ValueError, match="exactly one PBIP"):
        run(tmp_path, 88, {}, adapter=tmp_path / "missing.ps1")


def test_receipt_path_compares_physical_file_not_string(example, tmp_path: Path) -> None:
    """The OS reports the launch casing; Path.resolve() the on-disk one."""
    pbip, record, model = example
    other = tmp_path / "Other.pbip"
    other.write_text("{}", encoding="utf8")
    record["pbip"] = str(pbip.parent / "." / pbip.name)
    assert validate_step(record, model, expected="Latin America",
                         prior="Europe", pid=88, pbip=pbip)
    record["pbip"] = str(other)
    with pytest.raises(ValueError, match="target selection"):
        validate_step(record, model, expected="Latin America",
                      prior="Europe", pid=88, pbip=pbip)


@pytest.mark.skipif(__import__("os").name != "nt",
                    reason="case-insensitive Windows filesystem only")
def test_receipt_accepts_launch_casing_on_windows(example) -> None:
    pbip, record, model = example
    record["pbip"] = str(pbip).swapcase()
    assert validate_step(record, model, expected="Latin America",
                         prior="Europe", pid=88, pbip=pbip)
