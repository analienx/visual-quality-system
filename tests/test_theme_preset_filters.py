"""Theme UX and report filter chrome regression cases (GH-hosted tests)."""
import json
from pathlib import Path

import pytest

from test_theme_engine import _color, _read, _visual_path, _write, build_report
from vqs.cli import main
from vqs.theme import (
    ThemeError,
    apply_theme,
    audit_candidate,
    load_palette,
    palette_presets,
    source_digest,
)


def test_bundled_presets_match_reviewed_examples() -> None:
    assert palette_presets() == ("executive-blue", "graphite-mint",
                                "warm-basalt", "slate-lavender")
    root = Path(__file__).resolve().parents[1] / "examples/theme-palettes"
    for name in palette_presets()[1:]:
        actual = load_palette("dark", None, name)
        expected = load_palette("dark", root / f"dark-{name}.json")
        assert actual == expected
        assert load_palette("light", None, name) == load_palette("light", None)


def test_theme_presets_cli_and_invalid_combinations(tmp_path: Path, capsys) -> None:
    target = tmp_path / "presets.json"
    assert main(["theme", "presets", "--out", str(target)]) == 0
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["presets"] == list(palette_presets())
    with pytest.raises(ThemeError, match="cannot combine"):
        load_palette("dark", tmp_path / "palette.json", "graphite-mint")
    report = build_report(tmp_path)
    planfile = tmp_path / "preview.json"
    assert main(["theme", "preview", str(report), "--mode", "dark",
                 "--palette-preset", "warm-basalt", "--out", str(planfile)]) == 0
    preview = json.loads(planfile.read_text(encoding="utf-8"))
    assert preview["palettePreset"] == "warm-basalt"
    assert main(["theme", "apply", str(report), "--mode", "dark",
                 "--palette-preset", "warm-basalt",
                 "--candidate-root", str(tmp_path / "candidate")]) == 0
    assert main(["theme", "audit", str(tmp_path / "candidate")]) == 2
    assert capsys.readouterr().out


def test_page_filter_pane_and_cards_are_themed_without_filter_mutation(
        tmp_path: Path) -> None:
    report = build_report(tmp_path)
    path = report / "definition/pages/P1/page.json"
    page = _read(path)
    page["filterConfig"] = {"filters": [{"name": "Pinned",
        "field": {"Column": {"Expression": {"SourceRef": {
            "Entity": "Fact"}}, "Property": "X"}}}]}
    original_filter = json.loads(json.dumps(page["filterConfig"]))
    _write(path, page)
    digest = source_digest(report)
    palette = load_palette("dark", None, "graphite-mint")
    apply_theme(report, "dark", palette, tmp_path / "themed")
    assert source_digest(report) == digest
    target = tmp_path / "themed" / "Demo.Report" / "definition/pages/P1/page.json"
    result = _read(target)
    assert result["filterConfig"] == original_filter
    obj = result["objects"]
    pane = obj["outspacePane"][0]["properties"]
    assert pane["backgroundColor"]["solid"]["color"]["expr"][
        "Literal"]["Value"] == "'#2D3236'"
    assert pane["foregroundColor"]["solid"]["color"]["expr"][
        "Literal"]["Value"] == "'#F4F4F0'"
    cards = obj["filterCard"]
    assert [x["selector"]["id"] for x in cards] == ["Available", "Applied"]
    assert cards[0]["properties"]["backgroundColor"]["solid"]["color"]["expr"][
        "Literal"]["Value"] == "'#22262A'"
    assert cards[1]["properties"]["backgroundColor"]["solid"]["color"]["expr"][
        "Literal"]["Value"] == "'#326C62'"
    assert cards[1]["properties"]["foregroundColor"]["solid"]["color"]["expr"][
        "Literal"]["Value"] == "'#F4F4F0'"
    audit = audit_candidate(tmp_path / "themed")
    assert audit["integrityStatus"] == "pass"


def test_existing_filter_card_state_and_slicer_search_preserved(tmp_path: Path) -> None:
    report = build_report(tmp_path)
    page_file = report / "definition/pages/P1/page.json"
    page = _read(page_file)
    page["objects"]["outspacePane"] = [{"properties": {
        "foregroundColor": _color("#111111"), "titleSize": {
            "expr": {"Literal": {"Value": "12D"}}}}}]
    page["objects"]["filterCard"] = [
        {"selector": {"id": "Available"}, "properties": {
            "backgroundColor": _color("#FFFFFF")}},
        {"selector": {"id": "Applied"}, "properties": {
            "backgroundColor": _color("#EFEFEF")}}]
    _write(page_file, page)
    slicer_file = _visual_path(report, "slicerx")
    slicer = _read(slicer_file)
    slicer["visual"]["objects"]["searchBox"] = [{"properties": {
        "background": _color("#FFFFFF"),
        "borderColor": _color("#777777")}}]
    slicer["visual"]["objects"]["selection"] = [{"properties": {
        "singleSelect": {"expr": {"Literal": {"Value": "true"}}}}}]
    _write(slicer_file, slicer)
    palette = load_palette("dark", None, "graphite-mint")
    apply_theme(report, "dark", palette, tmp_path / "themed")
    target = tmp_path / "themed" / "Demo.Report"
    page2 = _read(target / "definition/pages/P1/page.json")
    cards = page2["objects"]["filterCard"]
    assert [c["selector"]["id"] for c in cards] == ["Available", "Applied"]
    assert cards[0]["properties"]["backgroundColor"]["solid"]["color"][
        "expr"]["Literal"]["Value"] == "'#22262A'"
    assert cards[1]["properties"]["backgroundColor"]["solid"]["color"][
        "expr"]["Literal"]["Value"] == "'#326C62'"
    slicer2 = _read(_visual_path(target, "slicerx"))
    assert slicer2["visual"]["objects"]["selection"] == slicer[
        "visual"]["objects"]["selection"]
    assert slicer2["visual"]["objects"]["searchBox"][0]["properties"][
        "background"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#292E32'"
