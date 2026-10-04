"""F15 RED: every applicable gate is required for each selected subject.

Coverage aggregates by (gate,kind), so a complete p1 plus an untested
p2 passes. A complete p1 plus untested p2 must block and identify
p2's missing gates.

M3 flip: test_materialized_record_passes distributes mandatory gates
between p1/p2 and expects pass; the full case must then cover every
applicable gate on every subject.
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
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {}}


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


def _p1_complete_p2_untested() -> _Case:
    """p1 carries every pbip gate; p2 is declared but never gated."""
    case = _Case()
    pairs = [("G0", "p1", SOURCE_A, "pbip"), ("G0", "d1", SOURCE_D, "docx"),
             ("G1", "p1", SOURCE_A, "pbip"), ("G1", "d1", SOURCE_D, "docx"),
             ("G2", "p1", SOURCE_A, "pbip"), ("G3", "p1", SOURCE_A, "pbip"),
             ("G4", "p1", SOURCE_A, "pbip"), ("G5", "d1", SOURCE_D, "docx"),
             ("G6", "p1", SOURCE_A, "pbip")]
    negatives = sorted(REQUIRED_NEGATIVES)
    for index, (gate_id, subject, source, kind) in enumerate(pairs):
        control = negatives[index] if index < len(negatives) else None
        case.add(gate_id, subject, source, kind, control=control)
    for extra, control in enumerate(negatives[len(pairs):]):
        case.add(f"G{extra % 7}", "p1", SOURCE_A, "pbip", control=control)
    return case


def test_f15_untested_subject_blocks(tmp_path: Path) -> None:
    """RED: complete p1 + untested p2 must block, naming p2's gates."""
    case = _p1_complete_p2_untested()
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    incomplete = next(finding for finding in verdict["findings"]
                      if finding["rule"] == "gate_set_incomplete")
    assert "p2" in json.dumps(incomplete["missing"])
