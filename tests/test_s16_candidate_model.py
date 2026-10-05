"""S16: candidate-side model identity through public repair routes.

A byPath model pins at apply; sealed verify rechecks the original
pin and the candidate side. Planting a different model beside the
candidate after sealing fails verification even though both trees
are untouched; a relocated-missing original model blocks the
repair itself. T10: a missing candidate-side model also blocks
repair before mutation, and fails sealed verify afterwards —
unresolved identity is not equivalence.
"""
import json
import shutil
from pathlib import Path

from vqs.cli import main
from vqs.repair.execute import tree_digest

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
SCHEMA_VERSION = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                  "report/definition/versionMetadata/1.0.0/schema.json")
VISUAL = "definition/pages/P1/visuals/v1/visual.json"
LEAF = ["visual", "objects", "categoryAxis", 0, "properties",
        "labelPrecision", "expr", "Literal", "Value"]


def _project(root: Path, model_text: str | None) -> tuple[Path, Path]:
    proj = root / "proj"
    report = proj / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    (definition / "pages" / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
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
        "visual": {"visualType": "barChart", "objects": {"categoryAxis": [{
            "properties": {"labelPrecision": {"expr": {"Literal": {
                "Value": "2"}}}}}]}}}), encoding="utf-8")
    (report / "definition.pbir").write_text(json.dumps(
        {"datasetReference": {"byPath":
                              {"path": "../Model.SemanticModel"}}}),
        encoding="utf-8")
    model = proj / "Model.SemanticModel"
    if model_text is not None:
        tables = model / "tables"
        tables.mkdir(parents=True)
        (tables / "T.tmdl").write_text(model_text, encoding="utf-8")
    return report, model


def _plan() -> dict:
    return {"operations": [{
        "type": "axis.tick_format", "target": "visual",
        "selector": {"page": "P1", "visual": "v1"},
        "path": LEAF, "value": "3", "writes": [VISUAL]}],
        "write_targets": [VISUAL],
        "rollback": "re-materialize from original"}


def _repair_cli(plan_path: Path, original: Path, root: Path,
                run_id: str, cand: Path | None = None) -> tuple:
    target = cand if cand is not None else root / "cand"
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(target),
                 "--run-root", str(root / "runs"),
                 "--run-id", run_id])
    return code


def _mirror_model(proj: Path, root: Path) -> Path:
    """Copy the project model beside an other-parent candidate root.

    The separate but initially identical model satisfies relocation
    by digest, so post-seal deletion/drift/unreadability exercises
    the candidate side alone.
    """
    mirror = root / "Model.SemanticModel"
    shutil.copytree(proj / "Model.SemanticModel", mirror)
    return mirror


def _sealed(root: Path, run_id: str, capsys) -> tuple:
    code = main(["verify", "--run-root", str(root / "runs"),
                 "--run-id", run_id])
    return code, capsys.readouterr().out


def test_model_backed_repair_verifies(tmp_path: Path, capsys) -> None:
    """S16: a pinned byPath model seals and verifies cleanly."""
    original, _model = _project(tmp_path, "table T\n")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    cand = original.parent / "cand"
    assert _repair_cli(plan_path, original, tmp_path, "s16m-ok",
                       cand=cand) == 0
    capsys.readouterr()
    code, out = _sealed(tmp_path, "s16m-ok", capsys)
    assert code == 0, out
    assert json.loads(out)["verdict"] == "pass"


def test_missing_candidate_model_blocks_repair(
        tmp_path: Path, capsys) -> None:
    """T10: an other-parent candidate without a model blocks pre-write."""
    original, _model = _project(tmp_path, "table T\n")
    before = tree_digest(original)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    code = _repair_cli(plan_path, original, tmp_path, "s16m-reloc")
    out = capsys.readouterr().out
    assert code == 2, out
    assert "relocated candidate model missing" in out
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before


def test_planted_candidate_model_fails_verify(
        tmp_path: Path, capsys) -> None:
    """S16: a drifted candidate-side model fails a sealed verify."""
    original, _model = _project(tmp_path, "table T\n")
    proj = original.parent
    _mirror_model(proj, tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    assert _repair_cli(plan_path, original, tmp_path, "s16m-drift") == 0
    capsys.readouterr()
    drifted = tmp_path / "Model.SemanticModel" / "tables" / "T.tmdl"
    drifted.write_text("table Evil\n", encoding="utf-8")
    code, out = _sealed(tmp_path, "s16m-drift", capsys)
    assert code == 1, out
    assert "sealed_candidate_model_mismatch" in out


def test_deleted_candidate_model_fails_verify(
        tmp_path: Path, capsys) -> None:
    """T10: deleting the separate candidate model fails sealed verify."""
    original, _model = _project(tmp_path, "table T\n")
    proj = original.parent
    _mirror_model(proj, tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    assert _repair_cli(plan_path, original, tmp_path, "s16m-del") == 0
    capsys.readouterr()
    shutil.rmtree(tmp_path / "Model.SemanticModel", ignore_errors=True)
    code, out = _sealed(tmp_path, "s16m-del", capsys)
    assert code == 1, out
    assert "sealed_candidate_model_missing" in out


def test_unreadable_candidate_model_fails_verify(
        tmp_path: Path, capsys) -> None:
    """T10: a candidate model with no readable TMDL fails sealed verify."""
    original, _model = _project(tmp_path, "table T\n")
    proj = original.parent
    _mirror_model(proj, tmp_path)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    assert _repair_cli(plan_path, original, tmp_path, "s16m-unread") == 0
    capsys.readouterr()
    tmdl = tmp_path / "Model.SemanticModel" / "tables" / "T.tmdl"
    tmdl.unlink()
    tmdl.mkdir()
    code, out = _sealed(tmp_path, "s16m-unread", capsys)
    assert code == 1, out
    assert "sealed_candidate_model_missing" in out


def test_relocated_missing_model_blocks_repair(
        tmp_path: Path, capsys) -> None:
    """S16: an unresolvable original model blocks before any write."""
    original, _model = _project(tmp_path, None)
    before = tree_digest(original)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    code = _repair_cli(plan_path, original, tmp_path, "s16m-missing")
    out = capsys.readouterr().out
    assert code == 2, out
    assert "original model unresolvable" in out
    assert not (tmp_path / "cand").exists()
    assert tree_digest(original) == before
