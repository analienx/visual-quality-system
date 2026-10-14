"""Cross-check clean report canvases with their raw Desktop screenshots.

Proof is intentionally independent of cached manifest declarations: remeasure
the raw Desktop boundary, decode the derived image and compare each sample
row. A clean-canvas entry may improve a REVIEWER'S view; it never upgrades
raw capture geometry, data readiness or semantic answer authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..evidence import _decode_png, _unfilter_scanlines, safe_render_name
from .canvas import CanvasUnproven, locate_desktop_canvas


def verified_review_canvases(
    root: Path, manifest: dict[str, Any], pages: list[str]
) -> dict[str, dict[str, Any]]:
    """Reprove all canvas crops or refuse the entire optional attachment."""
    claim = manifest.get("canvas_review")
    if claim is None:
        return {}
    if not isinstance(claim, dict) or claim.get("status") != "complete":
        return {}
    if claim.get("method") != "desktop-dotted-page-boundary-v1":
        raise CanvasUnproven("unsupported canvas review extraction method")
    if claim.get("proof_file") != "canvas-evidence.json":
        raise CanvasUnproven("missing canonical canvas evidence file")
    proof_path = root / "canvas-evidence.json"
    if proof_path.is_symlink() or not proof_path.is_file():
        raise CanvasUnproven("canvas evidence file missing or linked")
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise CanvasUnproven("canvas evidence JSON unreadable") from exc
    if not isinstance(proof, dict):
        raise CanvasUnproven("canvas evidence must be a JSON object")
    mapping = claim.get("page_images")
    hashes = claim.get("files")
    pixels = claim.get("pixels")
    recorded = proof.get("pages") if isinstance(proof, dict) else None
    raw_mapping = manifest.get("page_images")
    raw_hashes = manifest.get("files")
    calibration = manifest.get("calibration")
    if (proof.get("status") != "complete" or proof.get("page_count") != len(pages)
            or not all(isinstance(p, dict) for p in
                       (mapping, hashes, pixels, recorded, raw_mapping,
                        raw_hashes, calibration))
            or set(mapping) != set(pages) or set(recorded) != set(pages)
            or len(set(mapping.values())) != len(pages)):
        raise CanvasUnproven("canvas page inventory mismatch")
    expected_canvas = [calibration.get("canvas_width"),
                       calibration.get("canvas_height")]
    if any(type(x) is not int or x <= 0 for x in expected_canvas):
        raise CanvasUnproven("invalid authoritative PBIR canvas")
    expected_names = set(mapping.values())
    if set(hashes) != expected_names or set(pixels) != set(pages):
        raise CanvasUnproven("canvas hashes or dimensions not complete")
    result: dict[str, dict[str, Any]] = {}
    for page in pages:
        name = mapping[page]
        raw_name = raw_mapping.get(page)
        if (safe_render_name(name) != name
                or not name.startswith("canvas-") or not name.endswith(".png")
                or safe_render_name(raw_name) != raw_name
                or name == raw_name):
            raise CanvasUnproven("unsafe or noncanonical canvas filename")
        raw = root / raw_name
        derived = root / name
        if (raw.is_symlink() or derived.is_symlink()
                or not raw.is_file() or not derived.is_file()):
            raise CanvasUnproven("raw or clean image is missing or linked")
        raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
        crop_sha = hashlib.sha256(derived.read_bytes()).hexdigest()
        evidence = recorded.get(page)
        if (not isinstance(evidence, dict)
                or evidence.get("status") != "measured"
                or raw_sha != raw_hashes.get(raw_name)
                or raw_sha != evidence.get("source_sha256")
                or crop_sha != hashes.get(name)
                or crop_sha != evidence.get("canvas_sha256")
                or evidence.get("canvas_image") != name
                or evidence.get("source_canvas") != expected_canvas
                or evidence.get("canvas_pixels") != pixels[page]):
            raise CanvasUnproven(f"canvas hashes/claims differ: {page}")
        measured = locate_desktop_canvas(raw, tuple(expected_canvas))
        if measured["crop"] != evidence.get("crop"):
            raise CanvasUnproven(f"remeasured canvas crop mismatch: {page}")
        if measured["effective_scale"] != evidence.get("effective_scale"):
            raise CanvasUnproven(f"remeasured canvas scale mismatch: {page}")
        if measured["raw_pixels"] != evidence.get("raw_pixels"):
            raise CanvasUnproven(f"remeasured raw bounds mismatch: {page}")
        raw_w, raw_h, raw_c, encoded = _decode_png(raw)
        crop_w, crop_h, crop_c, crop_encoded = _decode_png(derived)
        x, y, crop_width, crop_height = measured["crop"]
        if ([crop_w, crop_h] != pixels[page] or crop_c != raw_c
                or crop_w != crop_width or crop_h != crop_height
                or x + crop_w > raw_w or y + crop_h > raw_h):
            raise CanvasUnproven(f"canvas format/dimensions mismatch: {page}")
        raw_samples = _unfilter_scanlines(raw_w, raw_c, encoded)
        crop_samples = _unfilter_scanlines(crop_w, crop_c, crop_encoded)
        raw_stride = raw_w * raw_c
        crop_stride = crop_w * crop_c
        for n in range(crop_h):
            begin = (y + n) * raw_stride + x * raw_c
            if (raw_samples[begin:begin + crop_stride]
                    != crop_samples[n * crop_stride:(n + 1) * crop_stride]):
                raise CanvasUnproven(
                    f"canvas pixel samples differ from raw image: {page}")
        result[page] = {
            "image": name, "sha256": crop_sha,
            "pixels": [crop_w, crop_h],
            "crop": list(measured["crop"]),
            "effective_scale": measured["effective_scale"],
            "source_image": raw_name,
            "source_sha256": raw_sha,
            "method": "lossless-verified-crop",
        }
    return result
