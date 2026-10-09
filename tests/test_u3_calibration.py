"""P0-U3: measured desktop capture calibration, never assumed geometry.

The PNG-to-canvas relation is measured per page from genuinely encoded
PNG bytes (stdlib struct+zlib; the only faked layer is the Bridge
transport, per R17 precedent) and cross-checked against Bridge
viewport evidence through production capture(), check_calibration(),
and image_evidence(). Genuine full-canvas captures keep passing;
host-DPI dimensions pass only with Bridge proof. The actual Bridge
1.0.0 contract exposes no viewport/DPR metadata, so viewport-less
captures record render identity (exact PID/path/page/source PNG,
enough for whole-page perceptual review) with geometry calibration
honestly blocked — never a refused capture, never an invented
transform.
"""
import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from vqs import capture as capture_module
from vqs.evidence import check_calibration, image_evidence, png_size

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")


def _png_split(width: int, height: int) -> bytes:
    """Genuine 8-bit RGB PNG, left/right halves so decoders break early."""
    left = width // 2
    row = b"\x00" + b"\x10\x20\x30" * left + b"\x40\x50\x60" * (width - left)
    body = zlib.compress(row * height)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", body) + chunk(b"IEND", b""))


def _report(root: Path, pages: dict[str, tuple[int, int]],
            name: str = "U3.Report") -> Path:
    report = root / name
    (report / "definition" / "pages").mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": sorted(pages)}), encoding="utf-8")
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}),
        encoding="utf-8")
    (report / "definition" / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT,
        "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")
    for page_id, (width, height) in pages.items():
        page_dir = report / "definition" / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(
            json.dumps({"displayName": page_id, "width": width,
                        "height": height}), encoding="utf-8")
    return report


def _fake_bridge(report: Path, shots: dict[str, tuple[bytes, str | None]],
                 mutate=None):
    """Bridge transport double: writes genuine PNG bytes, states viewports."""

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
            entries = []
            for page_id, (png, viewport) in shots.items():
                target = outdir / f"shot-{page_id}.png"
                target.write_bytes(png)
                entry: dict = {"pageId": page_id,
                               "outputPath": str(target)}
                if viewport is not None:
                    entry["viewport"] = viewport
                entries.append(entry)
            if mutate is not None:
                mutate()
            return 0, json.dumps({"screenshots": entries})
        return 1, f"unexpected bridge call: {args[:1]}"

    return _fake


def _run_capture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                 pages: dict[str, tuple[int, int]],
                 shots: dict[str, tuple[bytes, str | None]],
                 mutate=None) -> tuple[dict, Path]:
    report = _report(tmp_path, pages)
    monkeypatch.setattr(capture_module, "_bridge",
                        _fake_bridge(report, shots, mutate))
    renders = tmp_path / "renders"
    manifest = capture_module.capture(
        str(report), str(renders), pid=4242, scale=2, wait_seconds=5,
        lease_dir=str(tmp_path / "leases"))
    return manifest, renders


def _calibration_issues(manifest: dict, renders: Path,
                        canvases: dict) -> list:
    _, issues = image_evidence(renders, manifest["source_sha256"],
                               sorted(canvases), canvases)
    return [row for row in issues
            if str(row.get("rule", "")).startswith("calibration")]


def test_measured_host_dpi_capture_passes_with_bridge_proof(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-integer measured scale (2.5x) passes with Bridge DPR proof."""
    pages = {"P1": (320, 240)}
    png = _png_split(800, 600)
    manifest, renders = _run_capture(
        tmp_path, monkeypatch, pages, {"P1": (png, "800x600@2.5x")})
    calibration = manifest["calibration"]
    assert calibration["method"] == "bridge-viewport-measured"
    assert calibration["viewport"] == "800x600@2.5x"
    assert calibration["viewport_device_pixels"] == [800, 600]
    assert calibration["viewport_dpr"] == "5/2"
    assert calibration["effective_scale"] == "5/2"
    assert calibration["png_pixels"] == "800x600"
    assert manifest["files"] == {
        "P1.png": hashlib.sha256(png).hexdigest()}
    assert manifest["desktop"]["bridge_version"] == [1, 0, 0]
    assert manifest["page_images"] == {"P1": "P1.png"}
    assert check_calibration(calibration, [800, 600]) == []
    assert _calibration_issues(manifest, renders, {"P1": (320, 240)}) == []


def test_measured_integer_capture_passes_with_bridge_proof(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Genuine full-canvas capture keeps passing, now via measured path."""
    pages = {"P1": (320, 240)}
    manifest, renders = _run_capture(
        tmp_path, monkeypatch, pages,
        {"P1": (_png_split(640, 480), "640x480@2x")})
    calibration = manifest["calibration"]
    assert calibration["method"] == "bridge-viewport-measured"
    assert calibration["effective_scale"] == "2"
    assert check_calibration(calibration, [640, 480]) == []
    assert _calibration_issues(manifest, renders, {"P1": (320, 240)}) == []


def test_identity_record_without_viewport(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No Bridge viewport: render identity binds, geometry stays blocked."""
    pages = {"P1": (320, 240)}
    manifest, renders = _run_capture(
        tmp_path, monkeypatch, pages, {"P1": (_png_split(640, 480), None)})
    calibration = manifest["calibration"]
    assert calibration["method"] == "bridge-page-identity"
    assert calibration["geometry_calibration"] == "blocked"
    assert calibration["geometry_reason"].startswith("no-bridge-viewport")
    assert calibration["png_pixels"] == "640x480"
    assert manifest["files"] == {
        "P1.png": hashlib.sha256(_png_split(640, 480)).hexdigest()}
    assert manifest["page_images"] == {"P1": "P1.png"}
    assert check_calibration(calibration, [640, 480]) == []
    assert _calibration_issues(manifest, renders, {"P1": (320, 240)}) == []


def test_viewport_device_pixels_mismatch_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bridge attests 800x600 but decodes 640x480: precise block."""
    report = _report(tmp_path, {"P1": (320, 240)})
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(640, 480), "800x600@2.5x")}))
    with pytest.raises(OSError, match="calibration_viewport_pixels_mismatch"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_dpr_mismatch_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uniform 2.5x pixels against a @2x Bridge claim: transform unproven."""
    report = _report(tmp_path, {"P1": (320, 240)})
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(800, 600), "800x600@2x")}))
    with pytest.raises(OSError, match="calibration_dpr_mismatch"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_wrong_aspect_blocks_despite_bridge_attestation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attested device pixels with non-uniform canvas mapping still block."""
    report = _report(tmp_path, {"P1": (320, 240)})
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(780, 600), "780x600@2.5x")}))
    with pytest.raises(OSError, match="calibration_nonuniform_scale"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_malformed_viewport_blocks_not_silent_fallback(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A corrupt Bridge viewport never degrades silently into strict pass."""
    report = _report(tmp_path, {"P1": (320, 240)})
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(640, 480), "soon@big")}))
    with pytest.raises(OSError, match="calibration_viewport_unparseable"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_mixed_viewport_presence_and_shape_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Viewport on one page only, or differing shapes: unproven transform."""
    pages = {"P1": (320, 240), "P2": (320, 240)}
    report = _report(tmp_path, pages)
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(640, 480), "640x480@2x"),
                              "P2": (_png_split(640, 480), None)}))
    with pytest.raises(OSError, match="calibration_viewport_inconsistent"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))
    report2 = _report(tmp_path / "second", pages)
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report2, {"P1": (_png_split(640, 480), "640x480@2x"),
                               "P2": (_png_split(640, 480), "800x600@2.5x")}))
    with pytest.raises(OSError, match="calibration_viewport_inconsistent"):
        capture_module.capture(str(report2), str(tmp_path / "renders2"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_unproven_host_dpi_upscale_binds_identity_not_geometry(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Host-DPI dimensions without Bridge proof: identity binds, no transform."""
    pages = {"P1": (320, 240)}
    manifest, renders = _run_capture(
        tmp_path, monkeypatch, pages, {"P1": (_png_split(800, 600), None)})
    calibration = manifest["calibration"]
    assert calibration["geometry_calibration"] == "blocked"
    assert calibration["png_pixels"] == "800x600"
    assert manifest["page_images"] == {"P1": "P1.png"}
    assert check_calibration(calibration, [800, 600]) == []
    assert _calibration_issues(manifest, renders, {"P1": (320, 240)}) == []


def test_real_like_contoso_identity_without_viewport(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real-like 1280x720 -> 3915x2394 with no viewport: identity, blocked geometry.

    Mirrors the actual Bridge 1.0.0 host (screenshot JSON carries no
    viewport/DPR; the PNG decodes 3915x2394 against a 1280x720 canvas).
    The capture must succeed as page render identity bound by exact
    PID/path/page/source — geometry stays blocked, nothing is
    special-cased, and no coordinate transform is inferred.
    """
    from vqs.evidence import calibration_expected_pixels
    from vqs.pbir import source_digest
    from vqs.review.bundle import pack, verify

    png = _png_split(3915, 2394)
    probe = tmp_path / "probe.png"
    probe.write_bytes(png)
    assert png_size(probe) == (3915, 2394)
    pages = {"P1": (1280, 720)}
    manifest, renders = _run_capture(
        tmp_path, monkeypatch, pages, {"P1": (png, None)})
    calibration = manifest["calibration"]
    assert calibration["method"] == "bridge-page-identity"
    assert calibration["geometry_calibration"] == "blocked"
    assert calibration["png_pixels"] == "3915x2394"
    assert manifest["files"]["P1.png"] == hashlib.sha256(png).hexdigest()
    # Coordinate-dependent evidence stays unproven: no pixel expectation
    # exists, so nothing equates these pixels to canvas coordinates.
    assert calibration_expected_pixels(calibration) is None
    assert _calibration_issues(manifest, renders, {"P1": (1280, 720)}) == []
    manifest["data_readiness"] = {"populated": True,
                                  "method": "u3-test-double"}
    (renders / "capture-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    report = tmp_path / "U3.Report"
    pack(str(report), str(renders), str(tmp_path / "b3915"), "fixer-1")
    authority = verify(str(tmp_path / "b3915"), str(report))
    assert authority["status"] == "valid"
    assert authority["renders"]["P1"]["pixels"] == [3915, 2394]
    assert authority["renders"]["P1"]["sha256"] == hashlib.sha256(
        png).hexdigest()
    assert authority["calibration"]["geometry_calibration"] == "blocked"
    assert source_digest(report) == manifest["source_sha256"]


def test_real_like_contoso_dimensions_refused_precisely(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real-like 1280x720 -> 3915x2394 evidence refuses; never accepted."""
    png = _png_split(3915, 2394)
    probe = tmp_path / "probe.png"
    probe.write_bytes(png)
    assert png_size(probe) == (3915, 2394)
    report = _report(tmp_path, {"P1": (1280, 720)})
    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (png, "3915x2394@3x")}))
    with pytest.raises(OSError, match="calibration_nonuniform_scale"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_stale_source_during_capture_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A report edit mid-capture voids the manifest with real bytes."""
    pages = {"P1": (320, 240)}
    report = _report(tmp_path, pages)

    def _mutate() -> None:
        path = report / "definition" / "report.json"
        path.write_text(path.read_text(encoding="utf-8") + " ",
                        encoding="utf-8")

    monkeypatch.setattr(
        capture_module, "_bridge",
        _fake_bridge(report, {"P1": (_png_split(640, 480), "640x480@2x")},
                     mutate=_mutate))
    with pytest.raises(OSError, match="Report changed during capture"):
        capture_module.capture(str(report), str(tmp_path / "renders"),
                               pid=4242, scale=2, wait_seconds=5,
                               lease_dir=str(tmp_path / "leases"))


def test_two_page_uniform_measured_capture_passes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Uniform measured scale across pages manifests both pages."""
    pages = {"P1": (320, 240), "P2": (320, 240)}
    manifest, _ = _run_capture(
        tmp_path, monkeypatch, pages,
        {"P1": (_png_split(800, 600), "800x600@2.5x"),
         "P2": (_png_split(800, 600), "800x600@2.5x")})
    assert manifest["calibration"]["effective_scale"] == "5/2"
    assert manifest["page_images"] == {"P1": "P1.png", "P2": "P2.png"}


def test_check_calibration_honors_effective_scale() -> None:
    """Pure unit table: measurement governs when recorded, else request."""
    measured = {"canvas_width": 320, "canvas_height": 240, "scale": 2,
                "viewport": "800x600@2.5x", "method": "bridge-viewport-measured",
                "effective_scale": "5/2"}
    assert check_calibration(measured, [800, 600]) == []
    mismatch = check_calibration(measured, [640, 480])
    assert [row["rule"] for row in mismatch] == ["calibration_mismatch"]
    assert mismatch[0]["expected"] == [800, 600]
    legacy = {"canvas_width": 320, "canvas_height": 240, "scale": 2,
              "viewport": "640x480@2x", "method": "bridge-screenshot-all"}
    assert check_calibration(legacy, [640, 480]) == []
    assert check_calibration(legacy, [800, 600])[0]["expected"] == [640, 480]
    for bad in ("soon", "2/0", "-3", "0", "", None, True, 2.5 / 3):
        broken = dict(measured, effective_scale=bad)
        assert check_calibration(broken) == [
            {"rule": "calibration_invalid", "verdict": "blocked"}]
    fractional = dict(measured, effective_scale="1/3")
    assert check_calibration(fractional) == [
        {"rule": "calibration_invalid", "verdict": "blocked"}]


def test_measured_bundle_packs_and_verifies(tmp_path: Path) -> None:
    """Bundle honors recorded effective scale; a swapped render still fails."""
    from vqs.pbir import source_digest
    from vqs.review.bundle import pack, verify

    report = _report(tmp_path, {"P1": (320, 240)})
    renders = tmp_path / "renders"
    renders.mkdir()
    png = _png_split(800, 600)
    (renders / "P1.png").write_bytes(png)
    calibration = {"canvas_width": 320, "canvas_height": 240, "scale": 2,
                   "viewport": "800x600@2.5x",
                   "method": "bridge-viewport-measured",
                   "viewport_device_pixels": [800, 600],
                   "viewport_dpr": "5/2", "effective_scale": "5/2"}
    manifest_path = renders / "capture-manifest.json"
    manifest_path.write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": {"P1": "P1.png"},
         "files": {"P1.png": hashlib.sha256(png).hexdigest()},
         "calibration": calibration,
         "data_readiness": {"populated": True,
                             "method": "scoped-dax-probe"}}),
        encoding="utf-8")
    pack(str(report), str(renders), str(tmp_path / "b1"), "fixer-1")
    assert verify(str(tmp_path / "b1"), str(report))["status"] == "valid"
    swapped = _png_split(640, 480)
    (renders / "P1.png").write_bytes(swapped)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {"P1.png": hashlib.sha256(swapped).hexdigest()}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="calibration_mismatch"):
        pack(str(report), str(renders), str(tmp_path / "b2"), "fixer-1")
