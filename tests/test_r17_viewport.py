"""R17 RED: measured calibration from the Bridge, never invented flags.

capture records a viewport ONLY from Bridge screenshot-all output;
absent viewport stays absent and blocks downstream honestly.
Production capture runs here with only the Bridge transport faked
(modeling skipped), straight into actual materialized consumers.
"""
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs import capture as capture_module
from vqs.evidence import image_evidence

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
VIEWPORT = "1280x720@1x"


def _png(width: int, height: int) -> bytes:
    rows = []
    for y in range(height):
        color = b"\x10\x20\x30" if y < height // 2 else b"\x40\x50\x60"
        rows.append(b"\x00" + color * width)
    body = zlib.compress(b"".join(rows))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", body) + chunk(b"IEND", b""))


def _report(root: Path) -> Path:
    report = root / "R.Report"
    definition = report / "definition"
    page_dir = definition / "pages" / "P1"
    page_dir.mkdir(parents=True)
    index = {"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}
    (definition / "pages" / "pages.json").write_text(
        json.dumps(index), encoding="utf-8")
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (page_dir / "page.json").write_text(json.dumps({
        "displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    return report


def _fake_bridge(report: Path, viewport: str | None):
    png = _png(1280, 720)

    def _fake(args: list[str], timeout: int) -> tuple[int, str]:
        if args == ["--version"]:
            return 0, "powerbi-desktop bridge 1.0.0"
        if args == ["status"]:
            return 0, json.dumps({"instances": [{
                "pid": 4242, "currentFilePath": str(report),
                "reportDir": str(report), "hasUnsavedChanges": False,
                "desktopVersion": "2.0-test"}]})
        if args[0] == "screenshot-all":
            outdir = Path(args[args.index("--output-dir") + 1])
            shot = outdir / "shot-P1.png"
            shot.write_bytes(png)
            entry: dict = {"pageId": "P1", "outputPath": str(shot)}
            if viewport is not None:
                entry["viewport"] = viewport
            return 0, json.dumps({"screenshots": [entry]})
        return 1, f"unexpected bridge call: {args[:1]}"

    return _fake


def _run_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 viewport: str | None) -> tuple[dict, Path]:
    report = _report(tmp_path)
    monkeypatch.setattr(capture_module, "_bridge",
                        _fake_bridge(report, viewport))
    renders = tmp_path / "renders"
    manifest = capture_module.capture(
        str(report), str(renders), pid=4242, scale=1, wait_seconds=5,
        lease_dir=str(tmp_path / "leases"))
    return manifest, renders


def test_capture_records_bridge_viewport(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch
                                         ) -> None:
    """RED R17: a Bridge-reported viewport lands in calibration."""
    manifest, _ = _run_capture(tmp_path, monkeypatch, VIEWPORT)
    assert manifest["calibration"].get("viewport") == VIEWPORT


def test_capture_without_viewport_blocks_downstream(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Control: viewport-absent producer output blocks honestly."""
    manifest, renders = _run_capture(tmp_path, monkeypatch, None)
    assert "viewport" not in manifest["calibration"]
    _, issues = image_evidence(renders, manifest["source_sha256"],
                               ["P1"], {"P1": (1280, 720)})
    assert any(row.get("rule") == "calibration_invalid"
               for row in issues)


def test_screenshot_map_preserves_viewport() -> None:
    """RED R17: per-shot Bridge viewport survives parsing."""
    output = json.dumps({"screenshots": [
        {"pageId": "P1", "outputPath": "renders/P1.png",
         "viewport": VIEWPORT}]})
    shot = capture_module._screenshot_map(output)["P1"]
    assert shot.get("viewport") == VIEWPORT


def test_capture_manifest_helper_units() -> None:
    """RED R17: manifest assembly is a pure unit-testable helper."""
    try:
        build = capture_module._capture_manifest
    except AttributeError:
        pytest.fail("capture._capture_manifest missing")
    manifest = build(source_sha256="s" * 64,
                     page_images={"P1": "P1.png"},
                     files={"P1.png": "f" * 64},
                     pixels={"P1": [1280, 720]},
                     canvas=(1280, 720), scale=1,
                     bridge_version=[1, 0, 0],
                     desktop={"pid": 4242}, viewport=VIEWPORT)
    assert manifest["calibration"]["viewport"] == VIEWPORT
    bare = build(source_sha256="s" * 64,
                 page_images={"P1": "P1.png"},
                 files={"P1": "f" * 64},
                 pixels={"P1": [1280, 720]},
                 canvas=(1280, 720), scale=1,
                 bridge_version=[1, 0, 0],
                 desktop={"pid": 4242}, viewport=None)
    assert "viewport" not in bare["calibration"]
