"""End-to-end acceptance adjudication (WP-11 core, issue #16).

Aggregates per-subject gate results into a release verdict. The rules encode
the acceptance contract itself: two unrelated PBIP subjects plus a DOCX
(a partial suite is never acceptance), the complete scope-specific G0-G6
gate set with every passing gate bound to a declared subject and to a
sealed evidence envelope resolved through a trusted store, all named
negative controls present and caught on bound gates, reviewer different
from editor, and explicit user promotion approval. Anything short of that
fails or blocks — never passes.

Caller labels and hex strings alone are never evidence: without an exact
:class:`vqs.evidence.SealedEvidenceStore`, acceptance blocks. Mappings,
callables, the explicit unit-test double, and store subclasses are rejected
as untrusted. Residual assumption: the caller passes a root produced by seal
paths — acceptance verifies bytes and bindings inside the root, not which
process wrote the root. Producer-side envelope binding is later-lane work.
"""
from __future__ import annotations

from typing import Any

from vqs.evidence import SealedEvidenceStore

REQUIRED_NEGATIVES: frozenset[str] = frozenset({
    "stale_image", "wrong_pid", "blank_first_open", "partial_canvas",
    "empty_model", "hallucinated_defect", "missing_word_font",
    "narrative_mismatch", "hidden_fifth_bar", "broken_slicer",
    "false_agent_approval",
})

REQUIRED_GATES: frozenset[str] = frozenset({"G0", "G1", "G2", "G3", "G4", "G5", "G6"})

GATE_SUBJECT_KINDS: dict[str, frozenset[str]] = {
    "G0": frozenset({"pbip", "docx"}),
    "G1": frozenset({"pbip", "docx"}),
    "G2": frozenset({"pbip"}),
    "G3": frozenset({"pbip"}),
    "G4": frozenset({"pbip"}),
    "G5": frozenset({"docx"}),
    "G6": frozenset({"pbip", "docx"}),
}

COVERAGE_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("G0", "pbip"), ("G0", "docx"),
    ("G1", "pbip"), ("G1", "docx"),
    ("G2", "pbip"), ("G3", "pbip"), ("G4", "pbip"),
    ("G5", "docx"),
})

_HEX = frozenset("0123456789abcdefABCDEF")


def _is_hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in _HEX for char in value))


def run_acceptance(record: dict[str, Any],
                   evidence_store: SealedEvidenceStore | None = None
                   ) -> dict[str, Any]:
    """Adjudicate an acceptance record; see module docstring for the rules."""
    findings: list[dict[str, Any]] = []
    if not isinstance(record, dict):
        return {"verdict": "blocked", "findings": [{"rule": "record_not_an_object"}]}
    store_usable = True
    if evidence_store is None:
        findings.append({"rule": "evidence_store_missing", "status": "blocked",
                         "reason": "Release acceptance needs a trusted evidence store"})
        store_usable = False
    elif type(evidence_store) is not SealedEvidenceStore:
        findings.append({"rule": "evidence_store_untrusted", "status": "blocked",
                         "reason": "Only a sealed materialized store backs acceptance; "
                                   "mappings, doubles, and subclasses are rejected"})
        store_usable = False
    subjects = record.get("subjects", [])
    by_id: dict[str, dict[str, Any]] = {}
    if not isinstance(subjects, list):
        findings.append({"rule": "subjects_not_a_list", "status": "blocked"})
        subjects = []
    for subject in subjects:
        if (not isinstance(subject, dict) or not subject.get("id")
                or not isinstance(subject.get("id"), str)
                or subject.get("kind") not in ("pbip", "docx")
                or not _is_hex64(subject.get("source_sha256"))):
            findings.append({"rule": "subject_invalid", "status": "blocked"})
            continue
        if subject["id"] in by_id:
            findings.append({"rule": "subject_invalid", "status": "blocked",
                             "reason": f"duplicate subject id: {subject['id']}"})
            continue
        by_id[subject["id"]] = subject
    pbips = [s for s in by_id.values() if s["kind"] == "pbip"]
    docxs = [s for s in by_id.values() if s["kind"] == "docx"]
    layouts = {s.get("layout_digest") for s in pbips if s.get("layout_digest")}
    if len(pbips) < 2 or len(layouts) < 2 or len(docxs) < 1:
        findings.append({"rule": "partial_suite", "status": "blocked",
                         "reason": "Two unrelated PBIPs plus a DOCX are required"})
    gates = record.get("gates", [])
    if not isinstance(gates, list) or not gates:
        findings.append({"rule": "no_gates_evidence", "status": "blocked"})
        gates = []
    seen_negatives: set[str] = set()
    covered: set[tuple[str, str]] = set()
    g6_covered = False
    for gate in gates:
        if not isinstance(gate, dict):
            findings.append({"rule": "gate_not_an_object", "status": "blocked"})
            continue
        gate_id = gate.get("id", "?")
        status = gate.get("status", "")
        if status not in ("pass", "fail", "blocked", "unknown", "not_run"):
            findings.append({"rule": "invalid_gate_status", "status": "blocked",
                             "gate": gate_id})
            continue
        if status == "fail":
            findings.append({"rule": "gate_failed", "status": "fail", "gate": gate_id})
            continue
        if status in ("blocked", "unknown", "not_run"):
            findings.append({"rule": "gate_not_green", "status": "blocked", "gate": gate_id,
                             "detail": status})
            continue
        if not isinstance(gate_id, str) or gate_id not in REQUIRED_GATES:
            findings.append({"rule": "unknown_gate", "status": "blocked", "gate": gate_id})
            continue
        subject_ref = gate.get("subject_id", "")
        subject = by_id.get(subject_ref) if isinstance(subject_ref, str) else None
        if subject is None:
            findings.append({"rule": "gate_subject_unknown", "status": "blocked",
                             "gate": gate_id})
            continue
        if subject["kind"] not in GATE_SUBJECT_KINDS[gate_id]:
            findings.append({"rule": "gate_subject_mismatch", "status": "blocked",
                             "gate": gate_id})
            continue
        ref = gate.get("evidence_ref", {})
        if not isinstance(ref, dict) or not ref.get("sha256"):
            findings.append({"rule": "missing_evidence_link", "status": "blocked",
                             "gate": gate_id})
            continue
        if not _is_hex64(ref.get("sha256")) or not _is_hex64(ref.get("source_sha256")):
            findings.append({"rule": "invalid_evidence_ref", "status": "blocked",
                             "gate": gate_id})
            continue
        if not store_usable:
            continue
        assert evidence_store is not None
        try:
            envelope = evidence_store.resolve(ref["sha256"])
        except LookupError:
            findings.append({"rule": "evidence_unresolved", "status": "blocked",
                             "gate": gate_id})
            continue
        except ValueError:
            findings.append({"rule": "evidence_tampered", "status": "fail",
                             "gate": gate_id})
            continue
        if (envelope.get("source_sha256") != subject["source_sha256"]
                or ref.get("source_sha256") != subject["source_sha256"]):
            findings.append({"rule": "evidence_source_mismatch", "status": "fail",
                             "gate": gate_id})
            continue
        gate_env = gate.get("environment", {})
        if (not isinstance(gate_env, dict) or not gate_env.get("renderer")
                or not gate_env.get("renderer_version")):
            findings.append({"rule": "gate_environment_incomplete", "status": "blocked",
                             "gate": gate_id})
            continue
        envelope_env = envelope.get("environment", {})
        if (not isinstance(envelope_env, dict)
                or envelope_env.get("renderer") != gate_env.get("renderer")
                or envelope_env.get("renderer_version") != gate_env.get("renderer_version")):
            findings.append({"rule": "evidence_environment_mismatch", "status": "fail",
                             "gate": gate_id})
            continue
        if subject["kind"] == "pbip":
            scope = gate.get("data_scope", {})
            if (not isinstance(scope, dict) or not scope.get("role")
                    or not scope.get("refresh_id")):
                findings.append({"rule": "gate_data_scope_incomplete", "status": "blocked",
                                 "gate": gate_id})
                continue
            envelope_scope = envelope.get("data_scope", {})
            if (not isinstance(envelope_scope, dict)
                    or envelope_scope.get("role") != scope.get("role")
                    or envelope_scope.get("refresh_id") != scope.get("refresh_id")):
                findings.append({"rule": "evidence_data_scope_mismatch", "status": "fail",
                                 "gate": gate_id})
                continue
        covered.add((gate_id, subject["kind"]))
        if gate_id == "G6":
            g6_covered = True
        control = gate.get("negative_control", "")
        if control and not isinstance(control, str):
            findings.append({"rule": "invalid_negative_control", "status": "blocked",
                             "gate": gate_id})
        elif control:
            if gate.get("caught", False) is True:
                seen_negatives.add(control)
            else:
                findings.append({"rule": "negative_uncaught", "status": "fail",
                                 "control": control})
    missing_pairs = sorted(f"{gate_id}:{kind}" for gate_id, kind in COVERAGE_PAIRS
                           if (gate_id, kind) not in covered)
    if not g6_covered:
        missing_pairs.append("G6:any")
    if missing_pairs:
        findings.append({"rule": "gate_set_incomplete", "status": "blocked",
                         "missing": sorted(missing_pairs)})
    missing = REQUIRED_NEGATIVES - seen_negatives
    if missing:
        findings.append({"rule": "negative_controls_missing", "status": "blocked",
                         "missing": sorted(missing)})
    if record.get("reviewer_id", "") == record.get("editor_id", "") or not record.get("reviewer_id"):
        findings.append({"rule": "reviewer_not_independent", "status": "fail"})
    if record.get("user_approved", False) is not True:
        findings.append({"rule": "promotion_not_approved", "status": "blocked"})
    if not findings:
        return {"verdict": "pass", "findings": []}
    if any(finding.get("status") == "fail" for finding in findings):
        return {"verdict": "fail", "findings": findings}
    return {"verdict": "blocked", "findings": findings}
