"""P15: source-bound all-visual coverage and no fake G2/G4/G6 acceptance."""
from __future__ import annotations

import json

import pytest

from tests.test_review_canvas_bundle import _ready_bundle
from tests.test_visual_regions import SCHEMA, _run_one
from vqs.cli import main
from vqs.pbir import source_digest
from vqs.quality_assurance import SCHEMA as ASSURANCE_SCHEMA
from vqs.quality_assurance import assess_report_readiness
from vqs.review.bundle import pack
from vqs.visual.regions import RegionError, build_regions


def _shape_fixture(tmp_path, *, extra=False, partial=False):
    report, renders, bundle = _ready_bundle(tmp_path)
    visuals = report / "definition/pages/p1/visuals"
    visuals.mkdir()
    ids = ("v1", "v2") if extra else ("v1",)
    for index, visual_id in enumerate(ids):
        folder = visuals / visual_id
        folder.mkdir()
        (folder / "visual.json").write_text(json.dumps({
            "$schema": SCHEMA, "name": visual_id,
            "visual": {"visualType": "shape"},
            "position": {"x": 14 + index * 100, "y": 20,
                         "width": 80, "height": 60, "z": index + 1},
        }), encoding="utf-8")
    manifest_path = renders / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_sha256"] = source_digest(report)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pack(str(report), str(renders), str(bundle), "owner-fixer")
    regions = tmp_path / "all-regions"
    selectors = [("p1", "v1")] if partial else None
    build_regions(str(bundle), str(regions), report=str(report), selectors=selectors)
    return report, bundle, regions


def test_real_source_and_pixels_do_not_mint_independent_release_approval(tmp_path):
    report, bundle, regions = _shape_fixture(tmp_path)
    result = assess_report_readiness(str(bundle), str(regions), report=str(report))
    assert result["schema"] == ASSURANCE_SCHEMA
    assert result["premium"]["status"] in {"advisory", "blocked"}
    assert result["premium"]["evidence_basis"] == "PBIR static, not independent rendered approval"
    assert result["release_scope"] == "powerbi-core"
    assert "DOCX" not in " ".join(result["required_next_evidence"])
    assert result["verdict"] == "blocked"
    assert result["scope"]["full_report"] is True
    assert result["scope"]["expected_visuals"] == 1
    assert result["scope"]["covered_visuals"] == 1
    assert result["gates"] == {
        "G0_verified_source_and_images": "pass",
        "G2_independent_visual_design_review": "blocked",
        "G4_live_interaction_parity": "blocked",
        "G6_independent_multi_artifact_release": "blocked",
    }
    assert result["runtime"]["interactive"] == "blocked"


def test_partial_visual_inventory_is_an_explicit_blocker(tmp_path):
    report, bundle, regions = _shape_fixture(tmp_path, extra=True, partial=True)
    result = assess_report_readiness(str(bundle), str(regions), report=str(report))
    assert result["verdict"] == "blocked"
    assert result["blocked_reasons"] == ["visual_inventory_uninspected"]
    assert result["scope"]["missing_visuals"] == [{"page_id": "p1", "visual_id": "v2"}]


def test_current_verified_blank_card_fails_product_preacceptance(tmp_path):
    report, bundle, regions, _ = _run_one(tmp_path)
    result = assess_report_readiness(str(bundle), str(regions), report=str(report))
    assert result["verdict"] == "fail"
    assert "verified_rendered_pixel_defect" in result["failures"]
    assert result["pixel"]["status"] == "fail"
    assert result["gates"]["G6_independent_multi_artifact_release"] == "blocked"


def test_stale_report_and_missing_page_cannot_be_laundered_into_assurance(tmp_path):
    report, bundle, regions = _shape_fixture(tmp_path)
    with pytest.raises(RegionError, match="page scope"):
        assess_report_readiness(str(bundle), str(regions), report=str(report),
                                pages=["invented-page"])
    (report / "definition/pages/p1/visuals/v1/visual.json").write_text("{}")
    with pytest.raises((RegionError, ValueError), match="source|drift|mismatch"):
        assess_report_readiness(str(bundle), str(regions), report=str(report))


def test_wrong_source_runtime_claim_fails_even_if_it_says_ui_pass(tmp_path):
    report, bundle, regions = _shape_fixture(tmp_path)
    fake = {"source_sha256": "a" * 64, "interactive": "pass",
            "evidence_consistency": "pass"}
    result = assess_report_readiness(
        str(bundle), str(regions), report=str(report),
        oracle=fake, trace=fake, captures_dir=str(tmp_path))
    assert result["verdict"] == "fail"
    assert result["runtime"]["interactive"] == "blocked"
    assert result["runtime"]["evidence_consistency"] == "fail"


def test_cli_assurance_runs_real_pixel_check_and_never_prints_release_pass(tmp_path, capsys):
    report, bundle, regions, _ = _run_one(tmp_path)
    output = tmp_path / "assurance.json"
    args = ["assurance", str(bundle), str(regions), "--report", str(report),
            "--out", str(output)]
    assert main(args) == 1
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text())
    assert printed == saved
    assert saved["verdict"] == "fail"
    assert main(args) == 2  # Existing private audit must not be overwritten.


def test_cli_clean_synthetic_visual_cannot_become_release_pass(tmp_path, capsys):
    report, bundle, regions = _shape_fixture(tmp_path)
    code = main(["assurance", str(bundle), str(regions),
                 "--report", str(report)])
    output = json.loads(capsys.readouterr().out)
    assert code == 2
    assert output["verdict"] == "blocked"
    assert output["gates"]["G6_independent_multi_artifact_release"] == "blocked"


def test_legacy_combined_assurance_still_requires_word_and_never_approves(tmp_path):
    report, bundle, regions = _shape_fixture(tmp_path)
    result = assess_report_readiness(str(bundle), str(regions), report=str(report),
                                     release_scope="combined")
    assert result["release_scope"] == "combined"
    assert "DOCX" in " ".join(result["required_next_evidence"])
    assert result["verdict"] == "blocked"


@pytest.mark.parametrize("invalid", ["word-docx", "invalid", "", None])
def test_report_assurance_rejects_non_pbip_release_scopes(tmp_path, invalid):
    report, bundle, regions = _shape_fixture(tmp_path)
    with pytest.raises(RegionError, match="PBIP release scope"):
        assess_report_readiness(str(bundle), str(regions), report=str(report),
                                release_scope=invalid)
