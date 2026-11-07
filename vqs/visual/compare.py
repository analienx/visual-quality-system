"""Deterministic rendered before/after regression review.

Compares two source-bound page captures at pixel level. The page results
describe where pixels differ; the overall result remains blocked until
equivalent report data and interaction scope have independent evidence.
The current readiness probe only counts one table and cannot prove that.

Pixel differences are observations, not necessarily regressions. Data,
rendering nondeterminism, and interaction state can also change pixels.

What blocks, and never passes (AGENTS.md: missing data, stale captures
and unproven evidence are `blocked`, never a pass):

* either capture manifest is missing, wrong-shaped or not bound to the
  report revision it is being compared as;
* either capture declares ``data_population: unproven`` - a cache-less
  candidate renders ``(Blank)`` everywhere and still captures, so an
  "identical" comparison of two blank reports proves nothing;
* the population probe hashes differ or one capture was not populated;
* the page sets, PBIR canvas or capture scale differ;
* the report canvas cannot be located in a capture, or the two located
  canvases differ in size.

No raw screenshot is modified and no pixels are written anywhere: the
result carries counts, rectangles and digests only.
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..evidence import _decode_png, _unfilter_scanlines, digest, safe_render_name
from .canvas import CanvasUnproven, locate_desktop_canvas

SCHEMA = "vqs.render-comparison/1"
MANIFEST = "capture-manifest.json"
_VISUAL_REL = "definition/pages/{page}/visuals/{visual}/visual.json"


class ComparisonBlocked(ValueError):
    """The comparison cannot be trusted, so it refuses to produce a verdict."""


def _load_manifest(renders: Path, label: str) -> dict[str, Any]:
    path = Path(renders) / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ComparisonBlocked(f"{label}: unreadable {MANIFEST}: {exc}") from exc
    except ValueError as exc:
        raise ComparisonBlocked(f"{label}: malformed {MANIFEST}: {exc}") from exc
    if not isinstance(data, dict):
        raise ComparisonBlocked(f"{label}: {MANIFEST} is not an object")
    digest = data.get("source_sha256")
    images = data.get("page_images")
    canvas = data.get("canvas")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
            or not isinstance(images, dict) or not images
            or not all(isinstance(k, str) and isinstance(v, str)
                       for k, v in images.items())
            or ("canvas" in data and (not isinstance(canvas, list) or len(canvas) != 2
                or any(type(v) is not int or v <= 0 for v in canvas)))):
        raise ComparisonBlocked(
            f"{label}: {MANIFEST} lacks a usable source digest, page images "
            "or PBIR canvas")
    return data


def _require_bound(manifest: dict[str, Any], report: Path, label: str) -> None:
    """The capture must be of the revision it is being compared as."""
    from ..pbir import source_digest

    try:
        actual = source_digest(report)
    except (OSError, ValueError) as exc:
        raise ComparisonBlocked(
            f"{label}: cannot digest {report}: {exc}") from exc
    if actual != manifest["source_sha256"]:
        raise ComparisonBlocked(
            f"{label}: capture is bound to source {manifest['source_sha256'][:12]} "
            f"but {report} is {actual[:12]}; a capture of another revision is "
            "stale evidence, not a before/after pair")


def _require_data(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict:
    """Check populatedness probes without claiming report data parity.

    The current producer hashes COUNTROWS on one table, not the query
    definitions, answers, filters, roles, or other relevant tables.
    Matching hashes are insufficient to prove data equality.
    """
    proofs = {}
    for label, manifest in (("baseline", baseline), ("candidate", candidate)):
        modeling = manifest.get("modeling")
        modeling = modeling if isinstance(modeling, dict) else {}
        if modeling.get("data_population") == "unproven":
            raise ComparisonBlocked(
                f"{label}: capture declares data_population: unproven. A "
                "cache-less report renders (Blank) everywhere and still "
                "captures, so comparing these pixels proves nothing. "
                "Re-capture with --live-data.")
        readiness = manifest.get("data_readiness")
        if not isinstance(readiness, dict):
            raise ComparisonBlocked(
                f"{label}: capture carries no data_readiness evidence, so "
                "the rendered values are unproven")
        if readiness.get("populated") is not True:
            raise ComparisonBlocked(
                f"{label}: data_readiness says the report was not populated")
        query_hash = readiness.get("query_hash")
        if (not isinstance(query_hash, str) or len(query_hash) != 64
                or any(c not in "0123456789abcdef" for c in query_hash)):
            raise ComparisonBlocked(
                f"{label}: data_readiness carries no query_hash, so the two "
                "readiness probes cannot be compared")
        proofs[label] = query_hash
    if proofs["baseline"] != proofs["candidate"]:
        raise ComparisonBlocked(
            "the two captures have different readiness probe results "
            "(data_readiness.query_hash "
            f"{proofs['baseline'][:12]} vs {proofs['candidate'][:12]}); a "
            "pixel difference cannot be attributed to the source change")
    return {"query_hash": proofs["baseline"], "populated": True}


def _page_inventory(report: Path, label: str) -> dict[str, tuple[int, int]]:
    """Require the same complete source inventory as capture itself."""
    from ..pbir import report_context

    try:
        context = report_context(report, allow_unresolved_model=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ComparisonBlocked(f"{label}: report page inventory invalid: {exc}") from exc
    pages = context.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ComparisonBlocked(f"{label}: report page inventory is empty")
    ids = [page.get("id") if isinstance(page, dict) else None for page in pages]
    if (any(not isinstance(page, str) or not page for page in ids)
            or len(set(ids)) != len(ids)):
        raise ComparisonBlocked(f"{label}: report page inventory is malformed")
    inventory = {}
    for page in pages:
        canvas = page.get("canvas")
        if (not isinstance(canvas, list) or len(canvas) != 2
                or any(type(value) is not int or value <= 0 for value in canvas)):
            raise ComparisonBlocked(f"{label}/{page['id']}: source canvas is malformed")
        inventory[page["id"]] = (canvas[0], canvas[1])
    return inventory


def _manifest_geometry(manifest: dict[str, Any], inventory: dict[str, tuple[int, int]],
                       label: str) -> int:
    """Validate actual capture calibration against every source page."""
    calibration = manifest.get("calibration")
    desktop = manifest.get("desktop")
    if calibration is None:
        calibration = {}
    if desktop is None:
        desktop = {}
    if not isinstance(calibration, dict) or not isinstance(desktop, dict):
        raise ComparisonBlocked(f"{label}: capture geometry metadata is malformed")

    scales = [container["scale"] for container in (manifest, calibration, desktop)
              if "scale" in container]
    if (not scales or any(type(value) is not int or value not in (1, 2) for value in scales)
            or len(set(scales)) != 1):
        raise ComparisonBlocked(f"{label}: capture scale differs or is missing/malformed")

    canvases = []
    if "canvas" in manifest:
        canvases.append(manifest["canvas"])
    if "canvas_width" in calibration or "canvas_height" in calibration:
        canvases.append([calibration.get("canvas_width"), calibration.get("canvas_height")])
    if (not canvases or any(not isinstance(value, list) or len(value) != 2
                            or any(type(x) is not int or x <= 0 for x in value)
                            for value in canvases)):
        raise ComparisonBlocked(f"{label}: PBIR canvas missing or malformed")
    if any(value != canvases[0] for value in canvases[1:]):
        raise ComparisonBlocked(f"{label}: PBIR canvas differs between manifest declarations")
    primary = tuple(canvases[0])
    if primary != next(iter(inventory.values())):
        raise ComparisonBlocked(f"{label}: capture canvas differs from source page inventory")

    declared = calibration.get("page_canvases")
    if "page_canvases" not in calibration:
        if any(size != primary for size in inventory.values()):
            raise ComparisonBlocked(f"{label}: mixed source page inventory needs per-page canvases")
    elif not isinstance(declared, dict) or set(declared) != set(inventory):
        raise ComparisonBlocked(f"{label}: per-page canvas inventory is missing or malformed")
    else:
        for page, size in inventory.items():
            value = declared[page]
            if (not isinstance(value, list) or len(value) != 2
                    or any(type(x) is not int or x <= 0 for x in value)
                    or tuple(value) != size):
                raise ComparisonBlocked(f"{label}/{page}: capture canvas differs from source page inventory")
    return scales[0]


def _capture_files(renders: Path, manifest: dict[str, Any], pages: set[str],
                   label: str) -> dict[str, tuple[Path, str]]:
    """Verify every page is mapped to one contained, hash-bound PNG."""
    mapping = manifest["page_images"]
    if set(mapping) != pages:
        raise ComparisonBlocked(
            f"{label}: capture differs from report page inventory; "
            f"missing pages: {sorted(pages - set(mapping))}; "
            f"unexpected pages: {sorted(set(mapping) - pages)}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ComparisonBlocked(f"{label}: capture file hashes are missing or malformed")
    root = renders.resolve()
    out: dict[str, tuple[Path, str]] = {}
    names: set[str] = set()
    for page in sorted(pages):
        name = mapping[page]
        if safe_render_name(name) is None or not name.lower().endswith(".png"):
            raise ComparisonBlocked(f"{label}/{page}: unsafe capture filename")
        if name.casefold() in names:
            raise ComparisonBlocked(f"{label}/{page}: duplicate capture filename")
        names.add(name.casefold())
        expected = files.get(name)
        if (not isinstance(expected, str) or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)):
            raise ComparisonBlocked(f"{label}/{page}: missing or malformed capture hash")
        image = renders / name
        try:
            if image.is_symlink() or not image.is_file() or image.resolve().parent != root:
                raise ComparisonBlocked(f"{label}/{page}: missing or unsafe capture file")
            if any(image.samefile(previous[0]) for previous in out.values()):
                raise ComparisonBlocked(f"{label}/{page}: duplicate capture file")
            if digest(image) != expected:
                raise ComparisonBlocked(f"{label}/{page}: capture hash mismatch")
        except (OSError, ValueError) as exc:
            if isinstance(exc, ComparisonBlocked):
                raise
            raise ComparisonBlocked(f"{label}/{page}: unreadable capture file: {exc}") from exc
        out[page] = (image, expected)
    return out


def _canvas_window(image: Path, canvas: tuple[int, int], label: str, expected: str
                   ) -> tuple[dict[str, Any], int, int, int, bytes]:
    """Located canvas plus the decoded raw scanlines of its capture."""
    try:
        located = locate_desktop_canvas(image, canvas)
    except (CanvasUnproven, OSError, ValueError) as exc:
        raise ComparisonBlocked(
            f"{label}: report canvas not measurable in {image.name}: {exc}; "
            "a changed page is blocked, never passed") from exc
    width, height, channels, png = _decode_png(image)
    raw = _unfilter_scanlines(width, channels, png)
    if located.get("source_sha256") != expected or digest(image) != expected:
        raise ComparisonBlocked(f"{label}: capture hash changed during comparison")
    return located, width, height, channels, raw


def _changed_visuals(baseline_report: Path, candidate_report: Path,
                     pages: list[str]) -> dict[str, set[str]]:
    """Visuals whose PBIR bytes differ, per page.

    Byte identity is the honest test: any edit the candidate made to a
    visual shows up here, and a visual nobody touched cannot be used to
    excuse a rendered difference.
    """
    changed: dict[str, set[str]] = {page: set() for page in pages}
    for page in pages:
        base_dir = Path(baseline_report) / f"definition/pages/{page}/visuals"
        cand_dir = Path(candidate_report) / f"definition/pages/{page}/visuals"
        names = set()
        for directory in (base_dir, cand_dir):
            if directory.is_dir():
                names |= {child.name for child in directory.iterdir()
                          if child.is_dir()}
        for name in names:
            rel = _VISUAL_REL.format(page=page, visual=name)
            before = Path(baseline_report) / rel
            after = Path(candidate_report) / rel
            one = before.read_bytes() if before.is_file() else None
            two = after.read_bytes() if after.is_file() else None
            if one != two:
                changed[page].add(name)
    return changed


def _rects(report: Path) -> dict[tuple[str, str], dict[str, float]]:
    """Measured absolute page rectangles for every visual."""
    from ..powerbi.measure import measure_report

    facts = measure_report(str(report))
    rules = facts.get("rules")
    rules = rules if isinstance(rules, dict) else {}
    entry = rules.get("layout.no_visual_overlap")
    entry = entry if isinstance(entry, dict) else {}
    out: dict[tuple[str, str], dict[str, float]] = {}
    for item in entry.get("visuals") or []:
        if not (isinstance(item, dict) and isinstance(item.get("page"), str)
                and isinstance(item.get("visual"), str)):
            continue
        box = {key: item.get(key) for key in ("x", "y", "width", "height")}
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               for v in box.values()):
            continue
        if box["width"] <= 0 or box["height"] <= 0:
            continue
        out[(item["page"], item["visual"])] = box
    return out


def _scaled_box(box: dict[str, float], scale: Fraction, margin: int,
                limit: tuple[int, int]) -> tuple[int, int, int, int]:
    """A PBIR rect in canvas pixels, clamped to the canvas."""
    left = int(Fraction(box["x"]) * scale) - margin
    top = int(Fraction(box["y"]) * scale) - margin
    right = int(Fraction(box["x"] + box["width"]) * scale) + margin
    bottom = int(Fraction(box["y"] + box["height"]) * scale) + margin
    return (max(0, left), max(0, top),
            min(limit[0], max(0, right)), min(limit[1], max(0, bottom)))


def _compare_page(page: str, base: tuple, cand: tuple,
                  allowed: list[tuple[int, int, int, int]]
                  ) -> dict[str, Any]:
    """Per-pixel difference of one page, attributed to allowed rectangles."""
    (b_loc, b_w, _b_h, b_ch, b_raw) = base
    (c_loc, c_w, _c_h, c_ch, c_raw) = cand
    bx, by, cw, chh = b_loc["crop"]
    cx, cy, cw2, chh2 = c_loc["crop"]
    if (cw, chh) != (cw2, chh2):
        raise ComparisonBlocked(
            f"{page}: located canvases differ in size ({cw}x{chh} vs "
            f"{cw2}x{chh2}); these captures are not comparable")
    changed = 0
    min_x, min_y, max_x, max_y = cw, chh, -1, -1
    unexplained = 0
    u_min_x, u_min_y, u_max_x, u_max_y = cw, chh, -1, -1
    for row in range(chh):
        b_off = ((by + row) * b_w + bx) * b_ch
        c_off = ((cy + row) * c_w + cx) * c_ch
        b_line = b_raw[b_off:b_off + cw * b_ch]
        c_line = c_raw[c_off:c_off + cw * c_ch]
        if b_line == c_line and b_ch == c_ch:
            continue
        for col in range(cw):
            b_px = b_line[col * b_ch:(col + 1) * b_ch]
            c_px = c_line[col * c_ch:(col + 1) * c_ch]
            if b_ch == 1:
                b_px = b_px * 3 + b"\xff"
            elif b_ch == 3:
                b_px += b"\xff"
            if c_ch == 1:
                c_px = c_px * 3 + b"\xff"
            elif c_ch == 3:
                c_px += b"\xff"
            if b_px == c_px:
                continue
            changed += 1
            min_x, min_y = min(min_x, col), min(min_y, row)
            max_x, max_y = max(max_x, col), max(max_y, row)
            if not any(left <= col < right and top <= row < bottom
                       for left, top, right, bottom in allowed):
                unexplained += 1
                u_min_x, u_min_y = min(u_min_x, col), min(u_min_y, row)
                u_max_x, u_max_y = max(u_max_x, col), max(u_max_y, row)
    total = cw * chh
    result: dict[str, Any] = {
        "page": page,
        "canvas_pixels": [cw, chh],
        "pixels_changed": changed,
        "changed_fraction": round(changed / total, 8) if total else 0.0,
        "pixels_unexplained": unexplained,
        "baseline_capture_sha256": b_loc["source_sha256"],
        "candidate_capture_sha256": c_loc["source_sha256"],
        "effective_scale": b_loc["effective_scale"],
    }
    if changed:
        result["changed_box"] = [min_x, min_y, max_x, max_y]
    if unexplained:
        result["unexplained_box"] = [u_min_x, u_min_y, u_max_x, u_max_y]
    if unexplained:
        result["status"] = "fail"
        result["reason"] = (
            f"{unexplained} pixel(s) changed outside every visual the "
            "candidate edited: an unexplained pixel difference")
    elif changed:
        result["status"] = "pass"
        result["reason"] = (
            f"{changed} changed pixel(s), all inside the edited visual(s)")
    else:
        result["status"] = "pass"
        result["reason"] = "rendered identically"
    return result


def compare_renders(baseline_renders: str | Path, candidate_renders: str | Path,
                    *, baseline_report: str | Path,
                    candidate_report: str | Path,
                    margin: int = 0) -> dict[str, Any]:
    """Locate pixel differences in two source-bound captures.

    ``margin`` dilates each edited visual's rectangle by that many canvas
    pixels before attribution. It is a **declared tolerance**, not a
    measurement, so it defaults to 0: a non-zero value must be justified
    by real render evidence that Desktop draws a visual's border or
    shadow outside its declared rectangle, and it is recorded in the
    result so a reviewer can see what was allowed. Overall data-bound
    regression acceptance remains blocked until answer parity is proven.
    """
    baseline_renders = Path(baseline_renders)
    candidate_renders = Path(candidate_renders)
    baseline_report = Path(baseline_report)
    candidate_report = Path(candidate_report)
    if isinstance(margin, bool) or not isinstance(margin, int) or margin < 0:
        raise ComparisonBlocked("margin must be a non-negative integer")

    base_manifest = _load_manifest(baseline_renders, "baseline")
    cand_manifest = _load_manifest(candidate_renders, "candidate")
    _require_bound(base_manifest, baseline_report, "baseline")
    _require_bound(cand_manifest, candidate_report, "candidate")
    if base_manifest["source_sha256"] == cand_manifest["source_sha256"]:
        raise ComparisonBlocked(
            "baseline and candidate are the same source revision; there is "
            "no before/after to review")
    data_proof = _require_data(base_manifest, cand_manifest)

    base_pages = set(base_manifest["page_images"])
    cand_pages = set(cand_manifest["page_images"])
    if base_pages != cand_pages:
        raise ComparisonBlocked(
            "captured page sets differ; added or removed pages must be "
            f"reviewed, not diffed (only in baseline: "
            f"{sorted(base_pages - cand_pages)}; only in candidate: "
            f"{sorted(cand_pages - base_pages)})")

    pages = sorted(base_pages)
    baseline_inventory = _page_inventory(baseline_report, "baseline")
    candidate_inventory = _page_inventory(candidate_report, "candidate")
    base_files = _capture_files(baseline_renders, base_manifest, set(baseline_inventory), "baseline")
    cand_files = _capture_files(candidate_renders, cand_manifest, set(candidate_inventory), "candidate")
    base_scale = _manifest_geometry(base_manifest, baseline_inventory, "baseline")
    cand_scale = _manifest_geometry(cand_manifest, candidate_inventory, "candidate")
    if base_scale != cand_scale:
        raise ComparisonBlocked(f"capture scale differs ({base_scale} vs {cand_scale})")
    if baseline_inventory != candidate_inventory:
        raise ComparisonBlocked("PBIR canvas differs between source page inventories")
    changed_visuals = _changed_visuals(baseline_report, candidate_report, pages)
    base_rects = _rects(baseline_report)
    cand_rects = _rects(candidate_report)

    page_results = []
    for page in pages:
        base_image, base_hash = base_files[page]
        cand_image, cand_hash = cand_files[page]
        page_canvas = baseline_inventory[page]
        base = _canvas_window(base_image, page_canvas, f"baseline/{page}", base_hash)
        cand = _canvas_window(cand_image, page_canvas, f"candidate/{page}", cand_hash)
        scale = Fraction(base[0]["effective_scale"])
        if Fraction(cand[0]["effective_scale"]) != scale:
            raise ComparisonBlocked(
                f"{page}: measured canvas scale differs between captures "
                f"({base[0]['effective_scale']} vs "
                f"{cand[0]['effective_scale']})")
        crop_limit = (base[0]["crop"][2], base[0]["crop"][3])
        # A visual the candidate edited may legitimately change pixels in
        # both its old and its new rectangle.
        allowed = []
        touched = sorted(changed_visuals[page])
        for visual in touched:
            for rects in (base_rects, cand_rects):
                box = rects.get((page, visual))
                if box is not None:
                    allowed.append(_scaled_box(box, scale, margin, crop_limit))
        entry = _compare_page(page, base, cand, allowed)
        entry["edited_visuals"] = touched
        entry["attributed_rects"] = [list(r) for r in allowed]
        if entry["pixels_changed"] and not touched:
            entry["status"] = "fail"
            entry["reason"] = (
                f"{entry['pixels_changed']} pixel(s) changed although no "
                "visual on this page was edited")
        page_results.append(entry)

    failed = [p["page"] for p in page_results if p["status"] == "fail"]
    changed_pages = [p["page"] for p in page_results if p["pixels_changed"]]
    # Matching COUNTROWS hashes do not prove equal answers, model, roles,
    # filters, or interaction state. Report pixel observations while
    # refusing an overall regression verdict until those are evidenced.
    _require_bound(base_manifest, baseline_report, "baseline")
    _require_bound(cand_manifest, candidate_report, "candidate")
    # A capture that changed after its page was measured must not leave a
    # result pointing at stale evidence. Recheck the complete inventories.
    _capture_files(baseline_renders, base_manifest, set(baseline_inventory), "baseline")
    _capture_files(candidate_renders, cand_manifest, set(candidate_inventory), "candidate")
    verdict = "blocked"
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "baseline_source_sha256": base_manifest["source_sha256"],
        "candidate_source_sha256": cand_manifest["source_sha256"],
        "pages_compared": len(page_results),
        "pages_changed": changed_pages,
        "pages_failed": failed,
        "data_proof": data_proof,
        "declared_margin_px": margin,
        "pages": page_results,
        "note": ("Data parity and interaction scope are unproven: matching "
                 "row-count probes do not prove equal report answers. Page "
                 "results describe pixel differences only, not data-bound "
                 "regression or independent G2/G4 review or owner G6."),
    }


def comparison_digest(result: dict[str, Any]) -> str:
    """Stable digest of a comparison result, for sealing in run evidence."""
    return hashlib.sha256(json.dumps(
        result, sort_keys=True, ensure_ascii=False,
        default=str).encode("utf-8")).hexdigest()
