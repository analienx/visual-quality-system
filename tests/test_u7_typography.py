"""P1-U7: typography declaration rule semantics and proven format ops.

Item 27: explicit values proven different fail; mixed explicit/inherited
with an unknown effective value is unknown (needs_render_evidence),
never a visual-quality fail; all-default passes; proved-equal effectives
pass with a hygiene-only notice; proved-different effectives fail.
Item 28: hygiene stays separate from the verdict. Item 29: narrow typed
format.unset_override / format.set_explicit ops bind, apply, verify,
and synthesize only with a proved effective value plus named provenance.
"""
import json
from pathlib import Path

import pytest

from vqs.design_rules import format_declaration_consistency
from vqs.repair.allowlist import validate_plan
from vqs.repair.execute import apply_plan
from vqs.repair.recipes import RecipeError, bind_operation
from vqs.repair.regress import verify_candidate
from vqs.repair.synthesize import synthesize_plan

COHORT = "slicer/header.textSize"


def _reading(visual: str, value, effective=None) -> dict:
    entry: dict = {"cohort": COHORT, "visual": visual,
                   "page": "P1", "value": value}
    if effective is not None:
        entry["effective"] = effective
    return entry


# Rule semantics (item 27) -----------------------------------------------


def test_explicit_values_proven_different_fail() -> None:
    failed = format_declaration_consistency(
        [_reading("a", 10), _reading("b", 12)])
    assert failed["status"] == "fail"
    assert failed["evidence"]["conflicts"][0]["kind"] == "divergent_values"


def test_mixed_unknown_effective_is_unknown_not_fail() -> None:
    result = format_declaration_consistency(
        [_reading("a", None), _reading("b", 11)])
    assert result["status"] == "unknown"
    assert "needs_render_evidence" in result["evidence"]["reason"]
    assert result["evidence"]["pending"][0]["kind"] == "mixed_declaration"
    assert result["evidence"]["conflicts"] == []


def test_all_default_passes() -> None:
    result = format_declaration_consistency(
        [_reading("a", None), _reading("b", None)])
    assert result["status"] == "pass"
    assert result["evidence"]["conflicts"] == []
    assert result["evidence"]["pending"] == []
    assert result["evidence"]["hygiene"] == []


def test_proved_equal_effective_passes_with_hygiene_notice() -> None:
    result = format_declaration_consistency(
        [_reading("a", None, 11), _reading("b", 11)])
    assert result["status"] == "pass"
    assert result["evidence"]["conflicts"] == []
    assert result["evidence"]["pending"] == []
    assert len(result["evidence"]["hygiene"]) == 1
    assert "format.unset_override" in result["evidence"]["hygiene"][0]["note"]


def test_proved_different_effective_fails() -> None:
    failed = format_declaration_consistency(
        [_reading("a", None, 10), _reading("b", None, 12)])
    assert failed["status"] == "fail"
    assert (failed["evidence"]["conflicts"][0]["kind"]
            == "divergent_effective_values")


def test_explicit_disagreement_wins_over_unknown() -> None:
    failed = format_declaration_consistency(
        [_reading("a", 10), _reading("b", 12), _reading("c", None)])
    assert failed["status"] == "fail"
    assert failed["evidence"]["conflicts"][0]["kind"] == "divergent_values"


def test_literal_forms_share_hygiene_only() -> None:
    result = format_declaration_consistency(
        [_reading("a", 10), _reading("b", "10")])
    assert result["status"] == "pass"
    assert len(result["evidence"]["hygiene"]) == 1


def test_invalid_effective_is_unknown() -> None:
    assert format_declaration_consistency(
        [_reading("a", None, {"guessed": 1})])["status"] == "unknown"


def test_uniform_explicit_passes_clean() -> None:
    result = format_declaration_consistency(
        [_reading("a", 10), _reading("b", 10)])
    assert result["status"] == "pass"
    assert result["evidence"]["hygiene"] == []


# Recipe bindings (item 29) -----------------------------------------------

PROP = ["visual", "objects", "labels", 0, "properties", "fontSize"]


def _doc(value) -> dict:
    return {"name": "cardx",
            "position": {"x": 1, "y": 2, "width": 3, "height": 4},
            "visual": {"visualType": "card",
                       "objects": {"labels": [{"properties": {
                           "fontSize": {"expr": {"Literal": {
                               "Value": value}}}}}]}}}


def _unset(old, effective, proof="render:adapter/run-1") -> dict:
    # Sealed-finding bindings carry top-level page/visual (the U1 leaf
    # convention); plan operations additionally need the selector.
    return {"type": "format.unset_override", "target": "visual",
            "page": "P1", "visual": "cardx",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": list(PROP), "old": old, "effective": effective,
            "proof": proof,
            "writes": ["definition/pages/P1/visuals/cardx/visual.json"]}


def _setter(old, value, effective, proof="render:adapter/run-1") -> dict:
    return {"type": "format.set_explicit", "target": "visual",
            "page": "P1", "visual": "cardx",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": list(PROP), "old": old, "value": value,
            "effective": effective, "proof": proof,
            "writes": ["definition/pages/P1/visuals/cardx/visual.json"]}


def test_unset_binds_redundant_override() -> None:
    binding = bind_operation(_unset(11, 11), _doc(11))
    assert binding["op"] == "format.unset_override"
    assert binding["path"] == PROP
    assert binding["old"] == 11


def test_unset_requires_proof() -> None:
    with pytest.raises(RecipeError, match="provenance"):
        bind_operation(_unset(11, 11, ""), _doc(11))


def test_unset_rejects_effective_mismatch() -> None:
    with pytest.raises(RecipeError, match="must equal"):
        bind_operation(_unset(11, 12), _doc(11))


def test_unset_rejects_live_drift() -> None:
    with pytest.raises(RecipeError, match="precondition"):
        bind_operation(_unset(11, 11), _doc(12))


def test_unset_rejects_foreign_terminal() -> None:
    op = _unset(11, 11)
    op["path"] = ["visual", "objects", "labels", 0, "properties", "color"]
    with pytest.raises(RecipeError, match="outside this recipe"):
        bind_operation(op, _doc(11))


def test_set_binds_proved_value() -> None:
    binding = bind_operation(_setter(10, 12, 12), _doc(10))
    assert binding["op"] == "format.set_explicit"
    assert binding["path"] == [*PROP, "expr", "Literal", "Value"]
    assert binding["new"] == 12


def test_set_rejects_guessed_value() -> None:
    with pytest.raises(RecipeError, match="never guessed"):
        bind_operation(_setter(10, 13, 12), _doc(10))


def test_set_rejects_noop() -> None:
    with pytest.raises(RecipeError, match="already explicit"):
        bind_operation(_setter(12, 12, 12), _doc(12))


def test_set_requires_proof() -> None:
    with pytest.raises(RecipeError, match="provenance"):
        bind_operation(_setter(10, 12, 12, ""), _doc(10))


def test_unknown_format_op_rejected() -> None:
    op = _unset(11, 11)
    op["type"] = "format.nope"
    with pytest.raises(RecipeError, match="unknown operation"):
        bind_operation(op, _doc(11))


# Executor + regression ----------------------------------------------------


def _make_report(root: Path) -> Path:
    report = root / "original.Report"
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages.parent / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (pages.parent / "version.json").write_text(
        json.dumps({"$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                                "definition/versionMetadata/1.0.0/schema.json"),
                    "version": "2.0.0"}), encoding="utf-8")
    (pages.parent / "report.json").write_text(
        json.dumps({"$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                                "definition/report/3.3.0/schema.json"),
                    "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "O", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps(_doc(11)), encoding="utf-8")
    return report


def test_unset_applies_and_verifies(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    plan = {"operations": [_unset(11, 11)],
            "write_targets": [
                "definition/pages/P1/visuals/cardx/visual.json"],
            "rollback": "re-materialize from original"}
    assert validate_plan(plan, str(original), "cand") == []
    result = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "applied"
    visual_file = (tmp_path / "cand" / "definition" / "pages" / "P1"
                   / "visuals" / "cardx" / "visual.json")
    props = json.loads(visual_file.read_text(encoding="utf-8"))[
        "visual"]["objects"]["labels"][0]["properties"]
    assert "fontSize" not in props
    verdict = verify_candidate(str(original), str(tmp_path / "cand"),
                               result["edits"])
    assert verdict["verdict"] == "pass", verdict.get("problems")


def test_set_applies_and_verifies(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    plan = {"operations": [_setter(11, 12, 12)],
            "write_targets": [
                "definition/pages/P1/visuals/cardx/visual.json"],
            "rollback": "re-materialize from original"}
    assert validate_plan(plan, str(original), "cand") == []
    result = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "applied"
    verdict = verify_candidate(str(original), str(tmp_path / "cand"),
                               result["edits"])
    assert verdict["verdict"] == "pass", verdict.get("problems")


# Synthesis (items 27 + 29) -------------------------------------------------


def _fail_finding(binding: dict) -> dict:
    return {"check": "typography.format_declaration_consistency",
            "status": "fail",
            "detail": {"rule_id": "typography.format_declaration_consistency",
                       "status": "fail",
                       "evidence": {"binding": binding}}}


def test_unset_binding_synthesizes_candidate() -> None:
    result = synthesize_plan([_fail_finding(_unset(11, 11))], {"rules": {}})
    assert len(result["candidates"]) == 1, result["decisions"]
    record = result["candidates"][0]
    assert record["op"] == "format.unset_override"
    assert result["plan"] is not None
    assert validate_plan(result["plan"], "orig", "cand") == []


def test_set_binding_synthesizes_candidate() -> None:
    result = synthesize_plan([_fail_finding(_setter(10, 12, 12))],
                             {"rules": {}})
    assert len(result["candidates"]) == 1, result["decisions"]
    assert result["candidates"][0]["op"] == "format.set_explicit"
    assert result["plan"] is not None


def test_unproven_binding_needs_owner() -> None:
    result = synthesize_plan([_fail_finding(_unset(11, 11, ""))],
                             {"rules": {}})
    assert result["candidates"] == []
    assert result["plan"] is None
    assert any(entry["status"] == "needs_owner_decision"
               and "provenance" in entry["reason"]
               for entry in result["decisions"]), result["decisions"]


def test_mismatched_effective_needs_owner() -> None:
    result = synthesize_plan([_fail_finding(_unset(11, 12))], {"rules": {}})
    assert result["candidates"] == []
    assert any("would change the rendering" in entry["reason"]
               for entry in result["decisions"]), result["decisions"]


def test_unknown_render_evidence_needs_owner() -> None:
    finding = {"check": "typography.format_declaration_consistency",
               "status": "unknown",
               "detail": {"rule_id": "typography.format_declaration_consistency",
                          "status": "unknown",
                          "evidence": {
                              "reason": ("needs_render_evidence: mixed "
                                         "explicit/inherited declarations"),
                              "pending": [{"cohort": COHORT}]}}}
    result = synthesize_plan([finding], {"rules": {}})
    assert result["candidates"] == []
    assert result["plan"] is None
    assert any(entry["status"] == "needs_owner_decision"
               and "inherited default" in entry["reason"]
               for entry in result["decisions"])


def test_blocked_review_halts_workflow_before_runtime(tmp_path: Path) -> None:
    """U7: a needs_render_evidence review blocks the run; no runtime stages."""
    from vqs.coordinator import run_workflow

    facts = {"rules": {"typography.format_declaration_consistency": {
        "readings": [
            {"cohort": COHORT, "visual": "v1", "page": "P1", "value": "12D"},
            {"cohort": COHORT, "visual": "v2", "page": "P1",
             "value": None}]}}}
    envelope = run_workflow(facts=facts, mode="review", scope="static",
                            run_root=str(tmp_path / "runs"),
                            run_id="u7-blocked")
    stages = {entry["stage"]: entry for entry in envelope["stages"]}
    assert stages["review"]["status"] == "blocked"
    assert "readiness" not in stages and "handoff" not in stages
    assert envelope["verdict"] == "blocked"
    assert envelope["summary"]["outcome"] == "blocked"
    assert envelope["summary"]["review_verdict"] == "blocked"
