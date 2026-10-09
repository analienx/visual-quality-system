"""S06-S07: dynamic layers stay unknown; every run is retained.

S06: present-but-unresolvable transparency (visual or canvas) and
non-literal canvas/theme colors yield unresolved markers, never
invented opacity or raw passthrough colors. S07: runs with no
backdrop source are retained as unknown so mandatory contrast
blocks instead of passing on the remaining runs. All tests drive
measure_report and review_report, never _contrast alone.
"""
import json
from pathlib import Path

from vqs.pipeline import review_report
from vqs.powerbi.measure import measure_report

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
VERSION_DOC = {
    "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/versionMetadata/1.0.0/schema.json"),
    "version": "2.0.0"}


def _textbox(name, text_color, visual_bg=None):
    container = {}
    if visual_bg is not None:
        container = {"background": [{"properties": visual_bg}]}
    return {"name": name,
            "position": {"x": 0, "y": 0, "width": 100, "height": 100,
                         "z": 1},
            "visual": {
                "visualType": "textbox",
                "visualContainerObjects": container,
                "objects": {"general": [{"properties": {"paragraphs": [
                    {"textRuns": [{"text": "t", "textStyle": {
                        "color": text_color}}]}]}}]}}}


_MISSING = object()


def _solid(hexcolor: str) -> dict:
    return {"solid": {"color": {"expr": {"Literal": {
        "Value": f"'{hexcolor}'"}}}}}


def _report(root: Path, visuals: dict, page_bg="#FFFFFF",
            page_transparency=_MISSING, theme_bg="#FFFFFF") -> Path:
    report = root / "S.Report"
    definition = report / "definition"
    page_dir = definition / "pages" / "P1"
    (page_dir / "visuals").mkdir(parents=True)
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps(VERSION_DOC), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    if theme_bg is not None:
        resources = report / "StaticResources" / "RegisteredResources"
        resources.mkdir(parents=True)
        (resources / "theme.json").write_text(json.dumps({
            "name": "theme", "background": theme_bg,
            "foreground": "#000000"}), encoding="utf-8")
    page_doc = {"displayName": "P1", "width": 1280, "height": 720}
    if page_bg is not None:
        background = {"properties": {"color": _solid(page_bg)}}
        if page_transparency is not _MISSING:
            background["properties"]["transparency"] = page_transparency
        page_doc["objects"] = {"background": [background]}
    (page_dir / "page.json").write_text(json.dumps(page_doc),
                                        encoding="utf-8")
    for name, spec in visuals.items():
        (page_dir / "visuals" / name).mkdir(parents=True, exist_ok=True)
        (page_dir / "visuals" / name / "visual.json").write_text(
            json.dumps(_textbox(name, *spec)), encoding="utf-8")
    return report


def _readings(report: Path) -> list:
    return measure_report(str(report))["rules"][
        "typography.text_contrast"]["readings"]


def test_dynamic_visual_transparency_unknown(tmp_path: Path) -> None:
    """S06: present-but-dynamic visual transparency is unknown."""
    dynamic = {"transparency": {"expr": {"Dynamic": 1}},
               "color": _solid("#000000")}
    report = _report(tmp_path, {"darkbox": ("#FFFFFF", dynamic)})
    assert any(reading.get("visual") == "darkbox"
               and "unresolved" in reading
               for reading in _readings(report))


def test_dynamic_canvas_transparency_unknown(tmp_path: Path) -> None:
    """S06: present-but-dynamic canvas transparency is unknown."""
    dynamic = {"expr": {"Dynamic": 1}}
    report = _report(tmp_path, {"darkbox": ("#FFFFFF", None)},
                     page_bg="#000000", page_transparency=dynamic)
    assert any(reading.get("visual") == "darkbox"
               and "unresolved" in reading
               for reading in _readings(report))


def test_nonhex_theme_background_unknown(tmp_path: Path) -> None:
    """S06: a non-literal theme background never resolves a ratio."""
    report = _report(tmp_path, {"darkbox": ("#FFFFFF", None)},
                     page_bg=None, theme_bg="red")
    assert any(reading.get("visual") == "darkbox"
               and reading.get("unresolved") == "canvas-theme:unparsed"
               for reading in _readings(report))


def test_sourceless_run_retained_unknown(tmp_path: Path) -> None:
    """S07: a run with no backdrop source is retained as unknown."""
    report = _report(tmp_path, {"darkbox": ("#FFFFFF", None)},
                     page_bg=None, theme_bg=None)
    readings = _readings(report)
    assert any(reading.get("visual") == "darkbox"
               and reading.get("unresolved") == "backdrop-unknown"
               for reading in readings)


def test_mixed_known_unknown_blocks_review(tmp_path: Path) -> None:
    """S07: one passing run plus one unknown run must not pass review."""
    dynamic = {"transparency": {"expr": {"Dynamic": 1}},
               "color": _solid("#000000")}
    report = _report(tmp_path, {
        "brightbox": ("#FFFFFF", {"color": _solid("#000000")}),
        "darkbox": ("#FFFFFF", dynamic)})
    readings = _readings(report)
    assert any(reading.get("visual") == "brightbox"
               and reading.get("background") == "#000000"
               for reading in readings)
    assert any(reading.get("visual") == "darkbox"
               and "unresolved" in reading for reading in readings)
    verdict = review_report(report_dir=str(report),
                            run_root=str(tmp_path / "runs"))
    assert verdict["verdict"] != "pass"
