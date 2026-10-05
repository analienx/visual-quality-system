"""S12: PNG decode bounds, bundle decode enforcement, RGBA consistency.

Hostile IHDR claims fail before any IDAT body is kept; corruption
(truncation, bad signature, missing IDAT, forged CRC, oversized RAW)
is rejected; unknown ancillary chunks are tolerated; 16-bit stays
rejected while 8-bit RGBA is honored. Bundle verify decodes every
render (not just the container), through the installed CLI as well,
and identical pixels hash identically across RGB/RGBA encodings.
"""
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from vqs.capture import _png_pixels
from vqs.cli import main
from vqs.evidence import decode_png_pixels, pixel_digest
from vqs.review.bundle import unpack

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

BPP = {0: 1, 2: 3, 6: 4}


def _rows(width: int, height: int, channels: int,
          paint) -> list[bytes]:
    return [b"\x00" + b"".join(paint(x, y) for x in range(width))
            for y in range(height)]


def _png(width: int, height: int, *, depth: int = 8, color: int = 2,
         rows: list[bytes] | None = None, extra: list | None = None,
         cut: int | None = None, corrupt_crc: bool = False,
         signature: bool = True, no_idat: bool = False,
         no_iend: bool = False) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0)
    if rows is None:
        sample = b"\x20\x60\xc0\xff"[:BPP[color]]
        rows = [b"\x00" + sample * width for _ in range(height)]
    body_rows = rows
    comp = zlib.compress(b"".join(body_rows))
    chunks = [(b"IHDR", ihdr)] + list(extra or [])
    if not no_idat:
        chunks.append((b"IDAT", comp))
    if not no_iend:
        chunks.append((b"IEND", b""))
    out = [b"\x89PNG\r\n\x1a\n" if signature else b"BAD-SIGN"]
    for tag, body in chunks:
        crc = zlib.crc32(tag + body) & 0xFFFFFFFF
        if corrupt_crc and tag == b"IDAT":
            crc ^= 0x01
        out += [struct.pack(">I", len(body)), tag, body,
                struct.pack(">I", crc)]
    blob = b"".join(out)
    return blob[:cut] if cut is not None else blob


def _write(path: Path, blob: bytes) -> Path:
    path.write_bytes(blob)
    return path


def test_overflow_ihdr_dims_rejected(tmp_path: Path) -> None:
    """S12: a 4G-wide claim fails before any IDAT body is kept."""
    path = _write(tmp_path / "big.png", _png(0xFFFFFFFF, 1, rows=[b""]))
    with pytest.raises(ValueError):
        decode_png_pixels(path)


def test_truncated_stream_rejected(tmp_path: Path) -> None:
    """S12: a stream cut short of IEND is rejected."""
    blob = _png(4, 4)
    path = _write(tmp_path / "cut.png", blob[:len(blob) // 2])
    with pytest.raises(ValueError):
        decode_png_pixels(path)


def test_wrong_signature_rejected(tmp_path: Path) -> None:
    """S12: a non-PNG signature is rejected."""
    path = _write(tmp_path / "sig.png", _png(4, 4, signature=False))
    with pytest.raises(ValueError, match="signature"):
        decode_png_pixels(path)


def test_missing_idat_rejected(tmp_path: Path) -> None:
    """S12: IHDR plus IEND with no pixels is incomplete."""
    path = _write(tmp_path / "noidat.png", _png(4, 4, no_idat=True))
    with pytest.raises(ValueError, match="Incomplete"):
        decode_png_pixels(path)


def test_forged_crc_rejected(tmp_path: Path) -> None:
    """S12: a flipped IDAT byte against a stale CRC is corrupt."""
    path = _write(tmp_path / "crc.png", _png(4, 4, corrupt_crc=True))
    with pytest.raises(ValueError, match="Corrupt"):
        decode_png_pixels(path)


def test_oversized_raw_rejected(tmp_path: Path) -> None:
    """S12: IDAT inflating past the declared size is rejected mid-stream."""
    rows = _rows(2, 3, 3, lambda x, y: b"\x01\x02\x03")
    path = _write(tmp_path / "raw.png", _png(2, 2, rows=rows))
    with pytest.raises(ValueError, match="exceed"):
        decode_png_pixels(path)


def test_oversized_file_refused_before_read(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """S12: a file past the encoded cap fails before any read."""
    import vqs.evidence as evidence_mod

    monkeypatch.setattr(evidence_mod, "_PNG_FILE_CAP", 64)
    path = _write(tmp_path / "fat.png", _png(4, 4))
    with pytest.raises(ValueError, match="exceeds decode cap"):
        decode_png_pixels(path)


def test_trailing_stream_data_rejected(tmp_path: Path) -> None:
    """S12: a second stream fragment after the pixels is not kept."""
    rows = [b"\x00" + b"\x20\x60\xc0" * 2 for _ in range(2)]
    stream = zlib.compress(b"".join(rows))
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    blob = [b"\x89PNG\r\n\x1a\n"]
    chunks = [(b"IHDR", ihdr), (b"IDAT", stream),
              (b"IDAT", stream[:3]), (b"IEND", b"")]
    for tag, body in chunks:
        blob += [struct.pack(">I", len(body)), tag, body,
                 struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)]
    path = _write(tmp_path / "trail.png", b"".join(blob))
    with pytest.raises(ValueError, match="trailing data"):
        decode_png_pixels(path)


def test_unknown_ancillary_tolerated(tmp_path: Path) -> None:
    """S12: an unknown ancillary chunk does not break decoding."""
    extra = [(b"tEXt", b"Title\x00shot")]
    path = _write(tmp_path / "anc.png", _png(4, 4, extra=extra))
    assert decode_png_pixels(path) == (4, 4)


def test_16bit_rejected(tmp_path: Path) -> None:
    """S12: 16-bit samples are rejected, never silently accepted."""
    path = _write(tmp_path / "deep.png", _png(4, 4, depth=16))
    with pytest.raises(ValueError, match="Unsupported"):
        decode_png_pixels(path)


def test_rgba_honored(tmp_path: Path) -> None:
    """S12: 8-bit RGBA decodes with exact dimensions."""
    rows = _rows(4, 4, 4, lambda x, y: b"\x10\x20\x30\xff")
    path = _write(tmp_path / "alpha.png", _png(4, 4, color=6, rows=rows))
    assert decode_png_pixels(path) == (4, 4)


def test_rgb_rgba_consistent(tmp_path: Path) -> None:
    """S12: identical pixels hash identically across RGB/RGBA."""
    def paint(x: int, y: int) -> bytes:
        return bytes(((x * 7) & 0xFF, (y * 11) & 0xFF, 0x40))

    def paint_alpha(x: int, y: int) -> bytes:
        return paint(x, y) + b"\xff"

    rgb = _write(tmp_path / "rgb.png",
                 _png(4, 4, color=2, rows=_rows(4, 4, 3, paint)))
    rgba = _write(tmp_path / "rgba.png",
                  _png(4, 4, color=6, rows=_rows(4, 4, 4, paint_alpha)))
    assert pixel_digest(rgb) == pixel_digest(rgba)


def test_translucent_alpha_distinct(tmp_path: Path) -> None:
    """S12: translucent alpha is not the same picture as opaque."""
    solid = _write(tmp_path / "solid.png",
                   _png(4, 4, color=6,
                        rows=[b"\x00" + b"\x10\x20\x30\xff" * 4
                              for _ in range(4)]))
    clear = _write(tmp_path / "clear.png",
                   _png(4, 4, color=6,
                        rows=[b"\x00" + b"\x10\x20\x30\x00" * 4
                              for _ in range(4)]))
    assert pixel_digest(solid) != pixel_digest(clear)


def test_capture_rejects_forged_crc(tmp_path: Path) -> None:
    """S12: capture blank detection rejects a forged IDAT CRC."""
    path = _write(tmp_path / "crc.png", _png(4, 4, corrupt_crc=True))
    with pytest.raises(ValueError, match="corrupt"):
        _png_pixels(path)


def test_capture_rejects_missing_iend(tmp_path: Path) -> None:
    """S12: capture blank detection rejects a stream without IEND."""
    path = _write(tmp_path / "noiend.png", _png(4, 4, no_iend=True))
    with pytest.raises(ValueError, match="truncated"):
        _png_pixels(path)


CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}
REPORT_JSON = {
    "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/report/3.3.0/schema.json"),
    "layoutOptimization": "None", "themeCollection": {}}


def _report(root: Path) -> Path:
    report = root / "Example.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                    "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(
        json.dumps(REPORT_JSON), encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 500, "height": 500}),
        encoding="utf-8")
    return report


def _bundle_dir(root: Path, png_blob: bytes) -> Path:
    from vqs.pbir import source_digest
    from vqs.review.bundle import pack
    report = _report(root)
    renders = root / "renders"
    renders.mkdir()
    (renders / "p1.png").write_bytes(png_blob)
    sha = hashlib.sha256(png_blob).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha},
         "calibration": CALIBRATION, "data_readiness": READINESS}),
        encoding="utf-8")
    pack(str(report), str(renders), str(root / "b1"), "fixer-1")
    return root / "b1"


def _swap_png(bundle: Path, png_blob: bytes) -> None:
    sha = hashlib.sha256(png_blob).hexdigest()
    (bundle / "p1.png").write_bytes(png_blob)
    manifest_path = bundle / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["p1.png"] = sha
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_sha = hashlib.sha256(
        manifest_path.read_bytes()).hexdigest()
    header_path = bundle / "bundle.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["files"]["p1.png"] = sha
    header["files"]["capture-manifest.json"] = manifest_sha
    header_path.write_text(json.dumps(header), encoding="utf-8")


def _rgba_png() -> bytes:
    return _png(500, 500, color=6,
                rows=[b"\x00" + b"\x20\x60\xc0\xff" * 500
                      for _ in range(500)])


def _deep_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 500, 500, 16, 2, 0, 0, 0)
    comp = zlib.compress(b"\x00" * (500 * (1 + 500 * 6)))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def test_bundle_verify_rejects_16bit_container(tmp_path: Path,
                                              capsys) -> None:
    """S12: a container-valid 16-bit render fails bundle verification."""
    from vqs.evidence import png_size
    bundle = _bundle_dir(tmp_path, _png(500, 500))
    assert png_size(bundle / "p1.png") == (500, 500)
    _swap_png(bundle, _deep_png())
    assert png_size(bundle / "p1.png") == (500, 500)
    code = main(["bundle", "verify", str(bundle)])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "unreadable render dimensions" in out["reason"]


def test_bundle_verify_accepts_rgba(tmp_path: Path, capsys) -> None:
    """S12: an 8-bit RGBA render verifies through the bundle route."""
    bundle = _bundle_dir(tmp_path, _png(500, 500))
    _swap_png(bundle, _rgba_png())
    code = main(["bundle", "verify", str(bundle)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0, out
    assert out["status"] == "valid"


def test_bundle_unpack_rolls_back_undecodable(tmp_path: Path) -> None:
    """S12: unpacking a 16-bit bundle rolls back the destination."""
    bundle = _bundle_dir(tmp_path, _png(500, 500))
    _swap_png(bundle, _deep_png())
    dest = tmp_path / "copy"
    with pytest.raises(OSError, match="rolled back"):
        unpack(str(bundle), str(dest))
    assert not dest.exists()


@needs_vqs
def test_installed_bundle_verify_decodes(tmp_path: Path) -> None:
    """S12+C09: the installed route decodes renders, not just containers."""
    bundle = _bundle_dir(tmp_path, _png(500, 500))
    _swap_png(bundle, _rgba_png())
    good = subprocess.run(
        [VQS_BIN, "bundle", "verify", str(bundle)],
        capture_output=True, text=True, timeout=300, check=False)
    assert good.returncode == 0, good.stderr
    _swap_png(bundle, _deep_png())
    bad = subprocess.run(
        [VQS_BIN, "bundle", "verify", str(bundle)],
        capture_output=True, text=True, timeout=300, check=False)
    assert bad.returncode == 2
    assert "unreadable render dimensions" in bad.stdout
