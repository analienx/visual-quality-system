"""Adversarial tests: only exact, schema-equivalent native Save is attestable."""
from __future__ import annotations

import copy
import json
import os
import time

import pytest

from vqs.powerbi.desktop_native_provenance import (
    SCHEMA,
    metadata_source,
    snapshot,
    verify,
)
from vqs.powerbi.desktop_source import assess


@pytest.fixture
def native_witness(tmp_path):
    project = tmp_path / "scratch-copy"
    report = project / "Example.Report"
    model = project / "Example.SemanticModel"
    report.mkdir(parents=True)
    model.mkdir()
    wrapper = project / "Example.pbip"
    wrapper.write_text('{"$schema":"canonical","version":"1.0"}', encoding="utf8")
    ref = report / "definition.pbir"
    ref.write_text(json.dumps({
        "$schema": "canonical", "datasetReference": {
            "byPath": {"path": "../Example.SemanticModel"}
        }
    }), encoding="utf8")
    (report / "report.json").write_text('{"visuals":[]}', encoding="utf8")
    (model / "model.tmdl").write_text("model", encoding="utf8")
    pid = 5412
    created = time.time() + 5
    started = created + 4
    before = snapshot(project)
    metadata_pre = metadata_source(project)
    for path in (wrapper, ref):
        data = json.loads(path.read_text())
        data.pop("$schema")
        path.write_text(json.dumps(data), encoding="utf8")
    os.utime(wrapper, (started + .1, started + .1))
    os.utime(ref, (started + .1, started + .1))
    after = snapshot(project)
    metadata_post = metadata_source(project)
    witness = {
        "schema": SCHEMA, "desktop_pid": pid,
        "pbip": str(wrapper.resolve()), "report": str(report.resolve()),
        "model": str(model.resolve()), "process_created": created,
        "native_save_control": {
            "method": "InvokePattern", "automation_id": "save",
            "button": "Save", "pid": pid, "window": "Example",
        }, "save_start_epoch": started, "saved_observed_epoch": started + 3,
        "unsaved_before": True, "unsaved_after": False,
        "manifest_before": before, "manifest_after": after,
        "metadata_before": metadata_pre, "metadata_after": metadata_post,
        "independent_g2_g4_g6": "blocked",
    }
    process = {
        "pid": pid, "name": "PBIDesktop.exe",
        "cmdline": ["PBIDesktop.exe", str(wrapper)], "create_time": created,
    }
    preview = {"data": {
        "state": "ready", "reports": [{
            "folder": str(report), "hostInstanceId": str(pid),
        }], "details": {"hasUnsavedChanges": False},
    }}
    return project, pid, created, witness, process, preview


def test_native_source_save_has_positive_and_default_negative(native_witness):
    project, pid, created, witness, process, preview = native_witness
    passed, reason, detail = verify(project, pid, created, witness)
    assert passed and detail["native_save_witness_verified"] is True, reason
    assert len(detail["saved_metadata_only_byte_changes"]) == 2
    default = assess(project, pid, process, preview)
    assert default["status"] == "blocked"
    assert "modified after" in default["reason"]
    native = assess(
        project, pid, process, preview, native_save_witness=witness,
    )
    assert native["status"] == "pass"
    assert native["source_provenance_method"] == "native_uia_saved_source"
    assert native["local_model_reference"] == "byPath_source_checked"


@pytest.mark.parametrize("change", [
    lambda w: w.update(desktop_pid=10),
    lambda w: w.update(model="different.SemanticModel"),
    lambda w: w.update(unsaved_before=False),
    lambda w: w.update(unsaved_after=True),
    lambda w: w.update(save_start_epoch=0),
    lambda w: w["native_save_control"].update(method="synthetic-click"),
    lambda w: w["native_save_control"].update(automation_id="other"),
    lambda w: w["manifest_before"].clear(),
    lambda w: w["manifest_after"].clear(),
    lambda w: w["metadata_before"].update({"Example.pbip": "{}"}),
])
def test_forged_native_receipt_never_attests(native_witness, change):
    project, pid, created, witness, process, preview = native_witness
    tampered = copy.deepcopy(witness)
    change(tampered)
    assert verify(project, pid, created, tampered)[0] is False
    assert assess(project, pid, process, preview,
                  native_save_witness=tampered)["status"] == "blocked"


def test_dirty_bridge_blocks_even_valid_native_save(native_witness):
    project, pid, _, witness, process, preview = native_witness
    preview["data"]["details"]["hasUnsavedChanges"] = True
    attestation = assess(project, pid, process, preview, native_save_witness=witness)
    assert attestation["status"] == "blocked"
    assert "unsaved" in attestation["reason"]


def test_source_mutation_after_saved_snapshot_is_rejected(native_witness):
    project, pid, created, witness, *_ = native_witness
    (project / "Example.SemanticModel" / "model.tmdl").write_text("tampered")
    assert not verify(project, pid, created, witness)[0]


def test_witness_must_not_hide_substantive_save_change(native_witness):
    project, pid, created, witness, *_ = native_witness
    file = project / "Example.Report" / "report.json"
    file.write_text('{"visuals":[{"modified":true}]}', encoding="utf8")
    witness["manifest_after"] = snapshot(project)
    assert not verify(project, pid, created, witness)[0]


def test_changed_metadata_semantics_rejected_even_with_updated_fingerprint(native_witness):
    project, pid, created, witness, *_ = native_witness
    wrapper = project / "Example.pbip"
    wrapper.write_text('{"version":"9000"}', encoding="utf8")
    witness["manifest_after"] = snapshot(project)
    witness["metadata_after"] = metadata_source(project)
    assert not verify(project, pid, created, witness)[0]


def test_duplicate_bridge_registry_blocks(native_witness):
    project, pid, _, witness, process, preview = native_witness
    preview["data"]["reports"].append(dict(preview["data"]["reports"][0]))
    assert assess(project, pid, process, preview,
                  native_save_witness=witness)["status"] == "blocked"


def _witness_with_visual_reserialization(native_witness):
    project, pid, created, witness, _process, _preview = native_witness
    page_visual = (project / "Example.Report" / "definition" / "pages" /
                   "p1" / "visuals" / "a1" / "visual.json")
    page_visual.parent.mkdir(parents=True)
    original = '{"visual":{"visualType":"clusteredBarChart","objects":{"dataPoint":[{"properties":{"fill":{"solid":{"color":{"expr":{"ThemeDataColor":{"ColorId":2,"Percent":0}}}}}}}]}}}'
    page_visual.write_text(original, encoding="utf8")
    os.utime(page_visual, (created - 1, created - 1))
    rel = page_visual.relative_to(project).as_posix()
    witness["manifest_before"][rel] = snapshot(project)[rel]
    page_visual.write_text(json.dumps(json.loads(original), indent=2), encoding="utf8")
    os.utime(page_visual, (created + 4.5, created + 4.5))
    witness["manifest_after"] = snapshot(project)
    witness["visual_json_before"] = {rel: original}
    return project, pid, created, witness, page_visual, rel


def test_strict_byte_hash_matched_pbir_visual_reserialization_is_valid(native_witness):
    project, pid, created, witness, _file, rel = (
        _witness_with_visual_reserialization(native_witness))
    ok, reason, detail = verify(project, pid, created, witness)
    assert ok, reason
    assert detail["saved_semantically_equivalent_visual_changes"] == [rel]
    assert len(detail["saved_metadata_only_byte_changes"]) == 2


@pytest.mark.parametrize("mutation", ["wrong_before", "changed_value", "missing_before",
                                      "duplicate_json", "nonfinite_json"])
def test_visual_semantic_changes_and_forged_presave_bytes_fail_closed(
    native_witness, mutation,
):
    project, pid, created, witness, file, rel = (
        _witness_with_visual_reserialization(native_witness))
    if mutation == "wrong_before":
        witness["visual_json_before"][rel] = '{"visual":{"visualType":"other"}}'
    elif mutation == "missing_before":
        del witness["visual_json_before"][rel]
    else:
        if mutation == "changed_value":
            doc = json.loads(file.read_text())
            doc["visual"]["objects"]["dataPoint"][0]["properties"]["fill"][
                "solid"]["color"]["expr"]["ThemeDataColor"]["ColorId"] = 7
            file.write_text(json.dumps(doc, indent=2), encoding="utf8")
        elif mutation == "duplicate_json":
            file.write_text('{"visual":{"visualType":"x"},"visual":{"visualType":"x"}}')
        else:
            file.write_text('{"visual":{"visualType":"x","bad":NaN}}')
        os.utime(file, (created + 4.5, created + 4.5))
        witness["manifest_after"] = snapshot(project)
    ok, _reason, _detail = verify(project, pid, created, witness)
    assert ok is False


def test_report_json_mutation_cannot_claim_visual_reserialization(native_witness):
    project, pid, created, witness, *_ = native_witness
    target = project / "Example.Report" / "report.json"
    original = target.read_text(encoding="utf8")
    target.write_text('{"visuals":[] }', encoding="utf8")
    os.utime(target, (created + 4.5, created + 4.5))
    witness["manifest_after"] = snapshot(project)
    witness["visual_json_before"] = {
        "Example.Report/report.json": original}
    assert verify(project, pid, created, witness)[0] is False
