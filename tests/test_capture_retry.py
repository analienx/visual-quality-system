"""Partial all-pages captures recover only the missing pages via real CLI contract."""
import json
from pathlib import Path

import pytest

from tests.test_capture import _instance, _make_report, _write_png
from vqs import capture
from vqs.pbir import source_digest


def _two_pages(root: Path) -> Path:
    report = _make_report(root)
    pages = report / "definition" / "pages"
    (pages / "p2").mkdir()
    (pages / "p2" / "page.json").write_text(
        json.dumps({"displayName": "Sales", "width": 1280, "height": 720}),
        encoding="utf-8")
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1", "p2"]}), encoding="utf-8")
    return report


@pytest.mark.parametrize("scenario, expected_calls, expected_status", [
    ("recovers", 1, "captured"),
    ("transient", 2, "failed"),
    ("permanent", 0, "failed"),
    ("wrong-page", 1, "failed"),
])
def test_partial_capture_recovery(tmp_path, monkeypatch, scenario,
                                  expected_calls, expected_status):
    report = _two_pages(tmp_path)
    calls = []
    baseline = source_digest(report)

    def fake_bridge(args, timeout):
        if args[0] == "--version":
            return 0, "1.0.0"
        if args[0] == "status":
            return 0, json.dumps({"status": "ready",
                                  "instances": [_instance(report)]})
        if args[0] == "screenshot-all":
            out = Path(args[args.index("--output-dir") + 1])
            first = out / "Overview.png"
            _write_png(first, 1280, 720)
            return 0, json.dumps({
                "status": "partial", "screenshots": [
                    {"pageId": "p1", "outputPath": str(first)}],
                "failures": [{"pageId": "p2",
                              "error": {"code": "BRIDGE_ERROR",
                                        "message": "snapshot timeout 30s",
                                        "retryAfterMs": 0,
                                        "retryable": scenario != "permanent"}}]})
        assert args[0] == "screenshot"
        assert args[1] == "p2"
        calls.append(args[1])
        target = Path(args[args.index("--output") + 1])
        if scenario in ("recovers", "wrong-page"):
            _write_png(target, 1280, 720)
            page = "p1" if scenario == "wrong-page" else "p2"
            return 0, json.dumps({"status": "ok", "pageId": page})
        return 1, json.dumps({"error": {"code": "BRIDGE_ERROR",
                                       "message": "timeout", "retryable": True}})

    monkeypatch.setattr(capture, "_bridge", fake_bridge)
    monkeypatch.setattr(capture.tempfile, "gettempdir",
                        lambda: str(tmp_path / "leases"))
    output = tmp_path / "render"
    if scenario == "recovers":
        manifest = capture.capture(str(report), str(output), wait_seconds=1)
        assert set(manifest["page_images"]) == {"p1", "p2"}
        assert manifest["source_sha256"] == baseline
        assert (output / "p1.png").exists()
        assert (output / "p2.png").exists()
    else:
        with pytest.raises(OSError, match="p2"):
            capture.capture(str(report), str(output), wait_seconds=1)
        assert not (output / "capture-manifest.json").exists()
        assert (output / "p1.png").exists()
    attempts = json.loads((output / "capture-attempts.json").read_text())
    assert attempts["pages"]["p1"]["status"] == "captured"
    assert attempts["pages"]["p1"]["attempts"] == 1
    assert attempts["pages"]["p2"]["status"] == expected_status
    assert len(calls) == expected_calls
    assert source_digest(report) == baseline
