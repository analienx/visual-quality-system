"""S09: actual CLI plan/bundle inputs are sealed, not just the summary.

``vqs validate-plan`` and ``vqs adjudicate-bundle`` persist the
canonical actual input document plus applicable identities as
``input.json`` and bind its digest; changing any material input
while holding the verdict/findings constant changes the binding,
and tampering with the persisted input breaks the seal. The
installed entry point is exercised for the plan route.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.policy import POLICY_VERSION, REQUIRED
from vqs.run_store import verify_seal

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")


def _write(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _plan(**overrides):
    plan = {"operations": [{"type": "palette.assign", "target": "visual.card"}],
            "write_targets": ["theme.json"],
            "rollback": {"restore": "/orig/report"}}
    plan.update(overrides)
    return plan


def _observations():
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
                         "image_sha256": "d" * 64,
                         "pixels": [500, 500],
                         "observations": _observations()}]}
    bundle.update(overrides)
    return bundle


def _seal_of(out: dict) -> tuple[str, Path, dict]:
    run_dir = Path(out["run_dir"])
    stored = json.loads((run_dir / "input.json").read_text(encoding="utf-8"))
    return out["manifest"]["bindings"]["input_sha256"], run_dir, stored


def _run_validate(plan: dict, root: Path, run_id: str,
                 extra: list | None = None) -> list:
    plan_file = _write(root / f"{run_id}.json", plan)
    args = ["validate-plan", plan_file, "--original", "/orig/report",
            "--candidate-root", "/cand", "--run-root", str(root / "runs"),
            "--run-id", run_id]
    args.extend(extra or [])
    return args


def test_approve_flag_changes_binding_same_summary(tmp_path, capsys) -> None:
    """S09: --approve-change is sealed identity, verdict unchanged."""
    plan = _plan()
    args_a = _run_validate(plan, tmp_path, "s09-approve-a",
                           ["--approve-change", "owner-7"])
    assert main(args_a) == 0
    out_a = json.loads(capsys.readouterr().out)
    args_b = _run_validate(plan, tmp_path, "s09-approve-b")
    assert main(args_b) == 0
    out_b = json.loads(capsys.readouterr().out)
    assert out_a["verdict"] == out_b["verdict"] == "pass"
    assert out_a["findings"] == out_b["findings"]
    sha_a, _, stored_a = _seal_of(out_a)
    sha_b, _, stored_b = _seal_of(out_b)
    assert sha_a != sha_b
    assert stored_a["identities"]["approved"] == "owner-7"
    assert stored_b["identities"]["approved"] is None
    assert stored_a["actual"] == stored_b["actual"] == plan


def test_plan_content_changes_binding_same_summary(tmp_path, capsys) -> None:
    """S09: different plan bytes, same pass summary: different binding."""
    args_a = _run_validate(_plan(), tmp_path, "s09-plan-a")
    assert main(args_a) == 0
    out_a = json.loads(capsys.readouterr().out)
    other = _plan(rollback={"restore": "/orig/report-v2"})
    args_b = _run_validate(other, tmp_path, "s09-plan-b")
    assert main(args_b) == 0
    out_b = json.loads(capsys.readouterr().out)
    assert out_a["verdict"] == out_b["verdict"] == "pass"
    assert out_a["findings"] == out_b["findings"]
    sha_a, dir_a, stored_a = _seal_of(out_a)
    sha_b, _, stored_b = _seal_of(out_b)
    assert sha_a != sha_b
    assert stored_a["actual"] == _plan()
    assert stored_b["actual"] == other
    assert verify_seal(dir_a) == []


def test_bundle_fixer_changes_binding_same_summary(tmp_path, capsys) -> None:
    """S09: different reviewer-separation input, same pass: new binding."""
    good_a = _write(tmp_path / "bundle-a.json", _bundle(fixer_id="a"))
    assert main(["adjudicate-bundle", good_a,
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s09-bundle-a"]) == 0
    out_a = json.loads(capsys.readouterr().out)
    good_b = _write(tmp_path / "bundle-b.json", _bundle(fixer_id="c"))
    assert main(["adjudicate-bundle", good_b,
                 "--run-root", str(tmp_path / "runs"),
                 "--run-id", "s09-bundle-b"]) == 0
    out_b = json.loads(capsys.readouterr().out)
    assert out_a["verdict"] == out_b["verdict"] == "pass"
    assert out_a["findings"] == out_b["findings"]
    sha_a, _, stored_a = _seal_of(out_a)
    sha_b, _, stored_b = _seal_of(out_b)
    assert sha_a != sha_b
    assert stored_a["actual"]["fixer_id"] == "a"
    assert stored_b["actual"]["fixer_id"] == "c"


def test_tampered_input_breaks_seal(tmp_path, capsys) -> None:
    """S09: post-seal input.json mutation is detected by verify_seal."""
    args = _run_validate(_plan(), tmp_path, "s09-tamper")
    assert main(args) == 0
    out = json.loads(capsys.readouterr().out)
    _, run_dir, _ = _seal_of(out)
    assert verify_seal(run_dir) == []
    target = run_dir / "input.json"
    raw = bytearray(target.read_bytes())
    raw[10] ^= 0x01
    target.write_bytes(bytes(raw))
    assert verify_seal(run_dir) != []


@needs_vqs
def test_installed_validate_plan_seals_inputs(tmp_path: Path) -> None:
    """S09+C09: the installed route seals actual inputs, not summaries."""
    runs = tmp_path / "runs"
    plan_a = _write(tmp_path / "plan-a.json", _plan())
    first = subprocess.run(
        [VQS_BIN, "validate-plan", plan_a, "--original", "/orig/report",
         "--candidate-root", "/cand", "--run-root", str(runs),
         "--run-id", "s09-inst-a"],
        capture_output=True, text=True, timeout=300, check=False)
    assert first.returncode == 0, first.stderr
    out_a = json.loads(first.stdout)
    plan_b = _write(tmp_path / "plan-b.json",
                    _plan(rollback={"restore": "/orig/report-v2"}))
    second = subprocess.run(
        [VQS_BIN, "validate-plan", plan_b, "--original", "/orig/report",
         "--candidate-root", "/cand", "--run-root", str(runs),
         "--run-id", "s09-inst-b"],
        capture_output=True, text=True, timeout=300, check=False)
    assert second.returncode == 0, second.stderr
    out_b = json.loads(second.stdout)
    assert out_a["verdict"] == out_b["verdict"] == "pass"
    assert out_a["findings"] == out_b["findings"]
    sha_a = out_a["manifest"]["bindings"]["input_sha256"]
    sha_b = out_b["manifest"]["bindings"]["input_sha256"]
    assert sha_a != sha_b
    for out in (out_a, out_b):
        payload = (Path(out["run_dir"]) / "input.json").read_bytes()
        assert hashlib.sha256(payload).hexdigest() == out["manifest"][
            "bindings"]["input_sha256"]
