"""Answerable owner decisions: questions -> owner answers -> verified candidate.

Uses the committed fictional Contoso Retail PBIR, whose real static repair
run is blocked by two owner-dependent checks (typography cohorts and a
cross-page duplicate grain). Answers must turn that dead end into a
verified candidate or recorded waivers without guessing, without touching
the original, and fail closed on stale, unknown or conflicting answers.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vqs.coordinator import run_workflow
from vqs.pbir import source_digest
from vqs.repair.decisions import ANSWERS_SCHEMA, load, resolve, waived_checks
from vqs.repair.recipes import RecipeError, bind_operation
from vqs.repair.regress import _diff_paths
from vqs.repair.synthesize import synthesize_plan

REPORT = (Path(__file__).resolve().parents[1] / "examples" /
          "contoso-retail" / "Contoso Retail.Report")
TYPO = "typography.format_declaration_consistency"
GRAIN = "insight.no_cross_page_duplicate_grain"


def _blocked(tmp_path: Path, run_id: str = "first") -> dict:
    result = run_workflow(report_dir=str(REPORT), mode="repair",
                          scope="static", run_root=str(tmp_path / "runs"),
                          run_id=run_id, authoring_backend="direct")
    assert result["verdict"] == "blocked"
    return result


def _answers(result: dict, choose) -> dict:
    triage = result["summary"]["repair_triage"]
    return {"schema": ANSWERS_SCHEMA, "owner": "report owner",
            "source_sha256": triage["decision_source_sha256"],
            "answers": [{"decision_id": item["decision_id"],
                         "option": choose(item)}
                        for item in triage["decisions"]]}


def _ten_or_accept(item: dict) -> str:
    ids = [option["id"] for option in item["options"]]
    return "size:10D" if "size:10D" in ids else "accept"


def test_blocked_run_exposes_answerable_questions(tmp_path: Path) -> None:
    result = _blocked(tmp_path)
    triage = result["summary"]["repair_triage"]
    assert len(triage["decision_source_sha256"]) == 64
    decisions = triage["decisions"]
    assert len(decisions) == 5
    assert len({item["decision_id"] for item in decisions}) == 5
    for item in decisions:
        assert item["decision_id"].startswith("dec-")
        assert item["question"]
        assert item["options"][-1] == {
            "id": "accept", "effect": "waive", "edits": 0,
            "label": item["options"][-1]["label"]}
    by_cohort = {item.get("cohort"): item for item in decisions}
    grid = by_cohort["pivotTable/grid.textSize"]
    assert [o["id"] for o in grid["options"]] == ["size:10D", "size:11D", "accept"]
    grain = next(item for item in decisions if item["check"] == GRAIN)
    assert [o["id"] for o in grain["options"]] == ["accept"]
    assert len(grain["pair"]) == 2
    # Same revision -> identical ids (answers survive a re-run).
    again = _blocked(tmp_path, "second")["summary"]["repair_triage"]
    assert [d["decision_id"] for d in again["decisions"]] == [
        d["decision_id"] for d in decisions]
    assert any("--decisions" in action for action in result["next_actions"])


def test_answers_fix_typography_and_waive_grain(tmp_path: Path) -> None:
    before = source_digest(REPORT)
    blocked = _blocked(tmp_path)
    answers = _answers(blocked, _ten_or_accept)
    result = run_workflow(report_dir=str(REPORT), mode="repair",
                          scope="static", run_root=str(tmp_path / "runs"),
                          run_id="answered", authoring_backend="direct",
                          decisions=answers)
    summary = result["summary"]
    assert result["verdict"] == "pass"
    assert summary["outcome"] == "accepted_with_waivers"
    assert summary["resolved_findings"] == [TYPO]
    assert summary["remaining_findings"] == []
    assert summary["waived_findings"] == [GRAIN]
    assert summary["new_regressions"] == []
    # Honest quality: the candidate still literally fails the waived rule.
    assert summary["quality_after"] == "fail"
    assert summary["candidate_status"]["status"] == "verified"
    assert summary["repair_triage"]["status"] == "owner_decisions_applied"
    assert summary["promotion_status"]["status"] == "not-performed"
    owner = summary["owner_decisions"]
    assert owner["owner"] == "report owner"
    assert {item["effect"] for item in owner["answered"]} == {"apply", "waive"}
    assert "not G2/G4 review or G6" in owner["authority"]
    stage = next(s for s in result["stages"] if s["stage"] == "owner_decisions")
    assert stage["status"] == "pass"
    assert stage["evidence"]["edits"] == 7
    assert source_digest(REPORT) == before
    candidate = Path(summary["candidate"])
    changed = []
    for path in sorted(REPORT.rglob("*.json")):
        rel = path.relative_to(REPORT)
        old = json.loads(path.read_text(encoding="utf-8-sig"))
        new = json.loads((candidate / rel).read_text(encoding="utf-8-sig"))
        changed += [(rel.parts[-2], diff) for diff in _diff_paths(old, new)]
    assert len(changed) == 7
    assert all(diff[-1] in ("fontSize", "Value") for _visual, diff in changed)


def test_waivers_only_accept_original_without_candidate(tmp_path: Path) -> None:
    blocked = _blocked(tmp_path)
    result = run_workflow(
        report_dir=str(REPORT), mode="repair", scope="static",
        run_root=str(tmp_path / "runs"), run_id="waive-all",
        authoring_backend="direct",
        decisions=_answers(blocked, lambda _item: "accept"))
    summary = result["summary"]
    assert result["verdict"] == "pass"
    assert summary["outcome"] == "accepted_with_waivers"
    assert summary["candidate"] is None
    assert sorted(summary["waived_findings"]) == [GRAIN, TYPO]
    repair = next(s for s in result["stages"] if s["stage"] == "repair")
    assert repair["status"] == "not_run"


def test_partial_waiver_never_accepts(tmp_path: Path) -> None:
    blocked = _blocked(tmp_path)
    answers = _answers(blocked, lambda _item: "accept")
    answers["answers"] = [a for a in answers["answers"]
                          if a["decision_id"] == next(
                              d["decision_id"] for d in
                              blocked["summary"]["repair_triage"]["decisions"]
                              if d["check"] == GRAIN)]
    result = run_workflow(report_dir=str(REPORT), mode="repair",
                          scope="static", run_root=str(tmp_path / "runs"),
                          run_id="partial", authoring_backend="direct",
                          decisions=answers)
    summary = result["summary"]
    assert result["verdict"] == "blocked"
    assert summary["acceptance"] is False
    assert summary["waived_findings"] == [GRAIN]
    assert summary["remaining_findings"] == [TYPO]


@pytest.mark.parametrize("tamper", ["stale-source", "unknown-id", "unknown-option",
                                    "conflict"])
def test_bad_answers_block_and_apply_nothing(tmp_path: Path, tamper: str) -> None:
    blocked = _blocked(tmp_path)
    answers = _answers(blocked, _ten_or_accept)
    if tamper == "stale-source":
        answers["source_sha256"] = "0" * 64
    elif tamper == "unknown-id":
        answers["answers"][0]["decision_id"] = "dec-0000000000000000"
    elif tamper == "unknown-option":
        answers["answers"][0]["option"] = "size:99D"
    result = run_workflow(report_dir=str(REPORT), mode="repair",
                          scope="static", run_root=str(tmp_path / "runs"),
                          run_id=f"bad-{tamper}", authoring_backend="direct",
                          decisions=answers)
    if tamper == "conflict":
        # Two options writing different values to one path must block.
        triage = blocked["summary"]["repair_triage"]
        decisions = synthesize_plan(
            [{"check": TYPO, "status": "fail", "detail": {"evidence": {
                "conflicts": [{"cohort": "x"}], "pending": []}}}], None,
            source_sha256=triage["decision_source_sha256"])["decisions"]
        assert decisions[0]["options"][-1]["id"] == "accept"
        fake = [dict(decisions[0], decision_id="dec-a", subject="a", options=[
            {"id": "one", "effect": "apply", "label": "",
             "operations": [{"writes": ["f"], "path": ["p"], "value": 1}]}]),
                dict(decisions[0], decision_id="dec-b", subject="b", options=[
            {"id": "two", "effect": "apply", "label": "",
             "operations": [{"writes": ["f"], "path": ["p"], "value": 2}]}])]
        doc, issues = load({"schema": ANSWERS_SCHEMA, "owner": "o",
                            "source_sha256": "a" * 64, "answers": [
                                {"decision_id": "dec-a", "option": "one"},
                                {"decision_id": "dec-b", "option": "two"}]})
        assert not issues
        assert resolve(doc, fake, "a" * 64)["issues"]
        return
    stage = next(s for s in result["stages"] if s["stage"] == "owner_decisions")
    assert stage["status"] == "blocked"
    assert result["verdict"] == "blocked"
    assert result["summary"]["candidate"] is None
    assert not any(s["stage"] == "repair" and s["status"] == "pass"
                   for s in result["stages"])


@pytest.mark.parametrize("document,needle", [
    ([], "JSON object"),
    ({"schema": "nope", "owner": "o", "source_sha256": "a" * 64,
      "answers": [{"decision_id": "dec-1", "option": "accept"}]}, "schema"),
    ({"schema": ANSWERS_SCHEMA, "owner": " ", "source_sha256": "a" * 64,
      "answers": [{"decision_id": "dec-1", "option": "accept"}]}, "owner"),
    ({"schema": ANSWERS_SCHEMA, "owner": "o", "source_sha256": "short",
      "answers": [{"decision_id": "dec-1", "option": "accept"}]}, "source_sha256"),
    ({"schema": ANSWERS_SCHEMA, "owner": "o", "source_sha256": "a" * 64,
      "answers": [{"decision_id": "dec-1", "option": ""}]}, "no decision"),
    ({"schema": ANSWERS_SCHEMA, "owner": "o", "source_sha256": "a" * 64,
      "answers": [{"decision_id": "dec-1", "option": "a"},
                  {"decision_id": "dec-1", "option": "b"}]}, "twice"),
])
def test_malformed_answers_rejected_before_any_run(tmp_path: Path, document,
                                                   needle: str) -> None:
    result = run_workflow(report_dir=str(REPORT), mode="repair",
                          scope="static", run_root=str(tmp_path / "runs"),
                          decisions=document)
    assert result["verdict"] == "blocked"
    assert needle in " ".join(result["blocked_reasons"])
    assert not (tmp_path / "runs").exists()


def test_plan_and_decisions_are_mutually_exclusive(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    result = run_workflow(
        report_dir=str(REPORT), mode="repair", scope="static",
        run_root=str(tmp_path / "runs"), plan_path=str(plan),
        decisions={"schema": ANSWERS_SCHEMA, "owner": "o",
                   "source_sha256": "a" * 64,
                   "answers": [{"decision_id": "dec-1", "option": "accept"}]})
    assert result["verdict"] == "blocked"
    assert "not both" in result["blocked_reasons"][0]


def test_missing_evidence_is_never_waivable() -> None:
    findings = [{"check": "coverage:visual_doc_unreadable", "status": "fail",
                 "detail": {}}]
    decisions = synthesize_plan(findings, None, source_sha256="a" * 64)["decisions"]
    assert decisions[0]["status"] == "unsupported"
    assert "options" not in decisions[0]
    assert waived_checks(findings, None, ["coverage:visual_doc_unreadable"]) == []


def _visual_doc(properties: dict, selector: bool = False) -> dict:
    entry: dict = {"properties": properties}
    if selector:
        entry["selector"] = {"metadata": "x"}
    return {"visual": {"objects": {"header": [entry]}}}


def _declare(**override) -> dict:
    op = {"type": "format.declare_explicit",
          "selector": {"page": "P1", "visual": "v"}, "target": "visual",
          "path": ["visual", "objects", "header", 0, "properties", "textSize"],
          "old": None, "value": "11D", "effective": "11D",
          "proof": "owner-decision:dec-1:size:11D"}
    op.update(override)
    return op


def test_declare_explicit_adds_only_with_owner_proof() -> None:
    bound = bind_operation(_declare(), _visual_doc({"show": {}}))
    assert bound["old"] is None
    assert bound["new"] == {"expr": {"Literal": {"Value": "11D"}}}
    assert bound["path"][-1] == "textSize"


@pytest.mark.parametrize("doc,override,needle", [
    (_visual_doc({}), {"proof": "render-adapter:x"}, "owner decision"),
    (_visual_doc({"textSize": {}}), {}, "already declared"),
    (_visual_doc({}, selector=True), {}, "selector"),
    (_visual_doc({}), {"old": "10D"}, "old must be null"),
    (_visual_doc({}), {"effective": "12D"}, "owner-chosen"),
    ({"visual": {"objects": {}}}, {}, "missing"),
])
def test_declare_explicit_refusals(doc, override, needle) -> None:
    with pytest.raises(RecipeError, match=needle):
        bind_operation(_declare(**override), doc)


def test_emitter_bindings_can_never_declare() -> None:
    finding = {"check": TYPO, "status": "fail", "detail": {"evidence": {
        "binding": {"op": "format.declare_explicit", "page": "P1",
                    "visual": "v", "path": ["visual", "objects", "header", 0,
                                            "properties", "textSize"]}}}}
    result = synthesize_plan([finding], {"rules": {}})
    assert result["plan"] is None
    assert result["decisions"][0]["status"] == "unsupported"


def test_large_overlap_offers_verified_moves() -> None:
    facts = {"rules": {
        "layout.no_visual_overlap": {"visuals": [
            {"page": "P1", "visual": "a", "x": 0, "y": 0, "width": 100, "height": 100},
            {"page": "P1", "visual": "b", "x": 10, "y": 10, "width": 100, "height": 100},
            {"page": "P1", "visual": "c", "x": 300, "y": 0, "width": 50, "height": 50}]},
        "layout.visuals_within_page": {"pages": [
            {"page": "P1", "width": 1280, "height": 720}]}}}
    finding = {"check": "layout.no_visual_overlap", "status": "fail",
               "detail": {"evidence": {"conflicts": [
                   {"page": "P1", "visuals": ["a", "b"],
                    "overlap": {"x": 10, "y": 10, "width": 90, "height": 90}}]}}}
    result = synthesize_plan([finding], facts, source_sha256="a" * 64)
    decision = result["decisions"][0]
    assert decision["pair"] == ["a", "b"]
    moves = [o for o in decision["options"] if o["effect"] == "apply"]
    assert moves and len(moves) <= 4
    for option in moves:
        (op,) = option["operations"]
        assert op["type"] == "spacing.adjust"
        assert op["path"][0] == "position"
        # every option keeps the moved visual clear of every neighbor
        rects = {v["visual"]: dict(v) for v in
                 facts["rules"]["layout.no_visual_overlap"]["visuals"]}
        moved = dict(rects[op["selector"]["visual"]])
        moved[op["path"][1]] = op["value"]
        for name, other in rects.items():
            if name == op["selector"]["visual"]:
                continue
            assert (moved["x"] + moved["width"] <= other["x"]
                    or other["x"] + other["width"] <= moved["x"]
                    or moved["y"] + moved["height"] <= other["y"]
                    or other["y"] + other["height"] <= moved["y"])


def test_microsoft_gate_accepts_owner_size_literals(tmp_path: Path,
                                                    monkeypatch) -> None:
    from vqs.powerbi.author import compile as gate

    blocked = _blocked(tmp_path)
    decisions = blocked["stages"][[s["stage"] for s in blocked["stages"]].index(
        "propose")]["evidence"]["decisions"]
    ops = [op for item in decisions for option in item["options"]
           if option["id"] == "size:10D" for op in option["operations"]]
    assert {op["type"] for op in ops} == {"format.set_explicit",
                                          "format.declare_explicit"}
    attested = {"status": "pass", "validation_provider": "microsoft",
                "assurance": "microsoft_structural_only",
                "skill": {"snapshot": {"sha256": "a" * 64}},
                "cli": {"path": "/cli", "version": "0.5.0"}, "probe": {}}

    def metadata(_att, capability, *names, kind="formatting"):
        if capability == "catalog.describe":
            return {"status": "pass", "sha256": "b" * 64,
                    "data": {"deprecated": False}}
        prop_type = "numeric" if names[-1] == "textSize" else kind
        return {"status": "pass", "sha256": "c" * 64,
                "data": {"property": {"type": prop_type}}}

    monkeypatch.setattr(gate.metadata, "query", metadata)
    receipt = gate.evaluate({"operations": ops}, str(REPORT), attested)
    assert receipt["status"] == "pass", receipt
    assert {r["new"] for r in receipt["operations"]} == {"10D"}
    monkeypatch.setattr(gate.metadata, "query",
                        lambda a, c, *n: metadata(a, c, *n, kind="integer"))
    refused = gate.evaluate({"operations": ops}, str(REPORT), attested)
    assert refused["status"] == "blocked"


def test_cli_template_and_answer_round_trip(tmp_path: Path, capsys) -> None:
    from vqs.cli import main

    project = tmp_path / "proj"
    shutil.copytree(REPORT.parent, project)
    pbip = str(project / "Contoso Retail.pbip")
    runs = str(tmp_path / "runs")
    assert main(["fix", pbip, "--run-root", runs, "--run-id", "f1",
                 "--authoring-backend", "direct"]) == 2
    first = json.loads(capsys.readouterr().out)
    assert first["needs_review"][0]["options"]
    out = tmp_path / "answers.json"
    assert main(["decisions", "template", "--run-root", runs, "--run-id", "f1",
                 "--out", str(out)]) == 0
    capsys.readouterr()
    assert main(["decisions", "template", "--run-root", runs, "--run-id", "f1",
                 "--out", str(out)]) == 2  # never overwrites
    capsys.readouterr()
    skeleton = json.loads(out.read_text(encoding="utf-8"))
    skeleton["owner"] = "owner"
    for row in skeleton["answers"]:
        row["option"] = "size:10D" if "size:10D" in row["choices"] else "accept"
    out.write_text(json.dumps(skeleton), encoding="utf-8")
    assert main(["fix", pbip, "--run-root", runs, "--run-id", "f2",
                 "--authoring-backend", "direct", "--decisions", str(out)]) == 0
    done = json.loads(capsys.readouterr().out)
    assert done["outcome"] == "accepted_with_waivers"
    assert done["waived"] == [GRAIN]
    assert done["candidate_status"] == "verified"


def test_mcp_run_accepts_inline_decisions(monkeypatch) -> None:
    from vqs.mcp import server
    from vqs.mcp.schemas import validate_call

    spec, error = validate_call("vqs_run", {"run_root": "r", "decisions": {
        "schema": ANSWERS_SCHEMA}})
    assert error is None and spec is not None
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"tool": "vqs.run", "verdict": "blocked"}

    monkeypatch.setattr("vqs.coordinator.run_workflow", fake)
    server._dispatch("vqs_run", {"run_root": "r", "facts": {},
                                 "decisions": {"schema": ANSWERS_SCHEMA}})
    assert seen["decisions"] == {"schema": ANSWERS_SCHEMA}


def test_check_is_waived_only_when_every_subject_is_waived() -> None:
    finding = {"check": TYPO, "status": "fail", "detail": {"evidence": {
        "conflicts": [{"cohort": "card/labels.fontSize"},
                      {"cohort": "table/grid.textSize"}], "pending": []}}}
    one = f"{TYPO}|cohort=card/labels.fontSize"
    two = f"{TYPO}|cohort=table/grid.textSize"
    assert waived_checks([finding], None, [one]) == []
    assert waived_checks([finding], None, [one, two]) == [TYPO]
    # Envelope-shaped findings (evidence_basis) are recognized too.
    envelope = {"check": TYPO, "status": "fail",
                "evidence_basis": finding["detail"]}
    assert waived_checks([envelope], None, [one, two]) == [TYPO]
    assert waived_checks([dict(finding, status="blocked")], None,
                         [one, two]) == []
