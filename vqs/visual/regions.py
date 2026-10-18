"""Pixel-exact, PBIR-bound visual crops derived from a verified review bundle.

Never treats a guessed viewport as a transform. Source data and crop pixels
are bound to the existing authoritative bundle; the region index is a
separate private sidecar, not an undeclared member of a v1 bundle.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import tempfile
import zlib
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..evidence import _PNG_FILE_CAP, _decode_png, _unfilter_scanlines, digest


class RegionError(ValueError):
    """Unverifiable PBIR-to-pixel crop; never return a guessed rectangle."""


def _int(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RegionError(f"{name} must be an integer >= {minimum}")
    return value


def _png_chunk(tag: bytes, contents: bytes) -> bytes:
    return (struct.pack(">I", len(contents)) + tag + contents
            + struct.pack(">I", zlib.crc32(tag + contents) & 0xffffffff))


def _encode_crop(pixels: bytes, width: int, height: int, channels: int) -> bytes:
    if channels not in (1, 3, 4):
        raise RegionError("unsupported PNG channels")
    if len(pixels) != width * height * channels:
        raise RegionError("crop pixel length mismatch")
    color = {1: 0, 3: 2, 4: 6}[channels]
    stride = width * channels
    scan = b"".join(
        b"\x00" + pixels[y * stride:(y + 1) * stride] for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8,
                                          color, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(scan, 6))
        + _png_chunk(b"IEND", b"")
    )


def _number(value: Any, name: str, *, strictly_positive: bool = False) -> Fraction:
    # Genuine PBIR includes decimal positions (e.g. x=439.71819817621764).
    # Convert JSON decimals to exact rational coordinates rather than
    # rounding to integer before transformation.
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value)):
        raise RegionError(f"{name} must be a finite numeric PBIR coordinate")
    number = Fraction(str(value))
    if number < 0 or (strictly_positive and number == 0):
        raise RegionError(f"{name} is outside legal PBIR canvas geometry")
    return number


def _rect(position: Any, page_width: int, page_height: int) -> dict[str, int | float]:
    if not isinstance(position, dict):
        raise RegionError("visual has no PBIR position")
    names = ("x", "y", "width", "height")
    values = tuple(_number(position.get(k), k, strictly_positive=k in ("width", "height"))
                   for k in names)
    x, y, w, h = values
    if x + w > page_width or y + h > page_height:
        raise RegionError("PBIR visual extends beyond the page canvas")
    # Preserve the exact source literals, including non-integer coordinates.
    return {k: position[k] for k in names}


def _floor(value: Fraction) -> int:
    return value.numerator // value.denominator


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _transform(rect: dict[str, int], scale: Fraction, *,
               padding: int, image_width: int, image_height: int
               ) -> tuple[list[int], list[int]]:
    """Outward-rasterized target and padded-context boxes in canvas pixels."""
    _int(padding, "padding")
    x, y = (Fraction(str(rect[k])) for k in ("x", "y"))
    right = x + Fraction(str(rect["width"]))
    bottom = y + Fraction(str(rect["height"]))
    target = [_floor(x * scale), _floor(y * scale),
              _ceil(right * scale), _ceil(bottom * scale)]
    context = [max(0, _floor(x * scale) - padding),
               max(0, _floor(y * scale) - padding),
               min(image_width, _ceil(right * scale) + padding),
               min(image_height, _ceil(bottom * scale) + padding)]
    if (target[0] < 0 or target[1] < 0 or
            target[2] > image_width or target[3] > image_height or
            target[0] >= target[2] or target[1] >= target[3] or
            context[0] >= context[2] or context[1] >= context[3]):
        raise RegionError("transformed visual extends beyond rendered canvas")
    return target, context


def _region_pixels(raw: bytes, image_width: int, channels: int,
                   bounds: list[int]) -> bytes:
    x0, y0, x1, y1 = bounds
    stride = image_width * channels
    return b"".join(
        raw[y * stride + x0 * channels:y * stride + x1 * channels]
        for y in range(y0, y1))


def _inventory(bundle: Path) -> dict[str, Any]:
    header = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    raw = (bundle / "inventory.json").read_bytes()
    expected = header.get("files", {}).get("inventory.json")
    if not isinstance(expected, str) or hashlib.sha256(raw).hexdigest() != expected:
        raise RegionError("bundle inventory drifted after verification")
    inventory = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(inventory, dict):
        raise RegionError("invalid verified inventory")
    return inventory


def _page_evidence(authority: dict, page: dict, bundle: Path
                   ) -> tuple[Path, Fraction, bytes, int, int, int]:
    if authority["review_image_basis"] != "verified_canvas":
        raise RegionError("PBIR visual crops require a verified report-only canvas")
    page_id = page["id"]
    binding = authority["review_images"].get(page_id)
    shape = page.get("canvas")
    if not isinstance(shape, list) or len(shape) != 2:
        raise RegionError("PBIR page has no canvas dimensions")
    pbw = _int(shape[0], "PBIR width", minimum=1)
    pbh = _int(shape[1], "PBIR height", minimum=1)
    if not isinstance(binding, dict):
        raise RegionError("missing verified page image")
    image = bundle / binding["image"]
    if image.is_symlink() or image.resolve().parent != bundle.resolve():
        raise RegionError("canvas image path escapes verified bundle")
    # Freeze the exact bytes before decode: an input path could be
    # replaced between a metadata/hash check and the PNG decoder's open.
    # Bound the read even under a concurrent file-size change.
    with image.open("rb") as handle:
        frozen_bytes = handle.read(_PNG_FILE_CAP + 1)
    if (len(frozen_bytes) > _PNG_FILE_CAP
            or hashlib.sha256(frozen_bytes).hexdigest() != binding["sha256"]):
        raise RegionError("canvas bytes changed/oversized after verification")
    with tempfile.TemporaryDirectory(prefix="vqs-region-frozen-") as scratch:
        frozen_path = Path(scratch) / "verified-canvas.png"
        frozen_path.write_bytes(frozen_bytes)
        width, height, channels, png = _decode_png(frozen_path)
        samples = _unfilter_scanlines(width, channels, png)
    if (width, height) != tuple(binding["pixels"]):
        raise RegionError("canvas dimensions changed after verification")
    scale = Fraction(width, pbw)
    if scale != Fraction(height, pbh):
        raise RegionError("canvas-to-PBIR scale is not uniform")
    if (scale <= 0 or not  Fraction(1, 2) <= scale <= 3
            or binding.get("method") != "lossless-verified-crop"):
        raise RegionError("canvas-to-PBIR scale lacks verified provenance")
    return image, scale, samples, width, height, channels


def _validate_selector(page_id: str, visual_id: str) -> None:
    if (not isinstance(page_id, str) or not isinstance(visual_id, str)
            or not page_id or not visual_id):
        raise RegionError("selector needs exact non-empty page and visual IDs")


def build_regions(bundle_dir: str, dest_dir: str, *,
                  selectors: list[tuple[str, str]] | None = None,
                  padding_px: int = 16,
                  report: str | None = None) -> dict[str, Any]:
    """Derive immutable visual crops and verified-source identity, without edits.

    Selectors are exact (page_id, visual_id). None selects all in-canvas
    visuals; any requested missing or off-canvas visual blocks the build.
    Output never overwrites an existing directory and is verified before
    returning it. Unknown z-order is reported, not fabricated.
    """
    from ..review.bundle import verify as verify_bundle

    _int(padding_px, "padding_px")
    if padding_px > 128:
        raise RegionError("padding_px must not exceed 128")
    bundle = Path(bundle_dir).resolve()
    destination = Path(dest_dir)
    if (destination.exists() or destination.is_symlink()
            or destination.parent.is_symlink()):
        raise RegionError("refusing existing or symlinked region destination")
    authority = verify_bundle(str(bundle), report)
    if authority["review_image_basis"] != "verified_canvas":
        raise RegionError("calibration unproven: no verified canvas for visual crops")
    inventory = _inventory(bundle)
    if inventory.get("source_sha256") != authority["source_sha256"]:
        raise RegionError("inventory revision differs from verified source")
    pages = inventory.get("pages")
    if not isinstance(pages, list):
        raise RegionError("no PBIR page inventory")
    desired = None
    if selectors is not None:
        desired = set()
        for pair in selectors:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise RegionError("invalid region selector")
            _validate_selector(*pair)
            if tuple(pair) in desired:
                raise RegionError("duplicate region selector")
            desired.add(tuple(pair))
        if not desired:
            raise RegionError("no region selectors")
    plan: list[tuple[dict, dict]] = []
    found: set[tuple[str, str]] = set()
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("id"), str):
            raise RegionError("invalid page identity")
        page_id = page["id"]
        visuals = page.get("visuals")
        if not isinstance(visuals, list):
            raise RegionError("invalid PBIR visual inventory")
        used: set[str] = set()
        for visual in visuals:
            if not isinstance(visual, dict):
                raise RegionError("invalid visual metadata")
            visual_id = visual.get("visual_id")
            _validate_selector(page_id, visual_id)
            if visual_id in used:
                raise RegionError("duplicate visual ID on page")
            used.add(visual_id)
            pair = (page_id, visual_id)
            if desired is None or pair in desired:
                plan.append((page, visual))
                found.add(pair)
    if desired is not None and desired != found:
        raise RegionError(f"unresolved PBIR visual selectors: {sorted(desired - found)}")
    if not plan:
        raise RegionError("no supported visuals selected")
    output: dict[str, Any] = {
        "schema": "vqs.visual-regions/1",
        "source_sha256": authority["source_sha256"],
        "bundle_sha256": authority["bundle_sha256"],
        "review_image_basis": "verified_canvas",
        "padding_px": padding_px,
        "regions": [],
    }
    # Leave a failed private sidecar for explicit cleanup; never remove
    # a directory that might have been concurrently created by others.
    destination.mkdir(parents=True, exist_ok=False)
    active_page = None
    evidence = None
    for i, (page, visual) in enumerate(plan):
        if active_page != page["id"]:
            evidence = _page_evidence(authority, page, bundle)
            active_page = page["id"]
        assert evidence is not None
        image, scale, samples, iw, ih, channels = evidence
        shape = page["canvas"]
        rect = _rect(visual.get("position"), shape[0], shape[1])
        target, context = _transform(
            rect, scale, padding=padding_px,
            image_width=iw, image_height=ih)
        cropped = _region_pixels(samples, iw, channels, context)
        w, h = context[2] - context[0], context[3] - context[1]
        fname = f"region-{i+1:04d}.png"
        path = destination / fname
        path.write_bytes(_encode_crop(cropped, w, h, channels))
        cw, ch, cc, cpng = _decode_png(path)
        if (cw, ch, cc) != (w, h, channels) or (
                _unfilter_scanlines(cw, cc, cpng) != cropped):
            raise RegionError("lossless crop verification failed")
        # Reject time-of-check/time-of-use screenshot changes.
        if digest(image) != authority["review_images"][active_page]["sha256"]:
            raise RegionError("verified source pixels changed during crop")
        output["regions"].append({
            "page_id": active_page,
            "visual_id": visual["visual_id"],
            "visual_type": visual.get("visual_type"),
            "visual_label": None,  # no guessed title from OCR
            "rect_pbir": rect,
            "z_order": visual.get("position", {}).get("z"),
            "source_canvas_sha256": authority["review_images"][active_page]["sha256"],
            "source_canvas_pixels": [iw, ih],
            "canvas_pbir": list(shape),
            "effective_scale": str(scale),
            "target_bbox_px": target,
            "context_bbox_px": context,
            "pixel_rounding": "outward",
            "crop_image": fname,
            "crop_sha256": digest(path),
            "crop_pixels": [w, h],
            "clip_proof": "exact_unfiltered_pixel_rows",
        })
    (destination / "regions.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    verify_regions(str(bundle), str(destination), report=report)
    return output


def verify_regions(bundle_dir: str, regions_dir: str, *,
                   report: str | None = None) -> dict[str, Any]:
    """Independently reproduce PBIR rectangles and verify every region pixel."""
    from ..review.bundle import verify as verify_bundle
    bundle = Path(bundle_dir).resolve()
    requested = Path(regions_dir)
    if requested.is_symlink() or requested.parent.is_symlink():
        raise RegionError("symlinked derived region path refused")
    region_root = requested.resolve()
    authority = verify_bundle(str(bundle), report)
    inventory = _inventory(bundle)
    manifest = json.loads((region_root / "regions.json").read_text(encoding="utf-8"))
    if (not isinstance(manifest, dict)
            or set(manifest) != {
                "schema", "source_sha256", "bundle_sha256",
                "review_image_basis", "padding_px", "regions"}
            or manifest.get("schema") != "vqs.visual-regions/1"
            or manifest.get("bundle_sha256") != authority["bundle_sha256"]
            or manifest.get("source_sha256") != authority["source_sha256"]
            or manifest.get("review_image_basis") != "verified_canvas"):
        raise RegionError("derived region manifest is not source-bound")
    padding = manifest.get("padding_px")
    if type(padding) is not int or not 0 <= padding <= 128:
        raise RegionError("invalid derived context padding")
    recs = manifest.get("regions")
    if not isinstance(recs, list) or not recs:
        raise RegionError("no region evidence")
    allowed = {"regions.json"}
    page_by_id = {page["id"]: page for page in inventory["pages"]}
    seen = set()
    # Retain one source page at a time, not all pages' decoded rasters.
    # Build emits page-grouped crops; refuse relisting a completed page.
    active_page: str | None = None
    active_evidence: tuple[Path, Fraction, bytes, int, int, int] | None = None
    completed_pages: set[str] = set()
    required_record_fields = {
        "page_id", "visual_id", "visual_type", "visual_label",
        "rect_pbir", "z_order", "source_canvas_sha256",
        "source_canvas_pixels", "canvas_pbir", "effective_scale",
        "target_bbox_px", "context_bbox_px", "pixel_rounding",
        "crop_image", "crop_sha256", "crop_pixels", "clip_proof"}
    for record in recs:
        if (not isinstance(record, dict)
                or set(record) != required_record_fields
                or record.get("visual_label") is not None):
            raise RegionError("unexpected/unproven visual metadata in sidecar")
        page_id, vid = record["page_id"], record["visual_id"]
        pair = (page_id, vid)
        if pair in seen:
            raise RegionError("duplicate region identity")
        seen.add(pair)
        page = page_by_id.get(page_id)
        if page is None:
            raise RegionError("region references unknown page")
        visuals = [v for v in page["visuals"] if v["visual_id"] == vid]
        if len(visuals) != 1:
            raise RegionError("region references unknown PBIR visual")
        if page_id != active_page:
            if page_id in completed_pages:
                raise RegionError("region manifest revisits a completed page")
            if active_page is not None and active_evidence is not None:
                previous_image = active_evidence[0]
                if digest(previous_image) != authority["review_images"][active_page]["sha256"]:
                    raise RegionError("canvas mutated during region verification")
            active_evidence = _page_evidence(authority, page, bundle)
            active_page = page_id
            completed_pages.add(page_id)
        assert active_evidence is not None
        image, scale, samples, iw, ih, channels = active_evidence
        rect = _rect(visuals[0]["position"], *page["canvas"])
        target, context = _transform(
            rect, scale, padding=padding,
            image_width=iw, image_height=ih)
        fname = record["crop_image"]
        if (not isinstance(fname, str)
                or fname != f"region-{len(seen):04d}.png"
                or (region_root / fname).is_symlink()):
            raise RegionError("region crop filename is not safe/ordered")
        allowed.add(fname)
        path = region_root / fname
        width, height, cc, raw_png = _decode_png(path)
        cropped = _region_pixels(samples, iw, channels, context)
        if (width, height, cc) != (
                context[2] - context[0], context[3] - context[1], channels
        ) or _unfilter_scanlines(width, cc, raw_png) != cropped:
            raise RegionError("derived crop does not reproduce exact canvas pixels")
        expected_fields = {
            "rect_pbir": rect, "visual_type": visuals[0].get("visual_type"),
            "z_order": visuals[0]["position"].get("z"),
            "target_bbox_px": target, "context_bbox_px": context,
            "crop_pixels": [width, height], "source_canvas_pixels": [iw, ih],
            "canvas_pbir": list(page["canvas"]), "effective_scale": str(scale),
            "source_canvas_sha256": authority["review_images"][page_id]["sha256"],
            "crop_sha256": digest(path),
            "clip_proof": "exact_unfiltered_pixel_rows",
            "pixel_rounding": "outward",
        }
        for key, val in expected_fields.items():
            if record.get(key) != val:
                raise RegionError(f"region metadata drifted: {key}")
    # Final page may have been changed while its crops were inspected.
    if active_page is not None and active_evidence is not None:
        image = active_evidence[0]
        if digest(image) != authority["review_images"][active_page]["sha256"]:
            raise RegionError("canvas image drifted during region re-verification")
    members = {path.name for path in region_root.iterdir()
               if path.is_file() and not path.is_symlink()}
    if members != allowed or any(p.is_symlink() or not p.is_file()
                                 for p in region_root.iterdir()):
        raise RegionError("derived region sidecar contains unexpected members")
    return {
        "status": "verified", "regions": len(recs),
        "source_sha256": authority["source_sha256"],
        "bundle_sha256": authority["bundle_sha256"],
    }
