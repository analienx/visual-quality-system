"""P13: exact pixel evidence, blank/tiny/padding negatives, fail-closed binding."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from tests.test_visual_regions import _run_one, _scene_bundle
from vqs.cli import main
from vqs.visual import pixel_quality
from vqs.visual.pixel_quality import (
    PIXEL_SCHEMA,
    POLICY_SCHEMA,
    audit_regions,
    inspect_pixels,
)
from vqs.visual.regions import RegionError, build_regions


def _tile(width=160, height=120, *, marks=(), color=(238, 239, 242)) -> bytes:
    """Synthetic screenshots, not user report data or fabricated OCR."""
    raw = bytearray(bytes(color) * (width * height))
    for x0, y0, x1, y1 in marks:
        for y in range(y0, y1):
            for x in range(x0, x1):
                pos = (y * width + x) * 3
                raw[pos:pos+3] = b"\x13\x29\x61"
    return bytes(raw)


def _inspect(marks=(), *, kind="shapeMap", limits=None):
    return inspect_pixels(_tile(marks=marks), 160, 120, 3,
                          visual_type=kind, requirements=limits)


def test_true_blank_data_visual_is_a_hard_pixel_failure():
    result = _inspect()
    assert result["status"] == "fail"
    assert result["findings"] == [{
        "kind": "rendered_data_visual_blank", "severity": "fail",
        "remedy": "Inspect data readiness/bindings and host errors; repair a candidate and recapture",
    }]
    assert result["metrics"]["foreground_fraction"] == 0


def test_blank_nondata_background_shape_does_not_auto_fail():
    assert _inspect(kind="shape")["status"] == "no_pixel_issue_proven"


def test_tiny_map_is_review_only_without_explicit_design_budget():
    result = _inspect([(65, 47, 95, 73)])
    assert result["status"] == "review_required"
    assert "sparse_visual_needs_review" in {f["kind"] for f in result["findings"]}


def test_tiny_map_fails_with_source_bound_minimum_plot_width():
    result = _inspect([(65, 47, 95, 73)], limits={"min_content_width": 0.68})
    assert result["status"] == "fail"
    assert result["findings"][0]["budget"] == "min_content_width"


def test_thin_frame_cannot_hide_underfilled_data_visual():
    # The border makes the naive occupied rectangle almost the full panel,
    # even though the actual plotted mark is minuscule.
    frame = [(8, 7, 151, 8), (8, 112, 151, 113),
             (8, 7, 9, 113), (150, 7, 151, 113), (79, 58, 81, 60)]
    result = _inspect(frame)
    assert result["metrics"]["content_width_fraction"] > .85
    assert result["status"] == "review_required"
    assert "sparse_visual_needs_review" in {f["kind"] for f in result["findings"]}
    enforced = _inspect(frame, limits={"min_foreground_fraction": .06})
    assert enforced["status"] == "fail"
    assert enforced["findings"][0]["budget"] == "min_foreground_fraction"


def test_map_title_and_frame_cannot_disguise_a_blank_plot():
    # The title and decorative frame give the visual a substantial occupied
    # bounding box, yet no geographic mark is present in the actual body.
    title = (20, 7, 140, 16)
    frame = [(8, 5, 152, 8), (8, 112, 152, 115),
             (8, 5, 11, 115), (149, 5, 152, 115)]
    result = _inspect([title, *frame])
    assert result["metrics"]["foreground_fraction"] > .03
    assert result["metrics"]["map_plot_foreground_pixels"] == 0
    assert result["status"] == "fail"
    assert {item["kind"] for item in result["findings"]} == {
        "rendered_map_plot_blank"}


def test_map_geography_in_body_is_not_mistaken_for_blank_title_only():
    result = _inspect([(20, 7, 140, 16), (24, 32, 138, 99)])
    assert result["metrics"]["map_plot_foreground_pixels"] > 0
    assert result["status"] == "no_pixel_issue_proven"


def test_blank_non_map_card_with_title_is_not_subject_to_map_plot_rule():
    result = _inspect([(20, 7, 140, 16)], kind="cardVisual")
    assert result["status"] == "review_required"
    assert all(item["severity"] == "review" for item in result["findings"])


def test_explicit_foreground_policy_rejects_blank_even_for_nondata_surface():
    result = _inspect(kind="shape", limits={"min_foreground_fraction": 0.04})
    assert result["status"] == "fail"
    assert result["findings"][0]["budget"] == "min_foreground_fraction"


def test_thick_frame_does_not_fool_interior_content_measure():
    frame = [(7, 7, 153, 10), (7, 110, 153, 113),
             (7, 7, 10, 113), (150, 7, 153, 113), (79, 59, 81, 61)]
    report = _inspect(frame)
    assert report["metrics"]["foreground_fraction"] > .035
    assert report["metrics"]["interior_foreground_fraction"] < .02
    assert report["status"] == "review_required"
    enforced = _inspect(frame, limits={"min_interior_foreground_fraction": .05})
    assert enforced["status"] == "fail"
    assert enforced["findings"][0]["budget"] == "min_interior_foreground_fraction"


def test_balanced_full_panel_map_passes_declared_content_budget():
    limits = {"min_content_width": 0.68, "min_content_height": 0.58,
              "max_margin_skew_x": 0.1}
    result = _inspect([(18, 19, 142, 101)], limits=limits)
    assert result["status"] == "no_pixel_issue_proven"
    assert result["metrics"]["content_width_fraction"] > 0.7


def test_content_padding_asymmetry_is_measured_and_can_fail():
    result = _inspect([(5, 24, 75, 100)],
                      limits={"max_margin_skew_x": 0.12})
    assert result["status"] == "fail"
    assert result["findings"][0]["budget"] == "max_margin_skew_x"


def test_empty_interior_under_title_and_footer_is_detected():
    result = _inspect([(12, 8, 130, 15), (12, 102, 130, 112)],
                      kind="decompositionTreeVisual",
                      limits={"max_blank_band": 0.44})
    assert result["status"] == "fail"
    assert result["findings"][0]["budget"] == "max_blank_band"
    assert result["metrics"]["longest_central_blank_band"] > 0.5


def test_sparse_card_remains_valid_without_an_intent_specification():
    result = _inspect([(70, 40, 90, 64)], kind="cardVisual")
    assert result["status"] == "review_required"
    assert all(f["severity"] == "review" for f in result["findings"])


def test_background_without_stable_perimeter_remains_unknown():
    raw = bytearray(_tile())
    for y in range(120):
        for x in range(160):
            rgb = (8, 30, 52) if (x + y) % 2 else (240, 230, 220)
            at = (y * 160 + x) * 3
            raw[at:at+3] = bytes(rgb)
    result = inspect_pixels(bytes(raw), 160, 120, 3, visual_type="shapeMap")
    assert result["status"] == "unknown"
    assert result["findings"] == []


def test_thin_legitimate_shape_does_not_abort_page_or_fail_occupancy():
    tiny = bytes((240, 240, 240)) * (140 * 2)
    result = inspect_pixels(tiny, 140, 2, 3, visual_type="shape")
    assert result["status"] == "not_applicable"
    assert result["metrics"]["pixel_dimensions"] == [140, 2]
    assert inspect_pixels(tiny, 140, 2, 3, visual_type="card")["status"] == "unknown"


def test_uncomposited_alpha_must_not_be_mistaken_for_opaque_content():
    invisible_random_rgb = bytes((3, 118, 249, 0)) * (80 * 80)
    assert inspect_pixels(invisible_random_rgb, 80, 80, 4,
                          visual_type="shapeMap")["status"] == "unknown"
    opaque_white = bytes((249, 249, 249, 255)) * (80 * 80)
    assert inspect_pixels(opaque_white, 80, 80, 4,
                          visual_type="shapeMap")["status"] == "fail"


def test_tiny_pbip_data_visual_yields_unknown_not_uncaught_exception(tmp_path):
    report, bundle = _scene_bundle(tmp_path, extra={
        "v2": {"x": 30, "y": 110, "width": 100, "height": 6, "z": 9}})
    regions = tmp_path / "all-regions"
    build_regions(str(bundle), str(regions), report=str(report))
    result = audit_regions(str(bundle), str(regions), report=str(report))
    lookup = {r["visual_id"]: r for r in result["regions"]}
    assert lookup["v2"]["status"] == "unknown"
    assert result["status"] == "fail"  # The other real card is truly blank.


@pytest.mark.parametrize("bad", [
    {"min_content_width": True}, {"min_content_width": 1.4},
    {"unknown_metric": 0.2},
])
def test_invalid_content_budgets_are_refused(bad):
    with pytest.raises(RegionError, match="invalid"):
        _inspect([(10, 10, 100, 100)], limits=bad)


def _ready(tmp_path):
    report, bundle, regions, built = _run_one(tmp_path)
    return report, bundle, regions, built


def _policy(built, *, limits=None):
    return {
        "schema": POLICY_SCHEMA,
        "source_sha256": built["source_sha256"],
        "bundle_sha256": built["bundle_sha256"],
        "targets": [{"page_id": "p1", "visual_id": "v1",
                     "requirements": limits or {"min_content_width": 0.1}}],
    }


def test_audit_reverifies_exact_report_bundle_crops_and_binds_receipt(tmp_path):
    report, bundle, regions, built = _ready(tmp_path)
    result = audit_regions(str(bundle), str(regions), report=str(report))
    assert result["schema"] == PIXEL_SCHEMA
    assert result["source_sha256"] == built["source_sha256"]
    assert result["bundle_sha256"] == built["bundle_sha256"]
    assert result["regions_index_sha256"] == hashlib.sha256(
        (regions / "regions.json").read_bytes()).hexdigest()
    assert result["visual_acceptance"] == "not_run"
    assert len(result["regions"]) == 1
    assert result["regions"][0]["target_pixels"] == [97, 72]
    assert result["regions"][0]["crop_sha256"] == built["regions"][0]["crop_sha256"]


@pytest.mark.parametrize("mutation", ["source", "bundle", "selector", "duplicate", "threshold"])
def test_policy_cannot_use_stale_source_or_invent_unobserved_visual(tmp_path, mutation):
    report, bundle, regions, built = _ready(tmp_path)
    policy = _policy(built)
    if mutation == "source":
        policy["source_sha256"] = "f" * 64
    elif mutation == "bundle":
        policy["bundle_sha256"] = "e" * 64
    elif mutation == "selector":
        policy["targets"][0]["visual_id"] = "other-visual"
    elif mutation == "duplicate":
        policy["targets"].append(copy.deepcopy(policy["targets"][0]))
    else:
        policy["targets"][0]["requirements"]["max_blank_band"] = -1
    with pytest.raises(RegionError, match="policy|selector|threshold"):
        audit_regions(str(bundle), str(regions), report=str(report), policy=policy)


def test_modified_png_blocks_audit_even_if_original_policy_passes(tmp_path):
    report, bundle, regions, built = _ready(tmp_path)
    path = regions / built["regions"][0]["crop_image"]
    path.write_bytes(path.read_bytes()[:-2] + b"xx")
    with pytest.raises((RegionError, ValueError)):
        audit_regions(str(bundle), str(regions), report=str(report),
                      policy=_policy(built))


def test_crop_swapped_after_initial_verification_still_blocks_audit(tmp_path, monkeypatch):
    report, bundle, regions, built = _ready(tmp_path)
    original_verify = pixel_quality.verify_regions

    def verified_then_modified(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        path = regions / built["regions"][0]["crop_image"]
        path.write_bytes(path.read_bytes() + b"tamper")
        return result

    monkeypatch.setattr(pixel_quality, "verify_regions", verified_then_modified)
    with pytest.raises(RegionError, match="drifted"):
        audit_regions(str(bundle), str(regions), report=str(report))


def test_cli_audit_emits_private_measured_receipt_without_approval(tmp_path, capsys):
    report, bundle, regions, _ = _ready(tmp_path)
    code = main(["regions", "audit", str(bundle), str(regions),
                 "--report", str(report)])
    payload = json.loads(capsys.readouterr().out)
    assert code == {"fail": 1, "unknown": 2,
                    "review_required": 0, "no_pixel_issue_proven": 0}[payload["status"]]
    assert payload["visual_acceptance"] == "not_run"
    assert "regions" in payload


def test_policy_violation_exits_nonzero_in_integrated_cli(tmp_path, capsys):
    report, bundle, regions, built = _ready(tmp_path)
    policy = _policy(built, limits={"min_content_width": 1.0})
    (tmp_path / "pixel-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    code = main(["regions", "audit", str(bundle), str(regions),
                 "--policy", str(tmp_path / "pixel-policy.json"),
                 "--report", str(report)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "fail"
    assert payload["policy_targets"] == 1
    # This real synthetic review bundle is a fully blank card; the stronger
    # unconditioned blank-render failure fires before any occupancy budget.
    assert any(f["kind"] == "rendered_data_visual_blank"
               for row in payload["regions"] for f in row["findings"])
