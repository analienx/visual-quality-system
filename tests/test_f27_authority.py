"""F27 RED: sealed producer artifacts are gate evidence authority.

acceptance acknowledges its residual: anyone can construct matching
envelopes under a supplied root, because only bytes and bindings
inside the root are verified, not which process wrote the root. The
bounded producer/consumer contract (issue #22): expected
gate/result/control/source/environment bindings must come from
validated sealed producer artifacts, with an explicit
trusted-root/producer boundary.

M3 shape (committed): the trusted root holds producer runs
(<root>/<run_id>/manifest.json, sealed via run_store) alongside
objects/. Each envelope carries producer {run_id, gate, status,
control}; acceptance requires the producer run seal valid, the
producer manifest artifacts binding the envelope sha, and the bound
gate/result/control matching the referencing gate. Missing authority
blocks; mismatched replay fails. No new cryptography: the boundary is
the sealed producer run in the trusted root.
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
# R14 contract migration: sealed evidence states full identity; the
# authority checks below run against complete envelopes.
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
       "locale": "en-US", "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
         "query_context": "analyst-review", "query_hash": "q" * 64}


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
    pairs = [("G0", "p1", SOURCE_A, "pbip"), ("G0", "d1", SOURCE_D, "docx"),
             ("G1", "p1", SOURCE_A, "pbip"), ("G1", "d1", SOURCE_D, "docx"),
             ("G2", "p1", SOURCE_A, "pbip"), ("G3", "p2", SOURCE_B, "pbip"),
             ("G4", "p1", SOURCE_A, "pbip"), ("G5", "d1", SOURCE_D, "docx"),
             ("G6", "p1", SOURCE_A, "pbip")]
    negatives = sorted(REQUIRED_NEGATIVES)
    for index, (gate_id, subject, source, kind) in enumerate(pairs):
        control = negatives[index] if index < len(negatives) else None
        case.add(gate_id, subject, source, kind, control=control)
    for extra, control in enumerate(negatives[len(pairs):]):
        case.add(f"G{extra % 7}", "p2", SOURCE_B, "pbip", control=control)
    return case


def _authority_rules(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    return [finding for finding in verdict["findings"]
            if "produc" in finding.get("rule", "")
            or "authority" in finding.get("rule", "")]


def test_f27_fabricated_envelope_without_producer_blocks(tmp_path: Path) -> None:
    """RED: a hand-built envelope with no producer run must block."""
    case = _full_case()
    store = case.store(tmp_path)
    fabricated = {"source_sha256": SOURCE_A, "environment": dict(ENV),
                  "data_scope": {**SCOPE, "filters": {}}}
    raw = _envelope_bytes(fabricated)
    sha = hashlib.sha256(raw).hexdigest()
    (tmp_path / "objects" / sha).write_bytes(raw)
    gates = [dict(gate) for gate in case.gates]
    target = next(gate for gate in gates if gate["subject_id"] == "p1"
                  and "data_scope" in gate)
    target["evidence_ref"] = {"sha256": sha, "source_sha256": SOURCE_A}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert _authority_rules(verdict) != []


def test_f27_replay_under_another_gate_rejects(tmp_path: Path) -> None:
    """RED: an envelope bound to G1 must not satisfy gate G2."""
    case = _full_case()
    bound = {"source_sha256": SOURCE_A, "environment": dict(ENV),
             "data_scope": {**SCOPE, "filters": {}},
             "producer": {"run_id": "prod-1", "gate": "G1",
                          "status": "pass", "control": None}}
    raw = _envelope_bytes(bound)
    sha = hashlib.sha256(raw).hexdigest()
    case.blobs[sha] = raw
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    target = next(gate for gate in gates if gate["id"] == "G2")
    target["evidence_ref"] = {"sha256": sha, "source_sha256": SOURCE_A}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] != "pass"
    assert _authority_rules(verdict) != []


def test_f27_replay_under_another_control_rejects(tmp_path: Path) -> None:
    """An envelope bound to one control must not satisfy another control."""
    from vqs.run_store import append_event, create_run, seal_run

    case = _full_case()
    gates = [dict(gate) for gate in case.gates]
    target = next(gate for gate in gates
                  if gate.get("negative_control") and "data_scope" in gate)
    gate_id = target["id"]
    other = "control-from-another-gate"
    assert other != target["negative_control"]
    bound = {"source_sha256": SOURCE_A, "environment": dict(ENV),
             "data_scope": {**SCOPE, "filters": {}},
             "producer": {"run_id": "prod-1", "gate": gate_id,
                          "status": target["status"], "control": other},
             "result": {"gate": gate_id, "status": target["status"]}}
    raw = _envelope_bytes(bound)
    sha = hashlib.sha256(raw).hexdigest()
    case.blobs[sha] = raw
    store = case.store(tmp_path)
    run_dir = create_run(tmp_path, "prod-1", {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": gate_id,
                        "status": target["status"], "control": other})
    target["evidence_ref"] = {"sha256": sha, "source_sha256": SOURCE_A}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] != "pass"
    assert any(finding.get("rule") == "producer_control_mismatch"
               for finding in verdict["findings"])
