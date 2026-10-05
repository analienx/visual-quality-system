"""T11/T12: repair race boundaries and precision-by-property.

T11 routes: public `vqs repair` with after-copy and during-application
save hooks — the hook must run, the user's new bytes must survive,
and unsafe success must be refused without restoring user changes.
T12 routes: installed validate-plan plus repair->verify for every
precision alias; legal strings and format properties keep working.
"""
import json
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.repair.execute import tree_digest

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_VERSION = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                  "report/definition/versionMetadata/1.0.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
VISUAL = "definition/pages/P1/visuals/v1/visual.json"


def _project(root: Path, precision_old="1", label_old="2",
             fmt_old="$#,0") -> Path:
    report = root / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    (definition / "pages" / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
        encoding="utf-8")
    (definition / "pages.json").write_text(json.dumps({"pageOrder": ["P1"]}),
                                           encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps({"$schema": SCHEMA_VERSION, "version": "2.0.0"}),
        encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (definition / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(json.dumps({
        "name": "v1",
        "position": {"x": 0, "y": 0, "width": 100, "height": 100, "z": 1},
        "visual": {
            "visualType": "barChart",
            "objects": {"categoryAxis": [{"properties": {
                "precision": {"expr": {"Literal": {"Value": precision_old}}},
                "labelPrecision": {"expr": {"Literal": {
                    "Value": label_old}}}}}]}}}), encoding="utf-8")
    return report


def _plan(op_type: str, terminal: str, value, obj: str = "categoryAxis",
          ) -> dict:
    path = ["visual", "objects", obj, 0, "properties", terminal,
            "expr", "Literal", "Value"]
    return {"operations": [{
        "type": op_type, "selector": {"page": "P1", "visual": "v1"},
        "target": "visual", "path": path, "value": value,
        "writes": [VISUAL]}], "write_targets": [VISUAL],
        "rollback": "re-materialize from original"}


def _write_plan(root: Path, name: str, plan: dict) -> Path:
    plan_path = root / name
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path


# T11 ------------------------------------------------------------------


def test_after_copy_save_blocks_public_repair(
        tmp_path: Path, capsys, monkeypatch) -> None:
    """T11: after-copy save through `vqs repair` refuses; bytes survive."""
    from vqs.repair import execute

    original = _project(tmp_path)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan("axis.tick_format", "labelPrecision", "3"))
    real_guard = execute._assert_original_pinned
    state = {"ran": False}

    def hooked_guard(report, before_digest, stage):
        if not state["ran"]:
            state["ran"] = True
            with (original / VISUAL).open("ab") as handle:
                handle.write(b" ")
        return real_guard(report, before_digest, stage)

    monkeypatch.setattr(execute, "_assert_original_pinned", hooked_guard)
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "t11-copy"])
    out = capsys.readouterr().out
    assert state["ran"] is True
    assert code == 2, out
    assert "original changed during copy" in out
    assert not (tmp_path / "cand").exists()
    assert (original / VISUAL).read_bytes().endswith(b" ")


def test_during_application_save_blocks_public_repair(
        tmp_path: Path, capsys, monkeypatch) -> None:
    """T11: mid-application save through `vqs repair` refuses at sealing."""
    from vqs.repair import execute

    original = _project(tmp_path)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan("axis.tick_format", "labelPrecision", "3"))
    real_apply = execute._apply_op
    state = {"ran": False}

    def hooked_apply(*args, **kwargs):
        bound = real_apply(*args, **kwargs)
        if not state["ran"]:
            state["ran"] = True
            with (original / VISUAL).open("ab") as handle:
                handle.write(b" ")
        return bound

    monkeypatch.setattr(execute, "_apply_op", hooked_apply)
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "t11-apply"])
    out = capsys.readouterr().out
    assert state["ran"] is True
    assert code == 2, out
    assert "original changed during application" in out
    assert not (tmp_path / "cand").exists()
    assert (original / VISUAL).read_bytes().endswith(b" ")


# T12 ------------------------------------------------------------------

ALIASES = [("axis.tick_format", "labelPrecision", "2"),
           ("axis.precision", "precision", "1")]


@pytest.mark.parametrize("op_type,terminal,old", ALIASES)
@pytest.mark.parametrize("bad", ["banana", "99999", "", 2, 2.5, True])
def test_malformed_precision_rejected_validate_plan(
        tmp_path: Path, capsys, op_type, terminal, old, bad) -> None:
    """T12: validate-plan rejects malformed new precision per property."""
    original = _project(tmp_path)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan(op_type, terminal, bad))
    code = main(["validate-plan", str(plan_path),
                 "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", f"t12-{terminal}-{bad!r}"[:40]])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "precision_value_invalid" in out


@pytest.mark.parametrize("op_type,terminal,old", ALIASES)
@pytest.mark.parametrize("bad", ["banana", "99999", 2])
def test_malformed_precision_rejected_repair(
        tmp_path: Path, capsys, op_type, terminal, old, bad) -> None:
    """T12: repair refuses malformed precision; nothing is written."""
    original = _project(tmp_path)
    before = tree_digest(original)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan(op_type, terminal, bad))
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", f"t12r-{terminal}-{bad!r}"[:40]])
    out = capsys.readouterr().out
    assert code == 2, out
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before


@pytest.mark.parametrize("op_type,terminal,old", ALIASES)
def test_malformed_old_precision_blocks_at_apply(
        tmp_path: Path, capsys, op_type, terminal, old) -> None:
    """T12: valid new over malformed old blocks at bind, not silently."""
    kwargs = {"precision_old": 1} if terminal == "precision" else {
        "label_old": 1}
    original = _project(tmp_path, **kwargs)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan(op_type, terminal, "3"))
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", f"t12o-{terminal}"])
    out = capsys.readouterr().out
    assert code == 2, out
    assert "old precision" in out


@pytest.mark.parametrize("op_type,terminal,old", ALIASES)
def test_legal_precision_applies_and_verifies(
        tmp_path: Path, capsys, op_type, terminal, old) -> None:
    """T12 positive: legal precision strings apply and verify per alias."""
    original = _project(tmp_path)
    plan_path = _write_plan(tmp_path, "plan.json",
                            _plan(op_type, terminal, "3"))
    assert main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", f"t12p-{terminal}"]) == 0
    capsys.readouterr()
    code = main(["verify", "--run-root", str(tmp_path / "runs"),
                 "--run-id", f"t12p-{terminal}"])
    assert code == 0, capsys.readouterr().out


def test_format_string_property_unaffected(tmp_path: Path, capsys) -> None:
    """T12 control: label.format values are not precision-governed."""
    original = _project(tmp_path)
    plan = _plan("label.format", "format", "#,0%", obj="labels")
    plan_path = _write_plan(tmp_path, "plan.json", plan)
    code = main(["validate-plan", str(plan_path),
                 "--original", str(original),
                 "--candidate-root", str(tmp_path / "cand"),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "t12f"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "precision_value_invalid" not in out
