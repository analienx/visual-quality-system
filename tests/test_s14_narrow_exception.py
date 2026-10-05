"""S14: reviewer exceptions bind the exact approved artifact.

A same-reviewer note without an exact approved source/surface/
contract-revision triple no longer waives a divergent nested
artifact; a note approving one triple does not cover another; a
malformed nested artifact is rejected even with a note. A note
that approves the nested triple field-for-field stays valid, and
a stranger's narrow note still carries no weight.
"""
from vqs.contracts.validate import validate_manifest

SOURCE = "a" * 64
FOREIGN = "b" * 64
UNAPPROVED = "c" * 64
ARTIFACT = {"surface": "powerbi", "contract_revision": "1.0.0",
            "source_sha256": SOURCE}


def _finding(nested, **overrides):
    base = {"component": {"component_id": "P1/v1", "artifact": nested},
            "kind": "observed_symptom", "rule": "visual_defect",
            "status": "fail"}
    base.update(overrides)
    return base


def _manifest(*findings):
    return {"artifact": dict(ARTIFACT), "findings": list(findings),
            "reviewer": {"id": "reviewer-1"}, "fixer_id": "executor-1"}


def _note(**overrides):
    note = {"reviewed_by": "reviewer-1", "reason": "staged source verified"}
    note.update(overrides)
    return note


def _rules(issues):
    return {issue["rule"] for issue in issues}


def test_note_without_approval_rejects_foreign_source() -> None:
    """S14: a triple-less same-reviewer note waives nothing."""
    nested = dict(ARTIFACT, source_sha256=FOREIGN)
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=_note())))
    assert "component_source_mismatch" in _rules(issues)


def test_note_for_other_triple_rejects() -> None:
    """S14: approval of one triple does not cover another artifact."""
    nested = {"surface": "docx", "contract_revision": "9.9.9",
              "source_sha256": FOREIGN}
    note = _note(approved_source_sha256=UNAPPROVED,
                 approved_surface="powerbi",
                 approved_contract_revision="1.0.0")
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note)))
    rules = _rules(issues)
    assert "component_source_mismatch" in rules
    assert "component_surface_mismatch" in rules
    assert "component_contract_revision_mismatch" in rules


def test_incomplete_nested_with_note_rejects() -> None:
    """S14: a nested artifact missing keys matches no approval."""
    nested = {"surface": "powerbi", "contract_revision": "1.0.0"}
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="powerbi",
                 approved_contract_revision="1.0.0")
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note)))
    assert "component_source_mismatch" in _rules(issues)


def test_absent_nested_with_note_rejects_provenance() -> None:
    """S14: no nested artifact means no provenance, note or not."""
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="powerbi",
                 approved_contract_revision="1.0.0")
    issues = validate_manifest(_manifest(
        _finding(None, cross_artifact_contract=note)))
    assert "finding_missing_provenance" in _rules(issues)


def test_valid_narrow_exception_retained() -> None:
    """S14 positive: a note binding an exact SUPPORTED triple still waives."""
    nested = {"surface": "docx", "contract_revision": "1.0.0",
              "source_sha256": FOREIGN}
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="docx",
                 approved_contract_revision="1.0.0")
    assert validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note))) == []


def test_exception_cannot_approve_unsupported_revision() -> None:
    """T07: an exact note for revision 9.9.9 manufactures no support."""
    nested = {"surface": "docx", "contract_revision": "9.9.9",
              "source_sha256": FOREIGN}
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="docx",
                 approved_contract_revision="9.9.9")
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note)))
    assert "component_contract_revision_mismatch" in _rules(issues)


def test_exception_cannot_approve_foreign_surface() -> None:
    """T07: an exact note for surface 'alien' manufactures no support."""
    nested = {"surface": "alien", "contract_revision": "1.0.0",
              "source_sha256": FOREIGN}
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="alien",
                 approved_contract_revision="1.0.0")
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note)))
    assert "component_surface_mismatch" in _rules(issues)


def test_exception_with_missing_fixer_rejected() -> None:
    """T07: a note grants nothing when the run names no fixer."""
    nested = dict(ARTIFACT, source_sha256=FOREIGN)
    note = _note(approved_source_sha256=FOREIGN,
                 approved_surface="powerbi",
                 approved_contract_revision="1.0.0")
    manifest = _manifest(_finding(nested, cross_artifact_contract=note))
    del manifest["fixer_id"]
    issues = validate_manifest(manifest)
    assert "component_source_mismatch" in _rules(issues)


def test_stranger_narrow_note_rejects() -> None:
    """S14: a stranger's exact approval still carries no weight."""
    nested = dict(ARTIFACT, source_sha256=FOREIGN)
    note = _note(reviewed_by="someone-else",
                 approved_source_sha256=FOREIGN,
                 approved_surface="powerbi",
                 approved_contract_revision="1.0.0")
    issues = validate_manifest(_manifest(
        _finding(nested, cross_artifact_contract=note)))
    assert "component_source_mismatch" in _rules(issues)
