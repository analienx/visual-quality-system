"""P0-U1: deterministic safe plan synthesis for source-provable findings.

End-to-end through the sealed review run (review -> propose) for
geometry findings, plus direct contract tests for explicit leaf
bindings, duplicates, unknown checks, the CLI --out path, and the MCP
facts parameter. Stale facts block; ambiguous findings need the owner.
"""
import json
from pathlib import Path

from vqs.cli import main as vqs_main
from vqs.mcp.schemas import validate_call
from vqs.pipeline import propose_candidates, review_report
from vqs.repair.allowlist import validate_plan
from vqs.repair.synthesize import PLAN_SCHEMA_VERSION, synthesize_plan


def _facts(members, canvas=(1280, 720)):
    """Measured-facts shape the emitter produces for layout rules."""
    visuals = [{"page": "P1", "visual": name, "bound": True,
                "x": x, "y": y, "width": width, "height": height,
                "z": float(index)}
               for index, (name, x, y, width, height) in enumerate(members)]
    pages = [{"page": "P1", "width": canvas[0], "height": canvas[1],
              "visuals": [{"visual": name, "x": x, "y": y,
                           "width": width, "height": height}
                          for name, x, y, width, height in members]}]
    return {"rules": {"layout.no_visual_overlap": {"visuals": visuals},
                      "layout.visuals_within_page": {"pages": pages}}}


def _review(tmp_path: Path, facts: dict, run_id: str) -> str:
    runs = str(tmp_path / "runs")
    reviewed = review_report(facts=facts, run_root=runs, run_id=run_id)
    assert reviewed["run_dir"] is not None
    return runs


def _decisions_with(envelope: dict, text: str) -> list[dict]:
    return [item for item in envelope["decisions"] if text in item["reason"]]


# Small movable overlap -------------------------------------------------


def test_overlap_move_synthesizes_repair_plan(tmp_path: Path) -> None:
    """A small overlap yields one verified spacing.adjust candidate + plan."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 100, 100, 200, 200)])
    runs = _review(tmp_path, facts, "u1-move")
    triage = propose_candidates(runs, "u1-move", facts)
    assert triage["verdict"] == "pass"
    assert len(triage["candidates"]) == 1
    record = triage["candidates"][0]
    assert record["check"] == "layout.no_visual_overlap"
    assert (record["page"], record["visual"]) == ("P1", "B")
    assert record["path"] == ["position", "x"]
    assert record["old"] == 100 and record["new"] == 200
    assert record["write_targets"] == [
        "definition/pages/P1/visuals/B/visual.json"]
    assert record["affected_pages"] == ["P1"]
    assert record["rationale"] and record["confidence"] == "high"
    assert record["safety"] == "geometry-stays-in-canvas"
    plan = triage["plan"]
    assert plan is not None
    assert plan["schema_version"] == PLAN_SCHEMA_VERSION
    assert plan["finding_checks"] == ["layout.no_visual_overlap"]
    assert plan["rollback"] == "re-materialize from original"
    assert validate_plan(plan, "orig", "cand") == []
    again = propose_candidates(runs, "u1-move", facts)
    assert again["plan"] == plan
    assert again["candidates"] == triage["candidates"]


def test_overlap_no_free_slot_jammed(tmp_path: Path) -> None:
    """A tight canvas refuses both shifts instead of guessing."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 150, 150, 100, 100)],
                   canvas=(250, 250))
    runs = _review(tmp_path, facts, "u1-jam")
    triage = propose_candidates(runs, "u1-jam", facts)
    assert triage["candidates"] == []
    assert triage["plan"] is None
    held = _decisions_with(triage, "no free slot")
    assert len(held) == 1
    assert held[0]["status"] == "needs_owner_decision"


def test_overlap_third_visual_blocks_escapes(tmp_path: Path) -> None:
    """Shifts that would overlap a neighbor are refused as no free slot."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 150, 0, 200, 200),
                    ("C", 350, 0, 930, 720), ("D", 150, 300, 200, 200)])
    runs = _review(tmp_path, facts, "u1-blocked")
    triage = propose_candidates(runs, "u1-blocked", facts)
    assert triage["candidates"] == []
    assert triage["plan"] is None
    assert _decisions_with(triage, "no free slot")


def test_large_ambiguous_overlap_needs_owner(tmp_path: Path) -> None:
    """An overlap covering most of the visual is a redesign decision."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 50, 50, 200, 200)])
    runs = _review(tmp_path, facts, "u1-large")
    triage = propose_candidates(runs, "u1-large", facts)
    assert triage["candidates"] == []
    assert triage["plan"] is None
    held = _decisions_with(triage, "large ambiguous overlap")
    assert len(held) == 1
    assert held[0]["status"] == "needs_owner_decision"


def test_missing_source_binding_without_facts(tmp_path: Path) -> None:
    """Geometry synthesis without the sealed facts needs the owner."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 100, 100, 200, 200)])
    runs = _review(tmp_path, facts, "u1-nofacts")
    triage = propose_candidates(runs, "u1-nofacts")
    assert triage["verdict"] == "pass"
    assert triage["candidates"] == []
    assert triage["plan"] is None
    assert _decisions_with(triage, "missing source binding")


def test_stale_facts_block_propose(tmp_path: Path) -> None:
    """Facts that no longer match the sealed run block plan generation."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 100, 100, 200, 200)])
    runs = _review(tmp_path, facts, "u1-stale")
    drifted = _facts([("A", 0, 0, 200, 200), ("B", 101, 100, 200, 200)])
    refused = propose_candidates(runs, "u1-stale", drifted)
    assert refused["verdict"] == "blocked"
    assert any("stale finding/source" in reason
               for reason in refused["blocked_reasons"])


def test_unknown_inherited_default_needs_owner(tmp_path: Path) -> None:
    """Mixed explicit/inherited declarations are never guessed."""
    facts = {"rules": {"typography.format_declaration_consistency": {
        "readings": [
            {"cohort": "slicer/header.textSize", "visual": "v1",
             "page": "P1", "value": "12D"},
            {"cohort": "slicer/header.textSize", "visual": "v2",
             "page": "P1", "value": None}]}}}
    runs = _review(tmp_path, facts, "u1-default")
    triage = propose_candidates(runs, "u1-default")
    assert triage["candidates"] == []
    assert triage["plan"] is None
    held = _decisions_with(triage, "inherited default")
    assert len(held) == 1
    assert held[0]["status"] == "needs_owner_decision"


def test_outside_page_clamp_and_conflicting_plans(tmp_path: Path) -> None:
    """A verified move synthesizes; clashes and neighbor harm need owners."""
    facts = _facts([("a1", -100, 0, 120, 200), ("m", -50, 0, 200, 200)])
    runs = _review(tmp_path, facts, "u1-clash")
    triage = propose_candidates(runs, "u1-clash", facts)
    assert len(triage["candidates"]) == 1
    record = triage["candidates"][0]
    assert record["visual"] == "m"
    assert (record["old"], record["new"]) == (-50, 20)
    assert record["path"] == ["position", "x"]
    held = _decisions_with(triage, "conflicting plans")
    assert len(held) == 1
    assert held[0]["visual"] == "m"
    neighbor = _decisions_with(triage, "would overlap a measured neighbor")
    assert len(neighbor) == 1
    assert neighbor[0]["visual"] == "a1"
    assert triage["plan"] is not None
    assert len(triage["plan"]["operations"]) == 1
    assert validate_plan(triage["plan"], "orig", "cand") == []


# Explicit leaf bindings (forward contract for proven old/new) -----------


_LEAF_PATH = ["visual", "objects", "categoryAxis", 0, "properties",
              "precision", "expr", "Literal", "Value"]


def _leaf_finding(new: str) -> dict:
    return {"check": "axis.tick_format", "status": "fail",
            "detail": {"rule_id": "axis.tick_format", "status": "fail",
                       "evidence": {"binding": {
                           "op": "axis.precision", "page": "P1",
                           "visual": "v1", "path": _LEAF_PATH,
                           "old": "1", "new": new}}}}


def test_leaf_explicit_binding_synthesizes() -> None:
    """Proven old/new precision literals become a typed candidate."""
    result = synthesize_plan([_leaf_finding("2")], {"rules": {}})
    assert len(result["candidates"]) == 1
    record = result["candidates"][0]
    assert (record["old"], record["new"]) == ("1", "2")
    assert record["confidence"] == "medium"
    assert record["safety"] == "leaf-type-preserving"
    assert record["affected_pages"] == ["P1"]
    assert result["plan"] is not None
    assert validate_plan(result["plan"], "orig", "cand") == []


def test_duplicate_target_edits_need_owner() -> None:
    """Two values for one path arbitrate; no plan is emitted."""
    result = synthesize_plan([_leaf_finding("2"), _leaf_finding("3")],
                             {"rules": {}})
    assert result["candidates"] == []
    assert result["plan"] is None
    held = [item for item in result["decisions"]
            if "duplicate target edits" in item["reason"]]
    assert len(held) == 1
    assert held[0]["status"] == "needs_owner_decision"


def test_unknown_checks_stay_unsupported() -> None:
    """Semantic/coverage findings are never guessed into candidates."""
    findings = [
        {"check": "chart.future_rule", "status": "fail", "detail": {}},
        {"check": "coverage:visual_geometry_unproven", "status": "blocked",
         "detail": {"rule": "visual_geometry_unproven"}}]
    result = synthesize_plan(findings, {"rules": {}})
    assert result["candidates"] == []
    assert result["plan"] is None
    by_check = {item["check"]: item["status"]
                for item in result["decisions"]}
    assert by_check["chart.future_rule"] == "needs_owner_decision"
    assert by_check["coverage:visual_geometry_unproven"] == "unsupported"


# CLI --out and MCP facts plumbing ----------------------------------------


def test_propose_out_writes_repair_plan(tmp_path: Path, capsys) -> None:
    """--out writes a validate-plan-clean document for vqs repair."""
    facts = _facts([("A", 0, 0, 200, 200), ("B", 100, 100, 200, 200)])
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    runs = str(tmp_path / "runs")
    assert vqs_main(["review", "--facts", str(facts_path),
                     "--run-root", runs, "--run-id", "u1-cli"]) == 1
    capsys.readouterr()
    plan_path = tmp_path / "plan.json"
    assert vqs_main(["propose", "--run-root", runs, "--run-id", "u1-cli",
                     "--facts", str(facts_path),
                     "--out", str(plan_path)]) == 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert validate_plan(plan, "orig", "cand") == []
    assert plan["operations"][0]["value"] == 200


def test_propose_out_refuses_without_candidate(tmp_path: Path,
                                               capsys) -> None:
    """--out with nothing synthesizable fails closed and writes nothing.

    U7: the mixed cohort is unknown (needs_render_evidence), so review
    blocks (exit 2, not fail); propose still refuses and writes nothing.
    """
    facts = {"rules": {"typography.format_declaration_consistency": {
        "readings": [
            {"cohort": "slicer/header.textSize", "visual": "v1",
             "page": "P1", "value": "12D"},
            {"cohort": "slicer/header.textSize", "visual": "v2",
             "page": "P1", "value": None}]}}}
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    runs = str(tmp_path / "runs")
    assert vqs_main(["review", "--facts", str(facts_path),
                     "--run-root", runs, "--run-id", "u1-node"]) == 2
    capsys.readouterr()
    plan_path = tmp_path / "plan.json"
    assert vqs_main(["propose", "--run-root", runs, "--run-id", "u1-node",
                     "--out", str(plan_path)]) == 2
    assert not plan_path.exists()


def test_mcp_propose_accepts_optional_facts() -> None:
    """The MCP tool carries the same optional facts through the engine."""
    spec, error = validate_call("vqs_propose", {"run_root": "r",
                                                "run_id": "i"})
    assert error is None
    assert spec is not None
    spec, error = validate_call("vqs_propose", {"run_root": "r",
                                                "run_id": "i",
                                                "facts": {"rules": {}}})
    assert error is None
    assert spec is not None
    _, error = validate_call("vqs_propose", {"run_root": "r",
                                              "run_id": "i",
                                              "facts": [1]})
    assert error is not None
