"""Research-backed chart-palette regression gates (GitHub-hosted only).

CIE76 is a conservative RGB->XYZ->Lab check, not a color-vision-deficiency
certification. Actual chart values and line identity remain tested elsewhere.
"""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import pytest

from vqs.theme import (
    build_plan,
    contrast_ratio,
    load_palette,
    relative_luminance,
)

CONTOSO = (Path(__file__).resolve().parents[1]
           / "examples/contoso-retail/Contoso Retail.Report")
DARK_PRESETS = ("executive-blue", "graphite-mint", "warm-basalt",
                "slate-lavender")


def _lab(color: str) -> tuple[float, float, float]:
    """D65 CIELAB coordinates from an RGB hex value."""
    rgb = [int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045
              else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    x = (.4124564 * linear[0] + .3575761 * linear[1]
         + .1804375 * linear[2]) / .95047
    y = .2126729 * linear[0] + .7151522 * linear[1] + .0721750 * linear[2]
    z = (.0193339 * linear[0] + .1191920 * linear[1]
         + .9503041 * linear[2]) / 1.08883

    def f(value: float) -> float:
        return value ** (1 / 3) if value > .008856 else (7.787 * value + 16 / 116)

    return (116 * f(y) - 16, 500 * (f(x) - f(y)),
            200 * (f(y) - f(z)))


def _distance(left: str, right: str) -> float:
    a, b = _lab(left), _lab(right)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


@pytest.mark.parametrize("preset", DARK_PRESETS)
def test_dark_chart_colors_visible_coherent_distinct(preset: str) -> None:
    palette = load_palette("dark", None, preset)
    series = palette["dataColors"]
    assert len(series) == 8 and len(set(series)) == 8
    # Visual nontext contrast vs the *card*, not the report canvas.
    assert all(contrast_ratio(color, palette["surface"]) >= 3
               for color in series)
    # Especially safeguard the frequently used first four series.
    assert all(_distance(series[i], series[j]) >= 20
               for i, j in itertools.combinations(range(4), 2))
    # Avoid near duplicates anywhere in the eight-category fallback.
    assert all(_distance(series[i], series[j]) >= 15
               for i, j in itertools.combinations(range(8), 2))
    # Value ramps encode magnitude through increasing luminance.
    assert (relative_luminance(palette["gradientMin"])
            < relative_luminance(palette["gradientCenter"])
            < relative_luminance(palette["gradientMax"]))
    assert contrast_ratio(palette["gradientMin"], palette["surface"]) >= 2.8


def test_dark_presets_have_independent_chart_identity() -> None:
    palettes = {name: load_palette("dark", None, name)
                for name in DARK_PRESETS}
    for a, b in itertools.combinations(DARK_PRESETS, 2):
        assert palettes[a]["dataColors"] != palettes[b]["dataColors"]
        assert palettes[a]["dataColors"][0] != palettes[b]["dataColors"][0]
        assert palettes[a]["gradientMin"] != palettes[b]["gradientMin"]
        assert palettes[a]["gradientMax"] != palettes[b]["gradientMax"]


def test_white_light_theme_remains_untouched() -> None:
    light = load_palette("light", None)
    assert light["canvas"] == "#E9EEF4"
    assert light["dataColors"] == [
        "#2563EB", "#0E7490", "#047857", "#B45309",
        "#BE123C", "#6D28D9", "#0F766E", "#9D174D",
    ]
    for preset in DARK_PRESETS:
        assert load_palette("light", None, preset) == light


@pytest.mark.parametrize("preset", DARK_PRESETS)
def test_contoso_chart_ramps_use_distinct_preset_stops(preset: str) -> None:
    colors = load_palette("dark", None, preset)
    plan = build_plan(CONTOSO, "dark", colors)
    changes = [c for c in plan["changes"]
               if c.get("role") in ("gradientMin", "gradientMax")]
    assert len(changes) >= 2  # genuine Shape Map gradient only
    assert all(c["new"] == colors[c["role"]] for c in changes)
    assert any(c.get("visualType") == "shapeMap" for c in changes)
    # The sample's categorical columns now encode identity using colors;
    # the Shape Map retains the actual quantitative numeric gradient.
    assert not any("/Conditional/" in c["pointer"] for c in changes)
