"""Rendered before/after regression review: attribution and fail-closed cases.

Uses the committed fictional Contoso PBIR for real visual rectangles and real
source digests, plus controlled synthetic Desktop screenshots whose canvas the
measured extractor locates exactly. Every blocking condition has a test,
because a comparison that cannot be trusted must never read as "no regression".
"""
from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from vqs.pbir import source_digest
from vqs.visual.compare import (
    ComparisonBlocked,
    compare_renders,
    comparison_digest,
)

FIXTURE = (Path(__file__).resolve().parents[1] / "examples" /
           "contoso-retail" / "Contoso Retail.Report")
PAGE = "Executive_overview"
EDITED = "card-b8ef7dc2"          # x 336, y 104, w 296, h 96
CANVAS = (1280, 720)              # the fixture's PBIR canvas
# `_dotted_width` always reports a multiple of the 6px dash period, so the
# synthetic page edge is 1920px wide: an exact, uniform 3/2 scale onto the
# 1280x720 PBIR canvas. Marks below are therefore in *canvas pixels*, which
# are PBIR units x 3/2.
SCALE = 3, 2
PAGE_W, PAGE_H = 1920, 1080
IMG_W, IMG_H = 1980, 1200
TOP_Y = 60                        # dotted page edge row in the synthetic host
STROKE = 3
CROP_TOP = TOP_Y + STROKE         # 63; canvas row 0 sits here
# PBIR y 200..216 is a band no visual on this page covers (the cards end at
# y=200, the next row starts at y=216) and PBIR x=100 is clear there.
GAP = (150, 304, 190, 312)                 # PBIR ~(100, 202.7)-(126.7, 208)
# card-b8ef7dc2 is PBIR x 336..632, y 104..200 -> canvas 504..948, 156..300.
INSIDE_EDITED = (520, 170, 560, 190)
JUST_OUTSIDE_EDITED = (948, 170, 952, 190)  # 4px past its right edge


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def _scene(path: Path, *, marks=(), seam: bool = True) -> Path:
    """A Desktop host frame whose page edge measures exactly 1920x1080.

    `marks` are canvas-relative boxes painted in a distinct colour, so a
    test can place a rendered difference at a chosen place on the page.
    Rows are assembled from prebuilt templates: a per-pixel Python loop
    over two million pixels per image would dominate the test run.
    """
    bottom_y = TOP_Y + STROKE + PAGE_H
    plain = bytearray([255, 255, 255] * IMG_W)
    if seam:
        plain[3 * (PAGE_W + 1):3 * (PAGE_W + 2)] = bytes([209, 213, 219])
        for x in range(PAGE_W + 2, IMG_W):
            plain[3 * x:3 * x + 3] = bytes([249, 250, 251])
    dotted = bytearray(plain)
    for x in range(PAGE_W):
        if x % 6 in (2, 3, 4):
            dotted[3 * x:3 * x + 3] = bytes([75, 85, 99])
    content = bytearray(plain)          # identical in every capture
    for x in range(25, 180):
        content[3 * x:3 * x + 3] = bytes([12, 75, 170])
    painted: dict[int, list[tuple[int, int]]] = {}
    for x0, y0, x1, y1 in marks:
        for y in range(y0, y1):
            painted.setdefault(CROP_TOP + y, []).append((x0, x1))
    data = bytearray()
    for y in range(IMG_H):
        if TOP_Y <= y < TOP_Y + STROKE or bottom_y <= y < bottom_y + STROKE:
            row = dotted
        elif y == CROP_TOP + 600:
            row = content
        else:
            row = plain
        if y in painted:
            row = bytearray(row)
            for x0, x1 in painted[y]:
                for x in range(x0, x1):
                    row[3 * x:3 * x + 3] = bytes([200, 30, 40])
        data.append(0)
        data.extend(row)
    head = struct.pack(">IIBBBBB", IMG_W, IMG_H, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", head)
                     + _chunk(b"IDAT", zlib.compress(bytes(data), 6))
                     + _chunk(b"IEND", b""))
    return path


def _capture(renders: Path, report: Path, *, marks=(), pages=(PAGE,),
             seam: bool = True, **overrides) -> Path:
    renders.mkdir(parents=True, exist_ok=True)
    images = {}
    for page in pages:
        _scene(renders / f"{page}.png",
               marks=marks if page == PAGE else (), seam=seam)
        images[page] = f"{page}.png"
    manifest = {
        "source_sha256": source_digest(report),
        "page_images": images,
        "files": {},
        "pixels": {page: [IMG_W, IMG_H] for page in pages},
        "canvas": list(CANVAS),
        "scale": 1,
        "bridge_version": [1, 0, 0],
        "desktop": {"desktop_version": "2.159"},
        "calibration": {"canvas_width": CANVAS[0],
                        "canvas_height": CANVAS[1], "scale": 1},
        "modeling": {"status": "ready"},
        "data_readiness": {"populated": True, "rowcount": 42,
                           "query_hash": "a" * 64,
                           "method": "modeling-mcp:repeat-query"},
    }
    manifest.update(overrides)
    (renders / "capture-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return renders


def _edit_visual(report: Path, page: str = PAGE, visual: str = EDITED) -> None:
    """A real, benign PBIR edit, so this visual counts as edited."""
    path = report / f"definition/pages/{page}/visuals/{visual}/visual.json"
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    doc.setdefault("visual", {}).setdefault("objects", {})
    doc["visual"]["objects"].setdefault("general", [{}])
    doc["visual"]["objects"]["general"][0].setdefault("properties", {})
    doc["visual"]["objects"]["general"][0]["properties"]["vqsTestMarker"] = {
        "expr": {"Literal": {"Value": "'edited'"}}}
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


@pytest.fixture
def pair(tmp_path: Path):
    """A baseline report and an edited candidate, both real PBIR trees."""
    base = tmp_path / "base.Report"
    cand = tmp_path / "cand.Report"
    shutil.copytree(FIXTURE, base)
    shutil.copytree(FIXTURE, cand)
    _edit_visual(cand)
    assert source_digest(base) != source_digest(cand)
    return base, cand


def _run(tmp_path, base, cand, *, base_marks=(), cand_marks=(), **kw):
    b = _capture(tmp_path / "b", base, marks=base_marks,
                 **kw.pop("base_overrides", {}))
    c = _capture(tmp_path / "c", cand, marks=cand_marks,
                 **kw.pop("cand_overrides", {}))
    return compare_renders(b, c, baseline_report=base,
                           candidate_report=cand, **kw)


# --- positive: difference confined to the visual that was edited ------

def test_difference_inside_the_edited_visual_passes(tmp_path, pair):
    base, cand = pair
    result = _run(tmp_path, base, cand, cand_marks=(INSIDE_EDITED,))
    assert result["verdict"] == "pass", result
    page = result["pages"][0]
    assert page["pixels_changed"] == 40 * 20
    assert page["pixels_unexplained"] == 0
    assert page["edited_visuals"] == [EDITED]
    assert "unexplained_box" not in page
    assert result["data_proof"]["query_hash"] == "a" * 64
    assert result["declared_margin_px"] == 0
    assert len(comparison_digest(result)) == 64


def test_identical_renders_pass_and_say_so(tmp_path, pair):
    base, cand = pair
    result = _run(tmp_path, base, cand)
    assert result["verdict"] == "pass"
    assert result["pages_changed"] == []
    assert result["pages"][0]["reason"] == "rendered identically"


# --- negative: a rendered change the source does not explain ----------

def test_change_outside_every_edited_visual_fails(tmp_path, pair):
    """The core guarantee: an unexplained rendered regression is a failure."""
    base, cand = pair
    result = _run(tmp_path, base, cand, cand_marks=(GAP,))
    assert result["verdict"] == "fail", result
    page = result["pages"][0]
    assert page["status"] == "fail"
    assert page["pixels_unexplained"] == 40 * 8
    assert page["unexplained_box"] == [150, 304, 189, 311]
    assert "outside every visual" in page["reason"]
    assert result["pages_failed"] == [PAGE]


def test_change_with_no_edited_visual_fails(tmp_path):
    """Pixels moved although the candidate edited nothing on that page."""
    base = tmp_path / "base.Report"
    cand = tmp_path / "cand.Report"
    shutil.copytree(FIXTURE, base)
    shutil.copytree(FIXTURE, cand)
    # Edit a *different* page, so this page has no edited visual at all.
    _edit_visual(cand, page="Products_brands", visual="product-opportunity")
    result = _run(tmp_path, base, cand, cand_marks=(INSIDE_EDITED,))
    assert result["verdict"] == "fail"
    page = result["pages"][0]
    assert page["edited_visuals"] == []
    assert "no visual on this page was edited" in page["reason"]


def test_declared_margin_is_recorded_and_bounded(tmp_path, pair):
    base, cand = pair
    # One pixel outside the edited rect: refused at margin 0...
    just_outside = JUST_OUTSIDE_EDITED
    strict = _run(tmp_path / "s", base, cand, cand_marks=(just_outside,))
    assert strict["verdict"] == "fail"
    # ...and attributable only when a tolerance is explicitly declared.
    lenient = _run(tmp_path / "l", base, cand,
                   cand_marks=(just_outside,), margin=4)
    assert lenient["verdict"] == "pass"
    assert lenient["declared_margin_px"] == 4


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2", None])
def test_margin_must_be_a_non_negative_integer(tmp_path, pair, bad):
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="non-negative integer"):
        _run(tmp_path, base, cand, margin=bad)


# --- blocked: the comparison cannot be trusted ------------------------

def test_unproven_data_population_blocks(tmp_path, pair):
    """A cache-less report renders (Blank) and still captures."""
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="data_population: unproven"):
        _run(tmp_path, base, cand, cand_overrides={
            "modeling": {"status": "skipped",
                         "data_population": "unproven"}})


def test_missing_data_readiness_blocks(tmp_path, pair):
    base, cand = pair
    manifest = {"modeling": {"status": "ready"}}
    with pytest.raises(ComparisonBlocked, match="no data_readiness"):
        _run(tmp_path, base, cand,
             cand_overrides={**manifest, "data_readiness": None})


def test_unpopulated_report_blocks(tmp_path, pair):
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="not populated"):
        _run(tmp_path, base, cand, cand_overrides={
            "data_readiness": {"populated": False, "query_hash": "a" * 64}})


def test_different_data_between_captures_blocks(tmp_path, pair):
    """Different data means a pixel difference is not attributable."""
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="saw different data"):
        _run(tmp_path, base, cand, cand_overrides={
            "data_readiness": {"populated": True, "query_hash": "b" * 64}})


def test_missing_query_hash_blocks(tmp_path, pair):
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="no query_hash"):
        _run(tmp_path, base, cand, cand_overrides={
            "data_readiness": {"populated": True}})


def test_capture_bound_to_another_revision_blocks(tmp_path, pair):
    """A stale capture must never be compared as if it were current."""
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="stale evidence"):
        _run(tmp_path, base, cand,
             cand_overrides={"source_sha256": "c" * 64})


def test_same_revision_on_both_sides_blocks(tmp_path, pair):
    base, _cand = pair
    with pytest.raises(ComparisonBlocked, match="same source revision"):
        _run(tmp_path, base, base)


def test_page_set_difference_blocks(tmp_path, pair):
    base, cand = pair
    b = _capture(tmp_path / "b", base, pages=(PAGE,))
    c = _capture(tmp_path / "c", cand, pages=(PAGE, "Products_brands"))
    with pytest.raises(ComparisonBlocked, match="page sets differ"):
        compare_renders(b, c, baseline_report=base, candidate_report=cand)


def test_canvas_difference_blocks(tmp_path, pair):
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="PBIR canvas differs"):
        _run(tmp_path, base, cand, cand_overrides={"canvas": [1024, 576]})


def test_scale_difference_blocks(tmp_path, pair):
    base, cand = pair
    with pytest.raises(ComparisonBlocked, match="capture scale differs"):
        _run(tmp_path, base, cand, cand_overrides={"scale": 2})


def test_unmeasurable_canvas_blocks(tmp_path, pair):
    """A changed page whose canvas cannot be located is blocked, not passed."""
    base, cand = pair
    b = _capture(tmp_path / "b", base)
    c = _capture(tmp_path / "c", cand, marks=(INSIDE_EDITED,), seam=False)
    with pytest.raises(ComparisonBlocked, match="canvas not measurable"):
        compare_renders(b, c, baseline_report=base, candidate_report=cand)


@pytest.mark.parametrize(("body", "needle"), [
    (None, "unreadable"),
    ("not json", "malformed"),
    ("[]", "not an object"),
    ('{"source_sha256": "short"}', "lacks a usable source digest"),
    ('{"source_sha256": "' + "a" * 64 + '", "page_images": {}}',
     "lacks a usable source digest"),
    ('{"source_sha256": "' + "a" * 64 + '", "page_images": {"p": "p.png"},'
     ' "canvas": [0, 720]}', "lacks a usable source digest"),
])
def test_malformed_manifest_blocks(tmp_path, pair, body, needle):
    """Wrong-shaped but valid JSON must block, never crash."""
    base, cand = pair
    b = _capture(tmp_path / "b", base)
    c = _capture(tmp_path / "c", cand)
    target = c / "capture-manifest.json"
    if body is None:
        target.unlink()
    else:
        target.write_text(body, encoding="utf-8")
    with pytest.raises(ComparisonBlocked, match=needle):
        compare_renders(b, c, baseline_report=base, candidate_report=cand)


# --- CLI: exit 0 pass / 1 regression / 2 blocked -----------------------

def test_cli_exit_codes_and_out_file(tmp_path, pair, capsys):
    from vqs.cli import main

    base, cand = pair
    b = _capture(tmp_path / "b", base)
    ok = _capture(tmp_path / "ok", cand, marks=(INSIDE_EDITED,))
    bad = _capture(tmp_path / "bad", cand, marks=(GAP,))

    out = tmp_path / "comparison.json"
    code = main(["compare-renders", str(b), str(ok),
                 "--baseline-report", str(base),
                 "--candidate-report", str(cand), "--out", str(out)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["verdict"] == "pass"
    assert printed["schema"] == "vqs.render-comparison/1"
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "pass"

    code = main(["compare-renders", str(b), str(bad),
                 "--baseline-report", str(base),
                 "--candidate-report", str(cand)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert printed["verdict"] == "fail"
    assert printed["pages_failed"] == [PAGE]

    blocked = _capture(tmp_path / "blocked", cand,
                       modeling={"status": "skipped",
                                 "data_population": "unproven"})
    code = main(["compare-renders", str(b), str(blocked),
                 "--baseline-report", str(base),
                 "--candidate-report", str(cand)])
    printed = json.loads(capsys.readouterr().out)
    assert code == 2
    assert printed["verdict"] == "blocked"
    assert "data_population: unproven" in printed["reason"]


def test_cli_accepts_pbip_paths(tmp_path, pair, capsys):
    """A user passes the .pbip they opened, not the inner *.Report folder."""
    from vqs.cli import main

    base, cand = pair
    # Give each report a sibling .pbip wrapper, as a real project has.
    for report in (base, cand):
        wrapper = report.parent / f"{report.stem}.pbip"
        wrapper.write_text(json.dumps({
            "version": "1.0",
            "artifacts": [{"report": {"path": report.name}}]}),
            encoding="utf-8")
    b = _capture(tmp_path / "b", base)
    c = _capture(tmp_path / "c", cand, marks=(INSIDE_EDITED,))
    code = main(["compare-renders", str(b), str(c),
                 "--baseline-report", str(base.parent / f"{base.stem}.pbip"),
                 "--candidate-report", str(cand.parent / f"{cand.stem}.pbip")])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0, printed
    assert printed["verdict"] == "pass"
