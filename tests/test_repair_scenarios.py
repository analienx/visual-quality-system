"""Repair scenario tests: two unrelated synthetic candidates end to end.

Each scenario runs the full lane chain — validate, apply, regression
verify, answer preservation, rerender requirements, rollback — against
a committed fixture report. Render acceptance stays explicitly blocked
offline; no manifests are fabricated.
"""
import json
import shutil
from pathlib import Path

import pytest

from vqs.repair.allowlist import validate_plan
from vqs.repair.answers import answers_preserved
from vqs.repair.execute import apply_plan, rollback_candidate
from vqs.repair.regress import (
    rerender_requirements,
    verify_candidate,
    verify_renders,
)
from vqs.stories import scope_digest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vqs_agent_first" / "repair"


def _load(scenario):
    root = FIXTURES / scenario
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    oracle = json.loads((root / "oracle.json").read_text(encoding="utf-8"))
    return root / "original.Report", plan, oracle


def _run_chain(tmp_path, scenario):
    fixture_report, plan, oracle = _load(scenario)
    original = tmp_path / "original.Report"
    shutil.copytree(fixture_report, original)
    assert validate_plan(plan, str(original), str(tmp_path / "cand")) == []
    applied = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert applied["verdict"] == "applied"
    candidate = Path(applied["candidate"])
    assert verify_candidate(original, candidate, applied["edits"]) == {
        "verdict": "pass",
        "checks": ["inventory", "confinement", "identities", "geometry"]}
    scope = scope_digest(oracle["scope"].get("filters"),
                         role=oracle["scope"].get("role", ""),
                         period=oracle["scope"].get("period", ""),
                         measure=oracle["scope"].get("measure", ""))
    assert answers_preserved(scope, scope, oracle["rows"], oracle["rows"],
                             oracle["tolerance"],
                             ordered=oracle["ordered"])["verdict"] == "pass"
    return original, candidate, applied, oracle


@pytest.mark.parametrize("scenario", ["scenario_tick", "scenario_type"])
def test_scenario_full_chain(tmp_path, scenario):
    original, candidate, applied, _oracle = _run_chain(tmp_path, scenario)
    assert applied["affected_pages"] == ["P1"]
    assert applied["before"] != applied["after"]
    assert len(applied["patch"]) == 1
    rolled = rollback_candidate(str(original), str(candidate),
                                applied["before"])
    assert rolled["status"] == "pass"


def test_tick_hidden_category_breaks_answers(tmp_path):
    _original, _candidate, _applied, oracle = _run_chain(tmp_path,
                                                         "scenario_tick")
    scope = scope_digest(oracle["scope"].get("filters"),
                         measure=oracle["scope"].get("measure", ""))
    dropped = [row for row in oracle["rows"]
               if row["Category"] != "Accessories"]
    verdict = answers_preserved(scope, scope, oracle["rows"], dropped)
    assert verdict["verdict"] == "fail"
    assert verdict["rows"]["reason"] == "answer row count changed"


def test_type_neighbor_tamper_breaks_regression(tmp_path):
    original, candidate, applied, _oracle = _run_chain(tmp_path,
                                                       "scenario_type")
    other = candidate / "definition/pages/P2/visuals/archive/visual.json"
    doc = json.loads(other.read_text(encoding="utf-8"))
    doc["position"]["x"] = 9000
    other.write_text(json.dumps(doc), encoding="utf-8")
    verdict = verify_candidate(original, candidate, applied["edits"])
    assert verdict["verdict"] == "fail"


@pytest.mark.parametrize("scenario", ["scenario_tick", "scenario_type"])
def test_scenarios_require_renders_explicitly(tmp_path, scenario):
    _original, _candidate, applied, _oracle = _run_chain(tmp_path, scenario)
    _fixture, plan, _oracle_doc = _load(scenario)
    pages = ["P1", "P2"] if scenario == "scenario_type" else ["P1"]
    required = rerender_requirements(plan["operations"], pages)
    assert required["verdict"] == "ready"
    assert "P1" in required["pages"]
    assert verify_renders(required["pages"], [], applied["after"]) == {
        "verdict": "blocked",
        "reason": "fresh complete renders required for affected pages "
                  "and neighbors",
        "missing_pages": required["pages"]}
