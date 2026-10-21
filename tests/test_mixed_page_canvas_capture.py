"""Mixed report/tooltip PBIR canvas capture: page-bound evidence, no false transform."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_capture import _instance, _make_report, _stub
from vqs.capture import capture
from vqs.evidence import check_calibration, image_evidence
from vqs.pbir import source_digest
from vqs.review.bundle import pack, verify


def _mixed(tmp_path: Path) -> Path:
    report = _make_report(tmp_path)
    pages = report / "definition/pages"
    (pages / "tooltip").mkdir()
    (pages / "tooltip/page.json").write_text(
        json.dumps({"displayName": "Tooltip", "width": 350, "height": 250}),
        encoding="utf-8")
    (report / "definition/pages.json").write_text(
        json.dumps({"pageOrder": ["p1", "tooltip"]}), encoding="utf-8")
    return report


def test_capture_binds_mixed_page_sizes_without_claiming_calibration(tmp_path, monkeypatch):
    report = _mixed(tmp_path)
    _stub(monkeypatch, report, [_instance(report)], png_pages=("p1", "tooltip"))
    renders = tmp_path / "renders"
    manifest = capture(str(report), str(renders), pid=111)
    assert manifest["source_sha256"] == source_digest(report)
    assert set(manifest["page_images"]) == {"p1", "tooltip"}
    c = manifest["calibration"]
    assert c["geometry_calibration"] == "blocked"
    assert c["page_canvases"] == {"p1": [1280, 720], "tooltip": [350, 250]}
    assert "mixed-page-canvases" in c["geometry_reason"]
    assert check_calibration(c) == []
    assert manifest["canvas_review"]["status"] == "blocked"
    assert len(manifest["canvas_review"]["page_images"]) == 0
    # The pixel decoder and report inventory are still independently bound.
    info, issues = image_evidence(renders, source_digest(report),
                                  ["p1", "tooltip"],
                                  canvases={"p1": [1280, 720],
                                            "tooltip": [350, 250]})
    assert len(info) == 2
    assert not any(i["rule"] == "render_canvas_mismatch" for i in issues)
    assert any(i["rule"] == "data_readiness_missing" for i in issues)


def test_mixed_canvas_bundle_rejects_tampered_page_geometry(tmp_path, monkeypatch):
    report = _mixed(tmp_path)
    _stub(monkeypatch, report, [_instance(report)], png_pages=("p1", "tooltip"))
    renders = tmp_path / "renders"
    capture(str(report), str(renders), pid=111)
    # Synthetic modeling-readiness receipt for a *unit test* only. Real
    # capture still blocks bundling if actual model evidence is absent.
    manifest_path = renders / "capture-manifest.json"
    fabricated_fixture_receipt = json.loads(manifest_path.read_text())
    fabricated_fixture_receipt["data_readiness"] = {
        "populated": True, "method": "unit-test-only-synthetic-model",
        "scope": {}, "rowcount": 3, "query_hash": "synthetic"}
    manifest_path.write_text(json.dumps(fabricated_fixture_receipt),
                             encoding="utf-8")
    bundle = tmp_path / "bundle"
    pack(str(report), str(renders), str(bundle), "isolated-fixture-author")
    authority = verify(str(bundle), str(report))
    assert authority["source_sha256"] == source_digest(report)
    manifest = json.loads((renders / "capture-manifest.json").read_text())
    manifest["calibration"]["page_canvases"]["tooltip"] = [1280, 720]
    (renders / "capture-manifest.json").write_text(json.dumps(manifest),
                                                    encoding="utf-8")
    tampered = tmp_path / "bad-bundle"
    # Invalid per-page canvases must be rejected before an untrusted
    # bundle is sealed, rather than accepted and detected only on review.
    with pytest.raises(ValueError, match="render_canvas_mismatch"):
        pack(str(report), str(renders), str(tampered),
             "isolated-fixture-author")


def test_malformed_per_page_calibration_blocks():
    base = {"canvas_width": 1280, "canvas_height": 720, "scale": 2,
            "method": "bridge-page-identity", "geometry_calibration": "blocked",
            "geometry_reason": "mixed-page-canvases",
            "page_canvases": {"p1": [1280, -1]}}
    assert check_calibration(base)[0]["rule"] == "calibration_page_canvases_invalid"
    base["page_canvases"] = {"p1": [1280, 720]}
    base["geometry_calibration"] = "proven"
    assert check_calibration(base)[0]["rule"] == "calibration_page_canvases_invalid"
