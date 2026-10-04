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
