"""Bundle tests: pack/verify/unpack roundtrip plus tamper negatives."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs.cli import main as vqs_main
from vqs.review.bundle import pack, unpack, verify


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width for _ in range(height))
    comp = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _report(root: Path) -> Path:
    report = root / "Example.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8")
    return report


def _renders(report: Path, root: Path) -> Path:
    from vqs.pbir import source_digest
    renders = root / "renders"
    renders.mkdir()
    _write_png(renders / "p1.png")
    import hashlib
    sha = hashlib.sha256((renders / "p1.png").read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha}}),
        encoding="utf-8")
    return renders


def test_roundtrip(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    header = pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    assert header["fixer_id"] == "fixer-1"
    assert header["pages"] == ["p1"]
    result = verify(str(tmp_path / "b1"), str(report))
    assert result["status"] == "valid"
    assert unpack(str(tmp_path / "b1"), str(tmp_path / "b2"))["status"] == "valid"


def test_tampered_render_rejected(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    with open(tmp_path / "b1" / "p1.png", "r+b") as handle:
        handle.seek(100)
        handle.write(b"\x00")
    with pytest.raises(ValueError, match="tampered"):
        verify(str(tmp_path / "b1"))


def test_stale_source_rejected(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    page = report / "definition" / "pages" / "p1" / "page.json"
    page.write_text(page.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        verify(str(tmp_path / "b1"), str(report))


def test_pack_refuses_bad_renders(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = tmp_path / "renders"
    renders.mkdir()
    with pytest.raises((OSError, ValueError)):
        pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")


def test_bundle_cli(tmp_path: Path, capsys) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    bundle = tmp_path / "b1"
    assert vqs_main(["bundle", "pack", str(report), str(renders),
                     str(bundle), "--fixer-id", "f"]) == 0
    assert json.loads(capsys.readouterr().out)["fixer_id"] == "f"
    assert vqs_main(["bundle", "verify", str(bundle),
                     "--report", str(report)]) == 0
    assert vqs_main(["bundle", "unpack", str(bundle),
                     str(tmp_path / "b2")]) == 0
    assert vqs_main(["bundle", "verify", str(tmp_path / "nope")]) == 2
