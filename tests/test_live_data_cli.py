"""Explicit live-data flags reuse the one bound Modeling MCP capture path."""
from pathlib import Path

from vqs import capture as capture_mod
from vqs import cli as cli_mod
from vqs import pipeline as pipeline_mod
from vqs.repair import runtime as runtime_mod


def test_direct_modeling_optin_is_not_environment_only(monkeypatch):
    from vqs.powerbi import modeling

    monkeypatch.delenv("VQS_MODELING_AUTO", raising=False)
    created = []

    class FakeClient:
        def __init__(self, target_pid):
            created.append(target_pid)

    monkeypatch.setattr(modeling, "StdioModelingClient", FakeClient)
    disabled, owned = capture_mod._resolve_modeling(
        None, target_pid=42, live_data=False)
    assert disabled is None and owned is False
    enabled, owned = capture_mod._resolve_modeling(
        None, target_pid=42, live_data=True)
    assert owned is True and isinstance(enabled, FakeClient)
    assert created == [42]


def test_capture_cli_passes_explicit_live_data(monkeypatch, tmp_path, capsys):
    received = []

    def capture(report, renders, pid=None, **kwargs):
        received.append((Path(report), Path(renders), pid, kwargs))
        return {"page_images": {"p1": "p1.png"}}

    monkeypatch.setattr(capture_mod, "capture", capture)
    report = tmp_path / "Report"
    renders = tmp_path / "renders"
    assert cli_mod.main([
        "capture", str(report), str(renders), "--pid", "101",
        "--live-data"]) == 0
    capsys.readouterr()
    assert received[0][2] == 101
    assert received[0][3]["live_data"] is True


def test_verify_runtime_cli_passes_same_live_data_optin(
        monkeypatch, capsys):
    received = []

    def fake_verify_runtime(**kwargs):
        received.append(kwargs)
        return {"verdict": "blocked", "reason": "fixture: no real Desktop"}

    monkeypatch.setattr(pipeline_mod, "verify_runtime",
                        fake_verify_runtime)
    assert cli_mod.main([
        "verify-runtime", "--run-id", "synthetic",
        "--live-data"]) == 2
    capsys.readouterr()
    assert received[0]["live_data"] is True


def test_runtime_capture_wrapper_passes_optin_unchanged(monkeypatch):
    received = []

    def capture(report, renders, **kwargs):
        received.append(kwargs)
        return {"modeling": {"status": "ready"}}

    monkeypatch.setattr(capture_mod, "capture", capture)
    output = runtime_mod.capture_candidate(
        "candidate", "renders", 22, owned=True, live_data=True)
    assert output["modeling"]["status"] == "ready"
    assert received[0]["live_data"] is True
    assert received[0]["owned_candidate"] is True
