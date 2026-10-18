"""R18/R19 RED: pinned model identity and sealed repair verification.

Relocated candidates stage the exact byPath model byte-identically
into the disposable project (or refuse before mutation when the
model is unresolvable, different, or unsafe to represent); sealed
verify must fail on post-repair drift (declared-value tamper,
dual-tree drift, model-only drift, dangling model, changed answers)
while a mtime-only save still passes and the pre-copy pin defeats a
concurrent save during copy. Red pre-R3, green after.
"""
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from vqs.pipeline import repair_candidate, verify_candidate
from vqs.repair import execute as execute_module
from vqs.repair.execute import RepairError, apply_plan
from vqs.repair.regress import verify_candidate as compare

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
VISUAL_REL = "definition/pages/P1/visuals/v1/visual.json"
LEAF = ["visual", "objects", "categoryAxis", 0, "properties",
        "labelPrecision", "expr", "Literal", "Value"]


def _visual(value: str) -> dict:
    return {
        "name": "v1",
        "position": {"x": 0, "y": 0, "width": 100, "height": 100,
                     "z": 1},
        "visual": {
            "visualType": "barChart",
            "objects": {"categoryAxis": [{"properties": {
                "labelPrecision": {"expr": {"Literal": {
                    "Value": value}}}}}]}}}


def _project(root: Path, model_text: str | None) -> tuple[Path, Path]:
    proj = root / "proj"
    report = proj / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    index = {"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}
    (definition / "pages" / "pages.json").write_text(
        json.dumps(index), encoding="utf-8")
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (report / "definition.pbir").write_text(json.dumps(
        {"datasetReference": {"byPath":
                              {"path": "../Model.SemanticModel"}}}),
        encoding="utf-8")
    (report / "definition" / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(
        json.dumps(_visual("2")), encoding="utf-8")
    if model_text is not None:
        tables = proj / "Model.SemanticModel" / "tables"
        tables.mkdir(parents=True)
        (tables / "T.tmdl").write_text(model_text, encoding="utf-8")
    plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "P1", "visual": "v1"},
        "target": "visual", "path": list(LEAF), "value": "3",
        "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}
    (proj / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return proj, report


def _plan(proj: Path) -> dict:
    return json.loads((proj / "plan.json").read_text(encoding="utf-8"))


def _set_value(report: Path, value: str) -> None:
    path = report / VISUAL_REL
    doc = json.loads(path.read_text(encoding="utf-8"))
    node = doc
    for step in LEAF[:-1]:
        node = node[step] if isinstance(node, dict) else node[int(step)]
    node[LEAF[-1]] = value
    path.write_text(json.dumps(doc), encoding="utf-8")


def _sealed(proj: Path, report: Path, root: Path,
            run_id: str) -> dict:
    # T10: same-parent candidate so the byPath model resolves on both
    # sides (missing models stage byte-identical copies; unresolvable
    # ones still block, see s16 tests).
    cand = proj / f"cand-{run_id}"
    envelope = repair_candidate(str(proj / "plan.json"), str(report),
                                str(cand), run_root=str(root / "runs"),
                                run_id=run_id)
    assert envelope["verdict"] == "pass", envelope
    return envelope


def test_same_parent_repair_applies(tmp_path: Path) -> None:
    """Control: an intact same-parent relocation repairs cleanly."""
    proj, report = _project(tmp_path, "table T\n")
    result = apply_plan(_plan(proj), str(report),
                        str(tmp_path / "proj" / "cand"))
    assert result["verdict"] == "applied"


def _guard(original: Path, candidate_root: Path) -> None:
    func = getattr(execute_module, "check_relocation_model", None)
    assert callable(func), "execute.check_relocation_model missing"
    func(str(original), str(candidate_root))


def test_relocation_guard_missing_model(tmp_path: Path) -> None:
    """RED R18: the pre-copy guard refuses a missing model target."""
    _proj, report = _project(tmp_path, "table T\n")
    with pytest.raises(RepairError):
        _guard(report, tmp_path / "elsewhere" / "cand")


def test_relocation_guard_switched_model(tmp_path: Path) -> None:
    """RED R18: the pre-copy guard refuses a different same-name model."""
    _proj, report = _project(tmp_path, "table T\n")
    other = tmp_path / "other"
    tables = other / "Model.SemanticModel" / "tables"
    tables.mkdir(parents=True)
    (tables / "T.tmdl").write_text("table T\n\tmeasure M = 1\n",
                                   encoding="utf-8")
    with pytest.raises(RepairError):
        _guard(report, other / "cand")


def test_relocation_guard_intact_model(tmp_path: Path) -> None:
    """Guard-shape test: intact same-parent relocation must be accepted."""
    _proj, report = _project(tmp_path, "table T\n")
    _guard(report, tmp_path / "proj" / "cand")


def test_missing_model_staged_before_mutation(tmp_path: Path) -> None:
    """Layered R18: other-parent candidate stages the exact model, then applies.

    A resolvable byPath model is snapshotted byte-identically into the
    disposable project (never switched, never the original tree), so the
    candidate stays resolvable; the original is untouched.
    """
    from vqs.pbir import resolved_model_digest
    from vqs.repair.execute import tree_digest

    proj, report = _project(tmp_path, "table T\n")
    before = tree_digest(str(report))
    cand = tmp_path / "elsewhere" / "cand"
    result = apply_plan(_plan(proj), str(report), str(cand))
    assert result["verdict"] == "applied", result
    workspace = result["workspace"]
    assert workspace["model"]["adopted"] is False
    staged = Path(workspace["model"]["copy"])
    assert staged.is_dir() and staged.parent == tmp_path / "elsewhere"
    original_digest, _, _ = resolved_model_digest(report)
    staged_digest, _, _ = resolved_model_digest(cand)
    assert original_digest and staged_digest == original_digest
    assert workspace["wrapper"]["path"].endswith("cand.pbip")
    assert json.loads(Path(workspace["wrapper"]["path"]).read_text(
        encoding="utf-8"))["artifacts"] == [{"report": {"path": "cand"}}]
    assert tree_digest(str(report)) == before
    assert cand.is_dir()


def test_materialize_refusal_rolls_back_staged_workspace(
        tmp_path: Path) -> None:
    """Regression: a materialize failure must drop staged model/wrapper state.

    Staging runs before the copy; when the copy then refuses (the
    candidate root already exists and was never owned by this
    attempt), the staged model copy is removed while the pre-existing
    root is preserved byte-for-byte (F01).
    """
    proj, report = _project(tmp_path, "table T\n")
    elsewhere = tmp_path / "elsewhere"
    cand = elsewhere / "cand"
    cand.mkdir(parents=True)
    sentinel = cand / "sentinel.txt"
    sentinel.write_text("foreign", encoding="utf-8")
    result = apply_plan(_plan(proj), str(report), str(cand))
    assert result["verdict"] == "blocked", result
    assert result["stage"] == "materialize"
    assert sentinel.read_text(encoding="utf-8") == "foreign"
    assert not (elsewhere / "Model.SemanticModel").exists()
    assert list(elsewhere.iterdir()) == [cand]


def test_escaping_model_target_refused_before_any_write(
        tmp_path: Path) -> None:
    """A byPath target escaping the disposable project refuses with no writes.

    The original model resolves fine, but the candidate-relative target
    lands outside the project workspace: staging must refuse the
    traversal and leave neither the escape path nor the candidate root.
    """
    deep = tmp_path / "proj" / "deep"
    report = deep / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    (report / "definition.pbir").write_text(json.dumps(
        {"datasetReference": {"byPath":
                              {"path": "../../Model.SemanticModel"}}}),
        encoding="utf-8")
    (report / "definition" / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(
        json.dumps(_visual("2")), encoding="utf-8")
    tables = tmp_path / "proj" / "Model.SemanticModel" / "tables"
    tables.mkdir(parents=True)
    (tables / "T.tmdl").write_text("table T\n", encoding="utf-8")
    proj = tmp_path / "proj"
    (proj / "plan.json").write_text(json.dumps({
        "operations": [{
            "type": "axis.tick_format",
            "selector": {"page": "P1", "visual": "v1"},
            "target": "visual", "path": list(LEAF), "value": "3",
            "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}), encoding="utf-8")
    cand = tmp_path / "other" / "cand"
    result = apply_plan(json.loads((proj / "plan.json").read_text(
        encoding="utf-8")), str(report), str(cand))
    assert result["verdict"] == "blocked", result
    assert result["stage"] == "workspace"
    assert "escapes the disposable project" in result["reason"]
    assert not cand.exists()
    assert not (tmp_path / "Model.SemanticModel").exists()


def test_switched_model_refused_before_mutation(tmp_path: Path) -> None:
    """Layered R18: same-name/different-model must not mutate (see above)."""
    proj, report = _project(tmp_path, "table T\n")
    other = tmp_path / "other"
    tables = other / "Model.SemanticModel" / "tables"
    tables.mkdir(parents=True)
    (tables / "T.tmdl").write_text("table T\n\tmeasure M = 1\n",
                                   encoding="utf-8")
    cand = other / "cand"
    result = apply_plan(_plan(proj), str(report), str(cand))
    assert result["verdict"] == "blocked"
    assert not cand.exists()


def test_declared_value_tamper_fails(tmp_path: Path) -> None:
    """RED R19: post-repair tamper at a declared path fails verify."""
    proj, report = _project(tmp_path, "table T\n")
    result = apply_plan(_plan(proj), str(report),
                        str(tmp_path / "proj" / "cand"))
    candidate = Path(result["candidate"])
    _set_value(candidate, "9")
    verdict = compare(report, candidate, result["edits"])
    assert verdict["verdict"] == "fail"


def test_dual_tree_drift_fails_sealed(tmp_path: Path) -> None:
    """RED R19: identical drift in both trees defeats raw compare."""
    proj, report = _project(tmp_path, "table T\n")
    envelope = _sealed(proj, report, tmp_path, "r-dual")
    candidate = Path(envelope["evidence"][0]["candidate"])
    _set_value(candidate, "9")
    _set_value(report, "9")
    verdict = verify_candidate(run_root=str(tmp_path / "runs"),
                               run_id="r-dual")
    assert verdict["verdict"] == "fail"


def test_model_only_drift_fails_sealed(tmp_path: Path) -> None:
    """RED R19: a changed model after repair fails sealed verify."""
    proj, report = _project(tmp_path, "table T\n")
    _sealed(proj, report, tmp_path, "r-model")
    with (proj / "Model.SemanticModel" / "tables" / "T.tmdl").open(
            "a", encoding="utf-8") as handle:
        handle.write("\tmeasure M = 1\n")
    verdict = verify_candidate(run_root=str(tmp_path / "runs"),
                               run_id="r-model")
    assert verdict["verdict"] == "fail"


def test_dangling_model_fails_sealed(tmp_path: Path) -> None:
    """RED R18/R19: a deleted candidate model fails sealed verify."""
    proj, report = _project(tmp_path, "table T\n")
    _sealed(proj, report, tmp_path, "r-dangle")
    for child in (proj / "Model.SemanticModel").glob("*"):
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)
    (proj / "Model.SemanticModel").rmdir()
    verdict = verify_candidate(run_root=str(tmp_path / "runs"),
                               run_id="r-dangle")
    assert verdict["verdict"] == "fail"


def test_changed_answers_fail_sealed(tmp_path: Path) -> None:
    """RED R19: drifted answer rows fail sealed verify (new answers arg)."""
    proj, report = _project(tmp_path, "table T\n")
    _sealed(proj, report, tmp_path, "r-answers")
    scope = {"model": "m", "roles": [], "filters": {},
             "period": None, "source_sha256": "s" * 64}
    verdict = verify_candidate(
        run_root=str(tmp_path / "runs"), run_id="r-answers",
        answers={"questions": {"q1": {
            "dax_sha256": "d" * 64, "scope": scope,
            "rows_before": [{"n": 1}], "rows_after": [{"n": 2}],
            "tolerance": None, "ordered": False}}})
    assert verdict["verdict"] == "fail"


def test_concurrent_save_blocks_and_preserves_bytes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T11: a save to an already-copied file refuses; new bytes survive."""
    proj, report = _project(tmp_path, "table T\n")
    real_guard = execute_module._assert_original_pinned
    state = {"ran": False}

    def hooked_guard(original: str, before_digest: str, stage: str) -> None:
        if not state["ran"]:
            state["ran"] = True
            with (report / VISUAL_REL).open("ab") as handle:
                handle.write(b" ")
        return real_guard(original, before_digest, stage)

    monkeypatch.setattr(execute_module, "_assert_original_pinned",
                        hooked_guard)
    result = apply_plan(_plan(proj), str(report),
                        str(tmp_path / "proj" / "cand"))
    assert state["ran"] is True
    assert result["verdict"] == "blocked"
    assert "original changed during copy" in result["reason"]
    assert not (tmp_path / "proj" / "cand").exists()
    assert (report / VISUAL_REL).read_bytes().endswith(b" ")


def test_mtime_only_save_passes(tmp_path: Path) -> None:
    """Control: touching mtimes without content change still passes."""
    proj, report = _project(tmp_path, "table T\n")
    result = apply_plan(_plan(proj), str(report),
                        str(tmp_path / "proj" / "cand"))
    candidate = Path(result["candidate"])
    stamp = time.time()
    for path in list(report.rglob("*")) + list(candidate.rglob("*")):
        if path.is_file():
            os.utime(path, (stamp, stamp))
    verdict = compare(report, candidate, result["edits"])
    assert verdict["verdict"] == "pass"
