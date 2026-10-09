"""R14 RED: required identity dimensions; unknown never equals.

locale/view_state/query_context/query_hash missing on both sides
must block (new evidence_identity_incomplete); missing on one
side must block (not mismatch-fail); differing stated values
still fail. The explicit not-applicable sentinel lands with the
fix (documented pairs); plain None is never N/A.
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
FULL_ENV = {"renderer": "desktop-bridge", "renderer_version": "1.0.0",
            "locale": "en-US", "view_state": "default"}
FULL_SCOPE = {"role": "analyst", "refresh_id": "refresh-1", "filters": {},
              "query_context": "q", "query_hash": "h" * 64}


def _case(root: Path, env: dict, scope: dict,
          envelope_env: dict, envelope_scope: dict) -> tuple[dict, Any]:
    envelope: dict[str, Any] = {
        "source_sha256": SOURCE_A, "environment": dict(envelope_env),
        "producer": {"run_id": "prod-1", "gate": "G2",
                     "status": "pass", "control": None},
        "data_scope": dict(envelope_scope),
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    (root / "objects").mkdir(parents=True, exist_ok=True)
    (root / "objects" / sha).write_bytes(raw)
    run_dir = create_run(root, "prod-1", {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": "G2",
                        "status": "pass", "control": None})
    gate: dict[str, Any] = {
        "id": "G2", "subject_id": "p1", "status": "pass",
        "environment": dict(env), "data_scope": dict(scope),
        "evidence_ref": {"sha256": sha, "source_sha256": SOURCE_A},
    }
    record = {"subjects": [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE_A},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": SOURCE_B},
        {"kind": "docx", "id": "d1", "source_sha256": SOURCE_D},
    ], "gates": [gate], "editor_id": "agent-a",
        "reviewer_id": "agent-b", "user_approved": True}
    return record, SealedEvidenceStore(root)


def _rules(verdict: dict) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def _drop(mapping: dict, *keys: str) -> dict:
    return {key: value for key, value in mapping.items() if key not in keys}


def test_missing_dims_both_sides_blocked(tmp_path: Path) -> None:
    """RED R14: required unknown on both sides blocks, never passes."""
    thin_env = _drop(FULL_ENV, "locale", "view_state")
    thin_scope = _drop(FULL_SCOPE, "query_context", "query_hash")
    record, store = _case(tmp_path, thin_env, thin_scope,
                           thin_env, thin_scope)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_missing_dim_one_side_blocked(tmp_path: Path) -> None:
    """RED R14: stated-vs-missing is blocked-unknown, not a mismatch."""
    thin_env = _drop(FULL_ENV, "locale")
    record, store = _case(tmp_path, FULL_ENV, FULL_SCOPE,
                           thin_env, FULL_SCOPE)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_differing_stated_dims_fail(tmp_path: Path) -> None:
    """Control: two stated locales that differ still fail."""
    other = dict(FULL_ENV, locale="fr-FR")
    record, store = _case(tmp_path, FULL_ENV, FULL_SCOPE,
                           other, FULL_SCOPE)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "evidence_environment_mismatch" in _rules(verdict)
