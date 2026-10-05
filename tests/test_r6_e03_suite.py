"""R6-E03: suite-level G6 binds the exact subject/source set.

Oracle A03: one-subject G6, omitted DOCX, reordered/drifted suites,
and old review receipts all fail/block through the public acceptance
API and the real store. Suite checks precede producer capability, so
malformed suites get precise rules while the missing genuine reviewer
capability stays blocked, never a simulated pass.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore, canonical_json_sha256
from vqs.run_store import append_event, create_run, seal_run

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "d" * 64
SOURCE_OLD = "e" * 64
ENV = {"renderer": "r", "renderer_version": "1", "locale": "en",
       "view_state": "default"}


def _subjects() -> list[dict[str, str]]:
    return [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A,
             "layout_digest": "l" * 64},
            {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B,
             "layout_digest": "m" * 64},
            {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]


def _suite_digest(triples: list[dict[str, str]]) -> str:
    ordered = sorted(triples, key=lambda triple: triple["id"])
    return canonical_json_sha256(ordered)


def _suite(triples: list[dict[str, str]] | None = None) -> dict[str, Any]:
    members = triples if triples is not None else [
        {"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
        {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B},
        {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]
    return {"subjects": members, "suite_digest": _suite_digest(members)}


def _forge_g6(root: Path, run_id: str, suite_digest: str,
              env: dict[str, Any] | None = None) -> str:
    envelope = {"environment": dict(env or ENV),
                "producer": {"run_id": run_id, "gate": "G6",
                             "status": "pass", "control": None},
                "result": {"gate": "G6", "status": "pass",
                           "suite_digest": suite_digest}}
    raw = json.dumps(envelope, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    return sha


def _hand_seal(root: Path, run_id: str, sha: str) -> None:
    run_dir = create_run(root, run_id, {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": "G6",
                        "status": "pass", "control": None,
                        "observation": {"gate": "G6", "status": "pass",
                                      "controls": [],
                                      "input_sha256": "0" * 64}})


def _g6_gate(sha: str, suite_digest: str,
             env: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": "G6", "status": "pass", "suite_digest": suite_digest,
            "evidence_ref": {"sha256": sha, "suite_digest": suite_digest},
            "environment": dict(env or ENV)}


def _rules(verdict: dict[str, Any]) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_subject_bound_g6_retired(tmp_path: Path) -> None:
    """The exact R5 one-subject G6 encoding fails, never covers."""
    sha = _forge_g6(tmp_path, "run-1", _suite()["suite_digest"])
    _hand_seal(tmp_path, "run-1", sha)
    gate = _g6_gate(sha, _suite()["suite_digest"])
    gate["subject_id"] = "p1"
    gate["evidence_ref"] = {"sha256": sha, "source_sha256": SOURCE_A}
    record = {"subjects": _subjects(), "suite": _suite(), "gates": [gate]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "g6_subject_binding_retired" in _rules(verdict)


def test_suite_omission_fails(tmp_path: Path) -> None:
    """A suite that drops the DOCX does not bind the record."""
    members = [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
               {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B}]
    record = {"subjects": _subjects(), "suite": _suite(members),
              "gates": []}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "suite_digest_mismatch" in _rules(verdict)


def test_suite_substitution_fails(tmp_path: Path) -> None:
    """A suite swapping p2's source does not bind the record."""
    members = [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
               {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_OLD},
               {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]
    record = {"subjects": _subjects(), "suite": _suite(members),
              "gates": []}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "suite_digest_mismatch" in _rules(verdict)


def test_old_receipt_replay_fails(tmp_path: Path) -> None:
    """A digest valid for a past set fails against the current set."""
    old_members = [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
                   {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_OLD},
                   {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]
    record = {"subjects": _subjects(), "suite": _suite(old_members),
              "gates": []}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "suite_digest_mismatch" in _rules(verdict)


def test_suite_reorder_normalizes(tmp_path: Path) -> None:
    """Ordering alone never breaks the suite binding."""
    members = [{"id": "d1", "kind": "docx", "source_sha256": SOURCE_D},
               {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B},
               {"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A}]
    suite = _suite(members)
    sha = _forge_g6(tmp_path, "run-2", suite["suite_digest"])
    _hand_seal(tmp_path, "run-2", sha)
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [_g6_gate(sha, suite["suite_digest"])]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert "suite_digest_mismatch" not in _rules(verdict)
    assert "suite_subject_invalid" not in _rules(verdict)
    # Structure valid; only the missing G6-capable producer fails it.
    assert "producer_capability_exceeded" in _rules(verdict)


@pytest.mark.parametrize("suite", [
    {"subjects": "p1", "suite_digest": "0" * 64},
    {"subjects": [], "suite_digest": "short"},
    {"subjects": [{"id": "p1", "kind": "pbip"}], "suite_digest": "0" * 64},
    {"subjects": [{"id": "p1", "kind": "pbip", "source_sha256": "g" * 64}],
     "suite_digest": "0" * 64},
    {"subjects": [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
                 {"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A}],
     "suite_digest": "0" * 64},
])
def test_malformed_suite_blocks(tmp_path: Path,
                                suite: dict[str, Any]) -> None:
    """Malformed suite shapes block instead of binding anything."""
    record = {"subjects": _subjects(), "suite": suite, "gates": []}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "suite_subject_invalid" in _rules(verdict)


def test_g6_without_suite_blocks(tmp_path: Path) -> None:
    """A G6 claim with no suite block cannot bind anything."""
    digest = _suite()["suite_digest"]
    sha = _forge_g6(tmp_path, "run-3", digest)
    _hand_seal(tmp_path, "run-3", sha)
    record = {"subjects": _subjects(), "gates": [_g6_gate(sha, digest)]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "suite_subject_invalid" in _rules(verdict)


@pytest.mark.parametrize("ref", [
    {"sha256": "0" * 64},
    {"sha256": "0" * 64, "suite_digest": "1" * 64},
])
def test_g6_evidence_ref_must_bind_suite(tmp_path: Path,
                                         ref: dict[str, str]) -> None:
    """G6 evidence refs carry the suite digest, never a subject hash."""
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [{"id": "G6", "status": "pass",
                         "suite_digest": suite["suite_digest"],
                         "evidence_ref": ref, "environment": dict(ENV)}]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "invalid_evidence_ref" in _rules(verdict)


def test_envelope_suite_drift_fails(tmp_path: Path) -> None:
    """An envelope quoting a foreign suite digest fails the G6 gate."""
    suite = _suite()
    foreign = _suite_digest(
        [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_OLD}])
    sha = _forge_g6(tmp_path, "run-4", foreign)
    _hand_seal(tmp_path, "run-4", sha)
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [_g6_gate(sha, suite["suite_digest"])]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "producer_gate_mismatch" in _rules(verdict)


def test_valid_suite_g6_fails_only_on_capability(tmp_path: Path) -> None:
    """Exact suite + consistent seal: structure valid, producer missing."""
    suite = _suite()
    sha = _forge_g6(tmp_path, "run-5", suite["suite_digest"])
    _hand_seal(tmp_path, "run-5", sha)
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [_g6_gate(sha, suite["suite_digest"])]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "producer_capability_exceeded" in _rules(verdict)
    for structural in ("g6_subject_binding_retired", "suite_digest_mismatch",
                       "suite_subject_invalid", "invalid_evidence_ref",
                       "evidence_unresolved", "evidence_tampered",
                       "producer_gate_mismatch", "producer_binding_mismatch"):
        assert structural not in _rules(verdict)


def test_g6_na_unauthorized_without_subject(tmp_path: Path) -> None:
    """Suite G6 has no subject kind, so no N/A pair is authorized."""
    suite = _suite()
    env = dict(ENV, view_state="not_applicable")
    sha = _forge_g6(tmp_path, "run-6", suite["suite_digest"], env=env)
    _hand_seal(tmp_path, "run-6", sha)
    gate = _g6_gate(sha, suite["suite_digest"], env=env)
    gate["na_justification"] = {"view_state": "no view in a suite"}
    record = {"subjects": _subjects(), "suite": suite, "gates": [gate]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "na_unjustified" in _rules(verdict)
