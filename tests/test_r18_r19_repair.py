"""R18/R19 RED: pinned model identity and sealed repair verification.

Relocated candidates must refuse before mutation when the byPath
model is missing or different; sealed verify must fail on
post-repair drift (declared-value tamper, dual-tree drift,
model-only drift, dangling model, changed answers) while a
mtime-only save still passes and the pre-copy pin defeats a
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
from vqs.repair.execute import RepairError, apply_plan, tree_digest
from vqs.repair.regress import verify_candidate as compare

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/1.0.0/schema.json")
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
        json.dumps({"version": "1.0"}), encoding="utf-8")
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
    cand = root / f"cand-{run_id}"
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


def test_missing_model_refused_before_mutation(tmp_path: Path) -> None:
    """Layered R18: other-parent candidate with no model must not mutate.

    (Passes vacuously until the report:3 schema block is fixed, then
    exercises the guard end to end.)
    """
    proj, report = _project(tmp_path, "table T\n")
    cand = tmp_path / "elsewhere" / "cand"
    result = apply_plan(_plan(proj), str(report), str(cand))
    assert result["verdict"] == "blocked"
    assert not cand.exists()


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


def test_concurrent_save_does_not_rebaseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RED R19: a save during copy must not become the baseline."""
    proj, report = _project(tmp_path, "table T\n")
    pre = tree_digest(report)
    real = execute_module.tree_digest
    state = {"done": False}

    def hooked(root: object) -> str:
        if str(root) == str(report) and not state["done"]:
            state["done"] = True
            with (report / VISUAL_REL).open(
                    "ab") as handle:
                handle.write(b" ")
        return real(root)  # type: ignore[arg-type]

    monkeypatch.setattr(execute_module, "tree_digest", hooked)
    result = apply_plan(_plan(proj), str(report),
                        str(tmp_path / "proj" / "cand"))
    assert result["verdict"] == "applied"
    assert result["before"] == pre


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
