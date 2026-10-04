"""S17: repair emits legal PBIR literals through public routes.

Semantic-query QueryLiteralExpression.Value is a string, so
axis.precision "1"->"3" applies and seals through ``vqs repair``
plus ``vqs verify``; raw JSON numbers on either side block at
apply with the candidate removed and the original pinned.
"""
import json
from pathlib import Path

from vqs.cli import main
from vqs.repair.execute import tree_digest

VISUAL = "definition/pages/P1/visuals/cardx/visual.json"
PRECISION = ["visual", "objects", "labels", 0, "properties",
             "precision", "expr", "Literal", "Value"]


def _make_report(root: Path, value) -> Path:
    report = root / "original.Report"
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
        json.dumps({"displayName": "Overview", "width": 1280,
                    "height": 720}), encoding="utf-8")
    (pages / "P1" / "visuals" / "cardx" / "visual.json").write_text(
        json.dumps({"name": "cardx",
                    "position": {"x": 24, "y": 104, "width": 296,
                                 "height": 96, "tabOrder": 4, "z": 4},
                    "visual": {
                        "visualType": "card",
                        "objects": {"labels": [{"properties": {
                            "precision": {"expr": {"Literal": {
                                "Value": value}}}}}]}}}),
        encoding="utf-8")
    return report


def _plan(value) -> dict:
    return {"operations": [{
        "type": "axis.precision", "target": "visual",
        "selector": {"page": "P1", "visual": "cardx"},
        "path": PRECISION, "value": value, "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original"}


def _repair(root: Path, value, run_id: str) -> tuple:
    original = _make_report(root, "1")
    plan_path = root / f"{run_id}.json"
    plan_path.write_text(json.dumps(_plan(value)), encoding="utf-8")
    return original, plan_path


def test_legal_precision_applies_and_verifies(
        tmp_path: Path, capsys) -> None:
    """S17: string "1"->"3" applies, seals, and verifies."""
    original, plan_path = _repair(tmp_path, "3", "s17-legal")
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s17-legal"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["verdict"] == "pass"
    doc = json.loads((tmp_path / "cand" / VISUAL).read_text(
        encoding="utf-8"))
    node = doc
    for step in PRECISION:
        node = node[step] if isinstance(node, dict) else node[int(step)]
    assert node == "3" and isinstance(node, str)
    code = main(["verify", "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s17-legal"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["verdict"] == "pass"


def test_numeric_new_value_blocks(tmp_path: Path, capsys) -> None:
    """S17: a raw JSON number replacement blocks at apply."""
    original, plan_path = _repair(tmp_path, 3, "s17-new")
    before = tree_digest(original)
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s17-new"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert any("repair apply:" in reason for reason in
               out.get("blocked_reasons", []))
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before


def test_numeric_old_value_blocks(tmp_path: Path, capsys) -> None:
    """S17: a raw JSON number already in source blocks at apply."""
    original = _make_report(tmp_path, 1)
    plan_path = tmp_path / "s17-old.json"
    plan_path.write_text(json.dumps(_plan(3)), encoding="utf-8")
    before = tree_digest(original)
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s17-old"])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["verdict"] == "blocked"
    assert any("precision" in reason for reason in
               out.get("blocked_reasons", []))
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before
