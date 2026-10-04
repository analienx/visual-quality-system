"""R11/R13 RED: authoritative canvases on every consumer; pixels decoded.

verify_renders and image_evidence require per-page canvases (no
optional bypass), enforce canvas x scale fit with the reviewable
minimum, and decode PNG pixels with bounded work: CRC-correct
but undecodable IDAT (garbage, truncated stream, bad filter)
blocks at every consumer while legal PNGs pass. All red pre-R3.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

from vqs.evidence import image_evidence
from vqs.repair.regress import verify_renders

SOURCE = "e" * 64


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def _png(width: int, height: int, idat_body: bytes | None = None) -> bytes:
    if idat_body is None:
        rows = []
        for y in range(height):
            color = b"\x10\x20\x30" if y < height // 2 else b"\x40\x50\x60"
            rows.append(b"\x00" + color * width)
        idat_body = zlib.compress(b"".join(rows))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", idat_body) + _chunk(b"IEND", b""))


def _garbage_idat() -> bytes:
    return _png(500, 500, b"\x00" * 100)


def _truncated_idat() -> bytes:
    full = zlib.compress(b"".join(
        b"\x00" + b"\x10\x20\x30" * 500 for _ in range(500)))
    return _png(500, 500, full[:len(full) // 2])


def _bad_filter_idat() -> bytes:
    return _png(500, 500, zlib.compress(
        b"\x09" + b"\x10\x20\x30" * 500 + b"".join(
            b"\x00" + b"\x10\x20\x30" * 500 for _ in range(499))))


def _renders(root: Path, png: bytes, calibration: dict | None = None,
         visuals: dict | None = None) -> Path:
    renders = root / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / "P1.png").write_bytes(png)
    manifest = {
        "source_sha256": SOURCE,
        "page_images": {"P1": "P1.png"},
        "files": {"P1.png": hashlib.sha256(png).hexdigest()},
        "calibration": calibration if calibration is not None else {
            "canvas_width": 500, "canvas_height": 500, "scale": 1,
            "viewport": "500x500@1x", "method": "bridge-screenshot-all"},
        "data_readiness": {"populated": True,
                           "method": "modeling-mcp:repeat-query"},
        "visuals": visuals if visuals is not None else {"P1": []},
    }
    (renders / "capture-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return renders


def _blocked(rows: list[dict]) -> bool:
    return any(row.get("verdict") == "blocked" for row in rows)


def test_canvases_required_at_verify_renders(tmp_path: Path) -> None:
    """RED R11: renders without authoritative canvases cannot verify."""
    renders = _renders(tmp_path, _png(500, 500))
    verdict = verify_renders(["P1"], [renders], SOURCE)
    assert verdict["verdict"] == "blocked"


def test_garbage_idat_blocked(tmp_path: Path) -> None:
    """RED R13: CRC-correct non-zlib IDAT blocks the consumer."""
    renders = _renders(tmp_path, _garbage_idat())
    _, issues = image_evidence(renders, SOURCE, ["P1"],
                               {"P1": (500, 500)})
    assert _blocked(issues)
    assert verify_renders(["P1"], [renders], SOURCE,
                          {"P1": (500, 500)})["verdict"] == "blocked"


def test_truncated_idat_blocked(tmp_path: Path) -> None:
    """RED R13: a cut-short zlib stream blocks the consumer."""
    renders = _renders(tmp_path, _truncated_idat())
    _, issues = image_evidence(renders, SOURCE, ["P1"],
                               {"P1": (500, 500)})
    assert _blocked(issues)


def test_bad_filter_blocked(tmp_path: Path) -> None:
    """RED R13: an unknown PNG filter type blocks the consumer."""
    renders = _renders(tmp_path, _bad_filter_idat())
    _, issues = image_evidence(renders, SOURCE, ["P1"],
                               {"P1": (500, 500)})
    assert _blocked(issues)


def test_legal_png_passes(tmp_path: Path) -> None:
    """Control: a decodable canvas-fit PNG verifies end to end."""
    renders = _renders(tmp_path, _png(500, 500))
    pages, issues = image_evidence(renders, SOURCE, ["P1"],
                                   {"P1": (500, 500)})
    assert not _blocked(issues)
    assert [page["id"] for page in pages] == ["P1"]
    assert verify_renders(["P1"], [renders], SOURCE,
                          {"P1": (500, 500)})["verdict"] == "pass"


def test_mismatched_canvas_rejected(tmp_path: Path) -> None:
    """RED R11: a 500px image against a 1280 canvas rejects."""
    renders = _renders(tmp_path, _png(500, 500))
    _, issues = image_evidence(renders, SOURCE, ["P1"],
                               {"P1": (1280, 720)})
    assert _blocked(issues)


def test_missing_visual_inventory_blocks(tmp_path: Path) -> None:
    """RED R11: a page entry without visual inventory blocks."""
    renders = _renders(tmp_path, _png(500, 500), visuals=None)
    (renders / "capture-manifest.json").write_text(json.dumps({
        **json.loads((renders / "capture-manifest.json").read_text(
            encoding="utf-8"))} | {"visuals": {}}), encoding="utf-8")
    _, issues = image_evidence(renders, SOURCE, ["P1"],
                               {"P1": (500, 500)})
    assert any(row.get("rule") == "unknown_visual_context"
               for row in issues)
