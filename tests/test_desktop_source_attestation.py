"""Adversarial source identity checks: a matching label is never sufficient."""
from __future__ import annotations

import os
import time

import pytest

from vqs.powerbi.desktop_source import assess


@pytest.fixture
def witness(tmp_path):
    project = tmp_path / "candidate"
    report = project / "Contoso Retail.Report"
    report.mkdir(parents=True)
    (report / "report.json").write_text("{}", encoding="utf8")
    pbip = project / "Contoso Retail.pbip"
    pbip.write_text("{}", encoding="utf8")
    now = time.time()
    process = {"pid": 4107, "name": "PBIDesktop.exe",
               "cmdline": ["C:/Program Files/Power BI Desktop/PBIDesktop.exe", str(pbip)],
               "create_time": now + 5}
    preview = {"data": {"state": "ready",
                        "reports": [{"folder": str(report), "hostInstanceId": "4107"}],
                        "details": {"hasUnsavedChanges": False}}}
    return project, process, preview


def test_exact_process_bridge_and_saved_source_pass(witness):
    project, process, preview = witness
    proof = assess(project, 4107, process, preview)
    assert proof["status"] == "pass"
    assert proof["loaded_file_attested"] is True
    assert proof["source_report"] == str((project / "Contoso Retail.Report").resolve())


@pytest.mark.parametrize("change,reason", [
    (lambda p, b: p.update(pid=77), "PID"),
    (lambda p, b: p.update(name="msmdsrv.exe"), "executable"),
    (lambda p, b: p.update(cmdline=["PBIDesktop.exe"]), "PBIP"),
    (lambda p, b: p.update(cmdline=["PBIDesktop.exe", "unrelated.pbip"]), "PBIP"),
    (lambda p, b: p.update(cmdline=p["cmdline"] + [p["cmdline"][1]]), "ambiguous"),
    (lambda p, b: p.update(create_time=None), "timestamp"),
    (lambda p, b: b["data"].update(state="loading"), "ready"),
    (lambda p, b: b["data"].update(reports=[]), "ambiguous"),
    (lambda p, b: b["data"]["reports"][0].update(hostInstanceId="77"), "PID"),
    (lambda p, b: b["data"]["reports"][0].update(folder="/other/Contoso Retail.Report"),
     "folder"),
    (lambda p, b: b["data"]["details"].update(hasUnsavedChanges=True), "unsaved"),
    (lambda p, b: b["data"]["details"].pop("hasUnsavedChanges"), "flag"),
])
def test_negative_control_never_attests_wrong_or_unsaved_source(witness, change, reason):
    project, process, preview = witness
    change(process, preview)
    result = assess(project, 4107, process, preview)
    assert result["status"] == "blocked"
    assert result["loaded_file_attested"] is False
    assert reason.lower() in result["reason"].lower()


def test_source_changed_after_process_started_invalidates_prior_attestation(witness):
    project, process, preview = witness
    source = project / "Contoso Retail.Report" / "report.json"
    os.utime(source, (process["create_time"] + 10, process["create_time"] + 10))
    result = assess(project, 4107, process, preview)
    assert not result["loaded_file_attested"]
    assert "modified after" in result["reason"]


def test_process_label_does_not_override_ambiguous_registry(witness):
    project, process, preview = witness
    preview["data"]["reports"].append(dict(preview["data"]["reports"][0]))
    assert assess(project, 4107, process, preview)["status"] == "blocked"


def test_unknown_saved_state_does_not_default_to_saved(witness):
    project, process, preview = witness
    preview["data"]["details"]["hasUnsavedChanges"] = "false"
    assert assess(project, 4107, process, preview)["status"] == "blocked"


def test_broken_symlink_cannot_be_used_as_report_evidence(witness):
    project, process, preview = witness
    folder = project / "Contoso Retail.Report"
    marker = folder / "symlink.json"
    try:
        marker.symlink_to(project / "absent.json")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"filesystem symlinks unsupported: {exc}")
    evidence = assess(project, 4107, process, preview)
    assert evidence["status"] == "blocked"
    assert "symlink" in evidence["reason"]


def test_wrong_project_even_with_same_filename_must_block(witness, tmp_path):
    project, process, preview = witness
    wrong = tmp_path / "other" / "Contoso Retail.pbip"
    wrong.parent.mkdir()
    wrong.write_text("{}", encoding="utf8")
    process["cmdline"][-1] = str(wrong)
    assert assess(project, 4107, process, preview)["status"] == "blocked"


def test_missing_wrapper_does_not_get_file_attestation(witness):
    project, process, preview = witness
    (project / "Contoso Retail.pbip").unlink()
    assert assess(project, 4107, process, preview)["status"] == "blocked"


def test_unrelated_second_pbip_can_be_attested_without_contoso_names(tmp_path):
    report = tmp_path / "Corporate Spend.Report"
    report.mkdir()
    (report / "definition.pbir").write_text("{}", encoding="utf8")
    wrapper = tmp_path / "Corporate Spend.pbip"
    wrapper.write_text("{}", encoding="utf8")
    pid = 4500
    process = {"pid": pid, "name": "PBIDesktop.exe",
               "cmdline": ["PBIDesktop.exe", str(wrapper)],
               "create_time": time.time() + 5}
    bridge = {"data": {"state": "ready", "reports": [
        {"folder": str(report), "hostInstanceId": str(pid)}],
        "details": {"hasUnsavedChanges": False}}}
    record = assess(tmp_path, pid, process, bridge)
    assert record["loaded_file_attested"] is True
    assert record["source_report"] == str(report.resolve())


def test_generic_attestation_blocks_ambiguous_multiple_pbip_wrappers(witness):
    project, process, preview = witness
    (project / "Corporate Spend.pbip").write_text("{}", encoding="utf8")
    record = assess(project, 4107, process, preview)
    assert record["status"] == "blocked"
    assert "exactly one" in record["reason"]


def test_generic_attestation_blocks_missing_matching_report(tmp_path):
    (tmp_path / "Different.pbip").write_text("{}", encoding="utf8")
    record = assess(tmp_path, 4107, {}, {})
    assert not record["loaded_file_attested"]
