"""Capture tests: stubbed Bridge, synthetic report and PNGs, no Desktop."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs import desktop
from vqs.cli import main as vqs_main
from vqs.pbir import source_digest


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width for _ in range(height))
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
    (report / "definition" / "pages" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
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
        if args[0] == "status":
            return 0, json.dumps({"status": "ready",
                                  "instances": instances})
        assert args[0] == "screenshot-all"
        out = Path(args[args.index("--output-dir") + 1])
        shots = []
        for page in png_pages:
            raw = out / f"Display {page}.png"
            _write_png(raw)
            shots.append({"pageId": page, "outputPath": str(raw)})
        return 0, ("Capturing page 1/1" + chr(10) + json.dumps(
            {"status": "ok", "screenshots": shots})
            + chr(10) + "Captured 1 page in 12s")
    monkeypatch.setattr(desktop, "_bridge", fake_bridge)

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
        raise FileNotFoundError("powerbi-desktop not on PATH")
    monkeypatch.setattr(desktop, "_bridge", missing)
    assert vqs_main(["capture", str(report), str(tmp_path / "r")]) == 2
    assert "powerbi-desktop" in capsys.readouterr().out


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
    monkeypatch.setattr(desktop.shutil, "which", lambda name: "bridge")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)
    monkeypatch.setattr(desktop.subprocess, "run", timeout)
    with pytest.raises(OSError, match="timed out"):
        desktop._bridge(["status"], 1)
