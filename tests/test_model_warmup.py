"""Disposable Desktop model warm-up precedes authoritative readiness/capture."""
import json
from pathlib import Path

import pytest

from tests.test_capture_gates import FakePort, _make_report, _ready, _stub, _write_png
from vqs import capture as capture_mod


def _with_priming(monkeypatch, report, events, status="ok"):
    _stub(monkeypatch, report, actions={"p1": "ok"})
    underlying = capture_mod._bridge

    def bridge(args, timeout):
        if args[0] == "screenshot":
            events.append("warmup")
            target = Path(args[args.index("--output") + 1])
            if status == "missing":
                return 1, json.dumps({"status": "error"})
            _write_png(target, 1280, 720)
            page_id = "unexpected-page" if status == "wrong-page" else "p1"
            return 0, json.dumps({"status": "ok", "pageId": page_id})
        if args[0] == "screenshot-all":
            events.append("authoritative")
        return underlying(args, timeout)

    monkeypatch.setattr(capture_mod, "_bridge", bridge)


def test_owned_auto_port_warms_then_proves_twice_then_captures(
        tmp_path, monkeypatch):
    report = _make_report(tmp_path)
    events = []
    _with_priming(monkeypatch, report, events)
    original = FakePort([_ready(), _ready()])
    existing_readiness = original.readiness

    def readiness(scope):
        events.append("readiness")
        return existing_readiness(scope)

    original.readiness = readiness
    monkeypatch.setattr(capture_mod, "_resolve_modeling",
                        lambda _modeling, target_pid=None: (
                            original, True))
    manifest = capture_mod.capture(
        str(report), str(tmp_path / "renders"), wait_seconds=1,
        owned_candidate=True)
    assert events == ["warmup", "readiness", "authoritative", "readiness"]
    assert manifest["modeling"]["status"] == "ready"
    assert manifest["data_readiness"]["populated"] is True
    assert manifest["model_warmup"]["evidence"] == (
        "discarded-before-authoritative-capture")
    assert not (tmp_path / "renders" / "warmup.png").exists()
    assert original.closed  # run-owned auto port closes after capture


def test_user_owned_or_explicit_model_port_never_drives_warmup(
        tmp_path, monkeypatch):
    report = _make_report(tmp_path)
    events = []
    _with_priming(monkeypatch, report, events)
    port = FakePort([_ready(), _ready()])
    # User-owned is never driven by a warmup regardless of auto ownership.
    monkeypatch.setattr(capture_mod, "_resolve_modeling",
                        lambda *_args, **_kwargs: (port, True))
    manifest = capture_mod.capture(
        str(report), str(tmp_path / "user-renders"), wait_seconds=1,
        owned_candidate=False)
    assert events == ["authoritative"]
    assert "model_warmup" not in manifest
    # Caller-supplied ports are not warmed either.
    another = FakePort([_ready(), _ready()])
    monkeypatch.setattr(capture_mod, "_resolve_modeling",
                        lambda *_args, **_kwargs: (another, False))
    manifest = capture_mod.capture(
        str(report), str(tmp_path / "explicit-renders"), wait_seconds=1,
        owned_candidate=True, modeling=another)
    assert events == ["authoritative", "authoritative"]
    assert "model_warmup" not in manifest


@pytest.mark.parametrize("failure,reason", [
    ("missing", "warmup screenshot failed"),
    ("wrong-page", "wrong page identity"),
])
def test_invalid_warmup_blocks_without_authenticating_images(
        tmp_path, monkeypatch, failure, reason):
    report = _make_report(tmp_path)
    events = []
    _with_priming(monkeypatch, report, events, failure)
    port = FakePort([_ready(), _ready()])
    monkeypatch.setattr(capture_mod, "_resolve_modeling",
                        lambda *_args, **_kwargs: (port, True))
    renders = tmp_path / "renders"
    with pytest.raises(OSError, match=reason):
        capture_mod.capture(
            str(report), str(renders), wait_seconds=1,
            owned_candidate=True)
    assert events == ["warmup"]
    assert not port.calls
    assert not (renders / "capture-manifest.json").exists()
    assert not (renders / "p1.png").exists()
