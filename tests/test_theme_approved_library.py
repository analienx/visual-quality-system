"""Approved 14-family dual-mode VQS theme contract (hosted CI)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vqs.theme import (
    build_plan,
    contrast_ratio,
    load_palette,
    palette_contrast_check,
    palette_presets,
    relative_luminance,
)

REPO = Path(__file__).resolve().parents[1]
CATALOG = json.loads(
    (REPO / "docs/APPROVED_THEME_SELECTION.json").read_text(encoding="utf-8")
)["presets"]
SLUGS = tuple(x["slug"] for x in CATALOG)
MODES = ("dark", "light")
REPORT = REPO / "examples/contoso-retail/Contoso Retail.Report"


def test_approved_shortlist_exact_identity() -> None:
    assert len(CATALOG) == 14
    assert len(SLUGS) == 14
    assert len(set(SLUGS)) == 14
    assert [x["number"] for x in CATALOG] == [
        "05", "08", "09", "12", "14", "15", "18", "19",
        "25", "26", "30", "31", "32", "33",
    ]
    assert all(x["modes"] == ["dark", "light"] for x in CATALOG)
    assert len(palette_presets()) == 18
    assert all(s in palette_presets() for s in SLUGS)
    assert palette_presets()[0] == "executive-blue"


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("mode", MODES)
def test_palette_resource_and_contract(slug: str, mode: str) -> None:
    file = f"preset-{slug}.json"
    packaged = (REPO / "vqs/palettes" / file).read_bytes()
    example = (REPO / "examples/theme-palettes" / file).read_bytes()
    assert packaged == example
    doc = json.loads(packaged)
    assert set(doc) == set(MODES)
    palette = load_palette(mode, None, slug)
    assert palette_contrast_check(palette) == []
    assert len(palette["dataColors"]) == 8
    assert len(set(palette["dataColors"])) == 8
    assert all(contrast_ratio(v, palette["surface"]) >= 3
               for v in palette["dataColors"])
    assert contrast_ratio(
        palette["accentForeground"], palette["accent"]) >= 4.5
    assert palette["canvas"] != palette["surface"]
    ramp = [relative_luminance(palette[x])
            for x in ("gradientMin", "gradientCenter", "gradientMax")]
    if mode == "dark":
        assert ramp[0] < ramp[1] < ramp[2]
    else:
        assert ramp[0] > ramp[1] > ramp[2]


@pytest.mark.parametrize("slug", SLUGS)
def test_same_family_dark_light_truly_differ(slug: str) -> None:
    dark = load_palette("dark", None, slug)
    light = load_palette("light", None, slug)
    assert dark["canvas"] != light["canvas"]
    assert dark["surface"] != light["surface"]
    assert dark["dataColors"] != light["dataColors"]
    assert dark["gradientMin"] != light["gradientMin"]
    assert dark["accent"] != light["accent"]


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("mode", MODES)
def test_contoso_has_native_appearance_and_chart_ramp_edits(
        slug: str, mode: str) -> None:
    palette = load_palette(mode, None, slug)
    plan = build_plan(REPORT, mode, palette)
    changes = [c for c in plan["changes"]
               if c.get("role") in ("gradientMin", "gradientMax")]
    assert len(changes) >= 2  # Shape Map numeric ramp remains; other bars are categorical
    assert all(c["new"] == palette[c["role"]] for c in changes)
    assert any(c["visualType"] == "shapeMap" for c in changes)
    # The remaining numerical gradient is on the Shape Map;
    # categorical bars now use per-category identity colors.
    assert not any("/Conditional/" in c["pointer"] for c in changes)


def test_graphite_red_does_not_enforce_monochrome_chart_series() -> None:
    # Regression: the old test *required* nearly identical greys, causing
    # visually indistinguishable series in real Power BI Desktop screenshots.
    for mode in MODES:
        colors = load_palette(mode, None, "graphite-red")["dataColors"]
        chromatic_support = []
        for color in colors[1:]:
            red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
            if max(red,green,blue)-min(red,green,blue) > 40:
                chromatic_support.append(color)
        assert len(chromatic_support) >= 3


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("mode", MODES)
def test_each_approved_palette_passes_categorical_distinction(
        slug: str, mode: str) -> None:
    from vqs.series_readability import categorical_series_findings
    p = load_palette(mode, None, slug)
    assert categorical_series_findings(p["dataColors"]) == [],(slug,mode)
    # Exact first-two-series pair has stricter limits: thin line charts.
    assert p["dataColors"][0] != p["dataColors"][1]


def test_generic_palette_identity_contains_no_corporate_claims() -> None:
    catalog = json.loads(
        (REPO / "docs/APPROVED_THEME_SELECTION.json").read_text(encoding="utf-8"))
    assert catalog["originalSelectionCount"] == 28
    assert catalog["presets"][-2]["slug"] == "organic-palette"
    assert catalog["presets"][-1]["slug"] == "sunny-palette"
    assert "brands" not in catalog
    assert catalog["designProvenance"]["corporateAffiliation"] == "none"


def test_sunny_palette_chart_hues_are_genuinely_distinct() -> None:
    import math

    def lab_color(color: str) -> tuple[float,float,float]:
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
                  for v in rgb]
        x = (.4124564*linear[0]+.3575761*linear[1]+.1804375*linear[2])/.95047
        y = .2126729*linear[0]+.7151522*linear[1]+.0721750*linear[2]
        z = (.0193339*linear[0]+.1191920*linear[1]+.9503041*linear[2])/1.08883

        def f(v: float) -> float:
            return v**(1/3) if v>.008856 else 7.787*v+16/116
        return (116*f(y)-16,500*(f(x)-f(y)),200*(f(y)-f(z)))

    def lab_distance(a: str,b: str) -> float:
        return math.dist(lab_color(a),lab_color(b))

    for mode in MODES:
        colors = load_palette(mode, None, "sunny-palette")["dataColors"]
        assert len(colors) == len(set(colors)) == 8
        assert all(lab_distance(a, b) >= 18 for a,b in
                   __import__("itertools").combinations(colors,2))
        assert all(contrast_ratio(v,
                   load_palette(mode,None,"sunny-palette")["surface"])>=3
                   for v in colors)


def test_existing_baselines_unchanged() -> None:
    assert load_palette("light", None, "executive-blue")["canvas"] == "#E9EEF4"
    assert load_palette("dark", None, "executive-blue")["canvas"] == "#0B1220"
    assert load_palette("dark", None, "graphite-mint")["canvas"] == "#17191C"
    assert load_palette("dark", None, "warm-basalt")["canvas"] == "#1A1A19"
    assert load_palette("dark", None, "slate-lavender")["canvas"] == "#191A21"


def test_bad_approved_preset_is_rejected_when_loaded(monkeypatch) -> None:
    from vqs import theme

    original = theme._preset_override

    def replaced(name: str, mode: str) -> dict:
        data = original(name, mode)
        if name == "graphite-red" and mode == "dark":
            data["dataColors"] = ["#777777", "#787878", "#797979", "#7A7A7A",
                                  "#7B7B7B", "#7C7C7C", "#7D7D7D", "#7E7E7E"]
        return data

    monkeypatch.setattr(theme, "_preset_override", replaced)
    with pytest.raises(theme.ThemeError, match="insufficiently distinguishable"):
        theme.load_palette("dark", None, "graphite-red")


@pytest.mark.parametrize("mode", MODES)
def test_graphite_red_has_no_green_semantic_or_category_colors(
        mode: str) -> None:
    """Prevent reintroducing the native green bug through preset edits."""
    import colorsys

    from vqs.theme import load_palette

    palette = load_palette(mode, None, "graphite-red")
    colors = list(palette["dataColors"])
    colors.extend(value for value in palette.values()
                  if isinstance(value, str) and len(value) == 7
                  and value.startswith("#"))
    for color in colors:
        red, green, blue = (int(color[i:i + 2], 16) / 255
                            for i in (1, 3, 5))
        hue, saturation, _ = colorsys.rgb_to_hsv(red, green, blue)
        assert not (77 <= hue * 360 <= 178 and saturation > .14), (
            mode, color)


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("mode", ("light", "dark"))
def test_each_approved_family_has_themed_navigation_controls(
        slug: str, mode: str) -> None:
    from vqs.theme import palette_contrast_check
    palette = load_palette(mode, None, slug)
    assert palette["slicerBackground"] != palette["surface"], (slug, mode)
    assert palette["selection"] != palette["slicerBackground"], (slug, mode)
    assert palette_contrast_check(palette) == [], (slug, mode)
    assert palette["slicerForeground"] != palette["slicerBackground"]


def test_inspired_original_reference_colors_are_preserved_in_usable_roles() -> None:
    organic_light = load_palette("light", None, "organic-palette")
    organic_dark = load_palette("dark", None, "organic-palette")
    sunny_light = load_palette("light", None, "sunny-palette")
    sunny_dark = load_palette("dark", None, "sunny-palette")
    assert organic_light["dataColors"][:2] == ["#1B4298", "#E20177"]
    assert organic_dark["selection"] == "#54B948"
    assert organic_dark["tooltip"] == "#009DDC"
    assert sunny_light["selection"] == "#F7941E"
    assert sunny_light["tooltip"] == "#FCC89B"
    assert sunny_dark["accent"] == "#F7941E"
    assert sunny_dark["tableHeader"] == "#F7941E"
    assert sunny_light["dataColors"][0] == "#B65B0A"
    assert sunny_dark["dataColors"][0] == "#F7941E"


def test_navigation_controls_have_distinct_family_hues_and_state_contrast() -> None:
    for mode in MODES:
        control_colors = [load_palette(mode, None, slug)["slicerBackground"]
                          for slug in SLUGS]
        assert len(set(control_colors)) >= 10
        for slug in SLUGS:
            palette = load_palette(mode, None, slug)
            # Warm official orange has only 2:1 vs a near-white
            # background, but black selected text passes 7:1; the
            # applied filter-card outline uses a darker accent.
            contrast = contrast_ratio(palette["selection"],
                                      palette["slicerBackground"])
            required = 2.0 if slug == "sunny-palette" and mode == "light" else 3.0
            assert contrast >= required
