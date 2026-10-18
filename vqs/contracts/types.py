"""Versioned typed evidence/intent contracts (WP-01, issue #6).

Stdlib-only frozen records. These types describe *claims* about source, data,
render, and review identity; they do not capture, query, or certify anything.
`SCHEMA_VERSION` pins the contract revision every record carries so stale or
foreign-major payloads are rejectable, never silently accepted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0.0"
SCHEMA_MAJOR = 1

SURFACES: frozenset[str] = frozenset({"powerbi", "docx"})
GATE_STATUSES: frozenset[str] = frozenset(
    {"pass", "fail", "blocked", "unknown", "not_applicable", "not_run"}
)
FINDING_KINDS: frozenset[str] = frozenset({"fact", "observed_symptom", "hypothesis"})


@dataclass(frozen=True)
class ArtifactRef:
    """One versioned artifact: surface plus source hash plus contract revision."""

    surface: str
    source_sha256: str
    contract_revision: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ComponentRef:
    """One addressable component (page, visual, section, figure) in an artifact."""

    artifact: ArtifactRef
    component_id: str
    component_type: str


@dataclass(frozen=True)
class DataScope:
    """Scoped data context: filters, role, refresh identity, query context."""

    filters: dict[str, str] = field(default_factory=dict)
    role: str = ""
    refresh_id: str = ""
    query_context: str = ""


@dataclass(frozen=True)
class Environment:
    """Pinned render environment: backend, versions, locale, view state."""

    renderer: str = ""
    renderer_version: str = ""
    locale: str = "en-US"
    view_state: str = ""


@dataclass(frozen=True)
class Finding:
    """One atomic verdict: measured fact, observed symptom, or hypothesis."""

    kind: str
    rule: str
    status: str
    component: ComponentRef
    data_scope: DataScope = field(default_factory=DataScope)
    detail: str = ""
    finding_id: str = ""
    render: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExpectedAnswerOracle:
    """Scoped expected answer a repair must preserve (same filters, same scope)."""

    question_id: str = ""
    scope_digest: str = ""
    expected_summary: str = ""


@dataclass(frozen=True)
class RepairPlan:
    """Typed allowlisted repair: operations plus rollback; candidate-only."""

    operations: tuple[dict[str, Any], ...] = ()
    rollback: str = ""
    candidate_only: bool = True


@dataclass(frozen=True)
class EvidenceRef:
    """Immutable pointer to raw evidence (manifest ID, never the payload)."""

    evidence_uri: str = ""
    sha256: str = ""
    recorded_by: str = ""


@dataclass(frozen=True)
class ReviewIdentity:
    """Independent reviewer identity; must differ from the fixer (see validate)."""

    id: str = ""
    role: str = "independent_visual_reviewer"


def normalize_identity(value: object) -> str:
    """Canonical identity for comparison: stripped and case-folded.

    Quoted " Alice " and "alice" name the same human, so exact-string
    inequality is a minimum sanity check, never proof of independence.
    Sealed records keep the verbatim claimed id; every gate compares
    the normalized form.
    """
    return value.strip().casefold() if isinstance(value, str) else ""


@dataclass(frozen=True)
class RunManifest:
    """Top-level run record binding artifact, findings, oracles, and identities."""

    run_id: str = ""
    artifact: ArtifactRef | None = None
    environment: Environment = field(default_factory=Environment)
    findings: tuple[Finding, ...] = ()
    oracles: tuple[ExpectedAnswerOracle, ...] = ()
    repair: RepairPlan | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    reviewer: ReviewIdentity = field(default_factory=ReviewIdentity)
    fixer_id: str = ""


def to_dict(manifest: RunManifest) -> dict[str, Any]:
    """Serialize a manifest to plain JSON-compatible dicts."""
    return asdict(manifest)
