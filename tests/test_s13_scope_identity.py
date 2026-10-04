"""S13: gate-specific required nonempty typed scope/env identities.

Blank strings and wrong types are unknown, never stated values;
pbip filters must be present dictionaries on both sides (absent on
both sides no longer compares equal). A documented not-applicable
pair on both sides stays stated; one-sided N/A still mismatches.
All tests drive run_acceptance directly with sealed producer runs
and gate-result artifacts, isolating the identity rules.
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


def _subjects() -> list[dict[str, Any]]:
    return [
        {"kind": "pbip", "id": "p1", "layout_digest": "1" * 16,
         "source_sha256": SOURCE},
        {"kind": "pbip", "id": "p2", "layout_digest": "2" * 16,
         "source_sha256": "b" * 64},
        {"kind": "docx", "id": "d1", "source_sha256": "c" * 64},
    ]


def _case(root: Path, *, gate_env: dict, gate_scope: dict,
          env_env: dict, env_scope: dict):
    """One sealed G2 gate; env/scope differ per axis under test."""
    envelope: dict[str, Any] = {
        "source_sha256": SOURCE, "environment": dict(env_env),
        "producer": {"run_id": "solo-1", "gate": "G2",
                     "status": "pass", "control": None},
        "result": {"gate": "G2", "status": "pass"},
        "data_scope": dict(env_scope),
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    run_dir = create_run(root, "solo-1", {"pipeline": "vqs.producer/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": "G2",
                        "status": "pass", "control": None})
    gate: dict[str, Any] = {
        "id": "G2", "subject_id": "p1", "status": "pass",
        "environment": dict(gate_env),
        "data_scope": dict(gate_scope),
        "evidence_ref": {"sha256": sha, "source_sha256": SOURCE},
    }
    record = {"subjects": _subjects(), "gates": [gate],
              "editor_id": "agent-a", "reviewer_id": "agent-b",
              "user_approved": True}
    return record, SealedEvidenceStore(root)


def _rules(verdict: dict) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def _drop(mapping: dict, *keys: str) -> dict:
    return {key: value for key, value in mapping.items() if key not in keys}


def test_both_side_omitted_filters_block(tmp_path: Path) -> None:
    """S13: filters absent on both sides no longer compare equal."""
    thin = _drop(SCOPE, "filters")
    record, store = _case(tmp_path, gate_env=ENV, gate_scope=thin,
                           env_env=ENV, env_scope=thin)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_blank_locale_blocks(tmp_path: Path) -> None:
    """S13: a blank locale is unknown, not a stated value."""
    thin_env = dict(ENV, locale="")
    record, store = _case(tmp_path, gate_env=thin_env, gate_scope=SCOPE,
                           env_env=thin_env, env_scope=SCOPE)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_blank_query_identity_blocks(tmp_path: Path) -> None:
    """S13: blank query_context/query_hash are unknown, not stated."""
    thin_scope = dict(SCOPE, query_context="  ", query_hash="")
    record, store = _case(tmp_path, gate_env=ENV, gate_scope=thin_scope,
                           env_env=ENV, env_scope=thin_scope)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_wrong_type_gate_role_blocks(tmp_path: Path) -> None:
    """S13: a non-string gate role is not a stated identity."""
    thin_scope = dict(SCOPE, role=["analyst"])
    record, store = _case(tmp_path, gate_env=ENV, gate_scope=thin_scope,
                           env_env=ENV, env_scope=SCOPE)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "gate_data_scope_incomplete" in _rules(verdict)


def test_wrong_type_envelope_filters_block(tmp_path: Path) -> None:
    """S13: non-dict envelope filters are not a stated filter set."""
    thin_scope = dict(SCOPE, filters=["all"])
    record, store = _case(tmp_path, gate_env=ENV, gate_scope=SCOPE,
                           env_env=ENV, env_scope=thin_scope)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "evidence_identity_incomplete" in _rules(verdict)


def test_unjustified_na_still_fails(tmp_path: Path) -> None:
    """S13: one-sided not-applicable mismatches instead of passing."""
    gate_env = dict(ENV, locale="not_applicable")
    record, store = _case(tmp_path, gate_env=gate_env, gate_scope=SCOPE,
                           env_env=ENV, env_scope=SCOPE)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "evidence_environment_mismatch" in _rules(verdict)


def test_justified_na_pair_retained(tmp_path: Path) -> None:
    """S13: a documented both-side N/A pair stays stated."""
    na_env = dict(ENV, locale="not_applicable",
                  view_state="not_applicable")
    record, store = _case(tmp_path, gate_env=na_env, gate_scope=SCOPE,
                           env_env=na_env, env_scope=SCOPE)
    verdict = run_acceptance(record, store)
    assert "evidence_identity_incomplete" not in _rules(verdict)
    assert "evidence_environment_mismatch" not in _rules(verdict)


def test_fully_stated_passes_identity(tmp_path: Path) -> None:
    """S13 positive: stated strings plus dict filters clear identity."""
    record, store = _case(tmp_path, gate_env=ENV, gate_scope=SCOPE,
                           env_env=ENV, env_scope=SCOPE)
    verdict = run_acceptance(record, store)
    assert "evidence_identity_incomplete" not in _rules(verdict)
    assert "gate_data_scope_incomplete" not in _rules(verdict)
    assert "evidence_environment_mismatch" not in _rules(verdict)
    assert "evidence_data_scope_mismatch" not in _rules(verdict)
