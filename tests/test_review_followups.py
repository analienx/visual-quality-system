"""Regression tests for the independent review of PR #122."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vqs import gate
from vqs.coordinator import _owner_decisions, run_workflow
from vqs.repair.decisions import (
    ANSWERS_SCHEMA,
    decision_id,
    load,
    normalize_findings,
    subject_of,
    waived_checks,
)
from vqs.repair.synthesize import synthesize_plan

REPORT = (Path(__file__).resolve().parents[1] / "examples" /
          "contoso-retail" / "Contoso Retail.Report")
OVERLAP = "layout.no_visual_overlap"


def _overlap_facts(page: str = "P1") -> dict:
    return {"rules": {
        OVERLAP: {"visuals": [
            {"page": page, "visual": "a", "x": 0, "y": 0, "width": 100, "height": 100},
            {"page": page, "visual": "b", "x": 10, "y": 10, "width": 100, "height": 100},
            {"page": page, "visual": "c", "x": 400, "y": 0, "width": 50, "height": 50},
            {"page": page, "visual": "d", "x": 440, "y": 10, "width": 50, "height": 50}]},
        "layout.visuals_within_page": {"pages": [
            {"page": page, "width": 1280, "height": 720}]}}}


def _overlap_finding(page: str = "P1") -> dict:
    return {"check": OVERLAP, "status": "fail", "detail": {"evidence": {"conflicts": [
        {"page": page, "visuals": ["a", "b"],
         "overlap": {"x": 10, "y": 10, "width": 90, "height": 90}},
        {"page": page, "visuals": ["c", "d"],
         "overlap": {"x": 440, "y": 10, "width": 10, "height": 40}}]}}}


def test_autofixable_conflict_keeps_check_unwaivable() -> None:
    """Waiving the ambiguous overlap must not excuse the auto-fixable one."""
    result = synthesize_plan([_overlap_finding()], _overlap_facts())
    assert result["candidates"], "small overlap should be auto-fixable"
    ambiguous = [d for d in result["decisions"]
                 if d["status"] == "needs_owner_decision"]
    assert ambiguous
    waived = [d["subject"] for d in ambiguous]
    assert waived_checks([_overlap_finding()], _overlap_facts(), waived) == []


def test_candidate_and_decision_share_page_scoped_subject() -> None:
    result = synthesize_plan([_overlap_finding()], _overlap_facts())
    (candidate,) = result["candidates"]
    assert subject_of(candidate) == f"{OVERLAP}|page=P1|pair=c+d"
    decision = next(d for d in result["decisions"]
                    if d["status"] == "needs_owner_decision")
    assert decision["subject"] == f"{OVERLAP}|page=P1|pair=a+b"


def test_same_pair_on_two_pages_gets_distinct_ids() -> None:
    first = subject_of({"check": OVERLAP, "page": "P1", "pair": ["a", "b"]})
    second = subject_of({"check": OVERLAP, "page": "P2", "pair": ["a", "b"]})
    assert first != second
    assert decision_id(first, "s" * 64) != decision_id(second, "s" * 64)


def test_envelope_findings_normalize_to_sealed_shape() -> None:
    sealed = _overlap_finding()
    envelope = {"check": sealed["check"], "status": "fail",
                "evidence_basis": sealed["detail"]}
    assert normalize_findings([envelope]) == [{**envelope, "detail": sealed["detail"]}]
    assert normalize_findings(None) == []


def test_gate_fails_closed_when_review_never_produced_findings(
        tmp_path: Path, monkeypatch) -> None:
    head = tmp_path / "head"
    shutil.copytree(REPORT.parent, head)

    def refused(**_kwargs):
        return {"verdict": "blocked", "findings": [],
                "blocked_reasons": ["config refused"]}

    monkeypatch.setattr("vqs.pipeline.review_report", refused)
    result = gate.run(str(head / "Contoso Retail.Report"))
    assert result["verdict"] == "blocked"
    assert "config refused" in result["reason"]


def test_gate_reviews_baseline_with_the_head_config(tmp_path: Path,
                                                    monkeypatch) -> None:
    seen = []
    original = gate.evaluate

    def spy(report, model=None, config=None):
        seen.append(config)
        return original(report, model, config)

    monkeypatch.setattr(gate, "evaluate", spy)
    config = {"rules": {}, "marker": "strict"}
    gate.run(str(REPORT), baseline=REPORT, config=config)
    assert len(seen) == 2 and all(item is config for item in seen)


def test_review_mode_accepts_answers_from_a_repair_template(tmp_path: Path) -> None:
    runs = str(tmp_path / "runs")
    blocked = run_workflow(report_dir=str(REPORT), mode="repair", scope="static",
                           run_root=runs, run_id="t", authoring_backend="direct")
    triage = blocked["summary"]["repair_triage"]
    answers = {"schema": ANSWERS_SCHEMA, "owner": "owner",
               "source_sha256": triage["decision_source_sha256"],
               "answers": [{"decision_id": d["decision_id"], "option": "accept"}
                           for d in triage["decisions"]]}
    review = run_workflow(report_dir=str(REPORT), mode="review", scope="static",
                          run_root=runs, run_id="r", decisions=answers)
    stage = next(s for s in review["stages"] if s["stage"] == "owner_decisions")
    assert stage["status"] == "pass", stage.get("reason")
    assert review["summary"]["outcome"] == "accepted_with_waivers"


def test_owner_merge_keeps_report_wide_affected_pages(tmp_path: Path) -> None:
    source = "a" * 64
    subject = "typography.format_declaration_consistency|cohort=x"
    ident = decision_id(subject, source)
    owner_op = {"type": "format.set_explicit",
                "selector": {"page": "P1", "visual": "v"}, "target": "visual",
                "path": ["visual", "objects", "labels", 0, "properties", "fontSize"],
                "old": "9D", "value": "10D", "effective": "10D",
                "proof": f"owner-decision:{ident}:size:10D",
                "writes": ["definition/pages/P1/visuals/v/visual.json"]}
    theme_op = {"type": "theme.set", "selector": {"page": "P1", "visual": "w"},
                "target": "visual", "value": "x",
                "path": ["visual", "objects", "title", 0, "properties", "show",
                         "expr", "Literal", "Value"],
                "writes": ["definition/pages/P1/visuals/w/visual.json"]}
    answers, issues = load({"schema": ANSWERS_SCHEMA, "owner": "o",
                            "source_sha256": source,
                            "answers": [{"decision_id": ident, "option": "size:10D"}]})
    assert not issues
    state = {"answers": answers, "review_id": "r",
             "triage": {"source_sha256": source, "decisions": [{
                 "check": "typography.format_declaration_consistency",
                 "status": "needs_owner_decision", "decision_id": ident,
                 "subject": subject, "options": [
                     {"id": "size:10D", "effect": "apply", "label": "",
                      "operations": [owner_op]}]}]},
             "plan": {"operations": [theme_op], "affected_pages": ["P1", "P2", "P3"],
                      "finding_checks": ["x"]},
             "merged": {"rules": {"layout.visuals_within_page": {"pages": [
                 {"page": "P1"}, {"page": "P2"}, {"page": "P3"}]}}}}
    stages: list = []
    assert _owner_decisions(state, stages.append,
                            {"mode": "repair", "run_root": str(tmp_path)})
    assert state["plan"]["affected_pages"] == ["P1", "P2", "P3"]
    assert len(state["plan"]["operations"]) == 2


@pytest.mark.parametrize("module,attr", [
    ("vqs.powerbi.os_process", "_SCRIPT"),
])
def test_process_query_forces_utf8_output(module: str, attr: str) -> None:
    import importlib

    script = getattr(importlib.import_module(module), attr)
    assert script.startswith("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;")
