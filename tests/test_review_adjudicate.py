"""Review adjudication tests (WP-07 static half): synthetic bundles only.

No pixels, models, or renders involved; perceptual judgment itself remains
the job of a capable image reviewer on real evidence. Observation checks reuse
the canonical evidence validator, so this module and verify_review cannot drift.
"""
from vqs.policy import REQUIRED
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


def test_clean_bundle_passes() -> None:
    assert adjudicate_bundle(_bundle()) == {"verdict": "pass", "findings": []}


def test_same_reviewer_and_editor_fails() -> None:
    result = adjudicate_bundle(_bundle(reviewer={"id": "executor-1"}))
    assert result["verdict"] == "fail"
    assert any(row["rule"] == "own_review_forbidden" for row in result["findings"])


def test_missing_reviewer_blocks() -> None:
    """Supervisor #22 P0-6: reviewer {} plus observations can never pass."""
    result = adjudicate_bundle(_bundle(reviewer={}))
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "independent_reviewer_required"
               for row in result["findings"])
    wrong_role = _bundle(reviewer={"id": "reviewer-1", "role": "text_only_model"})
    result = adjudicate_bundle(wrong_role)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "independent_reviewer_required"
               for row in result["findings"])


def test_single_observation_cannot_pass() -> None:
    """Supervisor #22 P0-6: one passing observation is not complete criteria."""
    thin = _bundle()
    thin["pages"][0]["observations"] = [{
        "id": "text_legibility", "criterion": "text_legibility",
        "status": "pass", "reason": REASON}]
    result = adjudicate_bundle(thin)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "review_observations_incomplete"
               for row in result["findings"])


def test_stale_image_and_missing_capability() -> None:
    stale = _bundle()
    stale["pages"][0]["image_source_sha256"] = "e" * 64
    result = adjudicate_bundle(stale)
    assert result["verdict"] == "fail"
    assert any(row["rule"] == "stale_image" for row in result["findings"])
    nocap = _bundle(image_capability={"available": False})
    result = adjudicate_bundle(nocap)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "missing_image_capability" for row in result["findings"])


def test_missing_calibration_and_reasonless_verdicts_block() -> None:
    nocal = _bundle(calibration={"full_canvas": True})
    result = adjudicate_bundle(nocal)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] in ("calibration_missing", "calibration_invalid")
               for row in result["findings"])
    mismatch = _bundle()
    mismatch["pages"][0]["pixels"] = [500, 400]
    result = adjudicate_bundle(mismatch)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "calibration_mismatch" for row in result["findings"])
    noreason = _bundle()
    noreason["pages"][0]["observations"][0]["reason"] = ""
    result = adjudicate_bundle(noreason)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "observation_unsubstantiated"
               for row in result["findings"])


def test_missing_data_readiness_blocks() -> None:
    """Supervisor #22 P1-10: blank/unproven data can never carry approval."""
    blank = _bundle(data_readiness={"populated": False, "method": "scoped-dax-probe"})
    result = adjudicate_bundle(blank)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "data_unpopulated" for row in result["findings"])
    missing = _bundle()
    del missing["data_readiness"]
    result = adjudicate_bundle(missing)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "data_readiness_missing" for row in result["findings"])


def test_failing_observation_and_unknown_verdicts() -> None:
    bad = _bundle()
    bad["pages"][0]["observations"][0].update(
        status="fail", severity="high", region=[0.1, 0.1, 0.5, 0.4],
        proposed_fix="Increase title size to 20pt and re-render the page.")
    result = adjudicate_bundle(bad)
    assert result["verdict"] == "fail"
    assert any(row["rule"] == "visual_defect" for row in result["findings"])
    unlocated = _bundle()
    unlocated["pages"][0]["observations"][0]["status"] = "fail"
    result = adjudicate_bundle(unlocated)
    assert result["verdict"] == "blocked"
    assert any(row["rule"] == "issue_lacks_location_or_repair"
               for row in result["findings"])
    unknown = _bundle()
    unknown["pages"][0]["observations"][0]["status"] = "unknown"
    assert adjudicate_bundle(unknown)["verdict"] == "blocked"
    assert adjudicate_bundle("not-a-bundle")["verdict"] == "blocked"
