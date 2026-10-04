"""Executor tests: atomic apply, derived-write coverage, rollback.

Synthetic PBIR reports only. Failures remove the candidate (atomic
nothing); rollback re-materializes and proves the digest.
"""
import json
import os
import shutil
import subprocess
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
    get_template,
    register_template,
)

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"


def _make_report(root: Path, name: str = "original.Report") -> Path:
    report = root / name
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages.parent / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
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
    before = tree_digest(original)
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
    assert tree_digest(original) == before


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


def test_rollback_refuses_overlapping_roots(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    before = tree_digest(original)
    refused = rollback_candidate(str(original), str(original), before)
    assert refused["rule"] == "rollback_refused"
    assert refused["status"] == "blocked"
    assert original.is_dir()
    assert tree_digest(original) == before
    nested = rollback_candidate(str(original),
                                str(original / "definition"), before)
    assert nested["rule"] == "rollback_refused"
    assert (original / "definition").is_dir()


def test_structural_damage_blocks_without_leak(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    broken = tmp_path / "broken.Report"
    shutil.copytree(original, broken)
    visual = (broken / "definition/pages/P1/visuals/cardx/visual.json")
    doc = json.loads(visual.read_text(encoding="utf-8"))
    doc["visual"]["query"] = []
    visual.write_text(json.dumps(doc), encoding="utf-8")
    result = apply_plan(_plan(), str(broken), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert not (tmp_path / "cand").exists()
    listed = tmp_path / "listed.Report"
    shutil.copytree(original, listed)
    (listed / "definition/pages/P1/page.json").write_text("[]",
                                                         encoding="utf-8")
    result = apply_plan(_plan(), str(listed), str(tmp_path / "cand2"))
    assert result["verdict"] == "blocked"
    assert not (tmp_path / "cand2").exists()


def test_selector_escape_and_unknown_page_block_pre_write(
        tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    sneaky = _plan(operations=[{
        "type": "typography.size", "target": "visual",
        "selector": {"page": "P1/../P1", "visual": "cardx"},
        "path": ["visual", "objects"], "value": "x", "writes": [VISUAL]}])
    result = apply_plan(sneaky, str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "escapes" in result["reason"]
    assert not (tmp_path / "cand").exists()
    ghost = _plan(operations=[{
        "type": "typography.size", "target": "visual",
        "selector": {"page": "P9", "visual": "cardx"},
        "path": ["visual", "objects"], "value": "x", "writes": [VISUAL]}])
    result = apply_plan(ghost, str(original), str(tmp_path / "cand2"))
    assert result["verdict"] == "blocked"
    assert "not in the page order" in result["reason"]


def test_bool_canvas_rejected(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    page_file = original / "definition/pages/P1/page.json"
    page_file.write_text(json.dumps({"displayName": "O", "width": True,
                                     "height": 720}), encoding="utf-8")
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "integer canvas" in result["reason"]


def test_copy_walk_errors_fail_closed(tmp_path: Path, monkeypatch) -> None:
    import os as _os

    original = _make_report(tmp_path)
    real_walk = _os.walk

    def failing_walk(top, **kwargs):
        yield from real_walk(top, **kwargs)
        onerror = kwargs.get("onerror")
        if onerror is not None:
            onerror(OSError("simulated EACCES"))

    monkeypatch.setattr(_os, "walk", failing_walk)
    with pytest.raises(RepairError, match="unreadable|rejected"):
        materialize_candidate(str(original), str(tmp_path / "cand"))
    assert not (tmp_path / "cand").exists()


def test_post_copy_rescan_blocks(tmp_path: Path, monkeypatch) -> None:
    from vqs.repair import execute

    original = _make_report(tmp_path)
    calls = []
    real = execute.validate_materialized_roots

    def counting(original_path, candidate_root):
        calls.append(candidate_root)
        if len(calls) > 1:
            return [{"rule": "link_escape", "path": "swapped-in"}]
        return real(original_path, candidate_root)

    monkeypatch.setattr(execute, "validate_materialized_roots", counting)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "after copy" in result["reason"]
    assert len(calls) == 2


def test_tree_digest_refuses_escaped_entries(
        tmp_path: Path, monkeypatch) -> None:
    import os as _os

    original = _make_report(tmp_path)
    real = _os.path.realpath

    def fake(path):
        if str(path).endswith("page.json"):
            return _os.path.join(str(tmp_path), "elsewhere", "page.json")
        return real(path)

    monkeypatch.setattr(_os.path, "realpath", fake)
    with pytest.raises(RepairError, match="link inside repair tree"):
        tree_digest(original)


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


def test_template_bodies_and_copies() -> None:
    clear_templates()
    with pytest.raises(TemplateError, match="objects must be"):
        register_template("x", "1", "card", {"visual": {"objects": []}}, ["r"], "o")
    with pytest.raises(TemplateError, match="objects must be"):
        register_template("x", "1", "card", {"visual": {}}, ["r"], "o")
    with pytest.raises(TemplateError, match="non-finite"):
        register_template("x", "1", "card", {"visual": {"objects": {"w": float("nan")}}}, ["r"], "o")
    register_template("t", "1", "card", {"visual": {"objects": {"labels": []}}}, ["r"], "o")
    try:
        fetched = get_template("t", "1")
        fetched["body"]["visual"]["objects"]["labels"].append(
            "mutated")
        fetched["required_bindings"].append("mutated")
        again = get_template("t", "1")
        assert again["body"]["visual"]["objects"] == {"labels": []}
        assert again["required_bindings"] == ["r"]
    finally:
        clear_templates()


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_real_junction_inside_tree_refuses(
        tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "smuggled.json").write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J",
         str(original / "definition" / "jdir"), str(outside)],
        capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        pytest.skip(f"mklink /J unavailable: {completed.stderr[:200]}")
    with pytest.raises(RepairError, match="link inside repair tree"):
        tree_digest(original)
    with pytest.raises(RepairError, match="rejected|escapes|loop"):
        materialize_candidate(str(original), str(tmp_path / "cand"))
    assert not (tmp_path / "cand").exists()


def test_digest_failure_leaves_no_candidate(tmp_path: Path,
                                            monkeypatch) -> None:
    from vqs.repair import execute

    original = _make_report(tmp_path)
    before = tree_digest(original)

    def boom(report):
        raise RepairError("simulated planted link")

    monkeypatch.setattr(execute, "tree_digest", boom)
    with pytest.raises(RepairError, match="planted link"):
        materialize_candidate(str(original), str(tmp_path / "cand"))
    assert not (tmp_path / "cand").exists()
    monkeypatch.setattr(execute, "tree_digest", boom)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand2"))
    assert result["verdict"] == "blocked"
    assert result["stage"] == "materialize"
    assert not (tmp_path / "cand2").exists()
    monkeypatch.undo()
    assert tree_digest(original) == before


@pytest.mark.skipif(os.name != "nt", reason="junctions are Windows-only")
def test_planted_junction_leaves_no_candidate(tmp_path: Path,
                                              monkeypatch) -> None:
    from vqs.repair import execute

    original = _make_report(tmp_path)
    before = tree_digest(original)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "smuggled.json").write_text("{}", encoding="utf-8")
    real_validate = execute.validate_materialized_roots

    def planting(original_path, candidate_root):
        issues = real_validate(original_path, candidate_root)
        target = Path(candidate_root) / "pdir"
        if not issues and Path(candidate_root).is_dir() \
                and not os.path.lexists(target):
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(outside)],
                capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                pytest.skip("mklink /J unavailable: "
                            f"{completed.stderr[:200]}")
        return issues

    monkeypatch.setattr(execute, "validate_materialized_roots", planting)
    result = apply_plan(_plan(), str(original), str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "link inside repair tree" in result["reason"]
    assert not (tmp_path / "cand").exists()
    assert (outside / "smuggled.json").is_file()
    monkeypatch.undo()
    assert tree_digest(original) == before


def test_hardlink_inside_tree_refuses(tmp_path: Path) -> None:
    original = _make_report(tmp_path)
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    try:
        os.link(str(tmp_path / "outside.json"),
                str(original / "definition" / "hard.json"))
    except OSError as exc:
        pytest.skip(f"hardlinks unsupported on this host: {exc}")
    with pytest.raises(RepairError, match="hardlink inside repair tree"):
        tree_digest(original)
