"""Capture tests: stubbed Bridge, synthetic report and PNGs, no Desktop."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs import capture
from vqs.cli import main as vqs_main
from vqs.pbir import source_digest


def _forward_filter(rows: list, channels: int, filt: int) -> bytes:
    if filt == 0:
        return b"".join(b"\x00" + row for row in rows)
    out = b""
    prev = bytes(len(rows[0]))
    for row in rows:
        out += bytes([filt])
        filtered = bytearray(row)
        for i in range(len(filtered)):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            upper_left = prev[i - channels] if i >= channels else 0
            if filt == 1:
                sub = left
            elif filt == 2:
                sub = up
            elif filt == 3:
                sub = (left + up) >> 1
            elif filt == 4:
                pick = left + up - upper_left
                dist_left = abs(pick - left)
                dist_up = abs(pick - up)
                dist_corner = abs(pick - upper_left)
                if dist_left <= dist_up and dist_left <= dist_corner:
                    sub = left
                elif dist_up <= dist_corner:
                    sub = up
                else:
                    sub = upper_left
            else:
                sub = 0
            filtered[i] = (filtered[i] - sub) & 0xFF
        out += bytes(filtered)
        prev = bytes(row)
    return out


def _write_png(path: Path, width: int = 500, height: int = 500,
               blank: bool = False, filt: int = 0) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    first = b"\x00\x00\x00" if not blank else b"\x20\x60\xc0"
    plain = [first + b"\x20\x60\xc0" * (width - 1)]
    plain += [b"\x20\x60\xc0" * width for _ in range(height - 1)]
    raw = _forward_filter(plain, 3, filt)
    payload = (b"\x89PNG\r\n\x1a\n"
               + struct.pack(">I", 13) + b"IHDR" + ihdr
               + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
               + struct.pack(">I", len(zlib.compress(raw))) + b"IDAT"
               + zlib.compress(raw)
               + struct.pack(">I", zlib.crc32(b"IDAT" + zlib.compress(raw))
                             & 0xFFFFFFFF)
               + struct.pack(">I", 0) + b"IEND"
               + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF))
    path.write_bytes(payload)


def _make_report(root: Path) -> Path:
    report = root / "Example.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"version": "1.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/1.0.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8")
    return report


def _instance(report: Path, pid: int = 111, unsaved: bool = False) -> dict:
    return {"pid": pid, "bridgeStatus": "connected",
            "currentFilePath": str(report.with_suffix(".pbip")),
            "hasUnsavedChanges": unsaved, "reportDir": str(report),
            "pages": [{"id": "p1"}]}


def _stub(monkeypatch, report, instances, png_pages=("p1",)):
    def fake_bridge(args, timeout):
        if args[0] == "--version":
            return 0, "1.0.0\n"
        if args[0] == "status":
            return 0, json.dumps({"status": "ready",
                                  "instances": instances})
        assert args[0] == "screenshot-all"
        scale_arg = int(args[args.index("--scale") + 1])
        out = Path(args[args.index("--output-dir") + 1])
        shots = []
        for page in png_pages:
            raw = out / f"Display {page}.png"
            page_file = (report / "definition" / "pages" / page
                         / "page.json")
            try:
                dims = json.loads(page_file.read_text(encoding="utf-8"))
                size = (dims["width"] * scale_arg,
                        dims["height"] * scale_arg)
            except (OSError, ValueError, KeyError):
                size = (500, 500)
            _write_png(raw, *size)
            shots.append({"pageId": page, "outputPath": str(raw)})
        return 0, ("Capturing page 1/1" + chr(10) + json.dumps(
            {"status": "ok", "screenshots": shots})
            + chr(10) + "Captured 1 page in 12s")
    monkeypatch.setattr(capture.tempfile, "gettempdir",
                        lambda: str(Path(report).parent / "vqs-leases"))
    monkeypatch.setattr(capture, "_bridge", fake_bridge)

def test_capture_writes_manifest(tmp_path: Path, monkeypatch, capsys) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, [_instance(report)])
    renders = tmp_path / "renders"
    assert vqs_main(["capture", str(report), str(renders)]) == 0
    manifest = json.loads((renders / "capture-manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == source_digest(report)
    assert manifest["page_images"] == {"p1": "p1.png"}
    assert list(manifest["files"]) == ["p1.png"]
    assert json.loads(capsys.readouterr().out)["page_images"] == {"p1": "p1.png"}


def test_bridge_missing_blocks(tmp_path: Path, monkeypatch, capsys) -> None:
    report = _make_report(tmp_path)

    def missing(args, timeout):
        raise FileNotFoundError("powerbi-capture not on PATH")
    monkeypatch.setattr(capture, "_bridge", missing)
    assert vqs_main(["capture", str(report), str(tmp_path / "r")]) == 2
    assert "powerbi-capture" in capsys.readouterr().out


def test_wrong_report_and_unsaved_block(tmp_path: Path, monkeypatch,
                                        capsys) -> None:
    report = _make_report(tmp_path)
    other = _make_report(tmp_path / "other")
    _stub(monkeypatch, other, [_instance(other)])
    assert vqs_main(["capture", str(report), str(tmp_path / "r")]) == 2
    assert "not" in capsys.readouterr().out
    _stub(monkeypatch, report, [_instance(report, unsaved=True)])
    assert vqs_main(["capture", str(report), str(tmp_path / "r2")]) == 2
    assert "unsaved" in capsys.readouterr().out


def test_pid_disambiguates_instances(tmp_path: Path, monkeypatch,
                                     capsys) -> None:
    report = _make_report(tmp_path)
    other = _make_report(tmp_path / "other")
    both = [_instance(other, pid=1), _instance(report, pid=2)]
    _stub(monkeypatch, report, both)
    assert vqs_main(["capture", str(report), str(tmp_path / "r")]) == 2
    assert "--pid" in capsys.readouterr().out
    assert vqs_main(["capture", str(report), str(tmp_path / "r2"),
                     "--pid", "2"]) == 0


def test_missing_png_blocks(tmp_path: Path, monkeypatch, capsys) -> None:
    report = _make_report(tmp_path)
    _stub(monkeypatch, report, [_instance(report)], png_pages=())
    assert vqs_main(["capture", str(report), str(tmp_path / "r")]) == 2
    assert "p1" in capsys.readouterr().out


def test_bridge_timeout_becomes_block(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    monkeypatch.setattr(capture.shutil, "which", lambda name: "bridge")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)
    monkeypatch.setattr(capture.subprocess, "run", timeout)
    with pytest.raises(OSError, match="timed out"):
        capture._bridge(["status"], 1)

def test_shell_fallback_refuses_metachars(monkeypatch) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda _cmd: "C:\\fake\\bridge.cmd")
    calls = []

    def always_missing(*args, **kwargs):
        calls.append(kwargs.get("shell", False))
        raise OSError("not runnable")
    monkeypatch.setattr(capture.subprocess, "run", always_missing)
    with pytest.raises(OSError, match="Refusing shell fallback"):
        capture._bridge(["status", "1&calc"], 5)
    assert calls == [False]


def test_shell_fallback_runs_safe_commands(monkeypatch) -> None:
    import subprocess
    monkeypatch.setattr(capture.shutil, "which", lambda _cmd: "C:\\fake\\bridge.cmd")
    calls = []

    def flaky(cmd, **kwargs):
        calls.append(kwargs.get("shell", False))
        if not kwargs.get("shell"):
            raise OSError("needs a shell")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
    monkeypatch.setattr(capture.subprocess, "run", flaky)
    assert capture._bridge(["status"], 5) == (0, "ok")
    assert calls == [False, True]
