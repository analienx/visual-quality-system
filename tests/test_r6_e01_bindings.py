"""R6-E01: scoped projection identity preserves every same-label actual.

Oracle A01: installed measure -> check on same-alias healthy+dangling
and healthy+unsupported fields (same page, across pages, permuted
order, distinct roles). Dangling fails and unsupported blocks
regardless of ordering; two valid equal-label fields are both
represented; a missing queryRef blocks coverage instead of silently
erasing a bad actual. Original fields/units/categories preserved.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs.data.tmdl import check_bindings, inventory_model
from vqs.pipeline import _run_model
from vqs.powerbi.measure import measure_report

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

FAIR = "https://developer.microsoft.com/json-schemas/fabric/item/"
VERSION = {"$schema": FAIR + "report/definition/versionMetadata/1.0.0/schema.json",
           "version": "2.0.0"}
REPORT_DOC = {"$schema": FAIR + "report/definition/report/3.3.0/schema.json",
              "themeCollection": {}}


def _write_report(root: Path,
                  pages: dict[str, dict[str, dict[str, list[dict]]]]) -> Path:
    """Build a report from page -> visual -> role -> projections."""
    report = root / "R.Report"
    (report / "definition").mkdir(parents=True, exist_ok=True)
    (report / "definition" / "version.json").write_text(
        json.dumps(VERSION), encoding="utf-8")
    (report / "definition" / "report.json").write_text(
        json.dumps(REPORT_DOC), encoding="utf-8")
    for page_id, visuals in pages.items():
        page_dir = report / "definition" / "pages" / page_id
        (page_dir / "page.json").parent.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": page_id, "width": 1280,
                        "height": 720}), encoding="utf-8")
        for slot, (visual_id, roles) in enumerate(visuals.items()):
            visual_dir = page_dir / "visuals" / visual_id
            visual_dir.mkdir(parents=True, exist_ok=True)
            # Distinct geometry: the binding oracle must not trip the
            # unrelated layout-overlap rule in full-check runs.
            (visual_dir / "visual.json").write_text(json.dumps({
                "name": visual_id,
                "position": {"x": slot * 100, "y": 0, "width": 90,
                             "height": 90},
                "visual": {"visualType": "card",
                           "query": {"queryState": {
                               role: {"projections": projections}
                               for role, projections in roles.items()}}}}),
                encoding="utf-8")
    return report


def _model(root: Path) -> Path:
    model = root / "M.SemanticModel" / "definition"
    (model / "tables").mkdir(parents=True, exist_ok=True)
    (model / "tables" / "T.tmdl").write_text(
        "table T\n\n\tcolumn C\n\t\tdataType: string\n\n"
        "\tmeasure Good = 1\n\n\tmeasure Revenue = SUM('T'[C])\n",
        encoding="utf-8")
    return model


def _measure_projection(query_ref: str, entity: str, prop: str) -> dict:
    return {"queryRef": query_ref,
            "field": {"Measure": {
                "Expression": {"SourceRef": {"Entity": entity}},
                "Property": prop}}}


def _unsupported_projection(query_ref: str) -> dict:
    return {"queryRef": query_ref, "field": {"Percentile": {"k": 0.9}}}


def _statuses(bindings: list[dict], model: Path) -> list[str]:
    return [finding["status"] for finding in
            check_bindings(bindings, inventory_model(model))]


@pytest.mark.parametrize("dangling_first", [False, True])
def test_same_alias_dangling_fails_same_page(tmp_path: Path,
                                             dangling_first: bool) -> None:
    """Same page, alias Value: healthy T.Good + dangling T.Missing."""
    healthy = _measure_projection("Value", "T", "Good")
    dangling = _measure_projection("Value", "T", "Missing")
    first, second = (dangling, healthy) if dangling_first else (healthy, dangling)
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [first]}, "v2": {"Values": [second]}}})
    model = _model(tmp_path / "m")
    bindings = measure_report(str(report), str(model))["models"][0]["bindings"]
    assert len(bindings) == 2
    assert {(b["visual"], b["property"]) for b in bindings} == {
        ("v1", first["field"]["Measure"]["Property"]),
        ("v2", second["field"]["Measure"]["Property"])}
    assert sorted(_statuses(bindings, model)) == ["fail", "pass"]
    assert any(f["rule"] == "missing_dimension_or_measure"
               and f["status"] == "fail"
               for f in check_bindings(bindings, inventory_model(model)))


@pytest.mark.parametrize("dangling_first", [False, True])
def test_same_alias_dangling_fails_across_pages(tmp_path: Path,
                                                dangling_first: bool) -> None:
    """Alias Value on P1 healthy, P2 dangling (and swapped)."""
    healthy = _measure_projection("Value", "T", "Good")
    dangling = _measure_projection("Value", "T", "Missing")
    first, second = (dangling, healthy) if dangling_first else (healthy, dangling)
    report = _write_report(tmp_path / "r", {
        "P1": {"v1": {"Values": [first]}},
        "P2": {"v1": {"Values": [second]}}})
    model = _model(tmp_path / "m")
    bindings = measure_report(str(report), str(model))["models"][0]["bindings"]
    assert {(b["page"], b["property"]) for b in bindings} == {
        ("P1", first["field"]["Measure"]["Property"]),
        ("P2", second["field"]["Measure"]["Property"])}
    assert sorted(_statuses(bindings, model)) == ["fail", "pass"]


def test_same_alias_distinct_roles_both_preserved(tmp_path: Path) -> None:
    """One visual, alias Value in Values (healthy) + Category (dangling)."""
    report = _write_report(tmp_path / "r", {"P1": {"v1": {
        "Values": [_measure_projection("Value", "T", "Good")],
        "Category": [_measure_projection("Value", "T", "Missing")]}}})
    model = _model(tmp_path / "m")
    bindings = measure_report(str(report), str(model))["models"][0]["bindings"]
    assert {(b["role"], b["property"]) for b in bindings} == {
        ("Values", "Good"), ("Category", "Missing")}
    assert sorted(_statuses(bindings, model)) == ["fail", "pass"]


@pytest.mark.parametrize("unsupported_first", [False, True])
def test_same_alias_unsupported_blocks_regardless_of_order(
        tmp_path: Path, unsupported_first: bool) -> None:
    """Alias Value: healthy T.Good + unsupported Percentile shape."""
    healthy = _measure_projection("Value", "T", "Good")
    unknown = _unsupported_projection("Value")
    first, second = (unknown, healthy) if unsupported_first else (healthy, unknown)
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [first]}, "v2": {"Values": [second]}}})
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    bindings = facts["models"][0]["bindings"]
    assert len(bindings) == 2
    assert _run_model(facts["models"][0])["verdict"] == "blocked"
    rules = [f["rule"] for f in
             check_bindings(bindings, inventory_model(model))]
    assert "binding_expression_unsupported" in rules
    assert "binding_resolved" in rules


def test_two_valid_equal_labels_both_represented(tmp_path: Path) -> None:
    """Alias Value twice with distinct valid actuals: both pass."""
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good")]},
        "v2": {"Values": [_measure_projection("Value", "T", "Revenue")]}}})
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    bindings = facts["models"][0]["bindings"]
    assert {b["property"] for b in bindings} == {"Good", "Revenue"}
    assert _statuses(bindings, model) == ["pass", "pass"]
    assert _run_model(facts["models"][0])["verdict"] == "pass"


def test_missing_query_ref_blocks_instead_of_erasing(tmp_path: Path) -> None:
    """A projection without queryRef blocks coverage; nothing vanishes."""
    bad = {"field": {"Measure": {
        "Expression": {"SourceRef": {"Entity": "T"}},
        "Property": "Missing"}}}
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good"), bad]}}})
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    bindings = facts["models"][0]["bindings"]
    assert len(bindings) == 2
    stray = [b for b in bindings if b.get("query_ref_missing")]
    assert len(stray) == 1 and stray[0]["query_ref"] == ""
    assert stray[0]["visual"] == "v1" and stray[0]["projection"] == 1
    findings = check_bindings(bindings, inventory_model(model))
    assert any(f["rule"] == "binding_projection_unidentified"
               and f["status"] == "unknown" for f in findings)
    assert _run_model(facts["models"][0])["verdict"] == "blocked"


def test_fields_units_preserved(tmp_path: Path) -> None:
    """Scoped identity adds location; fields/units stay intact."""
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good")]},
        "v2": {"Values": [_measure_projection("Value", "T", "Revenue")]}}})
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    readings = facts["rules"]["encoding.metric_unit_consistency"]["readings"]
    assert {"measure": "T.Good", "unit": "undeclared",
            "page": "P1"} in readings
    assert {"measure": "T.Revenue", "unit": "undeclared",
            "page": "P1"} in readings
    for binding in facts["models"][0]["bindings"]:
        assert binding["entity"] == "T"
        assert binding["kind"] == "Measure"


@needs_vqs
def test_installed_measure_check_dangling_fails(tmp_path: Path) -> None:
    """Installed headline: measure -> check exits 1 on same-alias dangle."""
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good")]},
        "v2": {"Values": [_measure_projection("Value", "T", "Missing")]}}})
    model = _model(tmp_path / "m")
    facts_file = tmp_path / "facts.json"
    measured = subprocess.run(
        [VQS_BIN, "measure", str(report), "--model", str(model),
         "--out", str(facts_file)],
        capture_output=True, text=True, timeout=180, check=False)
    assert measured.returncode == 0, measured.stderr + measured.stdout
    checked = subprocess.run(
        [VQS_BIN, "check", str(facts_file), "--run-root",
         str(tmp_path / "runs"), "--run-id", "r6-e01-dangle"],
        capture_output=True, text=True, timeout=180, check=False)
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert "missing_dimension_or_measure" in checked.stdout


@needs_vqs
def test_installed_measure_check_unsupported_blocks(tmp_path: Path) -> None:
    """Installed headline: measure -> check exits 2 on unknown shape."""
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good")]},
        "v2": {"Values": [_unsupported_projection("Value")]}}})
    model = _model(tmp_path / "m")
    facts_file = tmp_path / "facts.json"
    measured = subprocess.run(
        [VQS_BIN, "measure", str(report), "--model", str(model),
         "--out", str(facts_file)],
        capture_output=True, text=True, timeout=180, check=False)
    assert measured.returncode == 0, measured.stderr + measured.stdout
    checked = subprocess.run(
        [VQS_BIN, "check", str(facts_file), "--run-root",
         str(tmp_path / "runs"), "--run-id", "r6-e01-unknown"],
        capture_output=True, text=True, timeout=180, check=False)
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert "binding_expression_unsupported" in checked.stdout


def test_non_dict_projection_keeps_scoped_diagnostic(
        tmp_path: Path) -> None:
    """A malformed (non-dict) projection blocks with its position."""
    report = _write_report(tmp_path / "r", {"P1": {
        "v1": {"Values": [_measure_projection("Value", "T", "Good")]},
        "v2": {"Values": ["not-a-projection"]}}})
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    bindings = facts["models"][0]["bindings"]
    assert len(bindings) == 2
    stray = [b for b in bindings if b.get("query_ref_missing")]
    assert len(stray) == 1
    assert (stray[0]["page"], stray[0]["visual"],
            stray[0]["role"], stray[0]["projection"]) == (
                "P1", "v2", "Values", 0)
    assert stray[0]["actual_unknown"] is True
    assert _run_model(facts["models"][0])["verdict"] == "blocked"
