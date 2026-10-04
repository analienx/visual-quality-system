"""R07-R08 RED: text contrast uses the visual's own painted background.

A black textbox on a white page must fail (not 21:1/pass); visual
and run location must survive into readings; transparent and
dynamic backgrounds are unknown, never silently canvas-paired;
explicit colors without any theme still emit contrast (unknown
canvas), never omit the rule. All red pre-R3, green after.
"""
import json
from pathlib import Path

from vqs.powerbi.measure import measure_report
from vqs.pipeline import review_report

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/1.0.0/schema.json")


def _solid(hexcolor: str) -> dict:
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hexcolor}'"}}}}


def _report(root: Path, page_bg: str, text_color: str,
            visual_bg: dict | None, transparency: object = 0,
            theme: bool = True) -> Path:
    report = root / "R.Report"
    definition = report / "definition"
    pages_root = definition / "pages"
    page_dir = pages_root / "P1"
    (page_dir / "visuals" / "darkbox").mkdir(parents=True)
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps({"version": "1.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    if theme:
        resources = (report / "StaticResources" / "RegisteredResources")
        resources.mkdir(parents=True)
        (resources / "theme.json").write_text(json.dumps({
            "name": "theme", "background": "#FFFFFF",
            "foreground": "#000000"}), encoding="utf-8")
    (page_dir / "page.json").write_text(json.dumps({
        "displayName": "P1", "width": 1280, "height": 720,
        "objects": {"background": [{"properties": {
            "color": _solid(page_bg)}}]}}), encoding="utf-8")
    container: dict = {}
    if visual_bg is not None:
        container = {"background": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "color": visual_bg, "transparency": transparency}}]}
    (page_dir / "visuals" / "darkbox" / "visual.json").write_text(
        json.dumps({
            "name": "darkbox",
            "position": {"x": 0, "y": 0, "width": 100,
                         "height": 100, "z": 1},
            "visual": {
                "visualType": "textbox",
                "visualContainerObjects": container,
                "objects": {"general": [{"properties": {"paragraphs": [
                    {"textRuns": [{"text": "t", "textStyle": {
                        "color": text_color}}]}]}}]}}}),
        encoding="utf-8")
    return report


def test_black_textbox_on_white_page_fails(tmp_path: Path) -> None:
    """RED R07: black text on an opaque black visual is 1:1, not 21:1."""
    report = _report(tmp_path, "#FFFFFF", "#000000", _solid("#000000"))
    readings = measure_report(str(report))["rules"][
        "typography.text_contrast"]["readings"]
    matches = [reading for reading in readings
               if reading.get("visual") == "darkbox"
               and reading.get("foreground") == "#000000"
               and reading.get("background") == "#000000"]
    assert len(matches) == 1
    verdict = review_report(report_dir=str(report),
                            run_root=str(tmp_path / "runs"))
    assert verdict["verdict"] == "fail"


def test_transparent_visual_background_is_unknown(tmp_path: Path) -> None:
    """RED R07: a translucent painted layer cannot resolve a ratio."""
    report = _report(tmp_path, "#FFFFFF", "#000000",
                     _solid("#000000"), transparency=100)
    readings = measure_report(str(report))["rules"][
        "typography.text_contrast"]["readings"]
    assert any(reading.get("visual") == "darkbox"
               and "unresolved" in reading for reading in readings)


def test_dynamic_visual_background_is_unknown(tmp_path: Path) -> None:
    """RED R07: theme-mediated visual color is unknown, not canvas."""
    report = _report(tmp_path, "#FFFFFF", "#000000", {
        "solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": 1}}}}})
    readings = measure_report(str(report))["rules"][
        "typography.text_contrast"]["readings"]
    assert any(reading.get("visual") == "darkbox"
               and "unresolved" in reading for reading in readings)


def test_explicit_colors_without_theme_emit_unknown(tmp_path: Path) -> None:
    """RED R08: explicit black/black with no theme must not omit contrast."""
    report = _report(tmp_path, "#000000", "#000000", None, theme=False)
    facts = measure_report(str(report))
    assert "typography.text_contrast" in facts["rules"]
    readings = facts["rules"]["typography.text_contrast"]["readings"]
    assert readings != []
    assert all("unresolved" in reading for reading in readings)
    verdict = review_report(report_dir=str(report),
                            run_root=str(tmp_path / "runs"))
    assert verdict["verdict"] == "blocked"
