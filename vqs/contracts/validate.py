"""Validation for versioned run manifests (WP-01, issue #6).

Every check returns issue rows shaped like ``{"rule": ..., ...}`` (matching
``vqs.evidence.verify_review``); an empty list means the manifest is valid.
Release adjudication lives in :func:`adjudicate`: ``unknown`` never becomes
``pass`` — it becomes ``blocked``.

Finding identity is ``(component_id, rule)``: several rules may target one
visual, but the same rule may not report the same component twice. Render
evidence binds through an explicit ``render`` block carrying both the image
digest and the source revision the pixels were captured from — an image SHA
is never compared directly to a source SHA.
"""
from __future__ import annotations

from typing import Any

from .types import (
    FINDING_KINDS,
    GATE_STATUSES,
    SCHEMA_MAJOR,
    SURFACES,
)

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in _HEX64 for char in value)
    )


def _schema_major(revision: object) -> int | None:
    if not isinstance(revision, str) or "." not in revision:
        return None
    major, _, _ = revision.partition(".")
    return int(major) if major.isdigit() else None


def _reviewer_bound_exception(contract: object, reviewer_id: object,
                              fixer_id: object) -> bool:
    """True when the run's own declared independent reviewer accepts the finding.

    R15/F22 reconciliation: a well-formed review note alone never
    suppresses nested identity checks; only a note from the manifest's
    declared reviewer (independent of the fixer) carries that weight,
    so a stranger's "looks fine" cannot waive a source mismatch.
    """
    return (isinstance(contract, dict)
            and isinstance(contract.get("reviewed_by"), str)
            and bool(contract["reviewed_by"])
            and contract["reviewed_by"] == reviewer_id
            and isinstance(reviewer_id, str) and bool(reviewer_id)
            and reviewer_id != fixer_id)


def _note_approves_nested(contract: dict, nested: object) -> bool:
    """True when a reviewer exception covers the exact nested identity.

    S14: an exception waives only the nested artifact it approves. The
    note must declare the approved source/surface/contract-revision
    triple and the nested artifact must match it field-for-field. A
    note without an exact approval, or a nested artifact that diverges
    from the approval (including missing keys), is not covered.
    """
    approved_source = contract.get("approved_source_sha256")
    approved_surface = contract.get("approved_surface")
    approved_revision = contract.get("approved_contract_revision")
    if (not _is_hex64(approved_source)
            or not isinstance(approved_surface, str) or not approved_surface
            or not isinstance(approved_revision, str)
            or not approved_revision):
        return False
    if not isinstance(nested, dict):
        return False
    return (nested.get("source_sha256") == approved_source
            and nested.get("surface") == approved_surface
            and nested.get("contract_revision") == approved_revision)


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a ``to_dict``-shaped run manifest; never infer proof."""
    issues: list[dict[str, Any]] = []
    if not isinstance(manifest, dict):
        return [{"rule": "manifest_not_an_object"}]
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        return [{"rule": "artifact_missing"}]
    if artifact.get("surface") not in SURFACES:
        issues.append({"rule": "invalid_surface", "surface": artifact.get("surface")})
    if _schema_major(artifact.get("contract_revision")) != SCHEMA_MAJOR:
        issues.append({
            "rule": "unsupported_schema_major",
            "revision": artifact.get("contract_revision"),
            "remediation": "Regenerate the manifest with the current contract version",
        })
    if not _is_hex64(artifact.get("source_sha256")):
        issues.append({
            "rule": "forged_source_hash",
            "remediation": "Recompute source_sha256 from the exact report/model source",
        })
    findings = manifest.get("findings")
    if not isinstance(findings, (list, tuple)):
        return issues + [{"rule": "findings_not_a_list"}]
    run_reviewer = manifest.get("reviewer")
    run_reviewer_id = run_reviewer.get("id") if isinstance(run_reviewer, dict) else ""
    run_fixer_id = manifest.get("fixer_id")
    seen: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            issues.append({"rule": "finding_not_an_object", "index": index})
            continue
        component = finding.get("component")
        component_id = component.get("component_id") if isinstance(component, dict) else None
        if not isinstance(component_id, str) or not component_id:
            issues.append({"rule": "finding_missing_component", "index": index})
        else:
            identity = (component_id, str(finding.get("rule", "")))
            if identity in seen:
                issues.append({"rule": "duplicate_finding",
                               "component": component_id,
                               "finding_rule": finding.get("rule")})
            else:
                seen.add(identity)
        finding_id = finding.get("finding_id")
        if finding_id:
            if not isinstance(finding_id, str):
                issues.append({"rule": "finding_id_invalid", "index": index})
            elif finding_id in seen_ids:
                issues.append({"rule": "duplicate_finding_id", "finding_id": finding_id})
            else:
                seen_ids.add(finding_id)
        if finding.get("kind") not in FINDING_KINDS:
            issues.append({"rule": "invalid_finding_kind", "index": index})
        status = finding.get("status")
        if status not in GATE_STATUSES:
            issues.append({"rule": "invalid_gate_status", "index": index, "status": status})
        if status == "not_applicable" and not finding.get("detail"):
            issues.append({"rule": "missing_applicability_reason", "index": index})
        if finding.get("kind") == "fact":
            scope = finding.get("data_scope")
            if not isinstance(scope, dict) or not scope.get("query_context"):
                issues.append({"rule": "missing_query_context", "index": index})
        nested = component.get("artifact") if isinstance(component, dict) else None
        if isinstance(component, dict) and not isinstance(nested, dict):
            issues.append({"rule": "finding_missing_provenance", "index": index,
                           "component": component_id})
        contract = finding.get("cross_artifact_contract")
        reviewed = False
        if contract is not None:
            if (isinstance(contract, dict)
                    and isinstance(contract.get("reviewed_by"), str) and contract["reviewed_by"]
                    and isinstance(contract.get("reason"), str) and contract["reason"]):
                reviewed = _reviewer_bound_exception(contract, run_reviewer_id,
                                                       run_fixer_id)
                if reviewed and not _note_approves_nested(contract, nested):
                    reviewed = False
            else:
                issues.append({"rule": "cross_artifact_contract_invalid", "index": index})
        if isinstance(nested, dict) and not reviewed:
            if nested.get("source_sha256") != artifact.get("source_sha256"):
                issues.append({"rule": "component_source_mismatch", "index": index,
                               "component": component_id})
            if nested.get("surface") != artifact.get("surface"):
                issues.append({"rule": "component_surface_mismatch", "index": index,
                               "component": component_id})
            if nested.get("contract_revision") != artifact.get("contract_revision"):
                issues.append({"rule": "component_contract_revision_mismatch", "index": index,
                               "component": component_id})
        render = finding.get("render")
        if render is not None:
            if (not isinstance(render, dict) or not _is_hex64(render.get("sha256"))
                    or not _is_hex64(render.get("source_sha256"))):
                issues.append({"rule": "render_binding_invalid", "index": index})
            elif render.get("source_sha256") != artifact.get("source_sha256"):
                issues.append({"rule": "render_source_mismatch", "index": index})
        if finding.get("render_sha256") is not None:
            issues.append({"rule": "render_binding_invalid", "index": index,
                           "remediation": "Use the explicit render block, never a bare hash"})
    reviewer = manifest.get("reviewer")
    reviewer_id = reviewer.get("id") if isinstance(reviewer, dict) else ""
    fixer_id = manifest.get("fixer_id")
    if reviewer_id and fixer_id and reviewer_id == fixer_id:
        issues.append({
            "rule": "own_approval_forbidden",
            "remediation": "Assign a reviewer whose id differs from the fixer",
        })
    return issues


def adjudicate(status: str) -> str:
    """Map a gate status to a release verdict; ``unknown`` becomes ``blocked``."""
    if status == "pass":
        return "pass"
    if status in ("fail", "blocked"):
        return status
    return "blocked"


def is_release_pass(statuses: list[str]) -> bool:
    """True only when every gate status is an explicit ``pass``."""
    return bool(statuses) and all(adjudicate(status) == "pass" for status in statuses)
