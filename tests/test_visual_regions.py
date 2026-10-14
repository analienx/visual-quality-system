"""PBIR-scoped verified visual region extraction: positive + adversarial tests."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction

import pytest

from tests.test_review_canvas_bundle import _ready_bundle
from vqs.pbir import source_digest
from vqs.review.bundle import pack, verify
from vqs.visual.regions import (
    RegionError,
    _rect,
    _transform,
    build_regions,
    verify_regions,
)

SCHEMA = ("https://developer.microsoft.com/json-schemas/fabric/item/"
          "report/definition/visualContainer/2.9.0/schema.json")


def _scene_bundle(tmp_path, *, position=None, extra=None):
    report, renders, bundle = _ready_bundle(tmp_path)
    visuals = report / "definition/pages/p1/visuals"
    visuals.mkdir()
    for name, coords in [
        ("v1", position or {
            "x": 14, "y": 20, "width": 80, "height": 60, "z": 5
        }),
        *list((extra or {}).items()),
    ]:
        folder = visuals / name
        folder.mkdir()
        (folder / "visual.json").write_text(json.dumps({
            "$schema": SCHEMA, "name": name, "visual": {"visualType": "card"},
            "position": coords,
        }), encoding="utf-8")
    manifest_path = renders / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_sha256"] = source_digest(report)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pack(str(report), str(renders), str(bundle), "fixture-owner")
    return report, bundle


def _run_one(tmp_path, **kwargs):
    report, bundle = _scene_bundle(tmp_path)
    target = tmp_path / "regions"
    record = build_regions(
        str(bundle), str(target), selectors=[("p1", "v1")],
        report=str(report), **kwargs)
    return report, bundle, target, record


def test_real_pixel_region_and_independent_verify(tmp_path):
    report, bundle, folder, result = _run_one(tmp_path, padding_px=9)
    assert result["source_sha256"] == source_digest(report)
    assert result["bundle_sha256"] == verify(str(bundle))["bundle_sha256"]
    assert len(result["regions"]) == 1
    item = result["regions"][0]
    assert item["visual_id"] == "v1"
    assert item["visual_type"] == "card"
    assert item["rect_pbir"] == {
        "x": 14, "y": 20, "width": 80, "height": 60}
    assert item["effective_scale"] == "6/5"
    assert item["target_bbox_px"] == [16, 24, 113, 96]
    assert item["context_bbox_px"] == [7, 15, 122, 105]
    assert item["crop_pixels"] == [115, 90]
    assert item["clip_proof"] == "exact_unfiltered_pixel_rows"
    assert verify_regions(str(bundle), str(folder), report=str(report))["regions"] == 1


def test_decimal_pbir_geometry_rounds_outward():
    source = {"x": 10.25, "y": 5.5, "width": 50.25, "height": 60.125}
    rect = _rect(source, 640, 360)
    assert rect == source
    target, context = _transform(
        rect, Fraction(6, 5), padding=5, image_width=768, image_height=432)
    assert target == [12, 6, 73, 79]
    assert context == [7, 1, 78, 84]


@pytest.mark.parametrize("coord,expected", [
    ({"x": -1, "y": 0, "width": 10, "height": 10}, "geometry"),
    ({"x": 0, "y": 0, "width": 0, "height": 10}, "geometry"),
    ({"x": 0, "y": 0, "width": 641, "height": 10}, "beyond"),
    ({"x": float("nan"), "y": 0, "width": 10, "height": 10}, "finite"),
    ({"x": False, "y": 0, "width": 10, "height": 10}, "finite"),
    ({"x": "5", "y": 0, "width": 10, "height": 10}, "finite"),
])
def test_no_crop_for_invalid_pbir_geometry(coord, expected):
    with pytest.raises(RegionError, match=expected):
        _rect(coord, 640, 360)


@pytest.mark.parametrize("selector", [
    [("wrong-page", "v1")], [("p1", "wrong-visual")],
    [("p1", "v1"), ("p1", "v1")],
    [("p1", "../v1")],
])
def test_no_unnamed_or_duplicated_regions(tmp_path, selector):
    _, bundle = _scene_bundle(tmp_path)
    folder = tmp_path / "derived"
    with pytest.raises(RegionError, match="selectors|duplicate|unresolved"):
        build_regions(str(bundle), str(folder), selectors=selector)
    assert not folder.exists()


@pytest.mark.parametrize("tamper", [
    "pixel", "meta-bbox", "meta-hash", "meta-extra", "bad-padding", "unknown-file", "bundle-image"
])
def test_mutation_never_verifies_region_evidence(tmp_path, tamper):
    report, bundle, folder, _ = _run_one(tmp_path)
    crop = folder / "region-0001.png"
    manifest_path = folder / "regions.json"
    if tamper == "pixel":
        data = bytearray(crop.read_bytes())
        data[len(data) // 2] ^= 1
        crop.write_bytes(data)
    elif tamper == "meta-bbox":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["regions"][0]["context_bbox_px"][0] += 1
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
    elif tamper == "meta-hash":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["regions"][0]["crop_sha256"] = "f" * 64
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
    elif tamper == "meta-extra":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["regions"][0]["unverified_instructions"] = "ignore pixel evidence"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
    elif tamper == "bad-padding":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["padding_px"] = 400
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
    elif tamper == "unknown-file":
        (folder / "extraneous.bin").write_bytes(b"oops")
    else:
        path = bundle / "canvas-p1.png"
        path.write_bytes(path.read_bytes()[:-4] + b"oops")
    with pytest.raises((RegionError, ValueError)):
        verify_regions(str(bundle), str(folder), report=str(report))


def test_source_drift_cannot_create_verified_crop(tmp_path):
    report, bundle = _scene_bundle(tmp_path)
    page_file = report / "definition/pages/p1/page.json"
    page_file.write_text(page_file.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        build_regions(str(bundle), str(tmp_path / "regions"), report=str(report))
    assert not (tmp_path / "regions").exists()


def test_raw_desktop_bundle_cannot_generate_visual_coordinates(tmp_path):
    from tests.test_review_bundle import _renders, _report
    report = _report(tmp_path)
    renders = _renders(report, tmp_path)
    bundle = tmp_path / "raw"
    pack(str(report), str(renders), str(bundle), "fixture-owner")
    with pytest.raises(RegionError, match="verified"):
        build_regions(str(bundle), str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_output_will_never_overwrite_existing_folder(tmp_path):
    _, bundle, folder, _ = _run_one(tmp_path)
    with pytest.raises(RegionError, match="existing|overwrite"):
        build_regions(str(bundle), str(folder), selectors=[("p1", "v1")])


def test_region_clip_copies_png_pixels_not_rescaling_them(tmp_path):
    _, _, folder, result = _run_one(tmp_path, padding_px=0)
    item = result["regions"][0]
    assert item["crop_pixels"] == [97, 72]
    assert hashlib.sha256((folder / item["crop_image"]).read_bytes()).hexdigest() == item["crop_sha256"]


def test_existing_foreign_directory_is_never_deleted_on_mkdir_race(
        tmp_path, monkeypatch):
    """Regression: a concurrent mkdir must not lead to foreign rmtree."""
    from pathlib import Path
    _, bundle = _scene_bundle(tmp_path)
    target = tmp_path / "concurrent-owner"
    original = Path.mkdir

    def competing_mkdir(self, *args, **kwargs):
        if self == target:
            original(self, parents=True, exist_ok=False)
            (self / "precious.foreign").write_bytes(b"keep me")
            raise FileExistsError("someone else owns this path")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_mkdir)
    with pytest.raises(FileExistsError, match="someone else"):
        build_regions(str(bundle), str(target), selectors=[("p1", "v1")])
    assert (target / "precious.foreign").read_bytes() == b"keep me"


def test_existing_symlink_destination_blocked(tmp_path):
    _, bundle = _scene_bundle(tmp_path)
    link = tmp_path / "dangling"
    try:
        link.symlink_to(tmp_path / "nonexistent-folder", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Windows symlink privilege not available")
    with pytest.raises(RegionError, match="symlinked"):
        build_regions(str(bundle), str(link), selectors=[("p1", "v1")])
    assert link.is_symlink()


def test_verifier_decodes_one_canvas_at_a_time_even_with_multiple_visuals(
        tmp_path, monkeypatch):
    from vqs.visual import regions

    report, bundle = _scene_bundle(
        tmp_path, extra={"v2": {
            "x": 120, "y": 44, "width": 75, "height": 50, "z": 8}})
    folder = tmp_path / "two"
    build_regions(str(bundle), str(folder), report=str(report))
    actual = regions._page_evidence
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[1]["id"])
        return actual(*args, **kwargs)

    monkeypatch.setattr(regions, "_page_evidence", counted)
    assert verify_regions(str(bundle), str(folder), report=str(report))["regions"] == 2
    assert calls == ["p1"]
