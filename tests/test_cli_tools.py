"""CLI/MCP lane tests (WP-02): config, shared engine, CLI surface.

The engine never raises on bad input: every adverse case below pins a
blocked envelope (or CLI exit 2), never a crash and never a silent pass.
CLI/MCP parity is asserted by comparing envelopes, not by snapshotting
implementation output.
"""
import json
import shutil
from pathlib import Path

import pytest

POWERBI_FIX = Path(__file__).parent / "powerbi" / "fixtures"
REPORT = str(POWERBI_FIX / "mini_report")
MODEL = str(POWERBI_FIX / "mini_model" / "definition")
INTERFACES = Path(__file__).parent / "fixtures" / "vqs_agent_first" / "interfaces"

ENVELOPE_KEYS = {"schema_version", "tool", "run_id", "run_dir", "scope",
                 "verdict", "coverage", "findings", "evidence",
                 "blocked_reasons", "next_actions", "provenance"}


def _plan(**overrides):
    base = {
        "operations": [{"type": "theme.set", "target": "visual",
                        "value": "#0F2A44"}],
        "write_targets": ["/cand/report.Report"],
        "rollback": "git checkout -- report.Report",
    }
    base.update(overrides)
    return base


def test_config_defaults_when_absent(tmp_path, monkeypatch) -> None:
    from vqs.config import default_config, load_config

    monkeypatch.chdir(tmp_path)
    config, issues = load_config()
    assert issues == []
    assert config == default_config()
    assert config["data_permissions"] == {"allow_cloud": False,
                                          "allow_desktop": False}


def test_config_sample_loads() -> None:
    from vqs.config import load_config

    config, issues = load_config(INTERFACES / "goal17_vqs.json")
    assert issues == []
    assert config["supported_states"] == ["alt", "default"]
    assert config["data_permissions"]["allow_desktop"] is True
    assert config["oracles"] == [{"oracle_scope": "page",
                                 "run_scope": "page"}]


def test_config_rejects_bad_shapes(tmp_path: Path) -> None:
    from vqs.config import default_config, load_config

    bad = tmp_path / "vqs.json"
    bad.write_text(json.dumps({"bogus": 1, "supported_states": [],
                               "data_permissions": {"allow_cloud": "yes"}}),
                   encoding="utf-8")
    config, issues = load_config(bad)
    assert config == default_config()
    assert len(issues) == 3
    bad.write_text("{oops", encoding="utf-8")
    _config, issues = load_config(bad)
    assert len(issues) == 1
    _config, issues = load_config(tmp_path / "absent.json")
    assert len(issues) == 1


def test_inspect_measures_mini_report() -> None:
    from vqs.pipeline import inspect_report

    envelope = inspect_report(REPORT, MODEL)
    assert ENVELOPE_KEYS <= set(envelope)
    assert envelope["tool"] == "vqs.inspect"
    assert envelope["verdict"] == "pass"
    assert "rules" in envelope["facts"]
    digest = envelope["provenance"]["source_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert envelope["provenance"]["model_sha256"] is not None
    assert envelope["findings"] == []
    assert envelope["next_actions"]


def test_inspect_bad_inputs_block() -> None:
    from vqs.pipeline import inspect_report

    assert inspect_report("tests/powerbi/fixtures/absent")["verdict"] == "blocked"
    assert inspect_report("")["verdict"] == "blocked"
    assert inspect_report(None)["verdict"] == "blocked"
    assert inspect_report(REPORT, 123)["verdict"] == "blocked"


def test_review_static_report_seals(tmp_path: Path) -> None:
    from vqs.pipeline import inspect_report, review_report, run_check

    run_root = str(tmp_path / "runs")
    envelope = review_report(report_dir=REPORT, model_dir=MODEL,
                             run_root=run_root, run_id="r1")
    expected = run_check(inspect_report(REPORT, MODEL)["facts"],
                         tmp_path / "expect", run_id="r1")
    assert envelope["verdict"] == expected["verdict"]
    assert envelope["tool"] == "vqs.review"
    assert envelope["run_id"] == "r1"
    manifest = json.loads((tmp_path / "runs" / "r1" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["status"] in ("completed", "failed", "blocked")
    assert manifest["artifacts"]["source_sha256"] == envelope[
        "provenance"]["source_sha256"]
    assert manifest["artifacts"]["verdict_sha256"]
    for finding in envelope["findings"]:
        assert {"check", "status", "severity", "location",
                "evidence_basis", "recipes"} <= set(finding)
        assert finding["recipes"] == []


def test_review_facts_fail_case(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    facts = {"rules": {"typography.text_contrast": {
        "foreground": "#000000", "background": "#000000"}}}
    envelope = review_report(facts=facts, run_root=str(tmp_path),
                             run_id="fail1")
    assert envelope["verdict"] == "fail"
    assert envelope["findings"][0]["severity"] == "error"


def test_review_input_and_scope_validation(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    both = review_report(report_dir=REPORT, facts={},
                         run_root=str(tmp_path))
    assert both["verdict"] == "blocked"
    neither = review_report(run_root=str(tmp_path))
    assert neither["verdict"] == "blocked"
    scope = review_report(facts={}, scope="nope", run_root=str(tmp_path))
    assert scope["verdict"] == "blocked"
    state = review_report(facts={}, state="nope", run_root=str(tmp_path))
    assert state["verdict"] == "blocked"


def test_review_desktop_blocked_by_permission_then_adapters(
        tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    denied = review_report(facts={}, scope="desktop",
                           run_root=str(tmp_path), run_id="d1")
    assert denied["verdict"] == "blocked"
    assert any("allow_desktop" in reason
               for reason in denied["blocked_reasons"])
    allowed = review_report(
        facts={}, scope="desktop", run_root=str(tmp_path), run_id="d2",
        config={"data_permissions": {"allow_desktop": True,
                                     "allow_cloud": False}})
    assert allowed["verdict"] == "blocked"
    assert any("Task 5" in reason for reason in allowed["blocked_reasons"])


def test_review_config_oracles_flow(tmp_path: Path) -> None:
    from vqs.config import load_config
    from vqs.pipeline import review_report

    config, _ = load_config(INTERFACES / "goal17_vqs.json")
    envelope = review_report(facts={"rules": {}}, config=config,
                             run_root=str(tmp_path), run_id="o1")
    oracles = [f for f in envelope["findings"]
               if f["check"].startswith("oracle:")]
    assert [f["check"] for f in oracles] == ["oracle:0", "oracle:1"]
    # The bare question names no known measure (clarify, honestly
    # blocked); the equal-scope oracle pair passes.
    assert oracles[0]["status"] == "blocked"
    assert oracles[1]["status"] == "pass"
    assert envelope["provenance"]["config_schema"] == "vqs.config/1"


def test_review_resume_same_sources(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    run_root = str(tmp_path / "runs")
    first = review_report(report_dir=str(clone), run_root=run_root,
                          run_id="a")
    assert first["run_dir"]
    second = review_report(report_dir=str(clone), run_root=run_root,
                           run_id="b", resume_from="a")
    assert second["verdict"] == first["verdict"]
    manifest = json.loads((tmp_path / "runs" / "b" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["resumed_from"] == "a"


def test_review_resume_changed_sources_blocks(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    run_root = str(tmp_path / "runs")
    review_report(report_dir=str(clone), run_root=run_root, run_id="a")
    target = (clone / "definition" / "pages" / "P1" / "visuals"
              / "titlebox" / "visual.json")
    target.write_text(target.read_text(encoding="utf-8") + " ",
                      encoding="utf-8")
    resumed = review_report(report_dir=str(clone), run_root=run_root,
                            run_id="b", resume_from="a")
    assert resumed["verdict"] == "blocked"
    assert any("source_sha256" in reason
               for reason in resumed["blocked_reasons"])


def test_review_resume_validates_prior_run(tmp_path: Path) -> None:
    from vqs.pipeline import review_report
    from vqs.run_store import append_event, create_run, seal_run

    run_root = str(tmp_path / "runs")
    missing = review_report(facts={}, run_root=run_root, run_id="x",
                            resume_from="nope")
    assert missing["verdict"] == "blocked"
    run_dir = create_run(tmp_path / "runs", "bare", {"pipeline": "t/1"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed")
    bare = review_report(facts={}, run_root=run_root, run_id="y",
                         resume_from="bare")
    assert bare["verdict"] == "blocked"
    assert any("provenance" in reason for reason in bare["blocked_reasons"])


def test_run_status_roundtrip_and_unknown(tmp_path: Path) -> None:
    from vqs.pipeline import review_report, run_status_report

    run_root = str(tmp_path / "runs")
    review = review_report(facts={"rules": {}}, run_root=run_root,
                           run_id="s1")
    status = run_status_report(run_root, "s1")
    assert status["verdict"] == review["verdict"]
    assert status["event_count"] >= 2
    assert status["events"]
    assert status["evidence"][0]["verdict_sha256"]
    unknown = run_status_report(run_root, "nope")
    assert unknown["verdict"] == "blocked"


def test_propose_repair_verify_honesty(tmp_path: Path) -> None:
    from vqs.pipeline import propose_candidates, repair_candidate, review_report, verify_candidate

    run_root = str(tmp_path / "runs")
    review_report(facts={"rules": {"nope.rule": {}}}, run_root=run_root,
                  run_id="p1")
    assert propose_candidates(run_root, "nope")["verdict"] == "blocked"
    triage = propose_candidates(run_root, "p1")
    assert triage["verdict"] == "pass"
    assert triage["candidates"] == []
    assert [item["check"] for item in triage["work_items"]] == ["nope.rule"]
    assert all(item["needs_plan"] for item in triage["work_items"])
    assert any("no safe automatic candidate was synthesizable" in action
               for action in triage["next_actions"])
    assert any(item["status"] == "needs_owner_decision"
               for item in triage["decisions"])

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    refused = repair_candidate(str(plan_path), "/orig.Report", "/cand",
                               run_root=run_root, run_id="r1")
    assert refused["verdict"] == "blocked"
    assert refused["run_dir"] is not None  # refusals seal too
    assert any("materialize" in reason
               for reason in refused["blocked_reasons"])
    shell_path = tmp_path / "shell.json"
    shell_path.write_text(json.dumps(_plan(operations=[
        {"type": "shell", "target": "os", "value": "x"}])), encoding="utf-8")
    invalid = repair_candidate(str(shell_path), "/orig.Report", "/cand",
                               run_root=run_root, run_id="r2")
    assert invalid["verdict"] == "fail"
    assert invalid["run_dir"] is None  # invalid plans never seal a run
    assert invalid["findings"]
    assert repair_candidate(str(tmp_path / "nope"), "/o", "/c")[
        "verdict"] == "blocked"

    assert verify_candidate(run_root=run_root, run_id="nope")[
        "verdict"] == "blocked"
    assert verify_candidate(original="/o", candidate="/c")[
        "verdict"] == "blocked"
    assert verify_candidate()["verdict"] == "blocked"


def test_render_report_sections_and_garbage(tmp_path: Path) -> None:
    from vqs.pipeline import render_report, review_report

    envelope = review_report(facts={"rules": {}},
                             run_root=str(tmp_path / "runs"))
    text = render_report(envelope)
    for section in ("# VQS vqs.review", "## Findings", "## Coverage",
                    "## Blocked reasons", "## Next actions", "## Diffs"):
        assert section in text
    assert "unavailable" in render_report(None)
    assert "unavailable" in render_report(12345)


def test_cli_review_inspect_parity_and_exits(tmp_path: Path, capsys) -> None:
    from vqs.cli import main as vqs_main
    from vqs.pipeline import inspect_report, review_report

    run_root = str(tmp_path / "runs")
    code = vqs_main(["review", REPORT, "--model", MODEL,
                     "--run-root", run_root, "--run-id", "cli1"])
    cli = json.loads(capsys.readouterr().out)
    engine = review_report(report_dir=REPORT, model_dir=MODEL,
                           run_root=run_root, run_id="eng1")
    assert cli["verdict"] == engine["verdict"]
    assert cli["findings"] == engine["findings"]
    assert cli["coverage"] == engine["coverage"]
    assert code == {"pass": 0, "fail": 1, "blocked": 2}[cli["verdict"]]

    code = vqs_main(["inspect", REPORT])
    inspected = json.loads(capsys.readouterr().out)
    assert code == 0
    assert inspected["facts"] == inspect_report(REPORT)["facts"]

    assert vqs_main(["inspect", "absent-dir"]) == 2
    assert vqs_main(["review", REPORT, "--scope", "nope",
                     "--run-root", run_root]) == 2
    assert vqs_main(["run-status", run_root, "nope"]) == 2
    assert vqs_main(["propose", "--run-root", run_root,
                     "--run-id", "cli1"]) == 0
    shell_path = tmp_path / "shell.json"
    shell_path.write_text(json.dumps(_plan(operations=[
        {"type": "shell", "target": "os", "value": "x"}])), encoding="utf-8")
    assert vqs_main(["repair", str(shell_path), "--original", "/o",
                     "--candidate-root", "/c"]) == 1
    assert vqs_main(["verify", "--original", "/o",
                     "--candidate", "/c"]) == 2


def test_review_malformed_config_oracles_block(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    envelope = review_report(
        facts={"rules": {}}, run_root=str(tmp_path), run_id="m1",
        config={"oracles": ["junk", 7], "questions": "not-a-list"})
    assert envelope["verdict"] == "blocked"
    oracles = [f for f in envelope["findings"]
               if f["check"].startswith("oracle:")]
    assert len(oracles) == 3
    assert all(f["status"] == "blocked" for f in oracles)


def test_review_resume_changed_facts_blocks(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    run_root = str(tmp_path / "runs")
    review_report(facts={"rules": {}}, run_root=run_root, run_id="a")
    resumed = review_report(
        facts={"rules": {"typography.text_contrast": {
            "foreground": "#000000", "background": "#FFFFFF"}}},
        run_root=run_root, run_id="b", resume_from="a")
    assert resumed["verdict"] == "blocked"
    assert any("facts_sha256" in reason
               for reason in resumed["blocked_reasons"])


def test_review_resume_changed_config_blocks(tmp_path: Path) -> None:
    from vqs.pipeline import review_report

    run_root = str(tmp_path / "runs")
    review_report(facts={"rules": {}}, run_root=run_root, run_id="a")
    resumed = review_report(
        facts={"rules": {}}, run_root=run_root, run_id="b",
        resume_from="a",
        config={"oracles": [{"oracle_scope": "x", "run_scope": "x"}]})
    assert resumed["verdict"] == "blocked"
    assert any("facts_sha256" in reason
               for reason in resumed["blocked_reasons"])


def test_review_resume_legacy_run_without_facts_digest(tmp_path: Path) -> None:
    from vqs.pipeline import review_report
    from vqs.run_store import append_event, create_run, seal_run

    run_dir = create_run(tmp_path / "runs", "legacy", {"pipeline": "t/1"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"source_sha256": None, "model_sha256": None})
    resumed = review_report(facts={"rules": {}},
                            run_root=str(tmp_path / "runs"), run_id="b",
                            resume_from="legacy")
    assert resumed["verdict"] == "blocked"
    assert any("no sealed facts digest" in reason
               for reason in resumed["blocked_reasons"])


def test_inspect_non_utf8_bytes_block(tmp_path: Path) -> None:
    from vqs.pipeline import inspect_report
    from vqs.powerbi.measure import measure_report

    model = tmp_path / "model"
    bad = model / "tables" / "T.tmdl"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"table T\n\n\xff\xfe not utf-8")
    with pytest.raises(UnicodeDecodeError):
        measure_report(REPORT, str(model))
    envelope = inspect_report(REPORT, str(model))
    assert envelope["verdict"] == "blocked"


def test_cli_review_report_out(tmp_path: Path, capsys) -> None:
    from vqs.cli import main as vqs_main

    out = tmp_path / "report.md"
    code = vqs_main(["review", REPORT, "--run-root", str(tmp_path / "runs"),
                     "--run-id", "rep1", "--report-out", str(out)])
    assert code in (0, 1, 2)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# VQS vqs.review")
    assert "## Findings" in text
