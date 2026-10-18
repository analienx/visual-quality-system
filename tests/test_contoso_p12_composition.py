"""P12: prove the old visual defects were detectable and candidate removes them."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.contoso_p12_layout_repair import FIXTURE, PAGE, POSITIONS, VISUALS, migrate
from vqs.design_rules import layout_composition
from vqs.pbir import read_report_files
from vqs.powerbi.measure import measure_report
from vqs.triage import _locations, _summary_recommendation
from vqs.visual.composition import composition_facts


@pytest.fixture()
def original(tmp_path: Path) -> Path:
    folder = tmp_path / "p10"
    folder.mkdir()
    with zipfile.ZipFile(FIXTURE) as archive:
        archive.extractall(folder)
    return folder


def _policy(folder: Path) -> dict:
    report = folder / "Contoso Retail.Report"
    return layout_composition(composition_facts(read_report_files(report)))


def test_original_p10_explicitly_fails_all_three_missed_defects(original):
    result = _policy(original)
    assert result["status"] == "fail"
    kinds = {finding["kind"] for finding in result["evidence"]["findings"]}
    assert kinds == {"redundant_slicer_caption", "kpi_row_crowding",
                     "kpi_detail_grid_drift"}
    assert {f["page"] for f in result["evidence"]["findings"]} == {PAGE}
    # Seven implicated elements; the eighth changed visual is the regional
    # panel, moved in concert with its right-column sibling.
    assert len(_locations(result)) == 7
    assert "Microsoft CLI" in _summary_recommendation(
        "layout.composition", "fail", result)
    rule_input = measure_report(str(original / "Contoso Retail.Report"))["rules"]
    assert "layout.composition" in rule_input
    assert layout_composition(rule_input["layout.composition"]["pages"])["status"] == "fail"


def test_p12_candidate_fixes_all_three_and_preserves_other_source(original, tmp_path):
    destination = tmp_path / "p12"
    result = migrate(destination)
    assert result["verdict"] == "candidate_only"
    assert result["layout_composition"] == "pass"
    assert len(result["changed_report_files"]) == len(POSITIONS) == 8
    assert result["semantic_model_unchanged"] is True
    assert _policy(destination)["status"] == "pass"
    assert {k for k in measure_report(str(destination / "Contoso Retail.Report"))["rules"]
            if k == "layout.composition"} == {"layout.composition"}
    with zipfile.ZipFile(FIXTURE) as archive:
        for name in archive.namelist():
            path = destination / name
            if name not in result["changed_report_files"]:
                assert path.read_bytes() == archive.read(name)
    for visual, pos in POSITIONS.items():
        doc = json.loads((destination / VISUALS / visual / "visual.json").read_text())
        assert all(doc["position"][k] == v for k, v in pos.items())
    slicer = json.loads((destination / VISUALS / "slicer-year" / "visual.json")
                        .read_text())
    assert (slicer["visual"]["visualContainerObjects"]["title"][0]
            ["properties"]["show"]["expr"]["Literal"]["Value"]) == "false"
    assert (slicer["visual"]["objects"]["header"][0]["properties"]["text"]
            ["expr"]["Literal"]["Value"]) == "'Reporting year'"
    # The same input produces byte-identical changed files in two clean outputs.
    other = tmp_path / "p12-second"
    migrate(other)
    for path in result["changed_report_files"]:
        assert hashlib.sha256((destination / path).read_bytes()).digest() == hashlib.sha256(
            (other / path).read_bytes()).digest()


def test_repair_refuses_existing_destination(original, tmp_path):
    with pytest.raises(FileExistsError):
        migrate(original)
    with pytest.raises(FileExistsError):
        migrate(tmp_path)


@pytest.mark.parametrize("change", ["duplicate", "height", "anchors"])
def test_individual_geometry_negative_controls(original, change):
    for visual, pos in POSITIONS.items():
        path = original / VISUALS / visual / "visual.json"
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        doc["position"].update(pos)
        if visual == "slicer-year":
            title = doc["visual"]["visualContainerObjects"]["title"][0]
            title["properties"]["show"]["expr"]["Literal"]["Value"] = "false"
        path.write_text(json.dumps(doc), encoding="utf-8")
    if change == "duplicate":
        path = original / VISUALS / "slicer-year" / "visual.json"
        doc = json.loads(path.read_text())
        title = doc["visual"]["visualContainerObjects"]["title"][0]
        title["properties"]["show"]["expr"]["Literal"]["Value"] = "true"
    elif change == "height":
        path = original / VISUALS / "card-units" / "visual.json"
        doc = json.loads(path.read_text())
        doc["position"]["height"] = 140
    else:
        path = original / VISUALS / "sales-by-channel" / "visual.json"
        doc = json.loads(path.read_text())
        doc["position"]["x"] += 16
        doc["position"]["width"] -= 16
    path.write_text(json.dumps(doc), encoding="utf-8")
    result = _policy(original)
    assert result["status"] == "fail"
    assert {f["kind"] for f in result["evidence"]["findings"]} == {
        {"duplicate": "redundant_slicer_caption", "height": "kpi_row_crowding",
         "anchors": "kpi_detail_grid_drift"}[change]}


def test_unproven_input_stays_unknown():
    assert layout_composition(None)["status"] == "unknown"
    assert layout_composition([{"page": "x", "visuals": [],
                                "height": None, "width": 1280}])["status"] == "unknown"
