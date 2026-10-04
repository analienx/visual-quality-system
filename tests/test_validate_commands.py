"""validate-plan and adjudicate-bundle: sealed verdicts with honest exits."""
from __future__ import annotations

import json

import pytest

from vqs.cli import main
from vqs.policy import POLICY_VERSION


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _plan(**overrides):
    plan = {"operations": [{"type": "palette.assign", "target": "visual.card"}],
            "write_targets": ["theme.json"],
            "rollback": {"restore": "/orig/report"}}
    plan.update(overrides)
    return plan


def _observations():
    from vqs.policy import REQUIRED
    return [{"id": check, "criterion": check, "status": "pass",
             "reason": "All labels legible at the target size on the fresh render."}
            for check in REQUIRED["report"]]


def _bundle(**overrides):
    bundle = {"source_sha256": "s", "surface": "report", "schema": 1,
              "policy_version": POLICY_VERSION, "fixer_id": "a",
              "reviewer": {"id": "b", "role": "independent_visual_reviewer"},
              "image_capability": {"available": True},
              "calibration": {"canvas_width": 500, "canvas_height": 500,
                              "scale": 1, "viewport": "500x500@1x",
                              "method": "bridge-screenshot-all"},
              "data_readiness": {"populated": True, "method": "scoped-dax-probe",
                                 "checked_at": "2026-10-03T00:00:00Z"},
              "pages": [{"id": "p1", "image_source_sha256": "s",
                         "pixels": [500, 500],
                         "observations": _observations()}]}
    bundle.update(overrides)
    return bundle


def test_validate_plan_pass_seals_completed(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_file = _write(tmp_path / "plan.json", _plan())
    code = main(["validate-plan", plan_file, "--original", "/orig/report",
                 "--candidate-root", "/cand", "--run-id", "vp0"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "pass"
    assert out["manifest"]["status"] == "completed"
    assert (tmp_path / ".vqs-runs" / "vp0" / "manifest.json").is_file()


def test_validate_plan_shell_op_fails(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_file = _write(tmp_path / "evil.json",
                       _plan(operations=[{"type": "shell", "target": "x"}]))
    code = main(["validate-plan", plan_file, "--original", "/orig/report",
                 "--candidate-root", "/cand", "--run-id", "vp1"])
    assert code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "fail"
    assert out["findings"][0]["detail"]["issues"][0]["rule"] == "plan_rejected_shell"


def test_validate_plan_duplicate_run_id_blocks(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_file = _write(tmp_path / "plan.json", _plan())
    args = ["validate-plan", plan_file, "--original", "/orig/report",
            "--candidate-root", "/cand", "--run-id", "vp-dup"]
    assert main(args) == 0
    capsys.readouterr()
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "blocked"


@pytest.mark.parametrize("payload", ["{oops", "[1,2]"])
def test_validate_plan_bad_documents_block(tmp_path, capsys, monkeypatch, payload):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(payload, encoding="utf-8")
    args = ["validate-plan", str(bad), "--original", "/o", "--candidate-root", "/c"]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    args[1] = str(tmp_path / "absent.json")
    assert main(args) == 2


def test_adjudicate_bundle_pass_fail_blocked(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    good = _write(tmp_path / "good.json", _bundle())
    assert main(["adjudicate-bundle", good, "--run-id", "ab0"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    stale_pages = [{"id": "p1", "image_source_sha256": "other",
                    "observations": [{"status": "pass", "criterion": "c",
                                      "reason": "r"}]}]
    stale = _write(tmp_path / "stale.json", _bundle(pages=stale_pages))
    assert main(["adjudicate-bundle", stale, "--run-id", "ab1"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "fail"
    assert out["findings"][0]["check"] == "stale_image"
    assert out["findings"][0]["status"] == "fail"
    nocap = _write(tmp_path / "nocap.json", _bundle(image_capability={}))
    assert main(["adjudicate-bundle", nocap, "--run-id", "ab2"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "blocked"


def test_adjudicate_bundle_bad_documents_block(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert main(["adjudicate-bundle", str(bad)]) == 2
    assert main(["adjudicate-bundle", str(tmp_path / "absent.json")]) == 2
    capsys.readouterr()
    array = tmp_path / "array.json"
    array.write_text("[1,2]", encoding="utf-8")
    assert main(["adjudicate-bundle", str(array)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
