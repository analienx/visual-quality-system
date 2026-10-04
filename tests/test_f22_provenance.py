"""F22 RED: nested component provenance must agree with the artifact.

validate_manifest checks the component ID but ignores the nested
component artifact: a finding can point at another source, surface,
or contract revision and still validate. Each nested mismatch must
produce a finding unless an explicit reviewed cross-artifact contract
applies (that exception shape lands with the M3 fix and its own test).
"""
from __future__ import annotations

from typing import Any

from vqs.contracts import (
    ArtifactRef,
    ComponentRef,
    Finding,
    ReviewIdentity,
    RunManifest,
    to_dict,
    validate_manifest,
)

SOURCE = "a" * 64
OTHER_SOURCE = "b" * 64


def _manifest() -> dict[str, Any]:
    artifact = ArtifactRef(surface="powerbi", source_sha256=SOURCE)
    component = ComponentRef(
        artifact=artifact, component_id="page-1", component_type="page")
    finding = Finding(
        kind="observed_symptom", rule="text_legibility", status="fail",
        component=component, detail="Title text clipped at 1280px width")
    return to_dict(RunManifest(
        run_id="run-1", artifact=artifact, findings=(finding,),
        reviewer=ReviewIdentity(id="reviewer-1"), fixer_id="executor-1"))


def _nested(manifest: dict[str, Any]) -> dict[str, Any]:
    nested = manifest["findings"][0]["component"]["artifact"]
    assert isinstance(nested, dict)
    return nested


def test_f22_matching_nested_provenance_validates() -> None:
    """Control (passes now and post-fix): agreement is valid."""
    assert validate_manifest(_manifest()) == []


def test_f22_nested_source_mismatch_findings() -> None:
    """RED: component source disagreeing with the artifact must finding."""
    manifest = _manifest()
    _nested(manifest)["source_sha256"] = OTHER_SOURCE
    assert validate_manifest(manifest) != []


def test_f22_nested_surface_mismatch_findings() -> None:
    """RED: component surface disagreeing with the artifact must finding."""
    manifest = _manifest()
    _nested(manifest)["surface"] = "docx"
    assert validate_manifest(manifest) != []


def test_f22_nested_contract_revision_mismatch_findings() -> None:
    """RED: component contract revision disagreeing must finding."""
    manifest = _manifest()
    _nested(manifest)["contract_revision"] = "2.0.0"
    assert validate_manifest(manifest) != []

def test_f22_reviewed_cross_artifact_contract_permits_mismatch() -> None:
    """M3 exception: an explicit reviewed contract permits a nested mismatch."""
    manifest = _manifest()
    _nested(manifest)["source_sha256"] = OTHER_SOURCE
    manifest["findings"][0]["cross_artifact_contract"] = {
        "reviewed_by": "reviewer-1",
        "reason": "p2 verified against staged source " + OTHER_SOURCE}
    assert validate_manifest(manifest) == []


def test_f22_malformed_cross_artifact_contract_findings() -> None:
    """M3 exception is fail-closed: a malformed contract still findings."""
    manifest = _manifest()
    _nested(manifest)["source_sha256"] = OTHER_SOURCE
    manifest["findings"][0]["cross_artifact_contract"] = {"reviewed_by": ""}
    assert validate_manifest(manifest) != []
