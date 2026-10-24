"""Regression for accessibility preflight; no image-model inference."""
from __future__ import annotations

import pytest

from vqs.series_readability import (
    categorical_series_findings,
    distance,
    lab,
)


def test_machado_deutan_matrix_is_applied_in_linear_rgb() -> None:
    # Pure sRGB red is linear (1,0,0). The deutan Machado transform is
    # (.367322,.280085,-.011820), clamped to (.,.,0).
    # The subsequent D65 XYZ / CIELAB transform has known reference values.
    l_value, a_value, b_value = lab("#FF0000", "deutan")
    assert l_value == pytest.approx(59.745983, abs=.001)
    assert a_value == pytest.approx(-5.426304, abs=.001)
    assert b_value == pytest.approx(63.842563, abs=.001)
    # In particular gamma-encoding a matrix product *before* XYZ wrongly
    # produces a much lower L*, so this is a useful non-regression witness.
    assert l_value > 55


def test_gray_palette_collision_is_explicit_and_line_pair_is_strict() -> None:
    colors = ["#777777", "#797979", "#7B7B7B",
              "#7D7D7D", "#808080", "#838383"]
    findings = categorical_series_findings(colors)
    assert findings
    assert findings[0]["series_indices"] == [0, 1]
    assert "normal" in findings[0]["simulations_below_threshold"]
    assert findings[0]["thresholds"] == {"normal": 43., "cvd": 19.}


def test_distinct_pair_is_not_a_visual_release_claim() -> None:
    assert distance("#B93847", "#2B5F82") > 43
    assert categorical_series_findings(["#B93847", "#2B5F82"]) == []
