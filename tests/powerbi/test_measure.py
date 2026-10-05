"""Emitter tests (WP-19): exact extraction from the committed mini fixture."""
from pathlib import Path

import pytest

from vqs.powerbi.measure import measure_report

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = str(FIXTURES / "mini_report")
MODEL = str(FIXTURES / "mini_model" / "definition")


def test_contrast_exposes_every_text_run_reading() -> None:
    # GOAL 10 (fact side): the emitter pairs every honestly-resolvable
    # text run with its own page background -- majority and minority
    # alike -- instead of collapsing to one weakest pair.
    rules = measure_report(REPORT)["rules"]
    assert rules["typography.text_contrast"] == {"readings": [
        {"foreground": "#52617A", "background": "#FFFFFF", "page": "P1",
         "visual": "titlebox", "paragraph": 1, "role": "subtitle", "count": 1},
        {"foreground": "#101828", "background": "#FFFFFF", "page": "P1",
         "visual": "titlebox", "paragraph": 0, "role": "title", "count": 1}]}


def test_palette_omitted_without_declared_series_colors() -> None:
    # A theme declares slot colors but never proves a page uses a slot,
    # and no visual here declares explicit series colors: the rule stays
    # omitted instead of emitting page x slot fiction.
    rules = measure_report(REPORT)["rules"]
    assert "palette.semantic_consistency" not in rules
    assert "typography.text_contrast" in rules  # emitter is alive


def test_cohorts_carry_declared_values_and_default_nulls() -> None:
    rules = measure_report(REPORT)["rules"]
    assert rules["typography.format_declaration_consistency"] == {"readings": [
        {"cohort": "card/labels.fontSize", "page": "P1", "value": 24,
         "visual": "cardx"},
        {"cohort": "slicer/header.textSize", "page": "P1", "value": None,
         "visual": "slicera"},
        {"cohort": "slicer/header.textSize", "page": "P1", "value": 11,
         "visual": "slicerb"}]}


def test_model_sections_needs_model_dir() -> None:
    facts = measure_report(REPORT, MODEL)
    assert facts["rules"]["encoding.metric_unit_consistency"] == {"readings": [
        {"measure": "Fact Sales.Revenue", "page": "P1", "unit": "raw:$#,0"}]}
    assert facts["models"] == [{"bindings": [
        {"query_ref": "Dim Date.Year", "kind": "Column",
         "entity": "Dim Date", "property": "Year"},
        {"query_ref": "Fact Sales.Revenue", "kind": "Measure",
         "entity": "Fact Sales", "property": "Revenue"}],
        "model_dir": MODEL}]
    bare = measure_report(REPORT)
    assert "encoding.metric_unit_consistency" not in bare["rules"]
    assert "models" not in bare


def test_missing_report_dir_raises() -> None:
    with pytest.raises(OSError):
        measure_report(str(FIXTURES / "absent"))


def test_missing_theme_retains_unknown_contrast(tmp_path: Path) -> None:
    """S07: without a theme, runs are retained as unknown, not omitted."""
    import shutil
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    for path in (clone / "StaticResources").rglob("*.json"):
        path.unlink()
    rules = measure_report(str(clone))["rules"]
    readings = rules["typography.text_contrast"]["readings"]
    assert len(readings) >= 1
    assert all("unresolved" in reading for reading in readings)
    assert "palette.semantic_consistency" not in rules
    assert "typography.format_declaration_consistency" in rules


def test_measured_readings_evaluate_through_run_check(
        tmp_path: Path) -> None:
    # D02: the pipeline forwards measured readings, so the rule
    # evaluates every honestly-paired run instead of reporting the
    # legacy unknown. The clean mini fixture evaluates to pass.
    from vqs.pipeline import run_check
    facts = measure_report(REPORT, MODEL)
    facts["rules"].pop("typography.format_declaration_consistency")
    result = run_check(facts, tmp_path, run_id="emitter-shape")
    assert result["verdict"] == "pass", result["findings"]
    by_check = {item["check"]: item for item in result["findings"]}
    contrast = by_check["typography.text_contrast"]
    assert contrast["status"] == "pass"
    assert contrast["detail"]["evidence"]["pairs"] == 2
    assert contrast["detail"]["evidence"]["failures"] == []

def test_nulls_only_cover_visuals_declaring_the_owner() -> None:
    readings = measure_report(REPORT)["rules"][
        "typography.format_declaration_consistency"]["readings"]
    # slicera declares header (without textSize) -> proven null.
    # slicerc is a slicer without any header object -> no reading at all.
    assert {"cohort": "slicer/header.textSize", "page": "P1", "value": None,
            "visual": "slicera"} in readings
    assert [r for r in readings if r["visual"] == "slicerc"] == []


def test_contrast_pairs_colors_within_their_page(tmp_path: Path) -> None:
    import json
    import shutil
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    # F14: canvas (objects.background) is the page background; wallpaper
    # (objects.outspace) must never stand in. See test_f14_canvas.py.
    dark = clone / "definition" / "pages" / "P2"
    (dark / "visuals" / "darkbox").mkdir(parents=True)
    (dark / "page.json").write_text(json.dumps({
        "objects": {"background": [{"properties": {"color": {"solid": {"color": {
            "expr": {"Literal": {"Value": "'#000000'"}}}}}}}]}}),
        encoding="utf-8")
    (dark / "visuals" / "darkbox" / "visual.json").write_text(json.dumps({
        "visual": {"objects": {"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"text": "t", "textStyle": {"color": "#FFFFFF"}}]},
            {"textRuns": [{"text": "s", "textStyle": {"color": "#EEEEEE"}}]}]}}]},
            "visualType": "textbox"}}), encoding="utf-8")
    index = clone / "definition" / "pages.json"
    doc = json.loads(index.read_text(encoding="utf-8"))
    doc["pageOrder"] = ["P1", "P2"]
    index.write_text(json.dumps(doc), encoding="utf-8")
    # Cross-page pairing would test P1's #101828 on P2's #000000
    # (ratio ~1.2). Honest per-page pairing keeps every run on its own
    # page background.
    assert measure_report(str(clone))["rules"][
        "typography.text_contrast"] == {"readings": [
            {"foreground": "#52617A", "background": "#FFFFFF",
             "page": "P1", "visual": "titlebox", "paragraph": 1,
             "role": "subtitle", "count": 1},
            {"foreground": "#101828", "background": "#FFFFFF",
             "page": "P1", "visual": "titlebox", "paragraph": 0,
             "role": "title", "count": 1},
            {"foreground": "#EEEEEE", "background": "#000000",
             "page": "P2", "visual": "darkbox", "paragraph": 1,
             "role": "subtitle", "count": 1},
            {"foreground": "#FFFFFF", "background": "#000000",
             "page": "P2", "visual": "darkbox", "paragraph": 0,
             "role": "title", "count": 1}]}


def test_unit_classification_proves_only_percent() -> None:
    from vqs.powerbi.measure import _format_of, _measure_formats, _unit_of
    assert _unit_of("0.0%") == "percent"
    assert _unit_of("") == "undeclared"
    assert _unit_of("$#,0") == "raw:$#,0"
    assert _unit_of("#,0") == "raw:#,0"
    formats = _measure_formats(MODEL)
    assert _format_of(formats, "fact sales.revenue") == "$#,0"
    assert _format_of(formats, "Nope.Missing") == ""
    assert _format_of(formats, "not-dotted") == ""

def test_non_hex_text_color_skipped(tmp_path: Path) -> None:
    import json
    import shutil
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    path = (clone / "definition" / "pages" / "P1" / "visuals" / "titlebox"
            / "visual.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    runs = doc["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    runs[1]["textRuns"][0]["textStyle"]["color"] = "RED"
    path.write_text(json.dumps(doc), encoding="utf-8")
    readings = measure_report(str(clone))["rules"][
        "typography.text_contrast"]["readings"]
    assert {"foreground": "#101828", "background": "#FFFFFF",
            "page": "P1", "visual": "titlebox", "paragraph": 0,
            "role": "title", "count": 1} in readings
    flagged = [reading for reading in readings
               if reading.get("foreground") == "RED"]
    assert len(flagged) == 1
    assert flagged[0]["page"] == "P1"


def test_invalid_theme_background_never_grounds(tmp_path: Path) -> None:
    """S06: a non-literal theme background resolves nothing, not WHITE."""
    import json
    import shutil
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    page_path = clone / "definition" / "pages" / "P1" / "page.json"
    doc = json.loads(page_path.read_text(encoding="utf-8"))
    doc.pop("objects", None)
    page_path.write_text(json.dumps(doc), encoding="utf-8")
    theme_path = next((clone / "StaticResources").rglob("*.json"))
    theme = json.loads(theme_path.read_text(encoding="utf-8"))
    theme["background"] = "WHITE"
    theme_path.write_text(json.dumps(theme), encoding="utf-8")
    readings = measure_report(str(clone))["rules"][
        "typography.text_contrast"]["readings"]
    assert len(readings) >= 1
    assert not any("background" in reading for reading in readings)
    assert any(reading.get("unresolved") == "canvas-theme:unparsed"
               for reading in readings)
