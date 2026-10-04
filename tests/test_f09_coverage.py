"""F09 RED: coverage issues must gate verdicts; model resolves from inventory.

Malformed pages/visuals, unresolvable model references, invalid
geometry, and unreadable sources must block report-wide approval with
affected source IDs. The model inventory resolves from the report's
own dataset reference (production inventory), never from the optional
caller claim alone.
"""
import json
from pathlib import Path

from vqs.pipeline import inspect_report, review_report
from vqs.powerbi.insights import page_insights
from vqs.powerbi.measure import measure_report


def _report(root: Path, *, pbir_dataset: str | None = None) -> Path:
    report = root / "R.Report"
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages.parent / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages.parent / "version.json").write_text(json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "1.0"}),
                                        encoding="utf-8")
    (pages.parent / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "O", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "visual": {"visualType": "card"}}),
        encoding="utf-8")
    if pbir_dataset is not None:
        (report / "definition.pbir").write_text(json.dumps(
            {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "1.0", "datasetReference": {
                "byPath": {"path": f"../{pbir_dataset}.SemanticModel"}}}),
            encoding="utf-8")
    return report


def test_f09_malformed_visual_blocks_inspect(tmp_path: Path) -> None:
    report = _report(tmp_path)
    visual = (report / "definition/pages/P1/visuals/cardx/visual.json")
    visual.write_text("{not json", encoding="utf-8")
    envelope = inspect_report(str(report))
    assert envelope["verdict"] == "blocked"
    assert any("visual_doc_unreadable" in reason
               for reason in envelope["blocked_reasons"])


def test_f09_coverage_issues_block_review(tmp_path: Path) -> None:
    report = _report(tmp_path)
    (report / "definition/pages/P1/visuals/cardx/visual.json").write_text(
        "{not json", encoding="utf-8")
    facts = measure_report(str(report))
    assert facts["coverage"]["issues"]
    envelope = review_report(facts=facts)
    assert envelope["verdict"] == "blocked"
    hits = [finding for finding in envelope["findings"]
            if finding.get("check") == "coverage:visual_doc_unreadable"]
    assert len(hits) == 1
    assert isinstance(hits[0]["evidence_basis"], dict)
    assert hits[0]["evidence_basis"]["rule"] == "visual_doc_unreadable"
    assert hits[0]["location"] == {"page": "P1", "visual": "cardx"}


def test_f09_unresolved_model_reference_blocks(tmp_path: Path) -> None:
    report = _report(tmp_path, pbir_dataset="Ghost")
    envelope = inspect_report(str(report))
    assert envelope["verdict"] == "blocked"
    assert any("model_reference_unresolved" in reason
               for reason in envelope["blocked_reasons"])


def test_f09_model_resolves_from_report_reference(tmp_path: Path) -> None:
    report = _report(tmp_path, pbir_dataset="M")
    model = tmp_path / "M.SemanticModel"
    (model / "tables").mkdir(parents=True)
    (model / "tables" / "T.tmdl").write_text("table T\n", encoding="utf-8")
    facts = measure_report(str(report))
    assert facts.get("models")
    assert facts["models"][0]["model_dir"] == str(model)


def test_f09_invalid_geometry_is_an_explicit_issue(tmp_path: Path) -> None:
    report = _report(tmp_path)
    visual = report / "definition/pages/P1/visuals/cardx/visual.json"
    doc = json.loads(visual.read_text(encoding="utf-8"))
    doc["position"]["width"] = "wide"
    visual.write_text(json.dumps(doc), encoding="utf-8")
    insight = page_insights(str(report))
    rules = [issue.get("rule") for issue in
             insight["coverage"]["issues"]]
    assert "visual_geometry_unproven" in rules
    named = [issue for issue in insight["coverage"]["issues"]
             if issue.get("rule") == "visual_geometry_unproven"]
    assert named[0]["page"] == "P1"
    assert named[0]["visual"] == "cardx"


def test_f09_absent_page_index_inspects_unindexed(tmp_path: Path) -> None:
    """R01: the page index is optional; an absent index inspects the
    physical pages in display-name order instead of blocking."""
    report = _report(tmp_path)
    (report / "definition" / "pages.json").unlink()
    envelope = inspect_report(str(report))
    assert envelope["verdict"] == "pass", envelope
