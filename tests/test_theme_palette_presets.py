"""Palette design contracts: verified on GitHub-hosted CI, not local workstation."""
from pathlib import Path

import pytest

from vqs.theme import contrast_ratio, load_palette, palette_contrast_check, relative_luminance

PRESETS = Path(__file__).resolve().parents[1] / "examples" / "theme-palettes"
NAMES = ("dark-graphite-mint", "dark-warm-basalt", "dark-slate-lavender")


@pytest.mark.parametrize("name", NAMES)
def test_flat_colorway_dark_accessibility(name: str) -> None:
    palette = load_palette("dark", PRESETS / f"{name}.json")
    assert palette_contrast_check(palette) == []
    # Restrained dark surfaces: visual elevation is tonal, not a blue cast.
    assert relative_luminance(palette["canvas"]) < relative_luminance(palette["surface"])
    assert relative_luminance(palette["surface"]) < relative_luminance(palette["surfaceElevated"])
    assert contrast_ratio(palette["foreground"], palette["surface"]) >= 4.5
    for color in palette["dataColors"]:
        assert contrast_ratio(color, palette["surface"]) >= 3.0


@pytest.mark.parametrize("name", NAMES)
def test_new_dark_colorway_does_not_change_light_mode(name: str) -> None:
    original = load_palette("light", None)
    from_custom = load_palette("light", PRESETS / f"{name}.json")
    assert from_custom == original


def test_graphite_muted_chrome_is_neutral_not_navy() -> None:
    graphite = load_palette("dark", PRESETS / "dark-graphite-mint.json")
    # Charcoal surface RGB channels should be near-neutral.
    rgb = [int(graphite["surface"][i:i+2], 16) for i in (1, 3, 5)]
    assert max(rgb) - min(rgb) <= 9
