"""F03: render verification must inspect materialized evidence.

verify_renders routes each renders dir through evidence.image_evidence
semantics (manifest, file hashes, PNG bytes, calibration, data
readiness, source binding). A page counts as covered only with complete
valid evidence; every adverse control below blocks.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

from vqs.repair.regress import verify_renders

CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "modeling-mcp:repeat-query"}


def _png(width: int, height: int) -> bytes:
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))
    def _chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw))
            + _chunk(b"IEND", b""))


def _renders(root: Path, name: str, digest: str, images: dict,
             *, files: bool = True, png: bool = True,
             calibration: bool = True, readiness: bool = True) -> Path:
    renders = root / name
    renders.mkdir(parents=True)
    hashes = {}
    for filename in images.values():
        if not isinstance(filename, str):
            continue
        if png:
            (renders / filename).write_bytes(_png(500, 500))
            hashes[filename] = hashlib.sha256(
                (renders / filename).read_bytes()).hexdigest()
    manifest: dict = {"source_sha256": digest, "page_images": images}
    if files:
        manifest["files"] = hashes
    if calibration:
        manifest["calibration"] = dict(CALIBRATION)
    if readiness:
        manifest["data_readiness"] = dict(READINESS)
    (renders / "capture-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    return renders


def test_f03_null_filename_blocks(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "d", {"P1": None})
    assert verify_renders(["P1"], [renders], "d")["verdict"] == "blocked"


def test_f03_maps_only_manifest_blocks(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "cand-digest",
                       {"P1": "p1.png", "P2": "p2.png"},
                       files=False, png=False,
                       calibration=False, readiness=False)
    verdict = verify_renders(["P1", "P2"], [renders], "cand-digest")
    assert verdict["verdict"] == "blocked"


def test_f03_missing_files_map_blocks(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "d", {"P1": "P1.png"}, files=False)
    assert verify_renders(["P1"], [renders], "d")["verdict"] == "blocked"


def test_f03_unknown_calibration_blocks(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "d", {"P1": "P1.png"},
                       calibration=False)
    assert verify_renders(["P1"], [renders], "d")["verdict"] == "blocked"


def test_f03_unknown_readiness_blocks(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "d", {"P1": "P1.png"},
                       readiness=False)
    assert verify_renders(["P1"], [renders], "d")["verdict"] == "blocked"


def test_f03_complete_renders_pass(tmp_path: Path) -> None:
    renders = _renders(tmp_path, "r1", "d",
                       {"P1": "P1.png", "P2": "P2.png"})
    verdict = verify_renders(["P1", "P2"], [renders], "d",
                             {"P1": (500, 500), "P2": (500, 500)})
    assert verdict == {"verdict": "pass", "pages": ["P1", "P2"]}
