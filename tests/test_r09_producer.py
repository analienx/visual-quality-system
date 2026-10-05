"""R09 RED: sealed producer authority over caller labels.

A sealed failed/blocked producer with pass artifacts must never
approve (bound status is cross-checked against the sealed
terminal, not the gate label); generic control labels outside
the allowlist must block fast; replay across subjects stays
rejected. Failing tests are red pre-R3, green after.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore
from vqs.run_store import append_event, create_run, seal_run

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "c" * 64
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
       "locale": "en-US", "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
         "query_context": "q", "query_hash": "h" * 64}

_TERMINAL = {"pass": "completed", "fail": "failed", "blocked": "blocked"}


def _subjects() -> list[dict[str, Any]]:
    return [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE_A},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": SOURCE_B},
        {"kind": "docx", "id": "d1", "source_sha256": SOURCE_D},
    ]


def _case(root: Path, *, gate_status: str = "pass",
          bound_status: str = "pass", terminal: str = "pass",
          control: str | None = None, caught: bool = False,
          subject_id: str = "p1", source: str = SOURCE_A,
          gate_id: str = "G2") -> tuple[dict, SealedEvidenceStore]:
    envelope: dict[str, Any] = {
        "source_sha256": source, "environment": dict(ENV),
        "producer": {"run_id": "prod-1", "gate": gate_id,
                     "status": gate_status, "control": control},
        "result": {"gate": gate_id, "status": gate_status},
        "data_scope": {**SCOPE, "filters": dict(SCOPE["filters"])},
    }
    if control is not None:
        envelope["control_result"] = {"control": control, "caught": True}
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    run_dir = create_run(root, "prod-1", {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": _TERMINAL[terminal]})
    seal_run(run_dir, _TERMINAL[terminal],
             artifacts={"envelope_sha256": sha, "gate": gate_id,
                        "status": bound_status, "control": control})
    gate: dict[str, Any] = {
        "id": gate_id, "subject_id": subject_id, "status": gate_status,
        "environment": dict(ENV),
        "data_scope": {**SCOPE, "filters": dict(SCOPE["filters"])},
        "evidence_ref": {"sha256": sha, "source_sha256": source},
    }
    if control is not None:
        gate["negative_control"] = control
        gate["caught"] = caught
    record = {"subjects": _subjects(), "gates": [gate],
              "editor_id": "agent-a", "reviewer_id": "agent-b",
              "user_approved": True}
    return record, SealedEvidenceStore(root)


def _rules(verdict: dict) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_failed_producer_with_pass_labels_rejected(tmp_path: Path) -> None:
    """RED R09: sealed terminal failed beats pass labels everywhere."""
    record, store = _case(tmp_path, gate_status="pass",
                          bound_status="pass", terminal="fail")
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "producer_terminal_mismatch" in _rules(verdict)


def test_generic_control_label_rejected(tmp_path: Path) -> None:
    """RED R09: a control outside the allowlist blocks fast."""
    record, store = _case(tmp_path, control="pass", caught=True)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "invalid_negative_control" in _rules(verdict)


def test_cross_subject_replay_rejected(tmp_path: Path) -> None:
    """Control: one envelope cannot back two subjects' gates."""
    record, store = _case(tmp_path, subject_id="p2", source=SOURCE_A)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "evidence_source_mismatch" in _rules(verdict)


def test_uncaught_control_rejected(tmp_path: Path) -> None:
    """Control: a named-but-uncaught control still fails."""
    record, store = _case(tmp_path, control="stale_image", caught=False)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "negative_uncaught" in _rules(verdict)
