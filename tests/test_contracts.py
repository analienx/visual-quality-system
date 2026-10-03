"""WP-01 contract tests: roundtrip both surfaces plus the named negatives.

Acceptance mapping (issue #6): forged source hashes, duplicate IDs, invalid
applicability, missing required query context, own-edit own-approval, stale
render, unsupported major schema, and unknown-never-pass adjudication.
Fixtures are synthetic; no Desktop, Word, or model query is exercised.
"""
from __future__ import annotations

from typing import Any

from vqs.contracts import (
    ArtifactRef,
    ComponentRef,
    DataScope,
    Finding,
    ReviewIdentity,
    RunManifest,
    adjudicate,
    is_release_pass,
    to_dict,
    validate_manifest,
)

SOURCE = "a" * 64
OTHER_SOURCE = "b" * 64


def _manifest(surface: str = "powerbi", **overrides: Any) -> dict[str, Any]:
    artifact = ArtifactRef(surface=surface, source_sha256=SOURCE)
    component = ComponentRef(
        artifact=artifact, component_id="page-1", component_type="page"
    )
    finding = Finding(
        kind="observed_symptom",
        rule="text_legibility",
        status="fail",
        component=component,
        detail="Title text clipped at 1280px width",
    )
    fields: dict[str, Any] = {
        "run_id": "run-1",
        "artifact": artifact,
        "findings": (finding,),
        "reviewer": ReviewIdentity(id="reviewer-1"),
        "fixer_id": "executor-1",
    }
    fields.update(overrides)
    return to_dict(RunManifest(**fields))


def test_roundtrip_both_surfaces() -> None:
    for surface in ("powerbi", "docx"):
        assert validate_manifest(_manifest(surface)) == []


def test_forged_source_hash_rejected() -> None:
    bad = _manifest()
    bad["artifact"]["source_sha256"] = "not-a-hash"
    assert any(row["rule"] == "forged_source_hash" for row in validate_manifest(bad))


def test_duplicate_findings_rejected_but_two_rules_share_a_visual() -> None:
    """Supervisor #22 P0-7: identity is (component, rule), not component alone."""
    dup = _manifest()
    dup["findings"] = [dup["findings"][0], dup["findings"][0]]
    assert any(row["rule"] == "duplicate_finding" for row in validate_manifest(dup))
    two_rules = _manifest()
    second = dict(two_rules["findings"][0])
    second["rule"] = "palette_consistency"
    two_rules["findings"] = [two_rules["findings"][0], second]
    assert validate_manifest(two_rules) == []


def test_invalid_applicability_rejected() -> None:
    bad = _manifest()
    bad["findings"][0]["status"] = "not_applicable"
    bad["findings"][0]["detail"] = ""
    rows = validate_manifest(bad)
    assert any(row["rule"] == "missing_applicability_reason" for row in rows)
    bad["findings"][0]["status"] = "maybe"
    assert any(row["rule"] == "invalid_gate_status" for row in validate_manifest(bad))


def test_missing_query_context_rejected_for_facts() -> None:
    bad = _manifest()
    bad["findings"][0]["kind"] = "fact"
    assert any(row["rule"] == "missing_query_context" for row in validate_manifest(bad))
    good = _manifest()
    good["findings"][0]["kind"] = "fact"
    good["findings"][0]["data_scope"] = {
        "filters": {"Year": "2024"},
        "role": "viewer",
        "refresh_id": "refresh-1",
        "query_context": "qctx-1",
    }
    assert validate_manifest(good) == []


def test_own_approval_forbidden() -> None:
    bad = _manifest()
    bad["reviewer"] = {"id": "executor-1", "role": "independent_visual_reviewer"}
    assert any(row["rule"] == "own_approval_forbidden" for row in validate_manifest(bad))


def test_render_binding_checks_source_not_image_bytes() -> None:
    """Supervisor #22 P0-8: image SHA != source SHA; bind via explicit render block."""
    bad = _manifest()
    bad["findings"][0]["render"] = {"sha256": "d" * 64, "source_sha256": OTHER_SOURCE}
    assert any(row["rule"] == "render_source_mismatch" for row in validate_manifest(bad))
    legacy = _manifest()
    legacy["findings"][0]["render_sha256"] = SOURCE
    assert any(row["rule"] == "render_binding_invalid"
               for row in validate_manifest(legacy))
    good = _manifest()
    good["findings"][0]["render"] = {"sha256": "d" * 64, "source_sha256": SOURCE}
    assert validate_manifest(good) == []


def test_unsupported_major_schema_rejected() -> None:
    bad = _manifest()
    bad["artifact"]["contract_revision"] = "2.0.0"
    assert any(row["rule"] == "unsupported_schema_major" for row in validate_manifest(bad))


def test_unknown_never_becomes_pass() -> None:
    assert adjudicate("unknown") == "blocked"
    assert adjudicate("not_applicable") == "blocked"
    assert adjudicate("not_run") == "blocked"
    assert adjudicate("pass") == "pass"
    assert not is_release_pass(["pass", "unknown"])
    assert is_release_pass(["pass", "pass"])


def test_unused_dataclass_imports_are_real() -> None:
    assert DataScope(query_context="q").query_context == "q"
