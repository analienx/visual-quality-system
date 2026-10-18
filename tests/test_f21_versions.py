"""F21 RED: adjudication must enforce schema and policy versions.

verify_review rejects foreign/missing policy/schema (evidence.py:349),
but adjudicate_bundle never checks them: a populated review with a
foreign policy passes public adjudication. M3 shares canonical policy
validation across entry points; CLI adjudication and verify_review get
identical mismatched payloads there.
"""
from vqs.evidence import verify_review
from vqs.policy import POLICY_VERSION, REQUIRED
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


def _version_rules(findings):
    return [row for row in findings
            if any(key in row.get("rule", "")
                   for key in ("polic", "schema", "version"))]


def test_f21_missing_versions_block_adjudication() -> None:
    """RED: bundle without schema/policy versions must not pass."""
    result = adjudicate_bundle(_bundle())
    assert result["verdict"] != "pass"
    assert _version_rules(result["findings"]) != []


def test_f21_foreign_policy_blocks_adjudication() -> None:
    """RED: bundle with a foreign policy version must not pass."""
    result = adjudicate_bundle(_bundle(schema=1, policy_version="9.9.9"))
    assert result["verdict"] != "pass"
    assert _version_rules(result["findings"]) != []


def test_f21_verify_review_already_rejects_mismatch() -> None:
    """Control (passes now): verify_review enforces what adjudication omits."""
    pages = [{"id": "page-1", "sha256": "d" * 64, "pixels": [500, 500]}]
    review = {"schema": 1, "policy_version": "9.9.9", "surface": "report",
              "source_sha256": SOURCE}
    findings = verify_review("report", SOURCE, pages, review, "executor-1")
    assert any(row.get("rule") == "review_policy_or_source_mismatch"
               for row in findings)


def test_f21_current_policy_version_is_expected() -> None:
    """Anchor: the canonical version the fix must require."""
    assert POLICY_VERSION == "1.0.0"
