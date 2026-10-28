"""Real fictional Contoso AI repair triage must be safe and actionable."""
from __future__ import annotations

from pathlib import Path

from vqs.coordinator import run_workflow
from vqs.pbir import source_digest

REPORT = (Path(__file__).resolve().parents[1] / "examples" /
          "contoso-retail" / "Contoso Retail.Report")


def test_real_contoso_only_owner_dependent_fixes_remain(tmp_path: Path) -> None:
    before = source_digest(REPORT)
    result = run_workflow(
        report_dir=str(REPORT), mode="repair", scope="static",
        run_root=str(tmp_path), run_id="agent-no-safe-candidate")
    assert result["verdict"] == "blocked"
    summary = result["summary"]
    assert summary["remaining_findings"] == [
        "insight.no_cross_page_duplicate_grain",
        "typography.format_declaration_consistency",
    ]
    assert summary["candidates_proposed"] == 0
    assert summary["candidate"] is None
    assert summary["repair_triage"]["status"] == "no_safe_candidate"
    assert summary["repair_triage"]["requires_proven_fix_or_owner_plan"] is True
    assert summary["repair_triage"]["promotion_performed"] is False
    decisions = summary["repair_triage"]["decisions"]
    assert len(decisions) >= 3
    assert all(d["status"] == "needs_owner_decision" for d in decisions)
    assert any("overview/detail" in d["reason"] for d in decisions)
    assert any("rendered effective style" in d["reason"] for d in decisions)
    assert any("explicit visual-size declarations diverge" in d["reason"]
               for d in decisions)
    assert not any("layout.no_visual_overlap" == d["check"]
                   for d in decisions)
    assert all("run propose mode" not in s for s in result["blocked_reasons"])
    assert any("never retry propose" in action for action in result["next_actions"])
    assert source_digest(REPORT) == before
    assert result["stages"][-1]["stage"] == "summary"


def test_multiple_same_check_findings_never_suppress_fallback_decision():
    from vqs.repair.synthesize import synthesize_plan

    findings = [
        {"check": "typography.format_declaration_consistency",
         "status": "fail", "detail": {"evidence": {
             "conflicts": [{"cohort": "table/grid.textSize"}],
             "pending": []}}},
        {"check": "typography.format_declaration_consistency",
         "status": "fail", "detail": {"evidence": {
             "conflicts": [], "pending": []}}},
    ]
    result = synthesize_plan(findings, {"rules": {}})
    assert result["plan"] is None
    assert result["candidates"] == []
    assert len(result["decisions"]) == 2
    assert "diverge" in result["decisions"][0]["reason"]
    assert "no proved effective format" in result["decisions"][1]["reason"]


def test_explicit_owner_plan_attempt_not_masked_by_no_autofix(
    tmp_path: Path, monkeypatch,
):
    import json

    from vqs.coordinator import run_workflow

    written = tmp_path / "owner-plan.json"
    written.write_text(json.dumps({"schema_version": "vqs.plan/1",
                                  "operations": []}), encoding="utf8")
    reached = []

    def bounded_repair(plan_path, original, candidate, **_kwargs):
        reached.append((plan_path, original, candidate))
        return {"verdict": "blocked",
                "blocked_reasons": ["owner plan reached independent validation"]}

    monkeypatch.setattr("vqs.pipeline.repair_candidate", bounded_repair)
    before = source_digest(REPORT)
    result = run_workflow(
        report_dir=str(REPORT), mode="repair", scope="static",
        run_root=str(tmp_path / "runs"),
        run_id="owner-explicit-plan",
        plan_path=str(written),
    )
    assert len(reached) == 1
    assert Path(reached[0][0]).is_file()
    assert result["summary"]["repair_triage"]["status"] == "owner_plan_supplied"
    assert result["summary"]["repair_triage"]["promotion_performed"] is False
    assert result["verdict"] == "blocked"
    assert result["summary"]["candidate"] is None
    assert source_digest(REPORT) == before
