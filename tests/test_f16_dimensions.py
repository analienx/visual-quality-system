"""F16 RED: acceptance must compare full scope/environment identity.

Only renderer/version and role/refresh_id are compared; filters, query
context, locale, and view state can differ while evidence passes. M3
canonicalizes and compares every applicable dimension (missing dims
are unknown, never equal to a stated value); each test alters exactly
one dimension against unchanged sealed evidence and requires rejection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.acceptance import REQUIRED_NEGATIVES, run_acceptance
from vqs.evidence import SealedEvidenceStore

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "c" * 64
# R14 contract migration: sealed evidence states full identity, so
# dimension drift below exercises real mismatch, not thin unknowns.
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
       "locale": "en-US", "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
         "query_context": "analyst-review", "query_hash": "h" * 64}


def _subjects() -> list[dict[str, Any]]:
    return [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE_A},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": SOURCE_B},
        {"kind": "docx", "id": "d1", "source_sha256": SOURCE_D},
    ]


def _envelope_bytes(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


class _Case:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.gates: list[dict[str, Any]] = []

    def add(self, gate_id: str, subject_id: str, source: str, kind: str,
            control: str | None = None, status: str = "pass") -> dict[str, Any]:
        envelope: dict[str, Any] = {"source_sha256": source,
                                    "environment": dict(ENV)}
        gate: dict[str, Any] = {"id": gate_id, "subject_id": subject_id,
                                "status": status, "environment": dict(ENV)}
        if kind == "pbip":
            envelope["data_scope"] = {**SCOPE, "filters": {}}
            gate["data_scope"] = {**SCOPE, "filters": {}}
        raw = _envelope_bytes(envelope)
        sha = hashlib.sha256(raw).hexdigest()
        self.blobs[sha] = raw
        gate["evidence_ref"] = {"sha256": sha, "source_sha256": source}
        if control:
            gate["negative_control"] = control
            gate["caught"] = True
        self.gates.append(gate)
        return gate

    def store(self, root: Path) -> SealedEvidenceStore:
        objects = root / "objects"
        objects.mkdir(parents=True, exist_ok=True)
        for sha, raw in self.blobs.items():
            (objects / sha).write_bytes(raw)
        return SealedEvidenceStore(root)

    def record(self, **overrides: Any) -> dict[str, Any]:
        record = {"subjects": _subjects(), "gates": list(self.gates),
                  "editor_id": "agent-a", "reviewer_id": "agent-b",
                  "user_approved": True}
        record.update(overrides)
        return record


def _full_case() -> _Case:
    case = _Case()
    # R6-E03: subject gates only (G6 is suite-level, tested in R6-E03).
    pairs = [("G0", "p1", SOURCE_A, "pbip"), ("G0", "d1", SOURCE_D, "docx"),
             ("G1", "p1", SOURCE_A, "pbip"), ("G1", "d1", SOURCE_D, "docx"),
             ("G2", "p1", SOURCE_A, "pbip"), ("G3", "p2", SOURCE_B, "pbip"),
             ("G4", "p1", SOURCE_A, "pbip"), ("G5", "d1", SOURCE_D, "docx")]
    negatives = sorted(REQUIRED_NEGATIVES)
    for index, (gate_id, subject, source, kind) in enumerate(pairs):
        control = negatives[index] if index < len(negatives) else None
        case.add(gate_id, subject, source, kind, control=control)
    for extra, control in enumerate(negatives[len(pairs):]):
        case.add(f"G{extra % 7}", "p2", SOURCE_B, "pbip", control=control)
    return case


def _rejects(verdict: dict[str, Any], *keywords: str) -> bool:
    if verdict["verdict"] == "pass":
        return False
    return any(any(word in finding.get("rule", "") for word in keywords)
               for finding in verdict["findings"])


def _first_pbip_gate(case: _Case) -> dict[str, Any]:
    gates = [dict(gate) for gate in case.gates]
    target = next(gate for gate in gates if "data_scope" in gate)
    return gates, target


def test_f16_filter_drift_rejects(tmp_path: Path) -> None:
    """RED: gate filters differing from sealed evidence must reject."""
    case = _full_case()
    store = case.store(tmp_path)
    gates, target = _first_pbip_gate(case)
    target["data_scope"] = {**target["data_scope"],
                            "filters": {"region": "EU"}}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert _rejects(verdict, "scope", "mismatch")


def test_f16_query_context_drift_rejects(tmp_path: Path) -> None:
    """RED: gate query context differing from evidence must reject."""
    case = _full_case()
    store = case.store(tmp_path)
    gates, target = _first_pbip_gate(case)
    target["data_scope"] = {**target["data_scope"],
                            "query_hash": "q" * 64}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert _rejects(verdict, "scope", "mismatch")


def test_f16_locale_drift_rejects(tmp_path: Path) -> None:
    """RED: gate locale differing from sealed evidence must reject."""
    case = _full_case()
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["environment"] = {**gates[0]["environment"], "locale": "fr-FR"}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert _rejects(verdict, "environment", "mismatch")


def test_f16_view_state_drift_rejects(tmp_path: Path) -> None:
    """RED: gate view state differing from evidence must reject."""
    case = _full_case()
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["environment"] = {**gates[0]["environment"],
                               "view_state": "filtered"}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert _rejects(verdict, "environment", "mismatch")
