"""F17 RED: source canvas must constrain evidence calibration.

pack() forwards only page IDs to image_evidence, which compares PNG
pixels solely to caller calibration. A 1280x720 source page accepts a
500x500 render with 500x500 calibration as valid. Each page's
scale/calibration must tie to its actual source canvas and trusted
capture evidence.

Side-robust: the M3 fix may refuse at pack time, at verify time, or
both. This control fails only while a mismatched bundle both packs
and verifies.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

from vqs.review.bundle import pack, verify

CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width for _ in range(height))
    comp = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _report(root: Path, width: int = 1280, height: int = 720) -> Path:
    report = root / "Example.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": width,
                    "height": height}),
        encoding="utf-8")
    return report


def _renders(report: Path, root: Path, width: int = 500,
             height: int = 500) -> Path:
    from vqs.pbir import source_digest
    renders = root / "renders"
    renders.mkdir()
    _write_png(renders / "p1.png", width, height)
    sha = hashlib.sha256((renders / "p1.png").read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha},
         "calibration": CALIBRATION, "data_readiness": READINESS}),
        encoding="utf-8")
    return renders


def _pack_and_verify(tmp_path: Path) -> tuple[bool, bool]:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    try:
        pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    except (ValueError, OSError, TypeError):
        return False, False
    try:
        result = verify(str(tmp_path / "b1"), str(report))
    except (ValueError, OSError, TypeError):
        return True, False
    return True, result.get("status") == "valid"


def test_f17_small_render_on_large_canvas_rejected(tmp_path: Path) -> None:
    """RED: 500x500 evidence on a 1280x720 source must not verify."""
    packed, verified = _pack_and_verify(tmp_path)
    assert not (packed and verified)
