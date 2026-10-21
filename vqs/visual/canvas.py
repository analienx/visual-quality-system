"""Measured, optional Desktop screenshot-to-report canvas extraction.

Only supports the observed Power BI Desktop dotted horizontal page boundaries
with a separately proved Filters-pane divider. This is a pixel-evidence parser,
not a heuristic rectangle guess: ambiguous images return an explicit refusal.
All original screenshot bytes are preserved.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..evidence import _decode_png, _unfilter_scanlines, png_size

_SIGNATURE = 48
_PERIOD = 6


class CanvasUnproven(ValueError):
    """A full-report-only crop cannot be established from this screenshot."""


def _pixel(raw: bytes, offset: int, channels: int) -> tuple[int, int, int]:
    if channels == 1:
        return (raw[offset],) * 3
    return tuple(raw[offset:offset + 3])  # type: ignore[return-value]


def _bright(rgb: tuple[int, int, int]) -> bool:
    return min(rgb) >= 245


def _dot(rgb: tuple[int, int, int]) -> bool:
    return max(rgb) <= 150


def _dotted_width(raw: bytes, row: int, width: int,
                  channels: int) -> int | None:
    """Measure a full-width, regular 3px dotted Desktop page outline."""
    stride = width * channels
    start = row * stride

    def matches(x: int) -> bool:
        rgb = _pixel(raw, start + x * channels, channels)
        if x % _PERIOD in (2, 3, 4):
            return _dot(rgb)
        return _bright(rgb)

    if width < 320 or not all(matches(x) for x in range(_SIGNATURE)):
        return None
    # Reject a plain black separator or arbitrary content stroke:
    # the long *periodic* pattern must extend to the actual page edge.
    x = _SIGNATURE
    while x < width and matches(x):
        x += 1
    candidate = x - (x % _PERIOD)
    if candidate < 320 or width - candidate < 40:
        return None
    return candidate


def locate_desktop_canvas(source: Path,
                          canvas: tuple[int, int]) -> dict[str, Any]:
    """Locate an observed report canvas from genuine raw PNG pixels.

    A credible region requires two separate 3-row dotted page edges, a
    repeated full-width dash pattern, exact uniform fit to the known PBIR
    canvas, blank outside page margins, and an independent vertical
    host/sidebar divider. No color/theme of report contents is assumed.
    """
    width, height, channels, png = _decode_png(source)
    raw = _unfilter_scanlines(width, channels, png)
    if channels not in (1, 3, 4):
        raise CanvasUnproven("unsupported screenshot color channels")
    if len(canvas) != 2 or any(
            isinstance(v, bool) or not isinstance(v, int) or v <= 0
            for v in canvas):
        raise CanvasUnproven("invalid PBIR canvas dimensions")
    edges = []
    for y in range(height):
        w = _dotted_width(raw, y, width, channels)
        if w is not None:
            edges.append((y, w))
    groups: list[list[tuple[int, int]]] = []
    for y, w in edges:
        if groups and groups[-1][-1] == (y - 1, w):
            groups[-1].append((y, w))
        else:
            groups.append([(y, w)])
    strong = [g for g in groups if len(g) >= 3]
    if len(strong) != 2 or any(len(g) != 3 for g in strong):
        raise CanvasUnproven(
            "expected exactly two distinct three-row page boundaries")
    top, bottom = strong
    assert top and bottom
    page_width = top[0][1]
    if any(w != page_width for group in strong for _, w in group):
        raise CanvasUnproven("horizontal boundaries have different widths")
    page_top = top[-1][0] + 1
    page_bottom = bottom[0][0]
    page_height = page_bottom - page_top
    if page_top < 12 or height - page_bottom < 12 or page_height < 300:
        raise CanvasUnproven("missing page margin or implausible page height")
    scale_x = Fraction(page_width, canvas[0])
    scale_y = Fraction(page_height, canvas[1])
    if scale_x != scale_y or not Fraction(1, 2) <= scale_x <= 3:
        raise CanvasUnproven(
            f"canvas aspect/scale mismatch: {page_width}x{page_height} "
            f"cannot uniformly map to {canvas[0]}x{canvas[1]}")
    # Verify the page/page-chrome split at multiple vertical positions.
    # The observed Desktop Filters-pane boundary is a single, stable,
    # non-white vertical hairline immediately after the page.
    if width - page_width < 40 or page_width + 2 >= width:
        raise CanvasUnproven("no right-side Desktop region to distinguish")
    samples = [
        page_top // 2, page_top + page_height // 4,
        page_top + page_height // 2, page_top + page_height * 3 // 4,
        page_bottom + (height - page_bottom) // 2,
    ]
    seam = [_pixel(raw, (y * width + page_width + 1) * channels, channels)
            for y in samples]
    if len(set(seam)) != 1 or not all(165 <= v <= 235 for v in seam[0]):
        raise CanvasUnproven("Desktop sidebar divider not independently proved")
    # Across the three dotted rows, the canvas must end *before* the seam;
    # this prevents accepting a crop that keeps the host Filters pane.
    for row in top + bottom:
        y = row[0]
        if not _bright(_pixel(raw, (y * width + page_width) * channels,
                              channels)):
            raise CanvasUnproven("page boundary extends into host pane")
    return {
        "method": "desktop-dotted-page-boundary-v1",
        "status": "measured",
        "raw_pixels": [width, height],
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "crop": [0, page_top, page_width, page_height],
        "source_canvas": list(canvas),
        "effective_scale": str(scale_x),
        "border_top_rows": [v[0] for v in top],
        "border_bottom_rows": [v[0] for v in bottom],
        "host_divider_x": page_width + 1,
        "host_divider_color": list(seam[0]),
        "host_ui_excluded": True,
    }


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))


def crop_canvas(source: Path, target: Path,
                evidence: dict[str, Any]) -> dict[str, Any]:
    """Encode a lossless cropped PNG with provenance, never modify raw."""
    if source.resolve() == target.resolve():
        raise CanvasUnproven("source and output crop must differ")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if evidence.get("source_sha256") != digest:
        raise CanvasUnproven("raw screenshot changed after frame measurement")
    width, height, channels, png = _decode_png(source)
    raw = _unfilter_scanlines(width, channels, png)
    x, y, crop_w, crop_h = evidence["crop"]
    if (not all(isinstance(n, int) for n in (x, y, crop_w, crop_h))
            or min(x, y) < 0 or min(crop_w, crop_h) <= 0
            or x + crop_w > width or y + crop_h > height
            or [width, height] != evidence["raw_pixels"]):
        raise CanvasUnproven("invalid or stale measured crop coordinates")
    row_stride = width * channels
    rows = bytearray()
    for row in range(y, y + crop_h):
        start = row * row_stride + x * channels
        rows.append(0)  # Unfiltered PNG row; no invented resampling.
        rows.extend(raw[start:start + crop_w * channels])
    color = {1: 0, 3: 2, 4: 6}[channels]
    header = struct.pack(">IIBBBBB", crop_w, crop_h, 8, color, 0, 0, 0)
    encoded = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
               + _chunk(b"IDAT", zlib.compress(bytes(rows), 6))
               + _chunk(b"IEND", b""))
    # Write atomically within output directory, avoiding stale/partial output.
    if target.exists() or target.is_symlink():
        raise CanvasUnproven("refusing overwrite of existing canvas image")
    tmp = target.with_suffix(".pending")
    if tmp.exists() or tmp.is_symlink():
        raise CanvasUnproven("stale pending canvas file")
    try:
        tmp.write_bytes(encoded)
        if png_size(tmp) != (crop_w, crop_h):
            raise CanvasUnproven("encoded canvas dimensions differ")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return {
        **evidence,
        "canvas_image": target.name,
        "canvas_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "canvas_pixels": [crop_w, crop_h],
        "pixel_processing": "lossless-PNG-unfiltered-sample-crop",
    }


def extract_report_canvases(renders: Path, pages: list[str],
                           canvas: tuple[int, int] | dict[str, tuple[int, int]]) -> dict[str, Any]:
    """Build private clean page images; partial proofs never become a PASS."""
    results: dict[str, Any] = {}
    for page in pages:
        if (not page or page.startswith(".")
                or any(char in page for char in ("/", "\\", ":"))):
            raise CanvasUnproven("unsafe page filename")
        source = renders / f"{page}.png"
        target = renders / f"canvas-{page}.png"
        try:
            page_canvas = canvas[page] if isinstance(canvas, dict) else canvas
            results[page] = crop_canvas(
                source, target, locate_desktop_canvas(source, page_canvas))
        except (CanvasUnproven, OSError, ValueError, KeyError) as exc:
            results[page] = {
                "status": "blocked", "reason": str(exc),
            }
    status = ("complete" if all(
        v.get("status") == "measured" for v in results.values())
              and len(results) == len(pages) and bool(pages)
              else "blocked")
    proof = {"status": status, "page_count": len(pages), "pages": results}
    (renders / "canvas-evidence.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8")
    return proof
