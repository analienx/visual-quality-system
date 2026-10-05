"""R6-E04: verified reviewer binding + separate promotion output.

Oracle A04: reviewer evidence binds the exact editor run, suite, and
review bytes through sealed runs in the trusted store. The same run
under two aliases, a different candidate, or a drifted suite fails;
missing/malformed/untrusted reviewer authority blocks. Caller id
strings and editor-authored approval bools never authorize anything:
technical verdict and owner promotion are distinct output states.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.acceptance import run_acceptance
from vqs.evidence import SealedEvidenceStore, canonical_json_sha256
from vqs.run_store import append_event, create_run, seal_run

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "d" * 64
ENV = {"renderer": "r", "renderer_version": "1", "locale": "en",
       "view_state": "default"}


def _subjects() -> list[dict[str, str]]:
    return [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A,
             "layout_digest": "l" * 64},
            {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B,
             "layout_digest": "m" * 64},
            {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]


def _suite() -> dict[str, Any]:
    members = [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A},
               {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B},
               {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]
    ordered = sorted(members, key=lambda triple: triple["id"])
    return {"subjects": members,
            "suite_digest": canonical_json_sha256(ordered)}


def _seal_run(root: Path, run_id: str,
              artifacts: dict[str, Any] | None = None) -> None:
    run_dir = create_run(root, run_id, {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed", artifacts=dict(artifacts or {}))


def _forge_review(root: Path, reviewer_run: str,
                  suite_digest: str) -> str:
    envelope = {"environment": dict(ENV),
                "producer": {"run_id": reviewer_run, "gate": "G6",
                             "status": "pass", "control": None},
                "result": {"gate": "G6", "status": "pass",
                           "suite_digest": suite_digest}}
    raw = json.dumps(envelope, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    return sha


def _forge_g6_gate(root: Path, suite_digest: str) -> dict[str, Any]:
    sha = _forge_review(root, "reviewer-1", suite_digest)
    run_dir = create_run(root, "reviewer-1", {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha, "gate": "G6",
                        "status": "pass", "control": None,
                        "observation": {"gate": "G6", "status": "pass",
                                      "controls": [],
                                      "input_sha256": "0" * 64}})
    return {"id": "G6", "status": "pass", "suite_digest": suite_digest,
            "evidence_ref": {"sha256": sha, "suite_digest": suite_digest},
            "environment": dict(ENV)}


def _rules(verdict: dict[str, Any]) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_same_run_under_two_aliases_fails(tmp_path: Path) -> None:
    """Reviewer run == editor run fails independence, with suite + G6."""
    _seal_run(tmp_path, "editor-1")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [_forge_g6_gate(tmp_path, suite["suite_digest"])],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "editor-1",
                         "editor_run_id": "editor-1",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "reviewer_not_independent" in _rules(verdict)


def test_review_for_different_candidate_fails(tmp_path: Path) -> None:
    """A review bound to another editor run fails the binding."""
    _seal_run(tmp_path, "editor-1")
    _seal_run(tmp_path, "editor-2")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "reviewer-9",
                         "editor_run_id": "editor-2",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "reviewer_binding_mismatch" in _rules(verdict)


def test_review_for_drifted_suite_fails(tmp_path: Path) -> None:
    """A review bound to a foreign suite digest fails the binding."""
    _seal_run(tmp_path, "editor-1")
    _seal_run(tmp_path, "reviewer-9")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "reviewer-9",
                         "editor_run_id": "editor-1",
                         "suite_digest": "2" * 64,
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "reviewer_binding_mismatch" in _rules(verdict)


def test_missing_review_with_g6_claim_blocks_reviewer_leg(
        tmp_path: Path) -> None:
    """A G6 claim without review evidence blocks the reviewer leg."""
    _seal_run(tmp_path, "editor-1")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite,
              "gates": [_forge_g6_gate(tmp_path, suite["suite_digest"])],
              "editor_run_id": "editor-1"}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert "reviewer_binding_missing" in _rules(verdict)
    # The G6 gate itself still fails on producer capability.
    assert "producer_capability_exceeded" in _rules(verdict)


def test_malformed_review_blocks(tmp_path: Path) -> None:
    """Malformed review blocks never bind anything."""
    _seal_run(tmp_path, "editor-1")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "reviewer-1"}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "reviewer_binding_missing" in _rules(verdict)


def test_untrusted_reviewer_run_blocks(tmp_path: Path) -> None:
    """A review naming an unsealed run blocks on missing evidence."""
    _seal_run(tmp_path, "editor-1")
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "ghost",
                         "editor_run_id": "editor-1",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "reviewer_binding_missing" in _rules(verdict)


def test_correct_structure_blocks_only_on_authority(tmp_path: Path) -> None:
    """Exact editor + suite + review bytes: only authority is missing."""
    _seal_run(tmp_path, "editor-1")
    suite = _suite()
    sha = _forge_review(tmp_path, "reviewer-1", suite["suite_digest"])
    run_dir = create_run(tmp_path, "reviewer-1",
                         {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed",
             artifacts={"envelope_sha256": sha,
                        "editor_run_id": "editor-1",
                        "suite_digest": suite["suite_digest"]})
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "reviewer-1",
                         "editor_run_id": "editor-1",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": sha}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "reviewer_authority_unsupported" in _rules(verdict)
    assert "reviewer_binding_mismatch" not in _rules(verdict)
    assert "reviewer_not_independent" not in _rules(verdict)


def test_editor_authored_approval_cannot_promote(tmp_path: Path) -> None:
    """Legacy id strings + approval bool authorize nothing."""
    record = {"subjects": _subjects(), "gates": [],
              "reviewer_id": "agent-a", "editor_id": "agent-a",
              "user_approved": True}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["promotion"] == {
        "status": "blocked",
        "findings": [{"rule": "promotion_authority_unregistered",
                      "status": "blocked"}]}
    assert "reviewer_not_independent" not in _rules(verdict)


def test_technical_and_promotion_are_separate_outputs(
        tmp_path: Path) -> None:
    """Promotion state never leaks into the technical verdict."""
    _seal_run(tmp_path, "editor-1")
    record = {"subjects": _subjects(), "gates": [],
              "editor_run_id": "editor-1",
              "review": {"reviewer_run_id": "editor-1",
                         "editor_run_id": "editor-1",
                         "suite_digest": "2" * 64,
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert verdict["promotion"]["status"] == "blocked"
    assert verdict["promotion"]["findings"] != verdict["findings"]
    assert set(verdict) == {"verdict", "promotion", "findings"}


def test_missing_editor_run_id_blocks(tmp_path: Path) -> None:
    """A review without a record-side editor run binds nothing."""
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "review": {"reviewer_run_id": "reviewer-9",
                         "editor_run_id": "editor-1",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "editor_run_unbound" in _rules(verdict)


def test_unsealed_editor_run_id_blocks(tmp_path: Path) -> None:
    """A review naming an unsealed editor run binds nothing."""
    suite = _suite()
    record = {"subjects": _subjects(), "suite": suite, "gates": [],
              "editor_run_id": "ghost-9",
              "review": {"reviewer_run_id": "reviewer-9",
                         "editor_run_id": "ghost-9",
                         "suite_digest": suite["suite_digest"],
                         "review_envelope_sha256": "1" * 64}}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "editor_run_unbound" in _rules(verdict)
