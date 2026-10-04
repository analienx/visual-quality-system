"""R15 RED: nested artifact provenance is always compared.

Absent/null/string/partial component provenance must issue
finding_missing_provenance; a review note never suppresses a
present nested mismatch; legitimate same-artifact provenance
stays clean. All red pre-R3, green after.
"""
from vqs.contracts.validate import validate_manifest

SOURCE = "a" * 64
OTHER = "b" * 64
ARTIFACT = {"surface": "powerbi", "contract_revision": "1.0.0",
            "source_sha256": SOURCE}


def _manifest(*findings: dict) -> dict:
    return {"artifact": dict(ARTIFACT), "findings": list(findings)}


def _finding(component: object, **overrides: object) -> dict:
    base: dict = {"component": component, "kind": "observed_symptom",
                  "rule": "visual_defect", "status": "fail"}
    base.update(overrides)
    return base


def _rules(issues: list[dict]) -> set[str]:
    return {issue["rule"] for issue in issues}


def test_absent_nested_provenance_issues() -> None:
    """RED R15: a component without artifact provenance must issue."""
    issues = validate_manifest(_manifest(
        _finding({"component_id": "P1/v1"})))
    assert "finding_missing_provenance" in _rules(issues)


def test_string_nested_provenance_issues() -> None:
    """RED R15: a non-object artifact reference must issue."""
    issues = validate_manifest(_manifest(
        _finding({"component_id": "P1/v1", "artifact": SOURCE})))
    assert "finding_missing_provenance" in _rules(issues)


def test_review_note_does_not_suppress_mismatch() -> None:
    """RED R15: reviewed_by/reason never voids an identity check."""
    issues = validate_manifest(_manifest(_finding(
        {"component_id": "P1/v1",
         "artifact": {"surface": "powerbi", "contract_revision": "1.0.0",
                      "source_sha256": OTHER}},
        cross_artifact_contract={"reviewed_by": "agent-b",
                                 "reason": "looks fine"})))
    assert "component_source_mismatch" in _rules(issues)


def test_partial_nested_identity_mismatches() -> None:
    """Control: present-but-partial provenance already mismatches."""
    issues = validate_manifest(_manifest(_finding(
        {"component_id": "P1/v1",
         "artifact": {"surface": "powerbi", "source_sha256": SOURCE}})))
    assert "component_contract_revision_mismatch" in _rules(issues)


def test_matching_nested_provenance_passes() -> None:
    """Control: complete same-artifact provenance stays clean."""
    issues = validate_manifest(_manifest(_finding(
        {"component_id": "P1/v1", "artifact": dict(ARTIFACT)})))
    assert issues == []
