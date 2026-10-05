"""T05/T06: gate result authority and N/A applicability policy.

Routes: run_acceptance directly with sealed producer runs (the
exposed consumer). Producer identity must be an exact known VQS
pipeline; actual result status must agree with the claim; N/A pairs
pass only for policy-authorized dims with a recorded reason.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore
from vqs.run_store import append_event, create_run, seal_run

SOURCE = "a" * 64
SOURCE_D = "c" * 64
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
        {"kind": "docx", "id": "d1", "source_sha256": SOURCE_D},
    ]


def _case(root: Path, *, gate_id: str = "G2", subject_id: str = "p1",
          source: str = SOURCE, kind: str = "pbip",
          gate_env: dict | None = None, env_env: dict | None = None,
          gate_scope: dict | None = None, env_scope: dict | None = None,
          pipeline: str = "vqs.check/1",
          result: dict | None = None,
          justification: dict | None = None):
    """One sealed gate; axes under test vary per case."""
    gate_env = dict(ENV if gate_env is None else gate_env)
    env_env = dict(ENV if env_env is None else env_env)
    envelope: dict[str, Any] = {
        "source_sha256": source, "environment": env_env,
        "producer": {"run_id": "solo-1", "gate": gate_id,
                     "status": "pass", "control": None},
        "result": {"gate": gate_id, "status": "pass"}
        if result is None else dict(result),
        "data_scope": dict(SCOPE if env_scope is None else env_scope),
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    run_dir = create_run(root, "solo-1", {"pipeline": pipeline})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": gate_id,
                        "status": "pass", "control": None})
    gate: dict[str, Any] = {
        "id": gate_id, "subject_id": subject_id, "status": "pass",
        "environment": gate_env,
        "evidence_ref": {"sha256": sha, "source_sha256": source},
    }
    if kind == "pbip":
        gate["data_scope"] = dict(
            SCOPE if gate_scope is None else gate_scope)
    if justification is not None:
        gate["na_justification"] = dict(justification)
    record = {"subjects": _subjects(), "gates": [gate],
              "editor_id": "agent-a", "reviewer_id": "agent-b",
              "user_approved": True}
    return record, SealedEvidenceStore(root)


def _rules(verdict: dict) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_failed_actual_result_rejected(tmp_path: Path) -> None:
    """T05: a pass claim over result.status fail is a mismatch (fail)."""
    record, store = _case(tmp_path, result={"gate": "G2", "status": "fail"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "gate_result_status_mismatch" in _rules(verdict)


def test_missing_actual_result_status_blocked(tmp_path: Path) -> None:
    """T05: result without status cannot corroborate the claim (blocked)."""
    record, store = _case(tmp_path, result={"gate": "G2"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "gate_result_status_missing" in _rules(verdict)


def test_generic_producer_blocked(tmp_path: Path) -> None:
    """T05: the generic vqs.producer/1 identity is not evidence."""
    record, store = _case(tmp_path, pipeline="vqs.producer/1")
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "producer_unsupported" in _rules(verdict)


def test_foreign_producer_blocked(tmp_path: Path) -> None:
    """T05: a foreign pipeline identity is not evidence."""
    record, store = _case(tmp_path, pipeline="evil.producer/9")
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "blocked"
    assert "producer_unsupported" in _rules(verdict)


def test_known_producer_matching_result_retained(tmp_path: Path) -> None:
    """T05 positive: known pipeline + agreeing result raises no finding."""
    record, store = _case(tmp_path)
    rules = _rules(run_acceptance(record, store))
    assert "producer_unsupported" not in rules
    assert "gate_result_status_mismatch" not in rules
    assert "gate_result_status_missing" not in rules


def test_justified_but_unauthorized_na_rejected(tmp_path: Path) -> None:
    """T06: a recorded reason cannot authorize a forbidden G2 N/A pair."""
    na_env = dict(ENV, locale="not_applicable")
    record, store = _case(
        tmp_path, gate_env=na_env, env_env=na_env,
        justification={"locale": "locale does not matter here"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)


def test_scope_na_rejected(tmp_path: Path) -> None:
    """T06: both-side query N/A is rejected even with a recorded reason."""
    na_scope = dict(SCOPE, query_context="not_applicable",
                    query_hash="not_applicable")
    record, store = _case(
        tmp_path, gate_scope=na_scope, env_scope=na_scope,
        justification={"query_context": "no query ran",
                       "query_hash": "no query ran"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)


def test_authorized_g5_view_state_na_accepted(tmp_path: Path) -> None:
    """T06 positive: G5/view_state N/A with reason is genuinely inapplicable."""
    na_env = dict(ENV, view_state="not_applicable")
    record, store = _case(
        tmp_path, gate_id="G5", subject_id="d1", source=SOURCE_D,
        kind="docx", gate_env=na_env, env_env=na_env,
        justification={"view_state": "documents have no view state"})
    assert "na_unjustified" not in _rules(run_acceptance(record, store))


def test_authorized_pair_without_reason_rejected(tmp_path: Path) -> None:
    """T06: even the authorized G5 pair needs its recorded reason."""
    na_env = dict(ENV, view_state="not_applicable")
    record, store = _case(
        tmp_path, gate_id="G5", subject_id="d1", source=SOURCE_D,
        kind="docx", gate_env=na_env, env_env=na_env)
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)


def test_g5_locale_na_rejected(tmp_path: Path) -> None:
    """T06: locale stays applicable for docx gates despite a reason."""
    na_env = dict(ENV, locale="not_applicable")
    record, store = _case(
        tmp_path, gate_id="G5", subject_id="d1", source=SOURCE_D,
        kind="docx", gate_env=na_env, env_env=na_env,
        justification={"locale": "language-neutral document"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)


@pytest.mark.parametrize("gate_id", ["G0", "G1", "G6"])
def test_docx_view_state_na_accepted(tmp_path: Path, gate_id: str) -> None:
    """T06: docx-subject view_state N/A with reason passes on docx gates."""
    na_env = dict(ENV, view_state="not_applicable")
    record, store = _case(
        tmp_path, gate_id=gate_id, subject_id="d1", source=SOURCE_D,
        kind="docx", gate_env=na_env, env_env=na_env,
        justification={"view_state": "documents have no view state"})
    assert "na_unjustified" not in _rules(run_acceptance(record, store))


@pytest.mark.parametrize("gate_id", ["G0", "G1", "G6"])
def test_pbip_view_state_na_rejected(tmp_path: Path, gate_id: str) -> None:
    """T06: pbip-subject view_state N/A fails even with a reason."""
    na_env = dict(ENV, view_state="not_applicable")
    record, store = _case(
        tmp_path, gate_id=gate_id, gate_env=na_env, env_env=na_env,
        justification={"view_state": "no view state in this run"})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)
