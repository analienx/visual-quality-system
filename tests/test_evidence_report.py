"""Human-readable evidence is bounded by the existing run seal."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.coordinator import run_workflow
from vqs.pbir import source_digest
from vqs.run_store import append_event, create_run, digest_bytes, seal_run

REPORT = Path(__file__).resolve().parents[1] / "examples/contoso-retail/Contoso Retail.Report"


def _sealed(root: Path, stages: object, *, run_id: str = "test-run", tool: str = "vqs.run/1",
            report: Path = REPORT, mismatch: bool = False) -> Path:
    run = create_run(root, run_id, {"pipeline": "vqs.run/1", "params": {
        "mode": "repair", "scope": "static", "report_dir": str(report),
        "source_sha256": source_digest(report)}})
    payload = json.dumps(stages).encode("utf-8")
    (run / "stages.json").write_bytes(payload)
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict):
                append_event(run, {"kind": "stage", **stage})
    if mismatch:
        append_event(run, {"kind": "stage", "stage": "foreign", "status": "pass"})
    append_event(run, {"kind": "blocked", "verdict": "blocked"})
    seal_run(run, "blocked", artifacts={"stages": {"path": "stages.json",
                                                      "sha256": digest_bytes(payload)}},
             bindings={"tool": tool})
    return run


def _stages() -> list[dict]:
    return [
        {"stage": "review", "status": "pass", "evidence": {"verdict": "fail", "findings": [
            {"check": "fixed", "status": "fail"}, {"check": "regressed", "status": "pass"}]}},
        {"stage": "propose", "status": "pass", "evidence": {"decisions": [{
            "status": "needs_owner_decision", "decision_id": "q1", "question": "Choose?",
            "options": [{"id": "a", "label": "One", "effect": "apply"},
                        {"id": "b", "label": "Two", "effect": "waive"}]}]}},
        {"stage": "repair", "status": "pass", "run_id": "repair-child",
         "evidence": {"candidate": "private candidate"}},
        {"stage": "verify", "status": "pass"},
        {"stage": "remeasure", "status": "pass", "evidence": {"verdict": "fail", "findings": [
            {"check": "fixed", "status": "pass"}, {"check": "regressed", "status": "fail"}]}},
        {"stage": "recapture", "status": "not_run", "reason": "static scope"},
        {"stage": "summary", "status": "blocked", "evidence": {"outcome": "blocked"}},
    ]


def test_sealed_report_compares_findings_and_shows_decisions(tmp_path, capsys):
    run = _sealed(tmp_path, _stages())
    original = (run / "stages.json").read_bytes()
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 0
    text = capsys.readouterr().out
    assert '"fixed"' in text and '"regressed"' in text
    assert '"q1"' in text and '"One"' in text and '"Two"' in text
    assert "not_run" in text and "not independent" in text.lower()
    assert "not a signature" in text.lower()
    assert (run / "stages.json").read_bytes() == original


def test_actual_blocked_fictional_run_reports_unknown_after(tmp_path, capsys):
    result = run_workflow(report_dir=str(REPORT), mode="repair", scope="static",
                          run_root=str(tmp_path), run_id="actual", authoring_backend="direct")
    assert result["verdict"] == "blocked"
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "actual"]) == 0
    text = capsys.readouterr().out
    assert "unknown" in text.lower()
    assert all(q["decision_id"] in text for q in result["summary"]["repair_triage"]["decisions"])
    assert "blocked" in text


@pytest.mark.parametrize("fault", ["tampered", "wrong-shape", "bad-tool", "missing-stages", "bad-id",
                                   "duplicate-stage", "bad-status", "bad-decision", "event-mismatch"])
def test_untrustworthy_input_blocks(tmp_path, capsys, fault):
    stages = _stages()
    if fault == "duplicate-stage":
        stages.insert(0, stages[0])
    elif fault == "bad-status":
        stages[0]["status"] = []
    elif fault == "bad-decision":
        stages[1]["evidence"]["decisions"][0]["options"] = [None]
    run = _sealed(tmp_path, {} if fault == "wrong-shape" else stages,
                  tool="other/1" if fault == "bad-tool" else "vqs.run/1",
                  mismatch=fault == "event-mismatch")
    if fault == "tampered":
        (run / "stages.json").write_text("[]", encoding="utf-8")
    elif fault == "missing-stages":
        (run / "stages.json").unlink()
    run_id = "../test-run" if fault == "bad-id" else "test-run"
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", run_id]) == 2
    assert "blocked" in capsys.readouterr().out.lower()


def test_many_owner_questions_and_options_are_not_truncated(tmp_path, capsys):
    stages = _stages()
    decisions = stages[1]["evidence"]["decisions"]
    decisions[0]["options"] = [{"id": f"option-{n}", "label": f"Choice {n}", "effect": "apply"}
                               for n in range(16)]
    decisions.extend({"status": "needs_owner_decision", "decision_id": f"question-{n}",
                      "question": f"Question {n}?", "options": [{"id": "a", "label": "A",
                                                                   "effect": "apply"}]}
                     for n in range(16))
    _sealed(tmp_path, stages)
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 0
    text = capsys.readouterr().out
    assert all(f'"question-{n}"' in text for n in range(16))
    assert all(f'"option-{n}"' in text for n in range(16))


def test_output_refuses_overwrite_and_run_directory(tmp_path, capsys):
    run = _sealed(tmp_path, _stages())
    existing = tmp_path / "existing.txt"
    existing.write_text("keep", encoding="utf-8")
    for output in (existing, run / "new.txt"):
        assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run",
                     "--out", str(output)]) == 2
        capsys.readouterr()
    assert existing.read_text(encoding="utf-8") == "keep"
    assert not (run / "new.txt").exists()


@pytest.mark.parametrize("fault", ["missing-check", "blocked-check", "duplicate-check", "contradictory-verdict"])
def test_incomplete_before_after_is_unknown(tmp_path, capsys, fault):
    stages = _stages()
    after = stages[4]["evidence"]
    if fault == "missing-check":
        after["findings"].pop()
    elif fault == "blocked-check":
        after["findings"][0]["status"] = "blocked"
    elif fault == "duplicate-check":
        after["findings"].append(after["findings"][0])
    else:
        after["verdict"] = "pass"
    _sealed(tmp_path, stages)
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 0
    text = capsys.readouterr().out
    assert "Comparison unknown" in text
    assert "New regressions: none" not in text


def test_output_file_is_new_and_never_follows_a_link(tmp_path, capsys):
    _sealed(tmp_path, _stages())
    target = tmp_path / "report.txt"
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run",
                 "--out", str(target)]) == 0
    assert "VQS evidence report" in target.read_text(encoding="utf-8")
    capsys.readouterr()
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links unavailable")
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run",
                 "--out", str(link)]) == 2
    assert "VQS evidence report" in target.read_text(encoding="utf-8")


def test_linked_stage_artifact_blocks_even_when_bytes_match(tmp_path, capsys):
    run = _sealed(tmp_path, _stages())
    path = run / "stages.json"
    other = tmp_path / "foreign.json"
    other.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(other)
    except OSError:
        pytest.skip("symbolic links unavailable")
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 2
    assert "blocked" in capsys.readouterr().out.lower()


def test_changed_source_blocks_historical_run(tmp_path, capsys):
    copy = tmp_path / "fictional"
    shutil.copytree(REPORT.parent, copy)
    report = copy / REPORT.name
    _sealed(tmp_path, _stages(), report=report)
    metadata = report / "definition/report.json"
    metadata.write_text(metadata.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 2
    assert "stale" in capsys.readouterr().out.lower()


def test_report_output_cannot_modify_original_source_tree(tmp_path, capsys):
    copy = tmp_path / "fictional"
    shutil.copytree(REPORT.parent, copy)
    report = copy / REPORT.name
    _sealed(tmp_path, _stages(), report=report)
    for output in (report / "unexpected.txt", report.parent / "unexpected.txt"):
        assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run",
                     "--out", str(output)]) == 2
        assert "blocked" in capsys.readouterr().out.lower()
        assert not output.exists()


def test_empty_report_cannot_supply_source_evidence(tmp_path, capsys):
    report = tmp_path / "empty.Report"
    report.mkdir()
    _sealed(tmp_path, _stages(), report=report)
    assert main(["evidence-report", "--run-root", str(tmp_path), "--run-id", "test-run"]) == 2
    assert "blocked" in capsys.readouterr().out.lower()
