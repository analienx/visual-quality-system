"""Adaptive theme engine tests (issue #80). Stdlib + tmp_path only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.theme import (
    apply_theme,
    audit_candidate,
    build_plan,
    contrast_ratio,
    inspect_report,
    load_palette,
    palette_contrast_check,
    preview_plan,
    tree_digest,
)

REPORT_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/"
    "report/definition/report/3.3.0/schema.json"
)
VERSION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/"
    "report/definition/versionMetadata/1.0.0/schema.json"
)
PAGE_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/"
    "report/definition/page/2.1.0/schema.json"
)
VISUAL_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/"
    "report/definition/visualContainer/2.11.0/schema.json"
)


def _lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _color(hex_value: str) -> dict:
    return {"solid": {"color": _lit(f"'{hex_value}'")}}


def _write(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(doc, str):
        path.write_text(doc, encoding="utf-8")
    else:
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _visual(name: str, visual_type: str, objects: dict,
            vco: dict | None = None) -> dict:
    doc: dict = {
        "$schema": VISUAL_SCHEMA, "name": name,
        "position": {"x": 0, "y": 0, "width": 200, "height": 100,
                     "z": 1, "tabOrder": 1},
        "visual": {"visualType": visual_type,
                   "query": {"queryState": {"Values": {"projections": []}}},
                   "objects": objects},
    }
    if vco is not None:
        doc["visual"]["visualContainerObjects"] = vco
    return doc


def build_report(root: Path) -> Path:
    """Minimal synthetic PBIP project; returns the .Report dir."""
    project = root / "src"
    report = project / "Demo.Report"
    theme = {
        "name": "DemoTheme.json", "background": "#FFFFFF",
        "foreground": "#0F1626",
        "dataColors": ["#2563EB", "#0E7490", "#047857", "#B45309",
                       "#BE123C", "#6D28D9", "#0F766E", "#9D174D"],
        "textClasses": {"label": {"color": "#4B5563"}},
    }
    _write(report / "StaticResources" / "RegisteredResources" / "DemoTheme.json",
           theme)
    _write(report / "definition" / "report.json", {
        "$schema": REPORT_SCHEMA, "layoutOptimization": "None",
        "themeCollection": {"customTheme": {
            "name": "DemoTheme.json", "type": "RegisteredResources",
            "reportVersionAtImport": {"visual": "2.12.0",
                                      "report": "3.4.0", "page": "2.3.1"}}},
        "resourcePackages": [{"name": "RegisteredResources",
                              "type": "RegisteredResources",
                              "items": [{"name": "DemoTheme.json",
                                         "path": "DemoTheme.json",
                                         "type": "CustomTheme"}]}],
    })
    _write(report / "definition" / "version.json",
           {"$schema": VERSION_SCHEMA, "version": "2.0.0"})
    _write(report / "definition.pbir",
           {"version": "1.0",
            "datasetReference": {"byPath": {"path": "../Demo.SemanticModel"}}})
    _write(report / "definition" / "pages" / "pages.json",
           {"pageOrder": ["P1"]})
    _write(report / "definition" / "pages" / "P1" / "page.json", {
        "$schema": PAGE_SCHEMA, "name": "P1", "displayName": "Page one",
        "width": 1280, "height": 720,
        "objects": {
            "background": [{"properties": {"color": _color("#FFFFFF")}}],
            "outspace": [{"properties": {"color": _color("#FFFFFF")}}],
        },
    })
    visuals = report / "definition" / "pages" / "P1" / "visuals"
    vco = {
        "background": [{"properties": {"color": _color("#FFFFFF"),
                                       "show": _lit("true")}}],
        "border": [{"properties": {"color": _color("#E5E7EB")}}],
        "title": [{"properties": {"fontColor": _color("#1F2937"),
                                  "text": _lit("'Chart'")}}],
    }
    chart = _visual("chart", "barChart", {
        "categoryAxis": [{"properties": {"labelColor": _color("#374151")}}],
        "valueAxis": [{"properties": {"labelColor": _color("#374151")}}],
        "labels": [{"properties": {"color": _color("#374151")}}],
        "dataPoint": [
            {"properties": {"fill": _color("#2563EB")}},
            {"selector": {"data": [{"scopeId": {"Category": "X"}}]},
             "properties": {"fill": _color("#FF0000")}},
        ],
    }, vco)
    _write(visuals / "chart" / "visual.json", chart)
    slicer = _visual("slicerx", "slicer", {
        "header": [{"properties": {"fontColor": _color("#111111"),
                                   "background": _color("#FFFFFF")}}],
        "items": [{"properties": {"fontColor": _color("#111111"),
                                  "background": _color("#FFFFFF")}}],
    })
    _write(visuals / "slicerx" / "visual.json", slicer)
    card = _visual("cardx", "card", {
        "labels": [{"properties": {"color": _color("#111111")}}],
        "categoryLabels": [{"properties": {"color": _color("#666666")}}],
    })
    _write(visuals / "cardx" / "visual.json", card)
    textbox = _visual("note", "textbox", {
        "general": [{"properties": {"paragraphs": [{
            "textRuns": [{"text": "Hi",
                          "textStyle": {"color": "#111111"}}]}]}}],
    })
    _write(visuals / "note" / "visual.json", textbox)
    dynamic = _visual("dyn", "barChart", {
        "labels": [{"properties": {"color": {"solid": {"color": {
            "expr": {"FillRule": {"FillRule": [{
                "GradientStop": [{"Color": "'#00FF00'"}]}]}}}}}}}],
    })
    _write(visuals / "dyn" / "visual.json", dynamic)
    themed = _visual("themed", "barChart", {
        "labels": [{"properties": {"color": {"solid": {"color": {
            "expr": {"ThemeDataColor": {"ColorId": 0, "Percent": 0}}}}}}}],
    })
    _write(visuals / "themed" / "visual.json", themed)
    shape = _visual("badge", "shape", {
        "fill": [{"properties": {"fillColor": _color("#1D4ED8")}}],
        "line": [{"properties": {"lineColor": _color("#111111")}}],
        "text": [{"properties": {"fontColor": _color("#FFFFFF")}}],
    })
    _write(visuals / "badge" / "visual.json", shape)
    ghost = _visual("ghost", "shape", {
        "fill": [{"properties": {"fillColor": {
            "solid": {"color": _lit("'transparent'")}}}}],
    })
    _write(visuals / "ghost" / "visual.json", ghost)
    model = project / "Demo.SemanticModel" / "definition" / "tables"
    _write(model / "Fact.tmdl", "table Fact\n\tcolumn X\n")
    _write(project / "Demo.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/"
                   "pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": "Demo.Report"}}],
    })
    return report


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(item.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _page_canvas(report: Path) -> str:
    page = _read(report / "definition" / "pages" / "P1" / "page.json")
    value = page["objects"]["background"][0]["properties"]["color"]
    return value["solid"]["color"]["expr"]["Literal"]["Value"]


def test_inspect_classifies(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    result = inspect_report(report)
    assert result["status"] == "pass"
    classes = {item["classification"] for item in result["occurrences"]}
    assert "supported" in classes or result["counts"]["total"] > 0
    chart = [o for o in result["occurrences"] if o["visual"] == "chart"]
    assert chart and all(o["file"].endswith("visual.json") for o in chart)
    assert result["counts"]["preserved_theme_data_color"] == 1


def test_preview_no_writes_and_matches_apply(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    before = _tree_hash(tmp_path / "src")
    palette = load_palette("dark", None)
    plan = preview_plan(report, "dark", palette)
    assert _tree_hash(tmp_path / "src") == before
    manifest = apply_theme(report, "dark", palette, tmp_path / "dark")
    key = lambda items: sorted(  # noqa: E731
        (i["file"], i["pointer"], str(i["old"]), str(i["new"]))
        for i in items)
    assert key(plan["changes"]) == key(manifest["changes"])


def test_apply_dark_candidate_and_original_untouched(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    before = _tree_hash(report)
    model_before = (tmp_path / "src" / "Demo.SemanticModel" / "definition"
                    / "tables" / "Fact.tmdl").read_bytes()
    palette = load_palette("dark", None)
    manifest = apply_theme(report, "dark", palette, tmp_path / "dark")
    assert _tree_hash(report) == before
    cand = tmp_path / "dark" / "Demo.Report"
    assert cand.is_dir()
    assert (tmp_path / "dark" / "theme-manifest.json").is_file()
    assert (tmp_path / "dark" / "Demo.pbip").is_file()
    model_after = (tmp_path / "dark" / "Demo.SemanticModel" / "definition"
                   / "tables" / "Fact.tmdl").read_bytes()
    assert model_after == model_before
    assert manifest["mode"] == "dark"
    assert _page_canvas(cand) == "'#0B1220'"
    theme_name = manifest["themeFileName"]
    assert theme_name.startswith("VQSAdaptive-dark-")
    theme_doc = _read(cand / "StaticResources" / "RegisteredResources"
                      / theme_name)
    assert theme_doc["name"] == theme_name
    assert len(theme_doc["dataColors"]) >= 8
    report_doc = _read(cand / "definition" / "report.json")
    assert report_doc["themeCollection"]["customTheme"]["name"] == theme_name


def test_role_collision_same_hex(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    palette = load_palette("dark", None)
    plan = build_plan(report, "dark", palette)
    by_role = {(c["file"], c["pointer"]): c for c in plan["changes"]}
    canvas = [c for c in plan["changes"] if c["role"] == "canvas"]
    surface = [c for c in plan["changes"] if c["role"] == "surface"]
    assert canvas and surface
    assert {str(c["old"]) for c in canvas} == {"#FFFFFF"}
    assert {str(c["new"]) for c in canvas} == {"#0B1220"}
    assert {str(c["new"]) for c in surface} == {"#111C2E"}
    assert by_role  # planner produced path-bound changes


def test_contrast_builtin_palettes_pass() -> None:
    for mode in ("light", "dark"):
        assert palette_contrast_check(load_palette(mode, None)) == []
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)


def test_idempotent_second_apply(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    palette = load_palette("dark", None)
    apply_theme(report, "dark", palette, tmp_path / "dark")
    first = tmp_path / "dark" / "Demo.Report"
    first_digest = tree_digest(first)
    apply_theme(first, "dark", palette, tmp_path / "dark2")
    assert tree_digest(tmp_path / "dark2" / "Demo.Report") == first_digest


def test_two_way_dark_then_light(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    apply_theme(report, "dark", load_palette("dark", None), tmp_path / "dark")
    dark_report = tmp_path / "dark" / "Demo.Report"
    assert _page_canvas(dark_report) == "'#0B1220'"
    apply_theme(dark_report, "light", load_palette("light", None),
                tmp_path / "light")
    assert _page_canvas(tmp_path / "light" / "Demo.Report") == "'#E9EEF4'"


def test_malformed_palette_blocked(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"dark": {"foreground": "blue"}}),
                   encoding="utf-8")
    out = tmp_path / "plan.json"
    rc = main(["theme", "preview", str(report), "--mode", "dark",
               "--palette", str(bad), "--out", str(out)])
    assert rc == 2
    assert _read(out)["status"] == "blocked"


def test_low_contrast_palette_blocked(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    bad = tmp_path / "low.json"
    bad.write_text(json.dumps({"dark": {"foreground": "#111C2E"}}),
                   encoding="utf-8")
    rc = main(["theme", "preview", str(report), "--mode", "dark",
               "--palette", str(bad), "--out", str(tmp_path / "p.json")])
    assert rc == 2


def test_malformed_report_blocked(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    target = report / "definition" / "pages" / "P1" / "visuals" / "chart" \
        / "visual.json"
    target.write_text("{not json", encoding="utf-8")
    rc = main(["theme", "inspect", str(report),
               "--out", str(tmp_path / "inv.json")])
    assert rc == 2


def test_overlap_candidate_blocked(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    rc = main(["theme", "apply", str(report), "--mode", "dark",
               "--candidate-root", str(tmp_path / "src" / "cand")])
    assert rc == 2
    rc = main(["theme", "apply", str(report), "--mode", "dark",
               "--candidate-root", str(report / "cand")])
    assert rc == 2


def test_fillrule_and_themedatacolor_preserved(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    dyn_before = _read(report / "definition" / "pages" / "P1" / "visuals"
                       / "dyn" / "visual.json")
    themed_before = _read(report / "definition" / "pages" / "P1" / "visuals"
                          / "themed" / "visual.json")
    apply_theme(report, "dark", load_palette("dark", None), tmp_path / "dark")
    cand = tmp_path / "dark" / "Demo.Report" / "definition" / "pages" \
        / "P1" / "visuals"
    assert _read(cand / "dyn" / "visual.json") == dyn_before
    assert _read(cand / "themed" / "visual.json") == themed_before


def test_audit_passes(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    apply_theme(report, "dark", load_palette("dark", None), tmp_path / "dark")
    result = audit_candidate(tmp_path / "dark")
    assert result["status"] == "pass"
    assert result["invariants"]["status"] == "pass"
    rc = main(["theme", "audit", str(tmp_path / "dark"),
               "--out", str(tmp_path / "audit.json")])
    assert rc == 0


def test_unknown_transparent(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    result = inspect_report(report)
    ghost = [o for o in result["occurrences"] if o["visual"] == "ghost"]
    assert ghost and ghost[0]["classification"] == "unknown"


def test_scoped_datapoint_preserved(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    palette = load_palette("dark", None)
    plan = build_plan(report, "dark", palette)
    scoped = [o for o in plan["occurrences"]
              if o["old"] == "#FF0000"]
    assert scoped and scoped[0]["classification"] == "preserved"
    mapped = [o for o in plan["occurrences"] if o["old"] == "#2563EB"
              and o["classification"] == "supported"]
    assert mapped and mapped[0]["role"].startswith("dataColors[")
