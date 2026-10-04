"""F20 RED: omitting the editor must not bypass independence.

check_reviewer skips the self-review check when the fixer id is empty,
and acceptance line 214 passes a reviewer with an absent editor. Both
identities of the correct type are required, plus the independent
reviewer capability rule that already exists. Missing/blank/non-string
editor must block; matching identities fail (already covered).
"""
from vqs.acceptance import run_acceptance
from vqs.policy import REQUIRED
from vqs.review import adjudicate_bundle

SOURCE = "c" * 64
REASON = "All labels legible at the target size on the fresh full-canvas render."


def _observations(status="pass"):
    return [{"id": check, "criterion": check, "status": status,
             "reason": REASON, "severity": None, "region": None,
             "visual_id": "page", "proposed_fix": ""}
            for check in REQUIRED["report"]]


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


def _identity_rules(findings):
    return [row for row in findings
            if any(key in row.get("rule", "")
                   for key in ("reviewer", "fixer", "editor", "independent"))]


def test_f20_missing_fixer_blocks_adjudication() -> None:
    """RED: bundle with blank fixer must not pass independence."""
    result = adjudicate_bundle(_bundle(fixer_id=""))
    assert result["verdict"] != "pass"
    assert _identity_rules(result["findings"]) != []


def test_f20_nonstring_fixer_blocks_adjudication() -> None:
    """RED: bundle with non-string fixer must not pass independence."""
    result = adjudicate_bundle(_bundle(fixer_id=["executor-1"]))
    assert result["verdict"] != "pass"
    assert _identity_rules(result["findings"]) != []


def test_f20_missing_editor_blocks_acceptance() -> None:
    """RED: acceptance with reviewer but no editor must flag identity."""
    result = run_acceptance({"reviewer_id": "reviewer-1"})
    assert _identity_rules(result["findings"]) != []


def test_f20_nonstring_editor_blocks_acceptance() -> None:
    """RED: acceptance with non-string editor must flag identity."""
    result = run_acceptance({"reviewer_id": "reviewer-1",
                             "editor_id": ["executor-1"]})
    assert _identity_rules(result["findings"]) != []
