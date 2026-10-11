"""One command gives real PBIR visual findings and safely synthesized edits."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_r6_e07_authoring import _project

from vqs.cli import main
from vqs.triage import analyze, markdown

SOURCE = Path(__file__).parent / "powerbi" / "fixtures" / "mini_report"


def _fixture(tmp_path: Path, *, moved: bool = False) -> Path:
    report = tmp_path / "original.Report"
    shutil.copytree(SOURCE, report)
    if moved:
        visual_file = (report / "definition/pages/P1/visuals/"
                       "titlebox/visual.json")
        doc = json.loads(visual_file.read_text(encoding="utf-8"))
        doc["position"]["x"] = -20
        visual_file.write_text(json.dumps(doc), encoding="utf-8")
    return report


def test_readable_triage_separates_render_unknown_from_failure(tmp_path: Path):
    report = _fixture(tmp_path)
    result = analyze(str(report), run_root=str(tmp_path / "runs"),
                     run_id="baseline")
    assert result["status"] == "diagnosed"
    assert result["summary"]["pages"] == 1
    assert result["summary"]["visuals"] == 5
    assert result["summary"]["proven_issues"] == 0
    assert result["summary"]["needs_evidence"] >= 1
    assert result["plan"] is None
    output = markdown(result)
    assert "Needs evidence:" in output
    assert "NOT visual approval" in output
    assert "None" not in output.split("Prioritized work")[1].split(
        "What this cannot prove")[0]


def test_typed_suggestion_for_real_visual_geometry(tmp_path: Path):
    report = _fixture(tmp_path, moved=True)
    result = analyze(str(report), run_root=str(tmp_path / "runs"),
                     run_id="geometry")
    assert result["status"] == "diagnosed", result
    assert result["summary"]["proven_issues"] >= 1
    issue = next(item for item in result["findings"]
                 if item["check"] == "layout.visuals_within_page")
    assert issue["priority"] == "high"
    assert issue["candidate_count"] >= 1, result["decisions"]
    assert "titlebox" in json.dumps(issue)
    assert result["plan"] is not None
    assert result["plan"]["operations"]
    assert any("titlebox" in op["writes"][0]
               for op in result["plan"]["operations"])
    assert result["source_sha256"]
    # Triage itself is read-only: the source visual is still out of canvas.
    path = report / "definition/pages/P1/visuals/titlebox/visual.json"
    assert json.loads(path.read_text(encoding="utf-8"))["position"]["x"] == -20


def test_cli_markdown_json_and_plan_export(tmp_path: Path, capsys):
    report = _fixture(tmp_path, moved=True)
    output = tmp_path / "report.md"
    plan = tmp_path / "candidate-plan.json"
    exit_code = main([
        "triage", str(report), "--run-root", str(tmp_path / "runs"),
        "--run-id", "cli-triage", "--out", str(output),
        "--plan-out", str(plan),
    ])
    assert exit_code == 0
    assert "Prioritized work" in output.read_text(encoding="utf-8")
    assert "titlebox" in output.read_text(encoding="utf-8")
    assert json.loads(plan.read_text(encoding="utf-8"))["operations"]
    printout = capsys.readouterr()
    assert not printout.err


def test_triage_fails_closed_for_unreadable_sources(tmp_path: Path):
    result = analyze(str(tmp_path / "missing.Report"),
                     run_root=str(tmp_path / "no-runs"))
    assert result["status"] == "blocked"
    assert result["plan"] is None
    assert "blocked" in markdown(result).lower()


def test_second_independent_fixture_can_be_diagnosed(tmp_path: Path):
    _proj, report = _project(tmp_path)
    result = analyze(str(report), run_root=str(tmp_path / "runs"),
                     run_id="second")
    assert result["status"] == "diagnosed", result
    assert result["summary"]["pages"] == 1
    assert result["summary"]["visuals"] == 1
    assert result["run_id"] == "second"
    assert (tmp_path / "runs" / "second" / "manifest.json").is_file()


def test_plan_not_exported_if_no_candidate(tmp_path: Path):
    report = _fixture(tmp_path)
    plan = tmp_path / "missing-plan.json"
    exit_code = main(["triage", str(report), "--run-root",
                      str(tmp_path / "runs"), "--run-id", "no-plan",
                      "--plan-out", str(plan)])
    assert exit_code == 0
    assert not plan.exists()


def test_pbip_input_resolves_report_and_local_semantic_model(tmp_path: Path):
    from test_u4_promotion import _project as create_project

    project, report = create_project(tmp_path, "pbip-project")
    semantic_definition = project / "Model.SemanticModel" / "definition"
    semantic_definition.mkdir()
    (semantic_definition / "tables").mkdir()
    (semantic_definition / "tables" / "T.tmdl").write_text(
        "table T\n\n    measure Example = 1\n", encoding="utf-8")
    pbip = project / "Report.pbip"
    pbip.write_text(json.dumps({"version": "1.0", "artifacts": [
        {"report": {"path": report.name}}
    ]}), encoding="utf-8")
    result = analyze(str(pbip), run_root=str(tmp_path / "runs"),
                     run_id="pbip-run")
    assert result["status"] == "diagnosed", result
    assert result["report_dir"] == str(report)
    assert result["model_dir"] == str(semantic_definition)
    assert result["model_sha256"]


def test_pbip_escaping_project_is_refused(tmp_path: Path):
    pbip = tmp_path / "unsafe.pbip"
    pbip.write_text(json.dumps({"version": "1.0", "artifacts": [
        {"report": {"path": "../escape.Report"}}
    ]}), encoding="utf-8")
    result = analyze(str(pbip), run_root=str(tmp_path / "no-runs"))
    assert result["status"] == "blocked"
    assert result["plan"] is None
    assert not (tmp_path / "no-runs").exists()


def test_functional_triage_to_verified_repair_reduces_defects(tmp_path: Path):
    from vqs.pipeline import repair_candidate, verify_candidate
    from vqs.repair.execute import tree_digest

    original = _fixture(tmp_path, moved=True)
    original_sha = tree_digest(original)
    before = analyze(str(original), run_root=str(tmp_path / "runs"),
                     run_id="before")
    assert before["summary"]["proven_issues"] == 1
    assert before["plan"] is not None
    plan_path = tmp_path / "safe-plan.json"
    plan_path.write_text(json.dumps(before["plan"]), encoding="utf-8")
    candidate = tmp_path / "candidate.Report"
    repair = repair_candidate(
        str(plan_path), str(original), str(candidate),
        run_root=str(tmp_path / "runs"), run_id="fix",
        authoring_backend="direct", authoring_assurance="portable")
    assert repair["verdict"] == "pass", repair
    verified = verify_candidate(run_root=str(tmp_path / "runs"), run_id="fix")
    assert verified["verdict"] == "pass", verified
    after = analyze(str(candidate), run_root=str(tmp_path / "runs"),
                    run_id="after")
    assert after["status"] == "diagnosed", after
    assert after["summary"]["proven_issues"] == 0
    assert after["summary"]["typed_candidates"] == 0
    assert tree_digest(original) == original_sha
    # No fake general visual approval: the unresolved render issue survives.
    assert after["summary"]["needs_evidence"] >= 1
