"""S16/S17: repair atomicity through the sealed public route.

A failing second op removes the whole candidate (nothing half
applied, original digest pinned); an unwritable candidate parent
blocks instead of leaking a partial tree; a zero-width canvas page
blocks numeric abuse at apply. The cited apply.py/repository splits,
migrations, --dry-run, design_tokens and penalties do not exist in
this tree (recorded omissions); order, rollback and bounds below are
the executable residue, driven through ``vqs repair``.
"""
import json
import os
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.repair.execute import tree_digest

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"


def _make_report(root: Path, name: str = "original.Report",
                 width: int = 1280, height: int = 720) -> Path:
    report = root / name
    pages = report / "definition" / "pages"
    (pages / "P1" / "visuals" / "cardx").mkdir(parents=True)
    (pages.parent / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (pages.parent / "version.json").write_text(json.dumps(
        {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
         "version": "1.0"}), encoding="utf-8")
    (pages.parent / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (pages / "P1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": width,
                    "height": height}), encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 24, "y": 104, "width": 296,
                                 "height": 96, "tabOrder": 4, "z": 4},
                    "visual": {
                        "visualType": "card",
                        "objects": {"labels": [{"properties": {
                            "fontSize": {"expr": {"Literal": {
                                "Value": "11D"}}}}}]}}),
        encoding="utf-8")
    return report


LEAF = ["visual", "objects", "labels", 0, "properties", "fontSize",
        "expr", "Literal", "Value"]


def _op(visual: str = "cardx"):
    return {"type": "typography.size", "target": "visual",
            "selector": {"page": "P1", "visual": visual},
            "path": LEAF, "value": "14D",
            "writes": [VISUAL]}


def _plan(*ops) -> dict:
    return {"operations": list(ops), "write_targets": [VISUAL],
            "rollback": "re-materialize from original"}


def _repair(plan: dict, root: Path, run_id: str) -> tuple:
    original = _make_report(root)
    plan_path = root / f"{run_id}.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return original, plan_path


def _run_cli(plan_path: Path, original: Path, root: Path,
             run_id: str, candidate: str, capsys,
             runs_root: Path | None = None) -> tuple:
    runs = runs_root if runs_root is not None else root
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(root / candidate),
                 "--run-root", str(runs / "runs"), "--run-id", run_id])
    return code, json.loads(capsys.readouterr().out)


def test_failed_second_op_removes_candidate(tmp_path: Path, capsys) -> None:
    """S16: op order applies then rolls back; nothing half applied."""
    original, plan_path = _repair(
        _plan(_op("cardx"), _op("ghost")), tmp_path, "s16-order")
    before = tree_digest(original)
    code, out = _run_cli(plan_path, original, tmp_path, "s16-order",
                         "cand", capsys)
    assert code == 2
    assert out["verdict"] == "blocked"
    reasons = out.get("blocked_reasons", [])
    assert any("repair apply:" in reason and "ghost" in reason
               for reason in reasons)
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before


def test_locked_parent_blocks_without_leak(tmp_path: Path, capsys) -> None:
    """S16: an unwritable candidate parent blocks; no partial tree leaks."""
    original, plan_path = _repair(
        _plan(_op("cardx")), tmp_path, "s16-lock")
    before = tree_digest(original)
    parent = tmp_path / "locked"
    parent.mkdir()
    os.chmod(parent, 0o555)
    try:
        probe = parent / "probe"
        try:
            probe.write_text("x", encoding="utf-8")
        except OSError:
            pass
        else:
            probe.unlink()
            pytest.skip("permissions not enforced here")
        code, out = _run_cli(plan_path, original, parent, "s16-lock",
                             "cand", capsys, runs_root=tmp_path)
    finally:
        os.chmod(parent, 0o755)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert not (parent / "cand").exists()
    assert tree_digest(original) == before


def test_zero_canvas_blocks_apply(tmp_path: Path) -> None:
    """S17: a zero-width canvas page cannot take edits."""
    from vqs.repair.execute import apply_plan
    original = _make_report(tmp_path, width=0)
    before = tree_digest(original)
    result = apply_plan(_plan(_op("cardx")), str(original),
                        str(tmp_path / "cand"))
    assert result["verdict"] == "blocked"
    assert "integer canvas" in result["reason"]
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before
