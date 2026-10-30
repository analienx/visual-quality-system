"""Native region G4 proof must reject false UIA or DAX matches."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from vqs.powerbi.corporate_region_acceptance import validate_step


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
