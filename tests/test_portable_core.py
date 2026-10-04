"""Self-contained regression checks for the extracted VQS pre-alpha core."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vqs.evidence import (
    check_calibration,
    check_data_readiness,
    digest,
    load,
    review_template,
    safe_render_name,
    verify_review,
)
from vqs.pbir import report_context, source_digest
from vqs.policy import CRITERIA, DOCUMENT, REPORT

FIXTURES = (Path(__file__).resolve().parents[0] / "fixtures" / "vqs_agent_first"
            / "trust")
CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}


def test_observation_contract_is_complete() -> None:
    assert len(REPORT) == 25 and len(DOCUMENT) == 23
    assert len(set(REPORT)) == len(REPORT)
    assert len(set(DOCUMENT)) == len(DOCUMENT)
    assert set(REPORT + DOCUMENT) == set(CRITERIA)


def test_trust_fixture_contracts_are_valid() -> None:
    calibration = json.loads((FIXTURES / "calibration.json").read_text())
    readiness = json.loads((FIXTURES / "data_readiness.json").read_text())
    assert check_calibration(calibration, (500, 500)) == []
    assert check_data_readiness(readiness) == []


def test_pending_self_review_or_stale_review_cannot_pass() -> None:
    pages = [{"id": "page-1", "image": "page-1.png", "sha256": "abc",
              "pixels": (500, 500)}]
    review = review_template("report", "source", pages, "executor",
                             calibration=CALIBRATION, data_readiness=READINESS)
    assert review["calibration"] == CALIBRATION
    assert review["data_readiness"] == READINESS
    assert any(row["rule"] == "independent_reviewer_required" for row in
               verify_review("report", "source", pages, review, "executor"))
    review["reviewer"]["id"] = "independent"
    assert any(row["rule"] == "observation_unsubstantiated" for row in
               verify_review("report", "source", pages, review, "executor"))
    for answer in review["pages"][0]["observations"]:
        answer.update(status="pass", reason="Inspected the correct fresh image specifically for this criterion.")
    assert verify_review("report", "source", pages, review, "executor") == []
    pages[0]["sha256"] = "changed"
    assert any(row["rule"] == "review_image_stale" for row in
               verify_review("report", "source", pages, review, "executor"))


def test_calibration_rejects_bool_scale_and_non_dict_scope() -> None:
    bad_scale = dict(CALIBRATION)
    bad_scale["scale"] = True
    assert check_calibration(bad_scale, (500, 500)) != []
    bad_scope = dict(READINESS)
    bad_scope["scope"] = ["not-a-dict"]
    assert check_data_readiness(bad_scope) != []


def test_review_without_calibration_or_readiness_cannot_pass() -> None:
    pages = [{"id": "page-1", "image": "page-1.png", "sha256": "abc",
              "pixels": (500, 500)}]
    with pytest.raises(ValueError, match="calibration"):
        review_template("report", "source", pages, "executor",
                        calibration=None, data_readiness=READINESS)
    with pytest.raises(ValueError, match="data_readiness"):
        review_template("report", "source", pages, "executor",
                        calibration=CALIBRATION, data_readiness=None)
    review = review_template("report", "source", pages, "executor",
                             calibration=CALIBRATION, data_readiness=READINESS)
    review["reviewer"]["id"] = "independent"
    for answer in review["pages"][0]["observations"]:
        answer.update(status="pass", reason="Inspected the correct fresh image specifically for this criterion.")
    pages[0]["pixels"] = (500, 400)
    assert any(row["rule"] == "calibration_mismatch" for row in
               verify_review("report", "source", pages, review, "executor"))
    pages[0]["pixels"] = (500, 500)
    review["data_readiness"] = {"populated": False, "method": "scoped-dax-probe"}
    assert any(row["rule"] == "data_unpopulated" for row in
               verify_review("report", "source", pages, review, "executor"))


def test_inventory_source_hash_and_explicit_unknowns(tmp_path: Path) -> None:
    report = tmp_path / "Example.Report"
    pages = report / "definition" / "pages"
    visual = pages / "p1" / "visuals" / "vis1"
    visual.mkdir(parents=True)
    (pages / "pages.json").write_text(json.dumps({"pageOrder": ["p1"]}))
    (pages / "p1" / "page.json").write_text(json.dumps({
        "displayName": "Overview", "width": 1280, "height": 720}))
    (visual / "visual.json").write_text(json.dumps({
        "name": "vis1", "position": {"x": 24, "y": 24, "width": 350, "height": 210},
        "visual": {"visualType": "clusteredBarChart", "query": {"queryState": {
            "Category": {"projections": [{"queryRef": "Dim Product.Brand"}]},
            "Y": {"projections": [{"queryRef": "Fact Sales.Amount"}]}}}}}))
    first = report_context(report)
    assert first["pages"][0]["visuals"][0]["visual_id"] == "vis1"
    assert first["pages"][0]["visuals"][0]["field_bindings"]["Category"][0]["query_ref"] == "Dim Product.Brand"
    assert first["pages"][0]["visuals"][0]["evidence_limits"]["data_values"].startswith("requires")
    assert first["source_sha256"] == source_digest(report)
    (report / ".pbi").mkdir()
    (report / ".pbi" / "localSettings.json").write_text("personal machine settings")
    assert source_digest(report) == first["source_sha256"]
    (visual / "visual.json").write_text((visual / "visual.json").read_text() + " ")
    assert report_context(report)["source_sha256"] != first["source_sha256"]
    record = tmp_path / "example.json"
    record.write_text('{"ok": true}', encoding="utf-8")
    assert load(record) == {"ok": True} and len(digest(record)) == 64

def test_render_name_rejects_ads_and_whitespace_fixer() -> None:
    assert safe_render_name("p1.png:evil") is None
    assert safe_render_name("p1.png") == "p1.png"
    pages = [{"id": "p1", "image": "p1.png", "sha256": "s"}]
    with pytest.raises(ValueError, match="fixer id"):
        review_template("report", "source", pages, "   ",
                        calibration=CALIBRATION, data_readiness=READINESS)
