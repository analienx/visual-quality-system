"""Conservative pixel-content QA over verified PBIR visual-region evidence.

This measures the *rendered target* inside the PBIR rectangle, excluding the
context gutter. A near-uniform, supposedly data-bearing visual is a concrete
defect candidate. Interior whitespace, tiny content, and margin skew are
enforced only when an exact source/bundle-bound design policy supplies budgets;
otherwise they remain review signals. No OCR, data inference, or auto-reflow.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..evidence import _PNG_FILE_CAP, _decode_png, _unfilter_scanlines
from .regions import RegionError, _region_pixels, verify_regions

PIXEL_SCHEMA = "vqs.pixel-content-audit/1"
POLICY_SCHEMA = "vqs.pixel-content-policy/1"
DATA_TYPES = frozenset({
    "card", "cardvisual", "multirowcard", "kpi", "newcard", "slicer",
    "pivottable", "tableex", "table", "matrix", "shapemap", "azuremap",
    "map", "filledmap", "decompositiontreevisual", "decompositiontree",
    "donutchart", "piechart", "scatterchart", "treemap", "waterfallchart",
})
THRESHOLD_NAMES = frozenset({
    "min_content_width", "min_content_height", "max_blank_band",
    "max_margin_skew_x", "max_margin_skew_y",
})


def _is_data_visual(kind: str) -> bool:
    return kind in DATA_TYPES or any(
        token in kind for token in ("barchart", "columnchart", "linechart", "areachart"))


def _pixel(raw: bytes, at: int, channels: int) -> tuple[int, int, int]:
    if channels == 1:
        return raw[at], raw[at], raw[at]
    return raw[at], raw[at + 1], raw[at + 2]


def _background(raw: bytes, width: int, height: int, channels: int
                ) -> tuple[tuple[int, int, int], float]:
    """Modal quantized perimeter color; report its actual sample support."""
    edge: list[tuple[int, int, int]] = []
    stride = width * channels
    # One or two pixels inside the edge avoids a 1px outer stroke, without
    # looking at unrelated neighboring visuals or the context gutter.
    inset = min(3, (width - 1) // 2, (height - 1) // 2)
    for x in range(inset, width - inset, max(1, width // 64)):
        for y in (inset, height - 1 - inset):
            edge.append(_pixel(raw, y * stride + x * channels, channels))
    for y in range(inset, height - inset, max(1, height // 64)):
        for x in (inset, width - 1 - inset):
            edge.append(_pixel(raw, y * stride + x * channels, channels))
    if not edge:
        raise RegionError("cannot inspect an empty target edge")
    bins = [tuple(channel // 16 for channel in rgb) for rgb in edge]
    mode, support = Counter(bins).most_common(1)[0]
    matching = [v for v, bucket in zip(edge, bins) if bucket == mode]
    background = tuple(round(sum(v[i] for v in matching) / len(matching)) for i in range(3))
    return background, support / len(edge)


def inspect_pixels(raw: bytes, width: int, height: int, channels: int, *,
                   visual_type: str | None, requirements: Mapping[str, float] | None = None
                   ) -> dict[str, Any]:
    """Measure one EXACT target crop; no resize, OCR or inferred report intent.

    Hard failures require a credible flat background and actual target pixels.
    Sparse visuals whose render intent is unknown are review candidates only.
    """
    if (channels not in (1, 3, 4) or type(width) is not int
            or type(height) is not int or min(width, height) < 24
            or len(raw) != width * height * channels):
        raise RegionError("invalid/review-unreadable target pixel buffer")
    budgets = dict(requirements or {})
    if set(budgets) - THRESHOLD_NAMES or any(
            type(value) not in (float, int) or not 0 <= value <= 1
            for value in budgets.values()):
        raise RegionError("unsupported or invalid content-occupancy policy")
    kind = visual_type.casefold() if isinstance(visual_type, str) else ""
    background, support = _background(raw, width, height, channels)
    reliable = support >= 0.58
    count = 0
    min_x, max_x, min_y, max_y = width, -1, height, -1
    row_has_content = [False] * height
    stride = width * channels
    if reliable:
        for y in range(height):
            base = y * stride
            for x in range(width):
                rgb = _pixel(raw, base + x * channels, channels)
                if max(abs(rgb[k] - background[k]) for k in range(3)) < 32:
                    continue
                count += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                row_has_content[y] = True
    density = count / (width * height)
    if count:
        content_width = (max_x + 1 - min_x) / width
        content_height = (max_y + 1 - min_y) / height
        left, right = min_x / width, (width - 1 - max_x) / width
        top, bottom = min_y / height, (height - 1 - max_y) / height
    else:
        content_width = content_height = 0.0
        left = right = top = bottom = 1.0
    # A central, contiguous blank band is more informative than overall white
    # fraction for plots with a title above and a footer/legend below.
    longest = run = 0
    for y, has_content in enumerate(row_has_content):
        if height // 10 <= y < height * 9 // 10 and not has_content:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    blank_band = longest / height
    metric = {
        "background_support": round(support, 4),
        "foreground_fraction": round(density, 5),
        "content_width_fraction": round(content_width, 4),
        "content_height_fraction": round(content_height, 4),
        "longest_central_blank_band": round(blank_band, 4),
        "left_margin_fraction": round(left, 4),
        "right_margin_fraction": round(right, 4),
        "top_margin_fraction": round(top, 4),
        "bottom_margin_fraction": round(bottom, 4),
    }
    findings: list[dict[str, Any]] = []
    if not reliable:
        return {"status": "unknown", "reason": "no dominant stable background",
                "metrics": metric, "findings": []}
    if _is_data_visual(kind) and density <= 0.0007:
        findings.append({"kind": "rendered_data_visual_blank", "severity": "fail",
                         "remedy": "Inspect data readiness/bindings and host errors; repair a candidate and recapture"})
    if budgets and density > 0.0007:
        measured = {
            "min_content_width": content_width,
            "min_content_height": content_height,
            "max_blank_band": blank_band,
            "max_margin_skew_x": abs(left - right),
            "max_margin_skew_y": abs(top - bottom),
        }
        for name, limit in sorted(budgets.items()):
            actual = measured[name]
            violates = actual < limit if name.startswith("min_") else actual > limit
            if violates:
                findings.append({
                    "kind": "content_budget_violation", "budget": name,
                    "measured": round(actual, 4), "limit": limit,
                    "severity": "fail",
                    "remedy": "Adjust ONLY a disposable PBIR candidate's visual/plot sizing or formatting; validate, reload and recapture",
                })
    if not budgets and density > 0.0007 and _is_data_visual(kind):
        if (content_width < 0.42 and content_height < 0.48) or blank_band > 0.53:
            findings.append({"kind": "sparse_visual_needs_review", "severity": "review",
                             "remedy": "Confirm expected plot occupancy from report design before an auto-fail or resize"})
        if abs(left - right) > 0.4 or abs(top - bottom) > 0.4:
            findings.append({"kind": "unbalanced_visual_padding_review", "severity": "review",
                             "remedy": "Compare visual content boundaries, axes, titles and legend with neighboring panels"})
    status = ("fail" if any(f["severity"] == "fail" for f in findings)
              else "review_required" if findings else "no_pixel_issue_proven")
    return {"status": status, "metrics": metric, "findings": findings}


def _policy(policy: Mapping[str, Any] | None, *, source: str, bundle: str
            ) -> dict[tuple[str, str], dict[str, float]]:
    if policy is None:
        return {}
    if (not isinstance(policy, Mapping) or set(policy) != {
            "schema", "source_sha256", "bundle_sha256", "targets"}
            or policy.get("schema") != POLICY_SCHEMA
            or policy.get("source_sha256") != source
            or policy.get("bundle_sha256") != bundle
            or not isinstance(policy.get("targets"), list)
            or not policy["targets"]):
        raise RegionError("pixel policy not bound to exact source and review bundle")
    targets: dict[tuple[str, str], dict[str, float]] = {}
    for item in policy["targets"]:
        if (not isinstance(item, dict) or set(item) != {
                "page_id", "visual_id", "requirements"}
                or not isinstance(item["page_id"], str) or not item["page_id"]
                or not isinstance(item["visual_id"], str) or not item["visual_id"]
                or not isinstance(item["requirements"], dict)
                or not item["requirements"]):
            raise RegionError("invalid pixel-policy target")
        key = item["page_id"], item["visual_id"]
        if key in targets:
            raise RegionError("duplicate pixel-policy selector")
        # Call the exact same bounded type validator used by the measurement.
        limits = item["requirements"]
        if set(limits) - THRESHOLD_NAMES or any(
                type(value) not in (int, float) or not 0 <= value <= 1
                for value in limits.values()):
            raise RegionError("invalid pixel-policy threshold")
        targets[key] = limits
    return targets


def audit_regions(bundle_dir: str, regions_dir: str, *,
                  report: str | None = None,
                  policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Reverify the real canvas/crops, then issue exact source-bound metrics.

    Results contain no image pixels. A clean metric report is NOT G2/G6 human
    acceptance; only a high-confidence defect or a declared budget can fail.
    """
    authority = verify_regions(bundle_dir, regions_dir, report=report)
    root = Path(regions_dir).resolve()
    manifest_bytes = (root / "regions.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    budgets = _policy(policy, source=authority["source_sha256"],
                      bundle=authority["bundle_sha256"])
    available = {(v["page_id"], v["visual_id"]) for v in manifest["regions"]}
    if set(budgets) - available:
        raise RegionError("pixel policy selects visual absent from verified crops")
    records = []
    for item in manifest["regions"]:
        page_id, visual_id = item["page_id"], item["visual_id"]
        path = root / item["crop_image"]
        if path.is_symlink() or path.resolve().parent != root:
            raise RegionError("pixel audit crop path escaped verified region sidecar")
        # Freeze exactly the reverified bytes, so another writer cannot swap
        # the input between its SHA check and the PNG decoder's open.
        with path.open("rb") as handle:
            frozen = handle.read(_PNG_FILE_CAP + 1)
        if (len(frozen) > _PNG_FILE_CAP
                or hashlib.sha256(frozen).hexdigest() != item["crop_sha256"]):
            raise RegionError("region crop drifted before pixel measurement")
        with tempfile.TemporaryDirectory(prefix="vqs-pixel-frozen-") as scratch:
            image = Path(scratch) / "verified.png"
            image.write_bytes(frozen)
            width, _height, channels, png = _decode_png(image)
        raw = _unfilter_scanlines(width, channels, png)
        target = item["target_bbox_px"]
        context = item["context_bbox_px"]
        relative = [target[0] - context[0], target[1] - context[1],
                    target[2] - context[0], target[3] - context[1]]
        pixels = _region_pixels(raw, width, channels, relative)
        pixel_width, pixel_height = relative[2] - relative[0], relative[3] - relative[1]
        finding = inspect_pixels(pixels, pixel_width, pixel_height, channels,
                                 visual_type=item.get("visual_type"),
                                 requirements=budgets.get((page_id, visual_id)))
        records.append({"page_id": page_id, "visual_id": visual_id,
                        "visual_type": item.get("visual_type"),
                        "crop_sha256": item["crop_sha256"],
                        "target_pixels": [pixel_width, pixel_height], **finding})
    fail = any(r["status"] == "fail" for r in records)
    unknown = any(r["status"] == "unknown" for r in records)
    review = any(r["status"] == "review_required" for r in records)
    if (root / "regions.json").read_bytes() != manifest_bytes:
        raise RegionError("region manifest drifted during pixel audit")
    # The secondary re-verification covers a source-canvas swap while
    # the (independently frozen) crops were measured.
    verify_regions(bundle_dir, regions_dir, report=report)
    return {
        "schema": PIXEL_SCHEMA, "source_sha256": authority["source_sha256"],
        "bundle_sha256": authority["bundle_sha256"],
        "regions_index_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "status": ("fail" if fail else "unknown" if unknown
                   else "review_required" if review else "no_pixel_issue_proven"),
        "visual_acceptance": "not_run", "regions": records,
        "policy_targets": len(budgets),
    }
