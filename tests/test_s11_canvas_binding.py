"""S11: source-canvas binding in capture/request-review/repair consumers.

``request-review`` derives per-page canvases from the report source
(never from the manifest's optional visuals) and addresses pages by
ID; a self-consistent manifest with source-wrong dimensions blocks.
``verify_renders`` refuses to verify without authoritative canvases.
Renamed PNGs resolve through the manifest mapping; scale 1 and 2
canvas fits produce the review template.
"""
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from vqs.cli import main
from vqs.pbir import source_digest
from vqs.repair.regress import verify_renders

FIX = Path(__file__).parent / "powerbi" / "fixtures"
VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

CANVAS = (1280, 720)


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def _png(width: int, height: int) -> bytes:
    rows = []
    for y in range(height):
        color = b"\x10\x20\x30" if y < height // 2 else b"\x40\x50\x60"
        rows.append(b"\x00" + color * width)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows)))
            + _chunk(b"IEND", b""))


def _project(root: Path) -> Path:
    report = root / "mini.Report"
    shutil.copytree(FIX / "mini_report", report)
    return report


def _renders(root: Path, report: Path, png: bytes, name: str = "P1.png",
             canvas: tuple = CANVAS, scale: int = 1) -> Path:
    renders = root / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    (renders / name).write_bytes(png)
    width, height = canvas
    manifest = {
        "source_sha256": source_digest(report),
        "page_images": {"P1": name},
        "files": {name: hashlib.sha256(png).hexdigest()},
        "calibration": {"canvas_width": width, "canvas_height": height,
                        "scale": scale,
                        "viewport": f"{width}x{height}@{scale}x",
                        "method": "bridge-screenshot-all"},
        "data_readiness": {"populated": True,
                           "method": "modeling-mcp:repeat-query"},
    }
    (renders / "capture-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return renders


def _request(report: Path, renders: Path, capsys) -> tuple:
    code = main(["request-review", str(report), str(renders),
                 "--fixer-id", "executor-1"])
    return code, json.loads(capsys.readouterr().out)


def test_wrong_size_blocks_despite_consistent_manifest(tmp_path: Path,
                                                      capsys) -> None:
    """S11: a manifest-consistent 500px render against a 1280 canvas blocks."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(500, 500),
                       canvas=(500, 500), scale=1)
    code, out = _request(report, renders, capsys)
    assert code == 2
    assert out["status"] == "blocked"
    assert any(row.get("rule") == "render_canvas_mismatch"
               for row in out["findings"])


def test_canvas_fit_template_passes(tmp_path: Path, capsys) -> None:
    """S11 positive: source-fit renders yield the review template by page ID."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(*CANVAS))
    code, out = _request(report, renders, capsys)
    assert code == 0, out
    assert out["pages"][0]["id"] == "P1"
    assert out["pages"][0]["image"] == "P1.png"
    assert out["pages"][0]["image_source_sha256"] == source_digest(report)


def test_renamed_png_resolves(tmp_path: Path, capsys) -> None:
    """S11: page-ID mapping works when the filename differs from the ID."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(*CANVAS), name="shot-a.png")
    code, out = _request(report, renders, capsys)
    assert code == 0, out
    assert out["pages"][0]["id"] == "P1"


def test_scale_two_canvas_fit(tmp_path: Path, capsys) -> None:
    """S11: a scale-2 canvas fit validates against source dimensions."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(2560, 1440), scale=2)
    code, out = _request(report, renders, capsys)
    assert code == 0, out
    assert out["pages"][0]["id"] == "P1"
    assert out["pages"][0]["image_source_sha256"] == source_digest(report)


def test_regress_refuses_without_canvases(tmp_path: Path) -> None:
    """S11: verify_renders without authoritative canvases cannot verify."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(*CANVAS))
    verdict = verify_renders(["P1"], [renders],
                             source_digest(report))
    assert verdict["verdict"] == "blocked"
    assert "canvases" in verdict["reason"]


@needs_vqs
def test_installed_request_review_binds_canvas(tmp_path: Path) -> None:
    """S11+C09: the installed route enforces source-canvas binding."""
    report = _project(tmp_path)
    renders = _renders(tmp_path, report, _png(*CANVAS))
    good = subprocess.run(
        [VQS_BIN, "request-review", str(report), str(renders),
         "--fixer-id", "executor-1"],
        capture_output=True, text=True, timeout=300, check=False)
    assert good.returncode == 0, good.stderr
    assert json.loads(good.stdout)["pages"][0]["id"] == "P1"
    small = _renders(tmp_path / "small", report, _png(500, 500),
                     canvas=(500, 500), scale=1)
    bad = subprocess.run(
        [VQS_BIN, "request-review", str(report), str(small),
         "--fixer-id", "executor-1"],
        capture_output=True, text=True, timeout=300, check=False)
    assert bad.returncode == 2
    assert any(row.get("rule") == "render_canvas_mismatch"
               for row in json.loads(bad.stdout)["findings"])
