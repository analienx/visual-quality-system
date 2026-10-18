"""Source-bound, metadata-backed pre-candidate cosmetic repair refusal oracle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_r6_e07_authoring import VISUAL_REL, _project

from vqs.pipeline import repair_candidate
from vqs.powerbi.author import compile as gate
from vqs.repair.execute import apply_plan, tree_digest


def _attested() -> dict:
    return {
        "status": "pass", "policy": "microsoft", "mutation_engine": "vqs_typed",
        "validation_provider": "microsoft", "assurance": "microsoft_structural_only",
        "skill": {"snapshot": {"sha256": "a" * 64}},
        "probe": {"path": "/approved/cli", "version": "0.5.0", "available": True},
        "cli": {"status": "pass", "path": "/approved/cli", "version": "0.5.0"},
    }


def _metadata(_att, operation: str, *args):
    if operation == "catalog.describe":
        return {"status": "pass", "sha256": "b" * 64,
                "data": {"deprecated": False, "requiredRoles": ["Category", "Y"]}}
    return {"status": "pass", "sha256": "c" * 64,
            "data": {"property": {"type": "integer"}}}


def _plan(proj: Path):
    return json.loads((proj / "plan.json").read_text(encoding="utf-8"))


def test_bound_visual_property_and_source_receipt(tmp_path: Path, monkeypatch):
    proj, original = _project(tmp_path)
    monkeypatch.setattr(gate.metadata, "query", _metadata)
    receipt = gate.evaluate(_plan(proj), str(original), _attested())
    assert receipt["status"] == "pass", receipt
    assert receipt["source_tree_sha256"] == tree_digest(original)
    assert receipt["operations"][0]["property"] == "categoryAxis.labelPrecision"
    assert receipt["operations"][0]["old"] == "2"
    assert receipt["operations"][0]["new"] == "3"
    assert len(receipt["sha256"]) == 64
    assert receipt["mutates_report"] is False


@pytest.mark.parametrize("alter", ["missing-visual", "wrong-id", "wrong-property",
                                     "wrong-type", "wrong-old", "selector-escape"])
def test_unknown_format_or_unbound_source_refused(tmp_path: Path, monkeypatch, alter):
    proj, original = _project(tmp_path)
    plan = _plan(proj)
    source_file = original / VISUAL_REL
    doc = json.loads(source_file.read_text(encoding="utf-8"))
    if alter == "missing-visual":
        source_file.unlink()
    elif alter == "wrong-id":
        doc["name"] = "someone-else"
    elif alter == "wrong-property":
        doc["visual"]["objects"]["categoryAxis"][0]["properties"].pop("labelPrecision")
    elif alter == "wrong-type":
        doc["visual"]["objects"]["categoryAxis"][0]["properties"]["labelPrecision"][
            "expr"]["Literal"]["Value"] = 2
    elif alter == "wrong-old":
        plan["operations"][0]["value"] = True
    else:
        plan["operations"][0]["selector"]["page"] = "../P1"
    if alter in ("wrong-id", "wrong-property", "wrong-type"):
        source_file.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(gate.metadata, "query", _metadata)
    result = gate.evaluate(plan, str(original), _attested())
    assert result["status"] == "blocked", (alter, result)


def test_metadata_lookup_refuses_unsupported_or_deprecated(tmp_path: Path, monkeypatch):
    proj, original = _project(tmp_path)
    for method in ("deprecated", "unknown-property", "unknown-type"):
        def outcome(_att, capability, *args, method=method):
            item = _metadata(_att, capability, *args)
            if method == "deprecated" and capability == "catalog.describe":
                item["data"]["deprecated"] = True
            if method == "unknown-property" and capability != "catalog.describe":
                item = {"status": "blocked", "reason": "unsupported"}
            if method == "unknown-type" and capability != "catalog.describe":
                item["data"]["property"]["type"] = "formatting"
            return item

        monkeypatch.setattr(gate.metadata, "query", outcome)
        receipt = gate.evaluate(_plan(proj), str(original), _attested())
        assert receipt["status"] == "blocked", (method, receipt)


def test_microsoft_metadata_refusal_precedes_run_and_candidate(
        tmp_path: Path, monkeypatch):
    from vqs.powerbi.author import preflight

    proj, original = _project(tmp_path)
    monkeypatch.setattr(preflight, "check", lambda policy: _attested())
    monkeypatch.setattr(gate.metadata, "query",
                        lambda *a: {"status": "blocked", "reason": "unknown"})
    candidate = proj / "candidate-no"
    runroot = tmp_path / "no-runs"
    result = repair_candidate(
        str(proj / "plan.json"), str(original), str(candidate),
        run_root=str(runroot), run_id="metadata-no",
        authoring_backend="microsoft")
    assert result["verdict"] == "blocked"
    assert "metadata" in result["blocked_reasons"][0].lower()
    assert not candidate.exists()
    assert not runroot.exists()


def test_successfully_metadata_bound_repair_is_sealed(
        tmp_path: Path, monkeypatch):
    from vqs.powerbi.author import adapter, preflight

    proj, original = _project(tmp_path)
    monkeypatch.setattr(preflight, "check", lambda policy: _attested())
    monkeypatch.setattr(gate.metadata, "query", _metadata)
    monkeypatch.setattr(adapter, "validate", lambda *a, **kw: {
        "status": "valid", "command": ["/approved/cli", "validate"],
        "warnings": [], "errors": [], "returncode": 0,
    })
    result = repair_candidate(
        str(proj / "plan.json"), str(original), str(proj / "candidate-yes"),
        run_root=str(tmp_path / "runs"), run_id="metadata-pass",
        authoring_backend="microsoft")
    assert result["verdict"] == "pass", result
    sealed = json.loads((Path(result["run_dir"]) / "authoring.json").read_text(
        encoding="utf-8"))
    assert sealed["metadata_gate"]["status"] == "pass"
    assert sealed["metadata_gate"]["operations"][0]["source_visual_sha256"]
    assert sealed["assurance"]["structural_validation"] == "pass"


def test_stale_source_pin_refused_before_creating_candidate(tmp_path: Path):
    proj, original = _project(tmp_path)
    old = tree_digest(original)
    visual = original / VISUAL_REL
    visual.write_text(visual.read_text(encoding="utf-8") + "\n",
                      encoding="utf-8")
    candidate = proj / "candidate-stale"
    result = apply_plan(_plan(proj), str(original), str(candidate),
                        expected_original_sha=old)
    assert result["verdict"] == "blocked"
    assert result["stage"] == "source-binding"
    assert not candidate.exists()


def test_native_only_run_does_not_claim_microsoft_metadata(tmp_path: Path):
    proj, original = _project(tmp_path)
    assert gate.evaluate(_plan(proj), str(original),
                         {"validation_provider": "direct"})["status"] == "not_applicable"


def test_metadata_crash_or_incomplete_receipt_fails_closed(
        tmp_path: Path, monkeypatch):
    proj, original = _project(tmp_path)
    for invalid in (
        RuntimeError("metadata transport failed"),
        {"status": "pass", "data": {"deprecated": False}},
    ):
        def response(_att, capability, *args, invalid=invalid):
            if isinstance(invalid, BaseException):
                raise invalid
            return invalid

        monkeypatch.setattr(gate.metadata, "query", response)
        result = gate.evaluate(_plan(proj), str(original), _attested())
        assert result["status"] == "blocked", result


def test_source_changes_after_metadata_evaluation_block_before_run(
        tmp_path: Path, monkeypatch):
    from vqs.powerbi.author import preflight

    proj, original = _project(tmp_path)
    monkeypatch.setattr(preflight, "check", lambda policy: _attested())
    monkeypatch.setattr(gate.metadata, "query", _metadata)
    actual_evaluate = gate.evaluate

    def changed_after_read(plan, source, receipt):
        result = actual_evaluate(plan, source, receipt)
        assert result["status"] == "pass"
        target = original / VISUAL_REL
        target.write_bytes(target.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(gate, "evaluate", changed_after_read)
    candidate = proj / "candidate-drift"
    runs = tmp_path / "drift-runs"
    result = repair_candidate(
        str(proj / "plan.json"), str(original), str(candidate),
        run_root=str(runs), run_id="source-drift",
        authoring_backend="microsoft")
    assert result["verdict"] == "blocked"
    assert "source changed" in result["blocked_reasons"][0]
    assert not candidate.exists()
    assert not runs.exists()
