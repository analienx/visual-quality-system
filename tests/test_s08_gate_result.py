"""S08: gates pass only on producer-emitted gate results and observed controls.

A gate with a passing label but no gate-output artifact blocks; a
caller caught flag without a producer-observed caught outcome fails;
proof replayed across gates fails; tampered envelopes fail. All
tests drive run_acceptance directly (no route consumes it yet).
"""
import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore
from vqs.run_store import append_event, create_run, seal_run

SOURCE = "a" * 64
ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
       "locale": "en-US", "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
         "query_context": "analyst-review", "query_hash": "q" * 64}
TERMINAL = {"pass": "completed", "fail": "failed", "blocked": "blocked"}


def _subjects() -> list[dict[str, Any]]:
    return [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": "b" * 64},
        {"kind": "docx", "id": "d1", "source_sha256": "c" * 64},
    ]


def _solo(root: Path, *, gate_id: str = "G2", control: str | None = None,
          caught: bool = False, emit_result: bool = True,
          prove: bool = True, result_gate: str | None = None,
          tamper: bool = False):
    """One gate plus its sealed producer run; mutate one axis at a time."""
    envelope: dict[str, Any] = {
        "source_sha256": SOURCE, "environment": dict(ENV),
        "producer": {"run_id": "solo-1", "gate": gate_id,
                     "status": "pass", "control": control},
        "data_scope": {**SCOPE, "filters": {}},
    }
    if emit_result:
        envelope["result"] = {"gate": result_gate or gate_id,
                              "status": "pass"}
    if control is not None and prove:
        envelope["control_result"] = {"control": control, "caught": True}
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(b"tampered" if tamper else raw)
    run_dir = create_run(root, "solo-1", {"pipeline": "vqs.producer/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": gate_id,
                        "status": "pass", "control": control})
    gate: dict[str, Any] = {
        "id": gate_id, "subject_id": "p1", "status": "pass",
        "environment": dict(ENV),
        "data_scope": {**SCOPE, "filters": {}},
        "evidence_ref": {"sha256": sha, "source_sha256": SOURCE},
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


def test_missing_gate_result_blocks(tmp_path: Path) -> None:
    """S08: passing labels without a gate-output artifact block."""
    record, store = _solo(tmp_path, emit_result=False)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "gate_result_missing" in _rules(verdict)


def test_wrong_gate_result_fails(tmp_path: Path) -> None:
    """S08: a result artifact bound to another gate fails."""
    record, store = _solo(tmp_path, result_gate="G3")
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "producer_gate_mismatch" in _rules(verdict)


def test_caught_toggle_without_proof_fails(tmp_path: Path) -> None:
    """S08: caller caught=True with unchanged unproofed bytes fails."""
    record, store = _solo(tmp_path, control="stale_image",
                          caught=True, prove=False)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "caught_uncorroborated" in _rules(verdict)


def test_observed_control_counts(tmp_path: Path) -> None:
    """S08 positive: corroborated caught counts toward the control."""
    record, store = _solo(tmp_path, control="stale_image",
                          caught=True, prove=True)
    verdict = run_acceptance(record, store)
    assert "caught_uncorroborated" not in _rules(verdict)
    assert "gate_result_missing" not in _rules(verdict)


def test_proof_replay_across_gates_fails(tmp_path: Path) -> None:
    """S08: one envelope cannot back a second gate's pass."""
    record, store = _solo(tmp_path)
    replay = dict(record["gates"][0])
    replay["id"] = "G3"
    record["gates"].append(replay)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "producer_gate_mismatch" in _rules(verdict)


def test_tampered_envelope_fails(tmp_path: Path) -> None:
    """S08: post-seal envelope bytes fail, never resolve."""
    record, store = _solo(tmp_path, tamper=True)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "evidence_tampered" in _rules(verdict)
