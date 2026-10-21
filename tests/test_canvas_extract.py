"""Pixel-backed Desktop canvas extraction: positive and fail-closed adversarial cases."""
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs.evidence import _decode_png, _unfilter_scanlines, png_size
from vqs.visual.canvas import (
    CanvasUnproven,
    crop_canvas,
    extract_report_canvases,
    locate_desktop_canvas,
)


def _chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def _scene(path: Path, *, top=True, bottom=True, seam=True,
           intruder=False, width=900, page_width=768, page_height=432,
           screenshot_height=600, doubled=False):
    """Controlled Desktop host with legacy or observed doubled-DPI dots."""
    top_y = 60
    stroke = 6 if doubled else 3
    period = 12 if doubled else 6
    bottom_y = top_y + stroke + page_height
    data = bytearray()
    for y in range(screenshot_height):
        row = bytearray([255, 255, 255] * width)
        if y == top_y + 120:
            # A report chart retained by the output crop.
            for x in range(25, 180):
                row[3*x:3*x+3] = bytes([12, 75, 170])
        if (top and top_y <= y < top_y + stroke
                or bottom and bottom_y <= y < bottom_y + stroke
                or intruder and top_y+35 <= y < top_y+35+stroke):
            for x in range(page_width):
                phase = x % period
                if (4 <= phase <= 9) if doubled else (phase in (2, 3, 4)):
                    row[3*x:3*x+3] = bytes([75, 85, 99])
        if seam:
            offset = 2 if doubled else 1
            for x in range(page_width + offset, width):
                row[3*x:3*x+3] = (bytes([209, 213, 219])
                                   if x in range(page_width + offset, page_width + offset + stroke // 3)
                                   else bytes([249, 250, 251]))
        data.append(0)
        data.extend(row)
    head = struct.pack(">IIBBBBB", width, screenshot_height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", head)
        + _chunk(b"IDAT", zlib.compress(bytes(data), 6))
        + _chunk(b"IEND", b""))
    return path


def test_measured_crop_preserves_actual_pixel_content(tmp_path):
    src = _scene(tmp_path / "raw.png")
    original_digest = hashlib.sha256(src.read_bytes()).hexdigest()
    frame = locate_desktop_canvas(src, (640, 360))
    assert frame["crop"] == [0, 63, 768, 432]
    assert frame["effective_scale"] == "6/5"
    assert frame["host_divider_x"] == 769
    out = tmp_path / "clean.png"
    proof = crop_canvas(src, out, frame)
    assert proof["status"] == "measured"
    assert png_size(out) == (768, 432)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == original_digest
    w, _, c, data = _decode_png(out)
    pixels = _unfilter_scanlines(w, c, data)
    assert tuple(pixels[(117 * w + 40)*3:(117 * w + 40)*3+3]) == (12, 75, 170)
    # Raw page boundary belongs to Desktop chrome, not the extracted canvas.
    assert tuple(pixels[3*2:3*2+3]) == (255, 255, 255)
    assert out.name == proof["canvas_image"]


@pytest.mark.parametrize("change,problem", [
    ({"bottom": False}, "three-row page boundaries"),
    ({"top": False}, "three-row page boundaries"),
    ({"seam": False}, "sidebar divider"),
    ({"intruder": True}, "three-row page boundaries"),
    ({"page_width": 762}, "aspect/scale mismatch"),
])
def test_ambiguous_or_hostless_raster_refused(tmp_path, change, problem):
    src = _scene(tmp_path / "bad.png", **change)
    with pytest.raises(CanvasUnproven, match=problem):
        locate_desktop_canvas(src, (640, 360))


def test_incorrect_source_canvas_does_not_calibrate(tmp_path):
    src = _scene(tmp_path / "bad.png")
    with pytest.raises(CanvasUnproven, match="aspect/scale mismatch"):
        locate_desktop_canvas(src, (1280, 720 + 8))


def test_frame_changed_between_measure_and_write(tmp_path):
    src = _scene(tmp_path / "raw.png")
    frame = locate_desktop_canvas(src, (640, 360))
    src.write_bytes(src.read_bytes() + b"unexpected")
    with pytest.raises(CanvasUnproven, match="changed"):
        crop_canvas(src, tmp_path / "clean.png", frame)
    assert not (tmp_path / "clean.png").exists()


def test_existing_output_never_overwritten(tmp_path):
    src = _scene(tmp_path / "raw.png")
    frame = locate_desktop_canvas(src, (640, 360))
    output = tmp_path / "clean.png"
    output.write_bytes(b"do not replace")
    with pytest.raises(CanvasUnproven, match="overwrite"):
        crop_canvas(src, output, frame)
    assert output.read_bytes() == b"do not replace"


def test_partial_page_boundaries_cannot_get_complete_evidence(tmp_path):
    good = _scene(tmp_path / "p1.png")
    _scene(tmp_path / "p2.png", bottom=False)
    result = extract_report_canvases(tmp_path, ["p1", "p2"], (640, 360))
    assert result["status"] == "blocked"
    assert result["pages"]["p1"]["status"] == "measured"
    assert result["pages"]["p2"]["status"] == "blocked"
    assert (tmp_path / "canvas-p1.png").exists()
    assert not (tmp_path / "canvas-p2.png").exists()
    assert json.loads((tmp_path / "canvas-evidence.json").read_text())["status"] == "blocked"
    assert png_size(good) == (900, 600)


def test_measured_doubled_dpi_page_crop_and_sidebar(tmp_path):
    """Observed Desktop signature: 6px dots/12px pitch and 2px pane seam."""
    source = _scene(tmp_path / "double.png", doubled=True, width=1800,
                    page_width=1536, page_height=864, screenshot_height=1200)
    frame = locate_desktop_canvas(source, (640, 360))
    assert frame["crop"] == [0, 66, 1536, 864]
    assert frame["effective_scale"] == "12/5"
    assert frame["host_divider_x"] == 1538
    assert frame["border_top_rows"] == list(range(60, 66))
    assert frame["border_bottom_rows"] == list(range(930, 936))
    clean = tmp_path / "report-only.png"
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    crop_canvas(source, clean, frame)
    assert png_size(clean) == (1536, 864)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.parametrize("change,reason", [
    ({"bottom": False}, "three-row page boundaries"),
    ({"seam": False}, "sidebar divider"),
    ({"intruder": True}, "three-row page boundaries"),
    ({"page_width": 1524}, "aspect/scale mismatch"),
])
def test_doubled_dpi_adversarial_host_and_geometry_block(tmp_path, change, reason):
    parameters = {"doubled": True, "width": 1800, "page_width": 1536,
                  "page_height": 864, "screenshot_height": 1200}
    parameters.update(change)
    source = _scene(tmp_path / "bad.png", **parameters)
    with pytest.raises(CanvasUnproven, match=reason):
        locate_desktop_canvas(source, (640, 360))
