"""R12 RED: static adjudication never approves; pixels stay mandatory.

A statically conformant bundle blocks with image_review_required
(plus a static_conformance label) instead of passing; metadata-
only, capability-label-only, duplicate-page, and omitted-page
bundles block. All red pre-R3, green after.
"""
from vqs.policy import POLICY_VERSION, REQUIRED
from vqs.review import adjudicate_bundle

SOURCE = "c" * 64
REASON = "All labels legible at the target size on the fresh full-canvas render."


def _observations(status="pass"):
    return [{"id": check, "criterion": check, "status": status, "reason": REASON,
             "severity": None, "region": None, "visual_id": "page",
             "proposed_fix": ""} for check in REQUIRED["report"]]


def _bundle(**overrides):
    base = {
        "source_sha256": SOURCE,
        "surface": "report",
        "schema": 1,
        "policy_version": POLICY_VERSION,
        "source_pages": ["page-1"],
        "reviewer": {"id": "reviewer-1", "role": "independent_visual_reviewer"},
        "fixer_id": "executor-1",
        "image_capability": {"available": True, "provider": "synthetic-test"},
        "calibration": {"canvas_width": 500, "canvas_height": 500, "scale": 1,
                        "viewport": "500x500@1x", "method": "bridge-screenshot-all"},
        "data_readiness": {"populated": True, "method": "scoped-dax-probe",
                           "checked_at": "2026-10-03T00:00:00Z"},
        "pages": [{
            "id": "page-1",
            "image_sha256": "d" * 64,
            "image_source_sha256": SOURCE,
            "pixels": [500, 500],
            "observations": _observations(),
        }],
    }
    base.update(overrides)
    return base


def test_conformant_bundle_blocks_for_visual_review() -> None:
    """RED R12: checklist-conformant still blocks; pixels decide release.

    R6-E05: form-only coverage is unbound, so static conformance
    fails; the completed form is still adjudicated for every other
    diagnostic. Authority-backed conformance: T09 + R6-E05/E06.
    """
    result = adjudicate_bundle(_bundle())
    assert result["verdict"] == "blocked"
    assert any(row.get("rule") == "image_review_required"
               for row in result["findings"])
    assert any(row.get("rule") == "source_pages_unbound"
               for row in result["findings"])
    assert result.get("static_conformance") == "fail"


def test_metadata_only_bundle_blocks() -> None:
    """RED R12: observations without materialized images never pass."""
    bundle = _bundle()
    for page in bundle["pages"]:
        page.pop("image_sha256", None)
        page.pop("pixels", None)
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"


def test_capability_label_only_blocks() -> None:
    """RED R12: an available-capability flag is not visual approval."""
    bundle = _bundle(image_capability={"available": True,
                                       "provider": "synthetic-test"})
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"


def test_duplicate_pages_block() -> None:
    """RED R12: the same page twice must block, never double-count."""
    bundle = _bundle()
    bundle["pages"] = [dict(bundle["pages"][0]), dict(bundle["pages"][0])]
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"
    assert any("duplicate" in str(row.get("rule", ""))
               for row in result["findings"])


def test_omitted_source_page_blocks() -> None:
    """RED R12: whole-source coverage; an omitted page blocks."""
    bundle = _bundle(source_pages=["page-1", "page-2"])
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"
    assert any("page-2" in str(row.values()) for row in result["findings"])
