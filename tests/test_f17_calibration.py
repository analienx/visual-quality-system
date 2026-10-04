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

import pytest

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
        json.dumps({"displayName": "Overview", "width": width,
                    "height": height}),
        encoding="utf-8")
    return report


def _renders(report: Path, root: Path, width: int = 500,
             height: int = 500, calibration: dict | None = None) -> Path:
    from vqs.pbir import source_digest
    renders = root / "renders"
    renders.mkdir()
    _write_png(renders / "p1.png", width, height)
    sha = hashlib.sha256((renders / "p1.png").read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha},
         "calibration": calibration or CALIBRATION,
         "data_readiness": READINESS}),
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

def _multi_report(root: Path) -> Path:
    """Two pages with different source canvases."""
    report = root / "Example.Report"
    pages = {"p1": (1280, 720), "p2": (800, 600)}
    (report / "definition" / "pages").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1", "p2"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"version": "1.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/1.0.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    for pid, (width, height) in pages.items():
        page_dir = report / "definition" / "pages" / pid
        page_dir.mkdir(parents=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": pid, "width": width, "height": height}),
            encoding="utf-8")
    return report


def _multi_renders(report: Path, root: Path, pngs: dict, calibration: dict) -> Path:
    from vqs.pbir import source_digest
    renders = root / "renders"
    renders.mkdir()
    files = {}
    for pid, (width, height) in pngs.items():
        _write_png(renders / f"{pid}.png", width, height)
        files[f"{pid}.png"] = hashlib.sha256(
            (renders / f"{pid}.png").read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {pid: f"{pid}.png" for pid in pngs},
         "files": files, "calibration": calibration,
         "data_readiness": READINESS}), encoding="utf-8")
    return renders


def test_f17_mixed_page_sizes_refuse_single_calibration(tmp_path: Path) -> None:
    """Mixed canvases cannot honestly share one global calibration."""
    report = _multi_report(tmp_path)
    renders = _multi_renders(report, tmp_path,
                             {"p1": (1280, 720), "p2": (800, 600)},
                             {"canvas_width": 1280, "canvas_height": 720,
                              "scale": 1, "viewport": "1280x720@1x",
                              "method": "bridge-screenshot-all"})
    with pytest.raises((ValueError, OSError), match="canvas|Renders incomplete"):
        pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")


def test_f17_full_scale2_capture_verifies(tmp_path: Path) -> None:
    """A true scale-2 capture (pixels == canvas x 2) packs and verifies."""
    report = _report(tmp_path)
    calib = {"canvas_width": 1280, "canvas_height": 720, "scale": 2,
             "viewport": "2560x1440@2x", "method": "bridge-screenshot-all"}
    renders = _renders(report, tmp_path, 2560, 1440, calibration=calib)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    assert verify(str(tmp_path / "b1"), str(report))["status"] == "valid"


def test_f17_partial_scale2_capture_rejected(tmp_path: Path) -> None:
    """x1 pixels on an x2 calibration must not verify."""
    report = _report(tmp_path)
    calib = {"canvas_width": 1280, "canvas_height": 720, "scale": 2,
             "viewport": "2560x1440@2x", "method": "bridge-screenshot-all"}
    renders = _renders(report, tmp_path, 1280, 720, calibration=calib)
    with pytest.raises((ValueError, OSError), match="calibration|canvas|pixels"):
        pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")


def test_f17_verify_rejects_canvas_drift_after_pack(tmp_path: Path) -> None:
    """Verify cross-checks calibration canvas against inventory + pixels."""
    report = _report(tmp_path, 500, 500)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    manifest_path = tmp_path / "b1" / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["calibration"]["canvas_width"] = 1280
    manifest["calibration"]["canvas_height"] = 720
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    header_path = tmp_path / "b1" / "bundle.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["files"]["capture-manifest.json"] = hashlib.sha256(
        manifest_path.read_bytes()).hexdigest()
    header_path.write_text(json.dumps(header), encoding="utf-8")
    with pytest.raises(ValueError, match="canvas"):
        verify(str(tmp_path / "b1"))
