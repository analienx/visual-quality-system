"""Public CLI/MCP parity for authoring-related fields (WP W02 slice).

Only transports are tested; the coordinator is replaced to guarantee that
schema/routing tests cannot modify a candidate, a live Desktop or a model.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from vqs.mcp.schemas import validate_call
from vqs.mcp.server import _dispatch


@pytest.mark.parametrize("name,kwargs", [
    ("vqs_run", {"run_root": ".runs", "pid": True}),
    ("vqs_run", {"run_root": ".runs", "pid": "91"}),
    ("vqs_run", {"run_root": ".runs", "live_answers": 1}),
    ("vqs_run", {"run_root": ".runs", "authoring_backend": "unreviewed"}),
    ("vqs_repair", {"plan_path": "p", "original": "o", "candidate_root": "c",
                    "authoring_timeout": True}),
    ("vqs_repair", {"plan_path": "p", "original": "o", "candidate_root": "c",
                    "authoring_allow_warnings": "true"}),
])
def test_authoring_schema_refuses_bad_types(name: str, kwargs: dict):
    assert validate_call(name, kwargs)[1] is not None


def test_mcp_run_forwards_all_supported_authoring_arguments(monkeypatch):
    import vqs.coordinator

    observed = {}
    def fake_run(**kwargs):
        observed.update(kwargs)
        return {"tool": "vqs.run", "verdict": "blocked"}

    monkeypatch.setattr(vqs.coordinator, "run_workflow", fake_run)
    arguments = {
        "report_dir": "synthetic.Report", "model_dir": "synthetic.SemanticModel",
        "run_root": ".runs", "run_id": "parity-test",
        "mode": "repair", "scope": "desktop", "pid": 2201,
        "authoring_backend": "microsoft", "live_answers": True,
        "renders_dir": ".runs/renders", "fixer_id": "fixer",
        "candidate_root": ".runs/candidate",
    }
    assert validate_call("vqs_run", arguments)[1] is None
    _dispatch("vqs_run", arguments)
    for key, value in arguments.items():
        assert observed[key] == value


def test_mcp_repair_preserves_microsoft_validation_flags(monkeypatch):
    from vqs import pipeline
    observed = {}

    def fake_repair(plan_path, original, candidate_root, **kwargs):
        observed.update({"plan_path": plan_path, "original": original,
                         "candidate_root": candidate_root, **kwargs})
        return {"tool": "vqs.repair", "verdict": "blocked"}

    monkeypatch.setattr(pipeline, "repair_candidate", fake_repair)
    arguments = {
        "plan_path": "synthetic.json", "original": "sample.Report",
        "candidate_root": "candidate.Report", "run_root": ".runs",
        "authoring_backend": "microsoft",
        "authoring_timeout": 125, "authoring_allow_warnings": False,
    }
    assert validate_call("vqs_repair", arguments)[1] is None
    _dispatch("vqs_repair", arguments)
    for key, value in arguments.items():
        assert observed[key] == value


def test_cli_and_mcp_run_authoring_parity(tmp_path: Path, monkeypatch, capsys):
    import vqs.coordinator
    from vqs.cli import main

    captured = []
    def fake_run(**kwargs):
        captured.append(kwargs)
        return {"tool": "vqs.run", "verdict": "blocked",
                "blocked_reasons": ["deliberate transport-only test"]}

    monkeypatch.setattr(vqs.coordinator, "run_workflow", fake_run)
    common = {
        "report_dir": "synthetic.Report", "model_dir": "model",
        "run_root": str(tmp_path), "mode": "repair", "scope": "desktop",
        "pid": 2201, "authoring_backend": "microsoft",
        "live_answers": True, "renders_dir": str(tmp_path / "renders"),
        "candidate_root": str(tmp_path / "candidate"), "fixer_id": "fixer",
    }
    main(["run", common["report_dir"], "--model", common["model_dir"],
          "--run-root", common["run_root"], "--mode", common["mode"],
          "--scope", common["scope"], "--pid", str(common["pid"]),
          "--authoring-backend", common["authoring_backend"],
          "--live-answers", "--renders-dir", common["renders_dir"],
          "--candidate-root", common["candidate_root"],
          "--fixer-id", common["fixer_id"]])
    capsys.readouterr()
    assert validate_call("vqs_run", common)[1] is None
    _dispatch("vqs_run", common)
    assert len(captured) == 2
    for key in common:
        assert captured[0][key] == captured[1][key], key
