"""Bundle tests: pack/verify/unpack roundtrip plus tamper negatives."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs.cli import main as vqs_main
from vqs.review.bundle import pack, unpack, verify

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


def _report(root: Path) -> Path:
    report = root / "Example.Report"
    (report / "definition" / "pages" / "p1").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                    "report/definition/report/3.3.0/schema.json"),
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 500, "height": 500}),
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
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha},
         "calibration": CALIBRATION, "data_readiness": READINESS}),
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


def test_tampered_inventory_rejected(tmp_path: Path) -> None:
    """Supervisor #22 P1-11: inventory.json is a hashed bundle member."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    inv_path = tmp_path / "b1" / "inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    inv["notes"] = "forged after packing"
    inv_path.write_text(json.dumps(inv), encoding="utf-8")
    with pytest.raises(ValueError, match="tampered.*inventory"):
        verify(str(tmp_path / "b1"))


def test_tampered_capture_metadata_rejected(tmp_path: Path) -> None:
    """Supervisor #22 P1-11: capture metadata is a hashed bundle member."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    meta_path = tmp_path / "b1" / "capture-manifest.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["desktop"] = {"pid": 99999, "note": "forged after packing"}
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="tampered.*capture-manifest"):
        verify(str(tmp_path / "b1"))


def test_dropped_member_hash_rejected(tmp_path: Path) -> None:
    """Review finding: files must cover every fixed member and mapped render."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    header_path = tmp_path / "b1" / "bundle.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    del header["files"]["inventory.json"]
    header_path.write_text(json.dumps(header), encoding="utf-8")
    with pytest.raises(ValueError, match="member hash missing"):
        verify(str(tmp_path / "b1"))


def test_extra_member_rejected(tmp_path: Path) -> None:
    """Supervisor #22 P1-12: bundle membership is allowlisted."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    (tmp_path / "b1" / "notes.txt").write_text("stowaway", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected bundle member"):
        verify(str(tmp_path / "b1"))


def test_symlink_member_rejected(tmp_path: Path) -> None:
    """Supervisor #22 P1-12: symlinks never pass as bundle members."""
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    link = tmp_path / "b1" / "p1-alias.png"
    try:
        link.symlink_to(tmp_path / "b1" / "p1.png")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="symlink|unexpected bundle member"):
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


def test_pack_refuses_renders_without_calibration(tmp_path: Path) -> None:
    import hashlib

    from vqs.pbir import source_digest
    report = _report(tmp_path)
    renders = tmp_path / "renders"
    renders.mkdir()
    _write_png(renders / "p1.png")
    sha = hashlib.sha256((renders / "p1.png").read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"p1": "p1.png"}, "files": {"p1.png": sha}}),
        encoding="utf-8")
    with pytest.raises(ValueError, match="calibration|data_readiness"):
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

def test_missing_source_everywhere_is_value_error(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    bundle = tmp_path / "bundle"
    pack(str(report), str(renders), str(bundle), "fixer-1")
    for name in ("bundle.json", "capture-manifest.json", "inventory.json"):
        path = bundle / name
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.pop("source_sha256", None)
        path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="missing source_sha256"):
        verify(str(bundle))


def test_duplicate_page_ids_rejected(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    bundle = tmp_path / "bundle"
    pack(str(report), str(renders), str(bundle), "fixer-1")
    header_path = bundle / "bundle.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header["pages"] = ["p1", "p1"]
    header_path.write_text(json.dumps(header), encoding="utf-8")
    inv_path = bundle / "inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    inv["pages"] = inv["pages"] + inv["pages"]
    inv_path.write_text(json.dumps(inv), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate page ids"):
        verify(str(bundle))


def test_unpack_rolls_back_failed_verification(tmp_path: Path) -> None:
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    bundle = tmp_path / "bundle"
    pack(str(report), str(renders), str(bundle), "fixer-1")
    with open(bundle / "p1.png", "r+b") as handle:
        handle.seek(100)
        handle.write(b"XX")
    dest = tmp_path / "copy"
    with pytest.raises(OSError, match="rolled back"):
        unpack(str(bundle), str(dest))
    assert not dest.exists()
