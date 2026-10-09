"""T04: structured actuals resolve; labels never substitute; units never mask.

Routes: measure_report (producer) -> check_bindings/_run_model
(consumer) plus installed `vqs review` for the headline adverse case.
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


def _report(root: Path, projections: list[dict]) -> Path:
    report = root / "R.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True, exist_ok=True)
    (report / "definition" / "version.json").write_text(
        json.dumps(VERSION), encoding="utf-8")
    (report / "definition" / "report.json").write_text(
        json.dumps(REPORT_DOC), encoding="utf-8")
    (report / "definition" / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(json.dumps({
        "name": "v1", "position": {"x": 0, "y": 0, "width": 10, "height": 10},
        "visual": {"visualType": "card",
                   "query": {"queryState": {"Values": {
                       "projections": projections}}}}}), encoding="utf-8")
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


def test_dangling_actual_fails_despite_valid_alias(tmp_path: Path) -> None:
    """T04 adverse: actual T.Missing fails though label T.Good exists."""
    report = _report(tmp_path / "r", [_measure_projection(
        "T.Good", "T", "Missing")])
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    bindings = facts["models"][0]["bindings"]
    assert bindings[0]["entity"] == "T"
    assert bindings[0]["property"] == "Missing"
    assert bindings[0]["query_ref"] == "T.Good"
    inventory = inventory_model(model)
    findings = check_bindings(bindings, inventory)
    # R6-E01: findings echo the producer's scoped identity.
    assert findings == [{"rule": "missing_dimension_or_measure",
                         "status": "fail", "query_ref": "T.Good",
                         "kind": "Measure", "entity": "T",
                         "property": "Missing", "page": "P1",
                         "visual": "v1", "role": "Values",
                         "projection": 0}]
    # The unit reading exists (undeclared) but cannot mask the failure.
    assert {"measure": "T.Missing", "unit": "undeclared",
            "page": "P1"} in facts["rules"][
                "encoding.metric_unit_consistency"]["readings"]
    assert _run_model(facts["models"][0])["verdict"] == "fail"


@needs_vqs
def test_installed_review_rejects_dangling_actual(tmp_path: Path) -> None:
    """T04 adverse installed: `vqs review` fails the dangling actual."""
    report = _report(tmp_path / "r", [_measure_projection(
        "T.Good", "T", "Missing")])
    model = _model(tmp_path / "m")
    completed = subprocess.run(
        [VQS_BIN, "review", str(report), "--model", str(model),
         "--run-root", str(tmp_path / "runs"), "--run-id", "t04"],
        capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 1, completed.stderr + completed.stdout
    assert "missing_dimension_or_measure" in completed.stdout


def test_valid_alias_resolves_via_actual(tmp_path: Path) -> None:
    """T04 positive: label 'Revenue' resolves through actual T.Revenue."""
    report = _report(tmp_path / "r", [_measure_projection(
        "Revenue", "T", "Revenue")])
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    assert _run_model(facts["models"][0])["verdict"] == "pass"


def test_aggregate_label_resolves_via_actual(tmp_path: Path) -> None:
    """T04 positive: 'Sum(T.Revenue)' resolves via Aggregation actual."""
    report = _report(tmp_path / "r", [{
        "queryRef": "Sum(T.Revenue)",
        "field": {"Aggregation": {
            "Expression": {"Measure": {
                "Expression": {"SourceRef": {"Entity": "T"}},
                "Property": "Revenue"}},
            "Function": "Sum"}}}])
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    binding = facts["models"][0]["bindings"][0]
    assert binding["kind"] == "Aggregation"
    assert binding["function"] == "Sum"
    assert _run_model(facts["models"][0])["verdict"] == "pass"


def test_unsupported_field_coverage_blocked(tmp_path: Path) -> None:
    """T04: unrecognized field shapes block instead of guessing."""
    report = _report(tmp_path / "r", [{
        "queryRef": "X",
        "field": {"Percentile": {"k": 0.9}}}])
    model = _model(tmp_path / "m")
    facts = measure_report(str(report), str(model))
    assert facts["models"][0]["bindings"][0]["actual_unknown"] is True
    verdict = _run_model(facts["models"][0])
    assert verdict["verdict"] == "blocked"
    assert verdict["checks"][0]["rule"] == "binding_expression_unsupported"


def test_legacy_label_bindings_still_resolve(tmp_path: Path) -> None:
    """Control: hand-fed query_ref-only bindings keep label resolution."""
    model = _model(tmp_path / "m")
    inventory = inventory_model(model)
    assert check_bindings([{"query_ref": "T.Good"}], inventory) == [
        {"rule": "binding_resolved", "status": "pass",
         "query_ref": "T.Good"}]
