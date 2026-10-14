"""User-visible regions CLI: real sidecar, source-bound routing, no false PASS."""
from __future__ import annotations

import json

from tests.test_visual_regions import _scene_bundle
from vqs.cli import main


def test_cli_build_then_verify_regions(tmp_path, capsys):
    report, bundle = _scene_bundle(tmp_path)
    output = tmp_path / "regions"
    assert main([
        "regions", "build", str(bundle), str(output),
        "--report", str(report), "--target", "p1/v1", "--padding-px", "9",
    ]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["status"] == "created"
    assert envelope["regions"] == 1
    assert (output / "regions.json").is_file()
    assert main(["regions", "verify", str(bundle), str(output),
                 "--report", str(report)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"


def test_cli_routing_plans_actual_inventory_without_quality_pass(tmp_path, capsys):
    report, bundle = _scene_bundle(tmp_path)
    output = tmp_path / "routing.json"
    assert main(["regions", "plan", str(bundle), str(output),
                 "--report", str(report)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["pages"] == 1
    assert summary["visuals"] == 1
    ledger = json.loads(output.read_text(encoding="utf-8"))
    assert ledger["visual_verdict"] == "not_run"
    assert ledger["page_risks"][0]["signals"][0]["visual_id"] == "v1"
    assert ledger["coverage"]["coverage"][0]["status"] == "planned_not_executed"
    assert main(["regions", "plan", str(bundle), str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_cli_malformed_targets_block_not_make_artifact(tmp_path, capsys):
    _, bundle = _scene_bundle(tmp_path)
    output = tmp_path / "no-region"
    assert main(["regions", "build", str(bundle), str(output),
                 "--target", "../escape"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert not output.exists()
