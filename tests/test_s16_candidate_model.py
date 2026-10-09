"""S16: candidate-side model identity through public repair routes.

A byPath model pins at apply; sealed verify rechecks the original
pin and the candidate side. Planting a different model beside the
candidate after sealing fails verification even though both trees
are untouched; a relocated-missing original model blocks the
repair itself. T10: a missing candidate-side model is staged
byte-identically into the disposable project (or blocks when
unresolvable/unsafe), and fails sealed verify afterwards —
unresolved identity is not equivalence.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

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
        # Realistic SemanticModel project: definition/ TMDL plus
        # project metadata, plus an ephemeral .pbi local cache that
        # staging must never import.
        definition = model / "definition"
        tables = definition / "tables"
        tables.mkdir(parents=True)
        (tables / "T.tmdl").write_text(model_text, encoding="utf-8")
        (model / ".platform").write_text(
            json.dumps({"$schema": ("https://developer.microsoft.com/"
                                    "json-schemas/fabric/item/platform/"
                                    "properties/1.0.0/schema.json")}),
            encoding="utf-8")
        (model / "definition.pbism").write_text(
            json.dumps({"version": "1.0"}), encoding="utf-8")
        (model / "diagramLayout.json").write_text(
            json.dumps({"nodes": []}), encoding="utf-8")
        cache = model / ".pbi" / "cache"
        cache.mkdir(parents=True)
        (cache / "localSettings.json").write_text(
            json.dumps({"ephemeral": True}), encoding="utf-8")
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


def test_missing_candidate_model_staged_byte_identical(
        tmp_path: Path, capsys) -> None:
    """T10: an other-parent candidate stages the exact model, then seals.

    The disposable project carries a byte-identical model snapshot at
    the candidate-relative target (same digest as the original), the
    candidate stays resolvable, the deterministic PBIP wrapper is
    recorded in the repairs evidence, and the original is untouched.
    """
    import hashlib

    from vqs.pbir import _hash_model_dir, resolved_model_digest

    original, _model = _project(tmp_path, "table T\n")
    before = tree_digest(original)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    code = _repair_cli(plan_path, original, tmp_path, "s16m-reloc")
    out = capsys.readouterr().out
    assert code == 0, out
    cand = tmp_path / "cand"
    assert cand.is_dir()
    staged = tmp_path / "Model.SemanticModel"
    assert staged.is_dir()
    # Valid project structure preserved; ephemeral .pbi never imported.
    for rel in (".platform", "definition.pbism", "diagramLayout.json",
                "definition/tables/T.tmdl"):
        assert (staged / rel).is_file(), rel
        assert (staged / rel).read_bytes() == (
            tmp_path / "proj" / "Model.SemanticModel" / rel).read_bytes()
    assert not (staged / ".pbi").exists()
    assert (_hash_model_dir(staged)
            == _hash_model_dir(tmp_path / "proj" / "Model.SemanticModel"))
    candidate_digest, _, _ = resolved_model_digest(cand)
    assert candidate_digest is not None
    wrapper = tmp_path / "cand.pbip"
    assert wrapper.is_file()
    doc = json.loads(wrapper.read_text(encoding="utf-8"))
    assert doc["version"] == "1.0"
    assert doc["artifacts"] == [{"report": {"path": "cand"}}]
    repairs = json.loads(
        (tmp_path / "runs" / "s16m-reloc" / "repairs.json").read_text(
            encoding="utf-8"))
    assert repairs["workspace"]["model"]["digest"] == candidate_digest
    assert repairs["workspace"]["wrapper"]["path"] == os.path.realpath(
        wrapper)
    assert repairs["workspace"]["wrapper"]["digest"] == hashlib.sha256(
        wrapper.read_bytes()).hexdigest()
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
    drifted = (tmp_path / "Model.SemanticModel" / "definition"
               / "tables" / "T.tmdl")
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
    tmdl = (tmp_path / "Model.SemanticModel" / "definition"
            / "tables" / "T.tmdl")
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


class _OpenPort:
    """Recording Bridge port with open support; no live Desktop.

    Serves one pre-existing foreign instance, then a freshly opened
    candidate instance per open call (fresh builds lie about
    hasUnsavedChanges, which the run-owned policy tolerates while
    recording it).
    """

    def __init__(self, candidate: Path, foreign: Path,
                 wrapper: Path) -> None:
        self.candidate = os.path.realpath(candidate)
        self.foreign = os.path.realpath(foreign)
        self.wrapper = os.path.realpath(wrapper)
        self.opened: list[str] = []
        self.reloaded: list[int] = []

    def status(self) -> dict:
        instances = [{"pid": 1111,
                      "currentFilePath": str(self.foreign),
                      "reportDir": str(self.foreign),
                      "hasUnsavedChanges": False,
                      "desktopVersion": "2.0-test"}]
        for index in range(len(self.opened)):
            instances.append({"pid": 4300 + index,
                              "currentFilePath": str(self.wrapper),
                              "reportDir": str(self.candidate),
                              "hasUnsavedChanges": True,
                              "desktopVersion": "2.0-test"})
        return {"instances": instances}

    def open(self, report: str, timeout: int = 60) -> None:
        self.opened.append(report)

    def reload(self, pid: int) -> None:
        self.reloaded.append(pid)


def _coordinator_layout_repair(tmp_path: Path, capsys,
                               run_id: str) -> tuple:
    """Repair into the coordinator default workspace: run/candidate."""
    from vqs.pbir import source_digest

    original, _model = _project(tmp_path, "table T\n")
    before = tree_digest(original)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    run_dir = tmp_path / "run"
    cand = run_dir / "candidate"
    code = main(["repair", str(plan_path), "--original", str(original),
                 "--candidate-root", str(cand),
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", run_id])
    assert code == 0, capsys.readouterr().out
    capsys.readouterr()
    return original, cand, before, source_digest(cand)


def test_candidate_project_opens_in_principle(tmp_path: Path, capsys) -> None:
    """The disposable project opens via Bridge and binds a fresh PID.

    Uses the coordinator default workspace (run/candidate): VQS opens
    the generated wrapper (never the original), binds the newly
    observed instance by exact candidate path, and records run
    ownership with the sealed source digest — the lying unsaved flag
    on the fresh instance is recorded, not treated as user edits.
    """
    from vqs.repair.runtime import open_candidate_instance

    original, cand, before, source_sha = _coordinator_layout_repair(
        tmp_path, capsys, "s16m-open")
    run_dir = tmp_path / "run"
    wrapper = run_dir / "candidate.pbip"
    assert wrapper.is_file()
    port = _OpenPort(cand, original, wrapper)
    proof = open_candidate_instance(
        port, str(original), str(cand), source_digest=source_sha,
        run_lease="s16m-open")
    assert port.opened == [os.path.realpath(wrapper)]
    assert proof["owned"] is True
    assert proof["opened_pid"] == 4300
    assert proof["source_digest"] == source_sha
    assert os.path.realpath(proof["candidate"]) == os.path.realpath(cand)
    assert port.reloaded == []
    assert tree_digest(original) == before


def test_candidate_open_refuses_stale_source(tmp_path: Path, capsys) -> None:
    """Opening a drifted candidate refuses before touching Desktop."""
    from vqs.repair.execute import tree_digest as _digest
    from vqs.repair.runtime import BridgeUnavailable, open_candidate_instance

    original, cand, _before, source_sha = _coordinator_layout_repair(
        tmp_path, capsys, "s16m-stale")
    visual = cand / "definition" / "pages" / "P1" / "visuals" / "v1" / (
        "visual.json")
    visual.write_text(visual.read_text(encoding="utf-8") + " ",
                      encoding="utf-8")
    assert _digest(str(cand)) is not None
    port = _OpenPort(cand, original, tmp_path / "run" / "candidate.pbip")
    with pytest.raises(BridgeUnavailable, match="drifted before open"):
        open_candidate_instance(port, str(original), str(cand),
                                source_digest=source_sha,
                                run_lease="s16m-stale")
    assert port.opened == []


def test_promotion_promotes_only_the_report(tmp_path: Path, capsys) -> None:
    """Promotion swaps the verified report; the staged model never ships.

    The original model beside the original report keeps its digest,
    no model copy lands inside the promoted report, and the backup
    preserves the pre-promotion bytes.
    """
    from vqs.pbir import _hash_model_dir
    from vqs.repair.execute import tree_digest as _digest

    original, cand, _before, _source = _coordinator_layout_repair(
        tmp_path, capsys, "s16m-promo")
    proj = original.parent
    model_before = _hash_model_dir(proj / "Model.SemanticModel")
    code = main(["promote", "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s16m-promo",
                 "--owner-approval", "owner: accept staged repair",
                 "--no-desktop-recheck"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert _digest(str(original)) == _digest(str(cand))
    assert _hash_model_dir(proj / "Model.SemanticModel") == model_before
    assert not (original / "Model.SemanticModel").exists()
    assert not (original / "tables").exists()
