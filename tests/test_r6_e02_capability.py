"""R6-E02: gate-specific producer capability + observed-result contract.

Oracle A02: an actual run_check -> SealedEvidenceStore -> run_acceptance
chain. A valid static run mislabeled G1/G5 fails (never uses its seal
beyond G0); forged caught controls fail; failed observations cannot be
relabeled pass; caller extras can never smuggle seal identity. A
genuine static observation stays usable for exactly G0.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from vqs.acceptance import PRODUCER_GATE_CAPABILITY, run_acceptance
from vqs.data.tmdl import inventory_model
from vqs.evidence import SealedEvidenceStore
from vqs.pipeline import STATIC_OBSERVATION_GATE, run_check
from vqs.run_store import append_event, create_run, seal_run

SOURCE_A = "a" * 64
SOURCE_B = "b" * 64
SOURCE_D = "d" * 64
ENV = {"renderer": "r", "renderer_version": "1", "locale": "en",
       "view_state": "default"}
SCOPE = {"role": "analyst", "refresh_id": "r1",
         "filters": {"period": "FY26"}}


def _subjects() -> list[dict[str, str]]:
    return [{"id": "p1", "kind": "pbip", "source_sha256": SOURCE_A,
             "layout_digest": "l" * 64},
            {"id": "p2", "kind": "pbip", "source_sha256": SOURCE_B,
             "layout_digest": "m" * 64},
            {"id": "d1", "kind": "docx", "source_sha256": SOURCE_D}]


def _model(tmp_path: Path) -> Path:
    model = tmp_path / "model" / "tables"
    model.mkdir(parents=True, exist_ok=True)
    (model / "T.tmdl").write_text(
        "table T\n\n\tmeasure Good = 1\n", encoding="utf-8")
    return model.parent


def _passing_facts(tmp_path: Path) -> dict[str, Any]:
    return {"models": [{"model_dir": str(_model(tmp_path)),
                        "bindings": [{"query_ref": "T.Good"}]}]}


def _failing_facts(tmp_path: Path) -> dict[str, Any]:
    return {"models": [{"model_dir": str(_model(tmp_path)),
                        "bindings": [{"query_ref": "T.Missing"}]}]}


def _gate(gate_id: str, subject: str, source: str, sha: str) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "id": gate_id, "subject_id": subject, "status": "pass",
        "evidence_ref": {"sha256": sha, "source_sha256": source},
        "environment": dict(ENV)}
    if subject != "d1":
        gate["data_scope"] = {key: (dict(value) if isinstance(value, dict) else value)
                              for key, value in SCOPE.items()}
    return gate


def _forge_envelope(root: Path, run_id: str, gate_id: str, status: str,
                    source: str, scope: dict[str, Any] | None,
                    control: str | None = None,
                    caught: bool = False) -> str:
    envelope: dict[str, Any] = {
        "source_sha256": source, "environment": dict(ENV),
        "producer": {"run_id": run_id, "gate": gate_id,
                     "status": status, "control": control},
        "result": {"gate": gate_id, "status": status}}
    if scope is not None:
        envelope["data_scope"] = scope
    if control is not None:
        envelope["control_result"] = {"control": control, "caught": caught}
    raw = json.dumps(envelope, sort_keys=True).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    objects = root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / sha).write_bytes(raw)
    return sha


def _hand_seal(root: Path, run_id: str, sha: str, gate_id: str,
               status: str, control: str | None,
               controls: list[str] | None) -> None:
    run_dir = create_run(root, run_id, {"pipeline": "vqs.check/1"})
    append_event(run_dir, {"kind": "started"})
    append_event(run_dir, {"kind": "completed"})
    artifacts: dict[str, Any] = {"envelope_sha256": sha, "gate": gate_id,
                                 "status": status, "control": control}
    if controls is not None:
        artifacts["observation"] = {"gate": gate_id, "status": status,
                                    "controls": controls,
                                    "input_sha256": "0" * 64}
    seal_run(run_dir, "completed", artifacts=artifacts)


def _rules(verdict: dict[str, Any]) -> set[str]:
    return {finding["rule"] for finding in verdict["findings"]}


def test_capability_table_matches_producer_seal() -> None:
    """The G0-only static capability is pinned on both sides."""
    assert PRODUCER_GATE_CAPABILITY["vqs.check/1"] == frozenset({"G0"})
    assert STATIC_OBSERVATION_GATE == "G0"
    assert STATIC_OBSERVATION_GATE in PRODUCER_GATE_CAPABILITY["vqs.check/1"]


def test_reserved_seal_keys_cannot_be_smuggled(tmp_path: Path) -> None:
    """Caller extras never overwrite seal identity or observations."""
    result = run_check(_passing_facts(tmp_path), tmp_path, run_id="smuggle",
                       artifacts={"gate": "G1", "status": "pass",
                                  "control": "hidden_fifth_bar",
                                  "observation": {"gate": "G6"},
                                  "verdict_sha256": "f" * 64,
                                  "envelope_sha256": "e" * 64},
                       manifest_extra={"pipeline": "evil/9",
                                       "status": "completed"})
    assert result["verdict"] == "pass"
    manifest = result["manifest"]
    assert manifest["pipeline"] == "vqs.check/1"
    assert "gate" not in manifest["artifacts"]
    assert manifest["artifacts"]["observation"]["gate"] == "G0"
    assert manifest["artifacts"]["observation"]["status"] == "pass"
    assert manifest["artifacts"]["observation"]["controls"] == []
    assert manifest["artifacts"]["verdict_sha256"] != "f" * 64
    assert manifest["bindings"]["tool"] == "vqs.check/1"


def test_genuine_static_observation_usable_for_g0_only(tmp_path: Path) -> None:
    """A real run_check observation covers G0; nothing else clears."""
    facts = _passing_facts(tmp_path)
    assert inventory_model(_model(tmp_path))["tables"]["T"]["measures"]["Good"]
    result = run_check(facts, tmp_path, run_id="genuine",
                       environment=dict(ENV),
                       evidence={"source_sha256": SOURCE_A,
                                 "data_scope": dict(SCOPE)})
    assert result["verdict"] == "pass"
    assert result["envelope_sha256"]
    record = {"subjects": _subjects(),
              "gates": [_gate("G0", "p1", SOURCE_A,
                              result["envelope_sha256"])]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert not any(finding["status"] == "fail"
                   for finding in verdict["findings"])
    incomplete = next(finding for finding in verdict["findings"]
                      if finding["rule"] == "gate_set_incomplete")
    assert "G0:p1" not in incomplete["missing"]
    assert "G6:suite" in incomplete["missing"]


@pytest.mark.parametrize("gate_id,subject,source",
                         [("G1", "p1", SOURCE_A), ("G5", "d1", SOURCE_D)])
def test_valid_static_run_mislabeled_beyond_g0_fails(
        tmp_path: Path, gate_id: str, subject: str, source: str) -> None:
    """A genuine run never acknowledged the forged beyond-G0 envelope."""
    result = run_check(_passing_facts(tmp_path), tmp_path, run_id="real",
                       environment=dict(ENV),
                       evidence={"source_sha256": source,
                                 "data_scope": dict(SCOPE)})
    assert result["verdict"] == "pass"
    forged = _forge_envelope(tmp_path, "real", gate_id, "pass", source,
                             None if subject == "d1" else dict(SCOPE))
    record = {"subjects": _subjects(),
              "gates": [_gate(gate_id, subject, source, forged)]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "producer_binding_mismatch" in _rules(verdict)


@pytest.mark.parametrize("gate_id,subject,source",
                         [("G1", "p1", SOURCE_A), ("G2", "p1", SOURCE_A),
                          ("G5", "d1", SOURCE_D)])
def test_consistent_forge_beyond_capability_fails(
        tmp_path: Path, gate_id: str, subject: str, source: str) -> None:
    """Even fully consistent bindings cannot mint unobserved gates."""
    scope = None if subject == "d1" else dict(SCOPE)
    sha = _forge_envelope(tmp_path, "forge-1", gate_id, "pass", source,
                          scope)
    _hand_seal(tmp_path, "forge-1", sha, gate_id, "pass", None, [])
    record = {"subjects": _subjects(),
              "gates": [_gate(gate_id, subject, source, sha)]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "producer_capability_exceeded" in _rules(verdict)


def test_forged_caught_control_on_static_run_fails(tmp_path: Path) -> None:
    """Static runs seal no controls, so caught claims are uncorroborated."""
    sha = _forge_envelope(tmp_path, "forge-2", "G0", "pass", SOURCE_A,
                          dict(SCOPE), control="hidden_fifth_bar",
                          caught=True)
    _hand_seal(tmp_path, "forge-2", sha, "G0", "pass",
               "hidden_fifth_bar", [])
    gate = _gate("G0", "p1", SOURCE_A, sha)
    gate["negative_control"] = "hidden_fifth_bar"
    gate["caught"] = True
    record = {"subjects": _subjects(), "gates": [gate]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "caught_uncorroborated" in _rules(verdict)


def test_failed_observation_cannot_relabel_pass(tmp_path: Path) -> None:
    """The emitted envelope carries the actual failed verdict."""
    result = run_check(_failing_facts(tmp_path), tmp_path, run_id="failed",
                       environment=dict(ENV),
                       evidence={"source_sha256": SOURCE_A,
                                 "data_scope": dict(SCOPE)})
    assert result["verdict"] == "fail"
    assert result["envelope_sha256"]
    record = {"subjects": _subjects(),
              "gates": [_gate("G0", "p1", SOURCE_A,
                              result["envelope_sha256"])]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "fail"
    assert "producer_result_mismatch" in _rules(verdict)


def test_missing_observation_blocks_coverage(tmp_path: Path) -> None:
    """A seal without an observation cannot corroborate its envelope."""
    sha = _forge_envelope(tmp_path, "forge-3", "G0", "pass", SOURCE_A,
                          dict(SCOPE))
    _hand_seal(tmp_path, "forge-3", sha, "G0", "pass", None, None)
    record = {"subjects": _subjects(),
              "gates": [_gate("G0", "p1", SOURCE_A, sha)]}
    verdict = run_acceptance(record, SealedEvidenceStore(tmp_path))
    assert verdict["verdict"] == "blocked"
    assert "producer_observation_missing" in _rules(verdict)


def test_malformed_evidence_context_blocks_without_run(tmp_path: Path) -> None:
    """Envelope emission needs an exact source digest, else no run."""
    result = run_check(_passing_facts(tmp_path), tmp_path, run_id="bad-ev",
                       evidence={"source_sha256": "short"})
    assert result["verdict"] == "blocked"
    assert result["run_dir"] is None
    assert result["envelope_sha256"] is None
