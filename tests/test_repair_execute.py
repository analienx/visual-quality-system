"""Executor tests: atomic apply, derived-write coverage, rollback.

Synthetic PBIR reports only. Failures remove the candidate (atomic
nothing); rollback re-materializes and proves the digest.
"""
import json
from pathlib import Path

import pytest

from vqs.repair.execute import (
    RepairError,
    apply_plan,
    materialize_candidate,
    rollback_candidate,
    tree_digest,
)
from vqs.repair.templates import (
    TemplateError,
    clear_templates,
    register_template,
)

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"


def _make_report(root: Path, name: str = "original.Report") -> Path:
    report = root / name
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                      encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 24, "y": 104, "width": 296,
                                 "height": 96, "tabOrder": 4, "z": 4},
                    "visual": {
                        "visualType": "card",
                        "objects": {"labels": [{"properties": {
                            "fontSize": {"expr": {"Literal": {
                                "Value": "11D"}}}}}]},
                        "query": {"queryState": {"Values": {"projections": [
                            {"queryRef": "Fact Sales.Revenue",
                             "field": {"Measure": {}},
                             "active": True}]}}}}}),
        encoding="utf-8")
    return report


def _plan(**overrides):
    base = {
        "operations": [{
            "type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": "cardx"},
            "path": ["visual", "objects", "labels", 0, "properties",
                     "fontSize", "expr", "Literal", "Value"],
            "value": "14D", "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original",
    }
    base.update(overrides)
    return base


def test_apply_edits_candidate_leaves_original(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    before = tree_digest(original)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "applied"
    assert result["before"] == before
    assert result["after"] != before
    assert result["affected_pages"] == ["P1"]
    assert len(result["edits"]) == 1
    assert VISUAL in result["patch"]
    assert "14D" in result["patch"][VISUAL]
    assert tree_digest(original) == before  # original untouched
    edited = json.loads((tmp_path / "cand" / VISUAL)
                        .read_text(encoding="utf-8"))
    assert edited["visual"]["objects"]["labels"][0][
        "properties"]["fontSize"]["expr"]["Literal"]["Value"] == "14D"


def test_invalid_plan_never_materializes(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    bad = _plan(operations=[{"type": "shell", "target": "os"}])
    result = apply_plan(bad, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "validate"
    assert not (tmp_path / "cand").exists()


def test_apply_failure_removes_candidate(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    missing = _plan(operations=[{
        "type": "typography.size", "target": "visual",
        "selector": {"page": "P1", "visual": "ghost"},
        "path": ["visual", "objects"], "value": "14D",
        "writes": [VISUAL]}])
    result = apply_plan(missing, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "apply"
    assert result["index"] == 0
    assert "ghost" in result["reason"]
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == tree_digest(original)


def test_derived_write_must_match_declared_targets(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    other = "definition/pages/P1/visuals/other/visual.json"
    sneaky = _plan(write_targets=[other])
    result = apply_plan(sneaky, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "validate"
    assert result["issues"][0]["rule"] == "operation_write_mismatch"


def test_existing_candidate_root_refused(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    candidate = tmp_path / "cand"
    candidate.mkdir()
    with pytest.raises(RepairError, match="fresh path"):
        materialize_candidate(str(original), str(candidate))
    with pytest.raises(RepairError, match="not a directory"):
        materialize_candidate(str(tmp_path / "nope"), str(tmp_path / "c2"))


def test_rollback_restores_exact_digest(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    before = tree_digest(original)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "applied"
    rolled = rollback_candidate(str(original), str(tmp_path / "cand"),
                                result["before"])
    assert rolled["status"] == "pass"
    assert rolled["rule"] == "rollback_restored"
    assert tree_digest(tmp_path / "cand") == before
    tampered = rollback_candidate(str(original), str(tmp_path / "cand2"),
                                  "0" * 64)
    assert tampered["status"] == "fail"


def test_chart_replace_needs_vetted_template(tmp_path: Path) -> None:
    clear_templates()
    original = _make_report(tmp_path)
    swap = _plan(operations=[{
        "type": "chart.replace", "target": "visual",
        "selector": {"page": "P1", "visual": "cardx"},
        "identical_intent": True,
        "template": {"name": "kpi-card", "version": "1.0.0"},
        "writes": [VISUAL]}])
    result = apply_plan(swap, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "no vetted template" in result["reason"]
    register_template("kpi-card", "1.0.0", "kpi",
                      {"visual": {"objects": {"labels": []},
                                  "visualType": "kpi"}},
                      ["Fact Sales.Revenue"], "oracle-revenue")
    try:
        result = apply_plan(swap, str(original), str(tmp_path / "cand2"))
        assert result["verdict"] == "applied"
        edited = json.loads((tmp_path / "cand2" / VISUAL)
                            .read_text(encoding="utf-8"))
        assert edited["visual"]["visualType"] == "kpi"
        assert edited["visual"]["query"]["queryState"]["Values"][
            "projections"][0]["queryRef"] == "Fact Sales.Revenue"
    finally:
        clear_templates()
    with pytest.raises(TemplateError, match="non-empty"):
        register_template("x", "1", "card", {"visual": {}}, [], "o")
    with pytest.raises(TemplateError, match="visual.json object"):
        register_template("x", "1", "card", {"nope": 1}, ["r"], "o")
