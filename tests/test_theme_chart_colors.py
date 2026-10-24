"""Source-bound graph palette tests executed only on GitHub-hosted CI."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_theme_engine import _read, _visual_path, _write, build_report

from vqs.theme import (
    apply_theme,
    audit_candidate,
    build_plan,
    compile_theme,
    load_palette,
    source_digest,
)

CONTOSO = (
    Path(__file__).resolve().parents[1]
    / "examples/contoso-retail/Contoso Retail.Report"
)
NAMES = ("graphite-mint", "warm-basalt", "slate-lavender")


def _literal(hex_color: str) -> dict:
    return {"Literal": {"Value": "'" + hex_color + "'"}}


def _ramp() -> dict:
    return {
        "solid": {"color": {"expr": {"FillRule": {
            "Input": {"Measure": {"Expression": {
                "SourceRef": {"Entity": "Fact Sales"}},
                "Property": "Reporting Year Sales"}},
            "FillRule": {"linearGradient2": {
                "min": {"color": _literal("#52698F")},
                "max": {"color": _literal("#4F7CFF")}}}
        }}}}
    }


@pytest.mark.parametrize("preset", NAMES)
def test_real_contoso_numeric_color_ramps_follow_preset(preset: str) -> None:
    palette = load_palette("dark", None, preset)
    plan = build_plan(CONTOSO, "dark", palette)
    changes = [c for c in plan["changes"]
               if c["role"] in ("gradientMin", "gradientMax")]
    assert len(changes) >= 6  # bar/column plus Shape Map live examples
    assert {"gradientMin", "gradientMax"} <= {c["role"] for c in changes}
    assert all(c["new"] == palette[c["role"]] for c in changes)
    assert any(c["visualType"] == "shapeMap" for c in changes)
    assert any(c["visualType"] == "clusteredColumnChart" for c in changes)
    assert all("/dataPoint/" in c["pointer"] and
               "/FillRule/FillRule/linearGradient2/" in c["pointer"]
               for c in changes)


@pytest.mark.parametrize("preset", NAMES)
def test_theme_data_colors_reach_chart_default_palette(preset: str) -> None:
    palette = load_palette("dark", None, preset)
    compiled = compile_theme(palette, "dark", "Test.json")
    assert compiled["dataColors"] == palette["dataColors"]
    assert len(compiled["dataColors"]) >= 8
    assert compiled["minimum"] == palette["gradientMin"]
    assert compiled["maximum"] == palette["gradientMax"]


def test_unscoped_chart_default_recolors_not_scoped_condition(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    chart = _read(_visual_path(report, "chart"))
    entries = chart["visual"]["objects"]["dataPoint"]
    entries[0]["properties"]["defaultColor"] = {
        "solid": {"color": {"expr": _literal("#8391A8")}}}
    before_scoped = copy.deepcopy(entries[1])
    _write(_visual_path(report, "chart"), chart)
    palette = load_palette("dark", None, "graphite-mint")
    plan = build_plan(report, "dark", palette)
    updates = [c for c in plan["changes"]
               if c["visual"] == "chart" and c["role"] == "dataColors[0]"]
    assert updates
    assert any(c["new"] == palette["dataColors"][0] for c in updates)
    apply_theme(report, "dark", palette, tmp_path / "candidate")
    new = _read(_visual_path(tmp_path / "candidate/Demo.Report", "chart"))
    assert new["visual"]["objects"]["dataPoint"][1] == before_scoped
    assert new["visual"]["objects"]["dataPoint"][0]["properties"][
        "defaultColor"]["solid"]["color"]["expr"]["Literal"]["Value"] == (
            f"'{palette['dataColors'][0]}'")


def test_numeric_gradient_stops_only_model_and_conditions_unchanged(
        tmp_path: Path) -> None:
    report = build_report(tmp_path)
    visual_file = _visual_path(report, "chart")
    chart = _read(visual_file)
    rule = _ramp()
    chart["visual"]["objects"]["dataPoint"][0]["properties"]["fill"] = rule
    source_rule = copy.deepcopy(rule)
    # Also add a dynamic conditional business rule: never touch its
    # green/red measure-bound values.
    condition = {"solid": {"color": {"expr": {"Conditional": {
        "Cases": [{"Condition": {"Comparison": {
            "ComparisonKind": 2, "Left": {"Literal": {"Value": "1D"}},
            "Right": {"Literal": {"Value": "0D"}}}},
            "Value": _literal("#BE123C")}]}}}}}
    chart["visual"]["objects"]["dataPoint"][0]["properties"]["borderColor"] = condition
    _write(visual_file, chart)
    before_digest = source_digest(report)
    palette = load_palette("dark", None, "warm-basalt")
    plan = build_plan(report, "dark", palette)
    changed_stops = [c for c in plan["changes"]
                     if c["visual"] == "chart" and
                     c["role"] in ("gradientMin", "gradientMax")]
    assert len(changed_stops) == 2
    assert not any("/Conditional/" in c["pointer"] for c in plan["changes"])
    apply_theme(report, "dark", palette, tmp_path / "candidate")
    assert source_digest(report) == before_digest
    new = _read(_visual_path(tmp_path / "candidate/Demo.Report", "chart"))
    props = new["visual"]["objects"]["dataPoint"][0]["properties"]
    old_expr = source_rule["solid"]["color"]["expr"]["FillRule"]
    new_expr = props["fill"]["solid"]["color"]["expr"]["FillRule"]
    assert new_expr["Input"] == old_expr["Input"]
    assert new_expr["FillRule"]["linearGradient2"]["min"]["color"] == (
        _literal(palette["gradientMin"]))
    assert new_expr["FillRule"]["linearGradient2"]["max"]["color"] == (
        _literal(palette["gradientMax"]))
    assert props["borderColor"] == condition
    assert audit_candidate(tmp_path / "candidate")["integrityStatus"] == "pass"


def test_unrelated_gradient_lookalike_is_preserved(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    file = _visual_path(report, "dyn")
    doc = _read(file)
    before = json.loads(json.dumps(doc))
    _write(file, doc)
    plan = build_plan(report, "dark", load_palette("dark", None))
    assert not any(c["visual"] == "dyn" and
                   c["role"] in ("gradientMin", "gradientMax")
                   for c in plan["changes"])
    assert _read(file) == before


def test_two_explicit_chart_line_series_receive_distinct_theme_colors(
        tmp_path: Path) -> None:
    report = build_report(tmp_path)
    doc = _read(_visual_path(report, "chart"))
    doc["visual"]["visualType"] = "lineChart"
    doc["visual"]["objects"]["lineStyles"] = [
        {"properties": {"strokeColor": {
            "solid": {"color": {"expr": _literal("#7F8FA0")}}}}},
        {"properties": {"strokeColor": {
            "solid": {"color": {"expr": _literal("#AFBFC0")}}}}},
    ]
    before = copy.deepcopy(doc)
    _write(_visual_path(report, "chart"), doc)
    palette = load_palette("dark", None, "slate-lavender")
    plan = build_plan(report, "dark", palette)
    line_changes = [c for c in plan["changes"]
                    if c["visual"] == "chart" and
                    "/lineStyles/" in c["pointer"]]
    assert len(line_changes) == 2
    assert [c["new"] for c in line_changes] == palette["dataColors"][:2]
    assert [c["role"] for c in line_changes] == [
        "dataColors[0]", "dataColors[1]"]
    apply_theme(report, "dark", palette, tmp_path / "candidate")
    newer = _read(_visual_path(
        tmp_path / "candidate/Demo.Report", "chart"))
    entries = newer["visual"]["objects"]["lineStyles"]
    for i, entry in enumerate(entries):
        assert entry["properties"]["strokeColor"]["solid"]["color"][
            "expr"]["Literal"]["Value"] == f"'{palette['dataColors'][i]}'"
    assert before["visual"]["objects"]["lineStyles"] == doc[
        "visual"]["objects"]["lineStyles"]


@pytest.mark.parametrize("mode", ("light", "dark"))
def test_real_contoso_wildcard_channel_fill_follows_theme(
        tmp_path: Path, mode: str) -> None:
    """Native-capture regression: bright default channel bars must retheme."""
    source = (CONTOSO / "definition/pages/Markets_drivers/visuals"
              / "channel-mix-bar/visual.json")
    original = _read(source)
    old = original["visual"]["objects"]["dataPoint"][1]
    assert old["selector"] == {
        "data": [{"dataViewWildcard": {"matchingOption": 1}}]}
    assert old["properties"]["fill"]["solid"]["color"]["expr"] == (
        _literal("#4F7CFF"))
    palette = load_palette(mode, None, "organic-palette")
    plan = build_plan(CONTOSO, mode, palette)
    updates = [change for change in plan["changes"]
               if change["visual"] == "channel-mix-bar"
               and change["role"] == "dataColors[0]"
               and "/dataPoint/1/properties/fill/" in change["pointer"]]
    assert len(updates) == 1
    assert updates[0]["old"] == "#4F7CFF"
    assert updates[0]["new"] == palette["dataColors"][0]
    candidate = tmp_path / ("candidate-" + mode)
    apply_theme(CONTOSO, mode, palette, candidate)
    revised = _read(candidate / "Contoso Retail.Report"
                    / "definition/pages/Markets_drivers/visuals"
                    / "channel-mix-bar/visual.json")
    selected = revised["visual"]["objects"]["dataPoint"][1]
    assert selected["selector"] == old["selector"]
    assert selected["properties"]["fill"]["solid"]["color"]["expr"] == (
        _literal(palette["dataColors"][0]))
    assert audit_candidate(candidate)["integrityStatus"] == "pass"


@pytest.mark.parametrize("mode", ("light", "dark"))
def test_real_contoso_dark_secondary_legend_and_subtitle(
        tmp_path: Path, mode: str) -> None:
    """Native evidence: waterfall description and donut legend readable."""
    palette = load_palette(mode, None, "sunny-palette")
    plan = build_plan(CONTOSO, mode, palette)
    waterfall = "b1c2d3e4f5061728394a"
    donut = "sales-by-channel"
    required = [c for c in plan["changes"]
                if c["visual"] == waterfall
                and "/subTitle/0/properties/fontColor" in c["pointer"]]
    assert len(required) == 1
    assert required[0]["new"]["solid"]["color"]["expr"] == _literal(
        palette["mutedForeground"])
    legend = [c for c in plan["changes"]
              if c["visual"] == donut
              and c["pointer"] == "/visual/objects/legend"]
    assert len(legend) == 1
    cand = tmp_path / mode
    apply_theme(CONTOSO, mode, palette, cand)
    wf = _read(cand / "Contoso Retail.Report/definition/pages/"
               "Markets_drivers/visuals" / waterfall / "visual.json")
    dn = _read(cand / "Contoso Retail.Report/definition/pages/"
               "d9bc3b8f90439bcc/visuals" / donut / "visual.json")
    props = wf["visual"]["visualContainerObjects"]["subTitle"][0]["properties"]
    assert props["fontColor"]["solid"]["color"]["expr"] == _literal(
        palette["mutedForeground"])
    assert props["show"]["expr"]["Literal"]["Value"] == "true"
    assert dn["visual"]["objects"]["legend"][0]["properties"][
        "labelColor"]["solid"]["color"]["expr"] == _literal(
            palette["mutedForeground"])
    assert audit_candidate(cand)["integrityStatus"] == "pass"


def test_real_contoso_numeric_gradient_legend_contrast_is_explicit(
        tmp_path: Path) -> None:
    """Native dark bar scales rendered low-contrast automatic legend captions."""
    palette = load_palette("dark", None, "sunny-palette")
    source = (CONTOSO / "definition/pages/Products_brands/visuals"
              / "6eef7fa2804207db6a94/visual.json")
    original = _read(source)
    assert "FillRule" in json.dumps(original["visual"]["objects"]["dataPoint"])
    assert "legend" not in original["visual"]["objects"]
    plan = build_plan(CONTOSO, "dark", palette)
    found = [c for c in plan["changes"]
             if c["visual"] == "6eef7fa2804207db6a94"
             and c["pointer"] == "/visual/objects/legend"]
    assert len(found) == 1
    dest = tmp_path / "candidate"
    apply_theme(CONTOSO, "dark", palette, dest)
    updated = _read(dest / "Contoso Retail.Report/definition/pages/"
                    "Products_brands/visuals/6eef7fa2804207db6a94/visual.json")
    assert updated["visual"]["objects"]["legend"][0]["properties"][
        "labelColor"]["solid"]["color"]["expr"] == _literal(
            palette["mutedForeground"])
    assert updated["visual"]["query"] == original["visual"]["query"]
    assert audit_candidate(dest)["integrityStatus"] == "pass"
