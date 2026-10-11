"""A validator may not approve bytes that change while it is running."""
from __future__ import annotations

import json
from pathlib import Path

from test_r6_e07_authoring import VISUAL_REL, _project

from vqs.pipeline import repair_candidate
from vqs.powerbi.author.validation_guard import snapshot
from vqs.repair.execute import tree_digest


def test_snapshot_detects_candidate_change(tmp_path):
    from shutil import copytree

    proj, original = _project(tmp_path)
    candidate = proj / "copied"
    copytree(original, candidate)
    pin = tree_digest(original)
    assert snapshot(str(original), str(candidate), pin, pin,
                    {"kind": "absent"})["status"] == "pass"
    target = candidate / VISUAL_REL
    target.write_bytes(target.read_bytes() + b" ")
    assert snapshot(str(original), str(candidate), pin, pin,
                    {"kind": "absent"})["status"] == "blocked"


def test_validator_edit_after_apply_blocks_sealing(tmp_path, monkeypatch):
    from vqs.powerbi.author import adapter

    proj, original = _project(tmp_path)

    def runner(candidate, **kwargs):
        target = Path(candidate) / VISUAL_REL
        target.write_bytes(target.read_bytes() + b" ")
        return {"backend": "direct", "verdict": "pass", "reason": "ok",
                "record": {"backend": "direct", "validation": None, "probe": {}}}

    monkeypatch.setattr(adapter, "run_backend", runner)
    runs = tmp_path / "runs"
    result = repair_candidate(str(proj / "plan.json"), str(original),
        str(proj / "candidate"), run_root=str(runs), run_id="during",
        authoring_backend="direct")
    assert result["verdict"] == "blocked"
    sealed = json.loads((runs / "during" / "authoring.json").read_text())
    assert sealed["validation_snapshot"]["before"]["status"] == "pass"
    assert sealed["validation_snapshot"]["after"]["status"] == "blocked"


def test_model_save_during_validation_invalidates_repair(
        tmp_path, monkeypatch):
    from test_u4_promotion import _project as project_with_model
    from vqs.powerbi.author import adapter

    proj, original = project_with_model(tmp_path, "model-project")

    def model_save(candidate, **kwargs):
        model = proj / "Model.SemanticModel" / "tables" / "T.tmdl"
        model.write_bytes(model.read_bytes() + b"\n")
        return {"backend": "direct", "verdict": "pass", "reason": "ok",
                "record": {"backend": "direct", "validation": None,
                           "probe": {}}}

    monkeypatch.setattr(adapter, "run_backend", model_save)
    runs = tmp_path / "runs"
    result = repair_candidate(str(proj / "plan.json"), str(original),
        str(proj / "candidate"), run_root=str(runs), run_id="model-changed",
        authoring_backend="direct")
    assert result["verdict"] == "blocked"
    record = json.loads((runs / "model-changed" / "authoring.json").read_text())
    assert record["validation_snapshot"]["before"]["status"] == "pass"
    assert record["validation_snapshot"]["after"]["status"] == "blocked"
    assert any("model" in problem for problem in
               record["validation_snapshot"]["after"]["problems"])
