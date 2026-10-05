"""WP-11 acceptance adjudication: materialized evidence, complete gates, no fabrication.

Acceptance mapping (issue #22 P0-5 plus supervisor repros): caller labels and
hex strings alone never pass; every gate binds a declared subject and a
sealed evidence envelope through a trusted store; the G0-G6 set must be
complete per scope; malformed records block without raising.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.acceptance import REQUIRED_NEGATIVES, run_acceptance
from vqs.evidence import SealedEvidenceStore, TestEvidenceStore
from vqs.run_store import append_event, create_run, seal_run

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "c" * 64
# R14 contract migration: acceptance requires stated identity on both
# sides (locale/view_state, query_context/query_hash), so the shared
# fixtures state them; thin-identity behavior moved to test_r14.
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
    """Accumulate gates plus the sealed envelopes that back them."""
    _seq = 0

    def __init__(self) -> None:
        type(self)._seq += 1
        self._tag = type(self)._seq
        self.blobs: dict[str, bytes] = {}
        self.gates: list[dict[str, Any]] = []
        self.runs: dict[str, dict[str, Any]] = {}

    def add(self, gate_id: str, subject_id: str, source: str, kind: str,
            control: str | None = None, status: str = "pass") -> dict[str, Any]:
        run_id = f"prod-{self._tag}-{gate_id}-{subject_id}-{len(self.gates)}"
        envelope: dict[str, Any] = {"source_sha256": source, "environment": dict(ENV),
                                    "producer": {"run_id": run_id, "gate": gate_id,
                                               "status": status, "control": control},
                                    "result": {"gate": gate_id, "status": status}}
        gate: dict[str, Any] = {"id": gate_id, "subject_id": subject_id,
                                "status": status, "environment": dict(ENV)}
        if kind == "pbip":
            envelope["data_scope"] = {**SCOPE, "filters": dict(SCOPE["filters"])}
            gate["data_scope"] = {**SCOPE, "filters": dict(SCOPE["filters"])}
        if control is not None:
            envelope["control_result"] = {"control": control, "caught": True}
        raw = _envelope_bytes(envelope)
        sha = hashlib.sha256(raw).hexdigest()
        self.blobs[sha] = raw
        self.runs[run_id] = {"sha": sha, "gate": gate_id, "status": status,
                             "control": control}
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
        for run_id, spec in self.runs.items():
            run_dir = create_run(root, run_id, {"pipeline": "vqs.check/1"})
            append_event(run_dir, {"kind": "started"})
            terminal = {"pass": "completed", "fail": "failed"}.get(spec["status"], "blocked")
            append_event(run_dir, {"kind": terminal})
            # R6-E02: hand seals carry a well-formed observation so
            # structural legs isolate their own check; capability and
            # observation rules are pinned by the R6-E02 oracle.
            controls = [spec["control"]] if spec["control"] else []
            seal_run(run_dir, terminal,
                     artifacts={"envelope_sha256": spec["sha"], "gate": spec["gate"],
                                "status": spec["status"], "control": spec["control"],
                                "observation": {"gate": spec["gate"],
                                              "status": spec["status"],
                                              "controls": controls,
                                              "input_sha256": "0" * 64}})
        return SealedEvidenceStore(root)

    def record(self, **overrides: Any) -> dict[str, Any]:
        # R6-E04: legacy reviewer_id/editor_id/user_approved retired;
        # reviewer/promotion evidence is bound runs, tested in R6-E04.
        record = {"subjects": _subjects(), "gates": list(self.gates)}
        record.update(overrides)
        return record


def _full_case() -> _Case:
    # R6-E02/E03: static seals observe G0 only, and G6 is suite-level
    # (R6-E03 oracle). The shared case covers every subject with G0
    # plus every negative control; release still blocks on the gates
    # no portable producer observes.
    case = _Case()
    pairs = [("G0", "p1", SOURCE_A, "pbip"), ("G0", "p2", SOURCE_B, "pbip"),
             ("G0", "d1", SOURCE_D, "docx")]
    negatives = sorted(REQUIRED_NEGATIVES)
    for index, (gate_id, subject, source, kind) in enumerate(pairs):
        control = negatives[index] if index < len(negatives) else None
        case.add(gate_id, subject, source, kind, control=control)
    for control in negatives[len(pairs):]:
        case.add("G0", "p2", SOURCE_B, "pbip", control=control)
    return case


def _rules(verdict: dict[str, Any]) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_g0_narrow_capability_covered_release_still_blocked(
        tmp_path: Path) -> None:
    # R6-E02/E03 rewrite: the old test manufactured G1-G6 coverage
    # with static seals (the E02 bypass) plus a subject-bound G6 (the
    # E03 bypass). Genuine G0 observations cover their narrow gate;
    # the release verdict stays blocked on unobservable gates, and
    # promotion is reported separately.
    case = _full_case()
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "negative_controls_missing" not in _rules(verdict)
    assert not any(finding["status"] == "fail"
                   for finding in verdict["findings"])
    incomplete = next(finding for finding in verdict["findings"]
                      if finding["rule"] == "gate_set_incomplete")
    assert "G6:suite" in incomplete["missing"]
    assert "G1:p1" in incomplete["missing"]
    assert verdict["promotion"]["status"] == "blocked"


def test_single_pbip_is_not_acceptance(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    subjects = [s for s in _subjects() if s["id"] != "p2"]
    verdict = run_acceptance(case.record(subjects=subjects), store)
    assert verdict["verdict"] == "blocked"
    assert {"rule": "partial_suite", "status": "blocked",
            "reason": "Two unrelated PBIPs plus a DOCX are required"} in verdict["findings"]


def test_identical_layouts_are_not_unrelated(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    subjects = _subjects()
    subjects[1]["layout_digest"] = subjects[0]["layout_digest"]
    verdict = run_acceptance(case.record(subjects=subjects), store)
    assert verdict["verdict"] == "blocked"
    assert "partial_suite" in _rules(verdict)


def test_missing_negative_control_blocks(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    gates = [gate for gate in case.gates
             if gate.get("negative_control") != "hidden_fifth_bar"]
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    missing_finding = next(f for f in verdict["findings"]
                           if f["rule"] == "negative_controls_missing")
    assert missing_finding["missing"] == ["hidden_fifth_bar"]


def test_uncaught_negative_fails(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    target = next(gate for gate in gates if gate.get("negative_control"))
    target["caught"] = False
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "fail"
    assert verdict["findings"][0]["rule"] == "negative_uncaught"


def test_same_run_under_two_aliases_fails(tmp_path: Path) -> None:
    # R6-E04 rewrite: caller reviewer_id/editor_id strings are retired
    # (they never proved independence). A review block binding the
    # same sealed run as reviewer and editor fails independence.
    case = _full_case()
    store = case.store(tmp_path)
    run_dir = create_run(tmp_path, "editor-1", {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    seal_run(run_dir, "completed", artifacts={})
    record = case.record(
        editor_run_id="editor-1",
        review={"reviewer_run_id": "editor-1", "editor_run_id": "editor-1",
                "suite_digest": "0" * 64,
                "review_envelope_sha256": "1" * 64})
    verdict = run_acceptance(record, store)
    assert verdict["verdict"] == "fail"
    assert "reviewer_not_independent" in _rules(verdict)


def test_legacy_approval_bool_ignored_promotion_split(tmp_path: Path) -> None:
    # R6-E04 rewrite: user_approved bools never authorized promotion.
    # The legacy key is ignored; promotion is a separate blocked
    # output while the technical verdict stands on its own.
    case = _full_case()
    verdict = run_acceptance(case.record(user_approved=True),
                             case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert verdict["promotion"] == {
        "status": "blocked",
        "findings": [{"rule": "promotion_authority_unregistered",
                      "status": "blocked"}]}


def test_unknown_gate_status_blocks(tmp_path: Path) -> None:
    case = _Case()
    case.add("G0", "p1", SOURCE_A, "pbip", status="skipped")
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "invalid_gate_status" in _rules(verdict)


def test_arbitrary_gate_id_blocks(tmp_path: Path) -> None:
    case = _Case()
    case.add("G9-custom", "p1", SOURCE_A, "pbip")
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "unknown_gate" in _rules(verdict)


def test_missing_evidence_link_blocks(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    gates[0] = {"id": "G0", "subject_id": "p1", "status": "pass",
                "evidence_ref": {}, "environment": dict(ENV),
                "data_scope": dict(SCOPE)}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert "missing_evidence_link" in _rules(verdict)


def test_failed_gate_fails(tmp_path: Path) -> None:
    case = _Case()
    case.add("G0", "p1", SOURCE_A, "pbip", status="fail")
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "gate_failed" in _rules(verdict)


def test_not_green_gate_blocks(tmp_path: Path) -> None:
    for status in ("blocked", "unknown", "not_run"):
        case = _Case()
        case.add("G0", "p1", SOURCE_A, "pbip", status=status)
        verdict = run_acceptance(case.record(), case.store(tmp_path))
        assert verdict["verdict"] == "blocked", status
        assert "gate_not_green" in _rules(verdict), status


def test_empty_gates_block(tmp_path: Path) -> None:
    case = _full_case()
    verdict = run_acceptance(case.record(gates=[]), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "no_gates_evidence" in _rules(verdict)


def test_non_object_gate_blocks(tmp_path: Path) -> None:
    case = _full_case()
    verdict = run_acceptance(case.record(gates=["not-a-gate"]), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "gate_not_an_object" in _rules(verdict)


def test_non_object_record_blocks(tmp_path: Path) -> None:
    case = _full_case()
    assert run_acceptance("not-a-record", case.store(tmp_path)) == {
        "verdict": "blocked",
        "promotion": {"status": "blocked",
                      "findings": [{"rule": "promotion_authority_unregistered",
                                    "status": "blocked"}]},
        "findings": [{"rule": "record_not_an_object"}]}


def test_fabricated_labels_without_store_block() -> None:
    """Supervisor repro 1: 64-hex strings plus labels, no materialized evidence."""
    fake = "f" * 64
    subjects = [
        {"id": "p1", "kind": "pbip", "layout_digest": "l1", "source_sha256": fake},
        {"id": "p2", "kind": "pbip", "layout_digest": "l2", "source_sha256": fake},
        {"id": "d1", "kind": "docx", "source_sha256": fake},
    ]
    gates: list[dict[str, Any]] = []
    # R6-E03: subject gates only (G6 is suite-level now); the store is
    # still missing, so every gate blocks on evidence_store_missing.
    for index, control in enumerate(sorted(REQUIRED_NEGATIVES)):
        sid = "p1" if index % 3 != 2 else "d1"
        gate: dict[str, Any] = {
            "id": f"G{index % 6}", "subject_id": sid, "status": "pass",
            "evidence_ref": {"sha256": "b" * 64, "source_sha256": fake},
            "environment": {"renderer": "fake", "renderer_version": "0"},
            "negative_control": control, "caught": True,
        }
        if sid.startswith("p"):
            gate["data_scope"] = {"role": "fake", "refresh_id": "fake", "filters": {}}
        gates.append(gate)
    record = {"subjects": subjects, "gates": gates, "reviewer_id": "reviewer",
              "editor_id": "editor", "user_approved": True}
    verdict = run_acceptance(record)
    assert verdict["verdict"] == "blocked"
    assert "evidence_store_missing" in _rules(verdict)


def test_non_hex_digest_rejected(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["evidence_ref"] = {"sha256": "x", "source_sha256": SOURCE_A}
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert "invalid_evidence_ref" in _rules(verdict)


def test_malformed_subjects_block_without_raise(tmp_path: Path) -> None:
    """Supervisor repro 2: subjects None/str/dict fail closed, never raise."""
    case = _full_case()
    store = case.store(tmp_path)
    for value in (None, "oops", {"id": "p1"}):
        verdict = run_acceptance(case.record(subjects=value), store)  # type: ignore[arg-type]
        assert verdict["verdict"] == "blocked", type(value).__name__
        assert "subjects_not_a_list" in _rules(verdict), type(value).__name__


def test_caller_envelopes_never_become_trusted(tmp_path: Path) -> None:
    """Supervisor repro 3: self-consistent fake envelopes via Mapping/double."""
    source = "a" * 64
    env = {"renderer": "fake", "renderer_version": "0"}
    scope = {"role": "fake", "refresh_id": "fake", "filters": {}}
    record: dict[str, Any] = {
        "subjects": [
            {"id": "p1", "kind": "pbip", "layout_digest": "l1", "source_sha256": source},
            {"id": "p2", "kind": "pbip", "layout_digest": "l2", "source_sha256": source},
            {"id": "d1", "kind": "docx", "source_sha256": source},
        ],
        "gates": [], "reviewer_id": "reviewer", "editor_id": "editor",
        "user_approved": True,
    }
    envelopes: dict[str, dict[str, Any]] = {}
    for index, control in enumerate(sorted(REQUIRED_NEGATIVES)):
        sid = "p1" if index % 3 != 2 else "d1"
        envelope: dict[str, Any] = {"source_sha256": source, "environment": dict(env)}
        if sid.startswith("p"):
            envelope["data_scope"] = dict(scope)
        raw = _envelope_bytes(envelope)
        sha = hashlib.sha256(raw).hexdigest()
        envelopes[sha] = envelope
        # R6-E03: subject gates only; G6 cannot ride a subject_id.
        gate: dict[str, Any] = {
            "id": f"G{index % 6}", "subject_id": sid, "status": "pass",
            "evidence_ref": {"sha256": sha, "source_sha256": source},
            "environment": dict(env), "negative_control": control, "caught": True,
        }
        if sid.startswith("p"):
            gate["data_scope"] = dict(scope)
        record["gates"].append(gate)
    assert run_acceptance(record, envelopes)["verdict"] == "blocked"  # type: ignore[arg-type]
    assert "evidence_store_untrusted" in _rules(run_acceptance(record, envelopes))  # type: ignore[arg-type]
    double = TestEvidenceStore(envelopes)
    verdict = run_acceptance(record, double)
    assert verdict["verdict"] == "blocked"
    assert "evidence_store_untrusted" in _rules(verdict)


def test_incomplete_gate_set_blocks(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    # R6-E02: drop p2's G0 pair; the missing pair is named exactly.
    gates = [gate for gate in case.gates
             if not (gate["id"] == "G0" and gate["subject_id"] == "p2")]
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    incomplete = next(finding for finding in verdict["findings"]
                      if finding["rule"] == "gate_set_incomplete")
    assert "G0:p2" in incomplete["missing"]


def test_evidence_source_mismatch_fails(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    gate["evidence_ref"]["source_sha256"] = SOURCE_B
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "evidence_source_mismatch" in _rules(verdict)


def test_unresolved_evidence_blocks(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    gate["evidence_ref"]["sha256"] = "d" * 64
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "evidence_unresolved" in _rules(verdict)


def test_tampered_envelope_bytes_fail(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    target = next(iter(case.blobs))
    path = tmp_path / "objects" / target
    raw = bytearray(path.read_bytes())
    raw[10] ^= 0x01
    path.write_bytes(bytes(raw))
    verdict = run_acceptance(case.record(), store)
    assert verdict["verdict"] == "fail"
    assert "evidence_tampered" in _rules(verdict)


def test_environment_mismatch_fails(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    gate["environment"] = {"renderer": "other", "renderer_version": "9"}
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "evidence_environment_mismatch" in _rules(verdict)


def test_data_scope_mismatch_fails(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    gate["data_scope"] = {"role": "someone-else", "refresh_id": "refresh-1",
                          "filters": {}}
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "evidence_data_scope_mismatch" in _rules(verdict)


def test_pbip_gate_without_data_scope_blocks(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    del gate["data_scope"]
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "gate_data_scope_incomplete" in _rules(verdict)


def test_unknown_gate_subject_blocks(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G0", "p1", SOURCE_A, "pbip")
    gate["subject_id"] = "no-such-subject"
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "gate_subject_unknown" in _rules(verdict)


def test_invalid_subject_blocks(tmp_path: Path) -> None:
    case = _full_case()
    store = case.store(tmp_path)
    subjects = _subjects()
    del subjects[0]["source_sha256"]
    verdict = run_acceptance(case.record(subjects=subjects), store)
    assert verdict["verdict"] == "blocked"
    assert "subject_invalid" in _rules(verdict)


def test_gate_without_environment_blocks(tmp_path: Path) -> None:
    case = _Case()
    gate = case.add("G5", "d1", SOURCE_D, "docx")
    del gate["environment"]
    verdict = run_acceptance(case.record(), case.store(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "gate_environment_incomplete" in _rules(verdict)


def test_unhashable_gate_fields_block_without_raise(tmp_path: Path) -> None:
    """Review finding: unhashable ids/controls fail closed, never raise."""
    case = _Case()
    case.add("G0", "p1", SOURCE_A, "pbip")
    store = case.store(tmp_path)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["id"] = ["G0"]
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert "unknown_gate" in _rules(verdict)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["subject_id"] = ["p1"]
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert "gate_subject_unknown" in _rules(verdict)
    gates = [dict(gate) for gate in case.gates]
    gates[0]["negative_control"] = ["stale_image"]
    gates[0]["caught"] = True
    verdict = run_acceptance(case.record(gates=gates), store)
    assert verdict["verdict"] == "blocked"
    assert "invalid_negative_control" in _rules(verdict)


def test_store_shadow_and_subclass_rejected(tmp_path: Path) -> None:
    """Review finding: only the exact sealed store type is trusted."""
    case = _full_case()
    record = case.record()
    shadowed = TestEvidenceStore({})
    shadowed.TRUSTED = True  # type: ignore[attr-defined]
    verdict = run_acceptance(record, shadowed)
    assert verdict["verdict"] == "blocked"
    assert "evidence_store_untrusted" in _rules(verdict)

    class FakeSealed(SealedEvidenceStore):
        def resolve(self, sha256: str):  # type: ignore[override]
            return {"source_sha256": SOURCE_A, "environment": dict(ENV)}

    verdict = run_acceptance(record, FakeSealed(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "evidence_store_untrusted" in _rules(verdict)
