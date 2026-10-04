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
as untrusted. Producer authority (F27): every envelope carries a producer pointer and
the trusted root holds the sealed producer runs; acceptance requires a
valid producer seal binding the envelope bytes plus matching
gate/result/control. The remaining boundary is the root itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vqs.evidence import SealedEvidenceStore
from vqs.run_store import verify_seal

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


_SCOPE_DIMS: tuple[str, ...] = ("role", "refresh_id", "filters", "query_context", "query_hash")
_ENV_DIMS: tuple[str, ...] = ("renderer", "renderer_version", "locale", "view_state")


def _canon_dim(value: object) -> object:
    """Canonical dimension value; missing/None is unknown, never a stated value."""
    if value is None:
        return ("unknown",)
    if isinstance(value, dict):
        return ("dict", json.dumps(value, sort_keys=True, ensure_ascii=False, default=str))
    if isinstance(value, list):
        return ("list", json.dumps(value, ensure_ascii=False, default=str))
    if isinstance(value, (str, int, float, bool)):
        return ("scalar", value)
    return ("other", str(value))


def _dims_mismatch(gate_slot: object, envelope_slot: object, dims: tuple[str, ...]) -> bool:
    """True when any applicable dimension differs (F16: unknown never equals stated)."""
    if not isinstance(gate_slot, dict) or not isinstance(envelope_slot, dict):
        return True
    return any(_canon_dim(gate_slot.get(dim)) != _canon_dim(envelope_slot.get(dim))
               for dim in dims)


def _is_safe_run_id(run_id: object) -> bool:
    """True for a single confined path segment (F27 producer lookup)."""
    return (isinstance(run_id, str) and bool(run_id) and "\x00" not in run_id
            and "/" not in run_id and "\\" not in run_id and ":" not in run_id
            and run_id not in (".", "..") and Path(run_id).name == run_id
            and not Path(run_id).is_absolute())


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
        if _dims_mismatch(gate_env, envelope_env, _ENV_DIMS):
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
            if _dims_mismatch(scope, envelope_scope, _SCOPE_DIMS):
                findings.append({"rule": "evidence_data_scope_mismatch", "status": "fail",
                                 "gate": gate_id})
                continue
        producer = envelope.get("producer")
        if (not isinstance(producer, dict)
                or not isinstance(producer.get("run_id"), str) or not producer["run_id"]
                or not isinstance(producer.get("gate"), str)
                or not isinstance(producer.get("status"), str)
                or not (producer.get("control") is None or isinstance(producer.get("control"), str))):
            findings.append({"rule": "producer_authority_missing", "status": "blocked",
                             "gate": gate_id})
            continue
        run_id = producer["run_id"]
        if not _is_safe_run_id(run_id) or not isinstance(getattr(evidence_store, "root", None), Path):
            findings.append({"rule": "producer_authority_missing", "status": "blocked",
                             "gate": gate_id})
            continue
        run_dir = evidence_store.root / run_id
        if verify_seal(run_dir):
            findings.append({"rule": "producer_seal_invalid", "status": "blocked",
                             "gate": gate_id})
            continue
        try:
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            findings.append({"rule": "producer_seal_invalid", "status": "blocked",
                             "gate": gate_id})
            continue
        bound = manifest.get("artifacts", {}) if isinstance(manifest, dict) else {}
        if not isinstance(bound, dict) or bound.get("envelope_sha256") != ref["sha256"]:
            findings.append({"rule": "producer_binding_mismatch", "status": "fail",
                             "gate": gate_id})
            continue
        if producer.get("gate") != gate_id or bound.get("gate") != gate_id:
            findings.append({"rule": "producer_gate_mismatch", "status": "fail",
                             "gate": gate_id})
            continue
        if producer.get("status") != status or bound.get("status") != status:
            findings.append({"rule": "producer_result_mismatch", "status": "fail",
                             "gate": gate_id})
            continue
        gate_control = gate.get("negative_control")
        if isinstance(gate_control, str) or gate_control is None:
            norm = gate_control or None
            if producer.get("control") != norm or bound.get("control") != norm:
                findings.append({"rule": "producer_control_mismatch", "status": "fail",
                                 "gate": gate_id})
                continue
        covered.add((gate_id, subject["id"]))
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
    # F15: every applicable gate is required for each selected subject;
    # G6 stays suite-global (see below).
    missing_pairs = sorted(
        f"{gate_id}:{subject_id}"
        for subject_id, subject in by_id.items()
        for gate_id, kind in sorted(COVERAGE_PAIRS)
        if subject["kind"] == kind and (gate_id, subject_id) not in covered)
    if not g6_covered:
        missing_pairs.append("G6:any")
    if missing_pairs:
        findings.append({"rule": "gate_set_incomplete", "status": "blocked",
                         "missing": sorted(missing_pairs)})
    missing = REQUIRED_NEGATIVES - seen_negatives
    if missing:
        findings.append({"rule": "negative_controls_missing", "status": "blocked",
                         "missing": sorted(missing)})
    reviewer_id = record.get("reviewer_id")
    editor_id = record.get("editor_id")
    if (not isinstance(reviewer_id, str) or not reviewer_id.strip()
            or not isinstance(editor_id, str) or not editor_id.strip()):
        findings.append({"rule": "reviewer_editor_identity_required", "status": "blocked"})
    elif reviewer_id == editor_id:
        findings.append({"rule": "reviewer_not_independent", "status": "fail"})
    if record.get("user_approved", False) is not True:
        findings.append({"rule": "promotion_not_approved", "status": "blocked"})
    if not findings:
        return {"verdict": "pass", "findings": []}
    if any(finding.get("status") == "fail" for finding in findings):
        return {"verdict": "fail", "findings": findings}
    return {"verdict": "blocked", "findings": findings}
