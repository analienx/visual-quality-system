"""P0-U2: single orchestrated Power BI workflow (vqs run / vqs_run).

Static legs run end-to-end on sealed runs; runtime legs record precise
BLOCKED stages when capability is missing; resume revalidates sealed
provenance before reusing any stage. Hosted CI only (no live Desktop).
"""
import json
import shutil
from pathlib import Path

from vqs.cli import main as vqs_main
from vqs.config import default_config
from vqs.coordinator import STAGE_ORDER, run_workflow
from vqs.mcp.schemas import validate_call
from vqs.pipeline import review_report
from vqs.repair.allowlist import validate_plan

POWERBI_FIX = Path(__file__).parent / "powerbi" / "fixtures"


def _overlap_facts():
    """Failing overlap plus measured canvas, no unknowns."""
    visuals = [
        {"page": "P1", "visual": "A", "bound": True,
         "x": 0, "y": 0, "width": 200, "height": 200, "z": 0.0},
        {"page": "P1", "visual": "B", "bound": True,
         "x": 100, "y": 100, "width": 200, "height": 200, "z": 1.0}]
    pages = [{"page": "P1", "width": 1280, "height": 720,
              "visuals": [{"visual": "A", "x": 0, "y": 0,
                           "width": 200, "height": 200},
                          {"visual": "B", "x": 100, "y": 100,
                           "width": 200, "height": 200}]}]
    return {"rules": {"layout.no_visual_overlap": {"visuals": visuals},
                      "layout.visuals_within_page": {"pages": pages}}}


def _stages(envelope):
    return {entry["stage"]: entry for entry in envelope["stages"]}


def _desktop_config():
    config = default_config()
    config["data_permissions"]["allow_desktop"] = True
    return config


# Static sequencing ------------------------------------------------------


def test_review_mode_facts_only_static(tmp_path: Path) -> None:
    """Review mode triages statically; runtime legs stay not_run."""
    envelope = run_workflow(facts=_overlap_facts(), mode="review",
                            scope="static", run_root=str(tmp_path),
                            run_id="u2-review")
    assert envelope["tool"] == "vqs.run"
    assert envelope["verdict"] == "fail"
    stages = _stages(envelope)
    assert set(stages) >= set(STAGE_ORDER)
    assert stages["inspect"]["status"] == "pass"
    assert stages["review"]["status"] == "pass"
    assert envelope["review_verdict"] == "fail"
    for name in ("readiness", "baseline_capture", "candidate_reload",
                 "answer_regression", "recapture", "handoff"):
        assert stages[name]["status"] == "not_run", name
    assert stages["propose"]["status"] == "not_run"
    assert stages["summary"]["status"] == "fail"
    assert envelope["summary"]["outcome"] == "not_accepted"
    assert envelope["summary"]["blocked_stages"] == []
    assert envelope["summary"]["child_runs"]["review"]["run_id"]
    by_check = {item["check"]: item for item in envelope["findings"]}
    review_finding = by_check["stage:review"]
    assert review_finding["status"] == "pass"
    assert "static verdict fail" in str(
        review_finding["evidence_basis"].get("reason"))


def test_release_scope_reviewer_authority_stays_blocked(
        tmp_path: Path) -> None:
    """Release scope never accepts on local observations alone.

    Release acceptance requires a trusted reviewer authority that
    does not exist yet, so the summary records reviewer_authority
    blocked and acceptance stays False whatever the local verdict.
    """
    envelope = run_workflow(facts=_overlap_facts(), mode="review",
                            scope="release", run_root=str(tmp_path),
                            run_id="u2-release")
    authority = envelope["summary"]["reviewer_authority"]
    assert authority["status"] == "blocked"
    assert authority["authority"] == "none"
    assert "no trusted release reviewer" in authority["reason"]
    assert envelope["summary"]["acceptance"] is False


def test_propose_mode_synthesizes_plan(tmp_path: Path) -> None:
    """Propose mode stops after the safe proposal with a plan.

    Generating fixes is workflow success, not report acceptance: the
    still-failing report reports proposal_ready instead of accepted.
    """
    envelope = run_workflow(facts=_overlap_facts(), mode="propose",
                            scope="static", run_root=str(tmp_path),
                            run_id="u2-propose")
    assert envelope["verdict"] == "pass"
    stages = _stages(envelope)
    assert stages["propose"]["status"] == "pass"
    assert envelope["summary"]["outcome"] == "proposal_ready"
    plan = envelope["plan"]
    assert plan is not None
    assert validate_plan(plan, "orig", "cand") == []
    assert stages["repair"]["status"] == "not_run"
    assert stages["verify"]["status"] == "not_run"


def test_repair_mode_static_end_to_end(tmp_path: Path) -> None:
    """Repair mode applies the synthesized overlap move and remeasures.

    U7: the overlap resolves, but the mixed textSize cohort (unknown
    effective inherited value) blocks the remeasure verdict instead of
    failing it; the run reports blocked with the move sealed.
    """
    report = tmp_path / "Overlap.Report"
    shutil.copytree(POWERBI_FIX / "mini_report", report)
    visual_path = (report / "definition" / "pages" / "P1" / "visuals"
                   / "slicerb" / "visual.json")
    visual = json.loads(visual_path.read_text(encoding="utf-8"))
    visual["position"]["x"] = 900
    visual_path.write_text(json.dumps(visual, indent=2) + "\n",
                           encoding="utf-8")
    model = tmp_path / "Overlap.SemanticModel"
    shutil.copytree(POWERBI_FIX / "mini_model", model)
    envelope = run_workflow(report_dir=str(report), model_dir=str(model),
                            mode="repair", scope="static",
                            run_root=str(tmp_path / "runs"),
                            run_id="u2-repair")
    assert envelope["verdict"] == "blocked", envelope["summary"]
    stages = _stages(envelope)
    assert stages["inspect"]["status"] == "pass"
    assert stages["review"]["status"] == "pass"
    assert envelope["review_verdict"] == "fail"
    assert stages["propose"]["status"] == "pass"
    assert stages["repair"]["status"] == "pass"
    assert stages["verify"]["status"] == "pass"
    assert stages["remeasure"]["status"] == "blocked"
    assert envelope["summary"]["outcome"] == "blocked"
    assert envelope["summary"]["blocked_stages"] == ["remeasure"]
    assert envelope["summary"]["resolved_findings"] != []
    assert envelope["summary"]["remaining_findings"] == []
    assert envelope["summary"]["new_regressions"] == []
    assert envelope["summary"]["candidate_status"]["status"] == "verified"
    candidate = envelope["summary"]["candidate"]
    assert candidate is not None
    moved = json.loads((Path(candidate) / "definition" / "pages" / "P1"
                        / "visuals" / "slicerb"
                        / "visual.json").read_text(encoding="utf-8"))
    assert moved["position"]["x"] == 944
    assert envelope["quality_after"] == "blocked"
    assert (tmp_path / "runs" / "u2-repair" / "plan.json").is_file()


# Runtime gating and resume -----------------------------------------------


def test_desktop_scope_without_runtime_blocks_readiness(tmp_path: Path
                                                       ) -> None:
    """Requested-but-missing live runtime is a precise BLOCKED stage."""
    envelope = run_workflow(facts=_overlap_facts(), mode="review",
                            scope="desktop", config=_desktop_config(),
                            run_root=str(tmp_path), run_id="u2-ready")
    stages = _stages(envelope)
    assert stages["readiness"]["status"] == "blocked"
    assert "desktop-bridge-cli" in str(
        stages["readiness"].get("evidence", {}))
    assert envelope["verdict"] == "blocked"
    assert envelope["summary"]["blocked_stages"] == ["readiness", "handoff"]


def test_desktop_scope_needs_permission(tmp_path: Path) -> None:
    """Desktop scope without the permission blocks before probing."""
    envelope = run_workflow(facts=_overlap_facts(), mode="review",
                            scope="desktop", run_root=str(tmp_path),
                            run_id="u2-perm")
    stages = _stages(envelope)
    assert stages["readiness"]["status"] == "blocked"
    assert "allow_desktop" in stages["readiness"]["reason"]
    assert envelope["verdict"] == "blocked"


def test_resume_reuses_sealed_evidence(tmp_path: Path) -> None:
    """Resume revalidates provenance and reuses the sealed review."""
    facts = _overlap_facts()
    first = run_workflow(facts=facts, mode="review", scope="static",
                         run_root=str(tmp_path), run_id="u2-a")
    assert first["verdict"] == "fail"
    assert first["summary"]["outcome"] == "not_accepted"
    second = run_workflow(facts=facts, mode="review", scope="static",
                          run_root=str(tmp_path), run_id="u2-b",
                          resume_from="u2-a")
    assert second["verdict"] == "fail"
    assert second["summary"]["outcome"] == "not_accepted"
    first_review = _stages(first)["review"]["run_id"]
    assert _stages(second)["review"]["run_id"] == first_review
    manifest = json.loads((tmp_path / "u2-b" / "manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["resumed_from"] == "u2-a"


def test_resume_refuses_changed_sources(tmp_path: Path) -> None:
    """Changed facts between resume runs block instead of blending."""
    run_workflow(facts=_overlap_facts(), mode="review", scope="static",
                 run_root=str(tmp_path), run_id="u2-c")
    drifted = _overlap_facts()
    drifted["rules"]["layout.no_visual_overlap"]["visuals"][1]["x"] = 101
    refused = run_workflow(facts=drifted, mode="review", scope="static",
                           run_root=str(tmp_path), run_id="u2-d",
                           resume_from="u2-c")
    assert refused["verdict"] == "blocked"
    assert any("provenance changed" in reason
               for reason in refused["blocked_reasons"])


def test_invalid_mode_blocked(tmp_path: Path) -> None:
    """An unknown mode blocks without creating a run."""
    refused = run_workflow(facts=_overlap_facts(), mode="bogus",
                           run_root=str(tmp_path), run_id="u2-mode")
    assert refused["verdict"] == "blocked"
    assert not (tmp_path / "u2-mode").exists()


# Ladders and surfaces ----------------------------------------------------


def test_review_desktop_ladder(tmp_path: Path, monkeypatch) -> None:
    """Review desktop scope names each missing prerequisite precisely."""
    denied = review_report(facts={}, scope="desktop",
                           config=_desktop_config(),
                           run_root=str(tmp_path), run_id="u2-noacc")
    assert denied["verdict"] == "blocked"
    assert any("Task 5" in reason and "report_dir" in reason
               for reason in denied["blocked_reasons"])
    from vqs import coordinator

    monkeypatch.setattr(coordinator, "bridge_present", lambda: False)
    noreport = review_report(
        report_dir=str(POWERBI_FIX / "mini_report"), scope="desktop",
        config=_desktop_config(), run_root=str(tmp_path),
        run_id="u2-nobridge")
    assert noreport["verdict"] == "blocked"
    assert any("Task 5" in reason and "Bridge" in reason
               for reason in noreport["blocked_reasons"])


def test_cli_run_review_mode(tmp_path: Path, capsys) -> None:
    """vqs run drives the same engine from the CLI."""
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(_overlap_facts()), encoding="utf-8")
    code = vqs_main(["run", "--facts", str(facts_path),
                     "--mode", "review", "--run-root", str(tmp_path),
                     "--run-id", "u2-cli", "--report-out",
                     str(tmp_path / "envelope.json")])
    capsys.readouterr()
    assert code == 1
    envelope = json.loads((tmp_path / "envelope.json").read_text(
        encoding="utf-8"))
    assert envelope["tool"] == "vqs.run"
    assert envelope["verdict"] == "fail"
    assert envelope["summary"]["outcome"] == "not_accepted"


def test_mcp_run_schema() -> None:
    """The MCP tool carries mode/scope through the same engine."""
    spec, error = validate_call("vqs_run", {"run_root": "r"})
    assert error is None
    assert spec is not None
    spec, error = validate_call("vqs_run", {"run_root": "r", "mode": "bogus"})
    assert error is not None
    spec, error = validate_call("vqs_run", {"run_root": "r", "mode": "repair",
                                            "scope": "desktop"})
    assert error is None
    assert spec is not None
