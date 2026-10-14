"""Canvas-attached review bundles: real pixel proofs, no invented observations."""
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_canvas_extract import _scene
from tests.test_review_bundle import _renders, _report
from vqs.pbir import source_digest
from vqs.review.bundle import pack, unpack, verify
from vqs.review.port import review_bundle
from vqs.visual.canvas import extract_report_canvases


def _ready_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    report = _report(tmp_path)
    page_file = report / "definition/pages/p1/page.json"
    page = json.loads(page_file.read_text())
    page["width"], page["height"] = 640, 360
    page_file.write_text(json.dumps(page), encoding="utf-8")
    renders = _renders(report, tmp_path)
    _scene(renders / "p1.png")
    manifest_path = renders / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["p1.png"] = hashlib.sha256(
        (renders / "p1.png").read_bytes()).hexdigest()
    manifest["source_sha256"] = source_digest(report)
    manifest["calibration"] = {
        "canvas_width": 640, "canvas_height": 360,
        "scale": 1, "method": "bridge-page-identity",
        "geometry_calibration": "blocked",
        "geometry_reason": "synthetic screenshot has no Bridge viewport"}
    proof = extract_report_canvases(renders, ["p1"], (640, 360))
    assert proof["status"] == "complete"
    manifest["canvas_review"] = {
        "status": "complete", "method": "desktop-dotted-page-boundary-v1",
        "proof_file": "canvas-evidence.json",
        "page_images": {"p1": "canvas-p1.png"},
        "files": {"canvas-p1.png": proof["pages"]["p1"]["canvas_sha256"]},
        "pixels": {"p1": [768, 432]},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    bundle = tmp_path / "bundle"
    return report, renders, bundle


def test_review_bundle_contains_verified_raw_and_clean_images(tmp_path):
    report, renders, bundle = _ready_bundle(tmp_path)
    pack(str(report), str(renders), str(bundle), "fixture-fixer")
    authority = verify(str(bundle), str(report))
    assert authority["review_image_basis"] == "verified_canvas"
    assert authority["renders"]["p1"]["image"] == "p1.png"
    assert authority["review_images"]["p1"]["image"] == "canvas-p1.png"
    assert authority["review_images"]["p1"]["pixels"] == [768, 432]
    assert (bundle / "p1.png").is_file()
    assert (bundle / "canvas-p1.png").is_file()
    assert (bundle / "canvas-evidence.json").is_file()
    copied = unpack(str(bundle), str(tmp_path / "restored"))
    assert copied["review_images"] == authority["review_images"]


def test_optional_clean_unsupported_keeps_raw_portable(tmp_path):
    report, renders, bundle = _ready_bundle(tmp_path)
    manifest_file = renders / "capture-manifest.json"
    manifest = json.loads(manifest_file.read_text())
    del manifest["canvas_review"]
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    pack(str(report), str(renders), str(bundle), "fixture-fixer")
    authority = verify(str(bundle))
    assert authority["review_image_basis"] == "raw_desktop_window"
    assert authority["review_images"] == authority["renders"]
    assert not (bundle / "canvas-p1.png").exists()


@pytest.mark.parametrize("tamper", [
    "image", "claim-crop", "header-image", "missing-raw", "proof-bytes"])
def test_changed_canvas_claim_or_pixel_refused(tmp_path, tamper):
    report, renders, bundle = _ready_bundle(tmp_path)
    if tamper == "claim-crop":
        proof_file = renders / "canvas-evidence.json"
        proof = json.loads(proof_file.read_text())
        proof["pages"]["p1"]["crop"][1] += 1
        proof_file.write_text(json.dumps(proof), encoding="utf-8")
        with pytest.raises(ValueError, match="crop mismatch"):
            pack(str(report), str(renders), str(bundle), "fixture-fixer")
        return
    pack(str(report), str(renders), str(bundle), "fixture-fixer")
    if tamper == "image":
        path = bundle / "canvas-p1.png"
        path.write_bytes(path.read_bytes()[:-16] + b"fake-canvas")
    elif tamper == "header-image":
        header_file = bundle / "bundle.json"
        header = json.loads(header_file.read_text())
        header["review_images"]["p1"]["image"] = "p1.png"
        header_file.write_text(json.dumps(header), encoding="utf-8")
    elif tamper == "missing-raw":
        (bundle / "p1.png").unlink()
    else:
        proof_path = bundle / "canvas-evidence.json"
        proof_path.write_text(proof_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid|missing|tampered|mismatch"):
        verify(str(bundle))


def test_reviewer_port_can_inspect_verified_clean_binding(tmp_path):
    report, renders, bundle = _ready_bundle(tmp_path)
    pack(str(report), str(renders), str(bundle), "fixture-fixer")

    class _InspectsCanvas:
        reviewer_id = "independent-test-adapter"

        def review(self, bundle_dir):
            # Synthetic test adapter only: proves access to real verified
            # pixels, NOT an independently obtained visual judgment.
            authority = verify(bundle_dir)
            clean = authority["review_images"]["p1"]
            assert (Path(bundle_dir) / clean["image"]).is_file()
            assert clean["image"] == "canvas-p1.png"
            return {"observations": [{
                "page_id": "p1", "check": "test-adapter-access",
                "verdict": "blocked", "detail": "synthetic adapter; no vision"}]}

    record = review_bundle(
        bundle_dir=str(bundle), reviewer=_InspectsCanvas(),
        reviewer_id="independent-test-adapter", fixer_id="fixture-fixer")
    assert record["visual"] == "blocked"
    assert record["review_images"]["p1"]["image"] == "canvas-p1.png"
