"""Adversarial validation for candidate rebaselining and acceptance identity."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from vqs.powerbi.acceptance_subjects import _asset, bound_subject, subject, verify_subject
from vqs.powerbi.desktop_native_provenance import snapshot
from vqs.powerbi.native_rebaseline import evaluate


@pytest.fixture
def example(tmp_path: Path) -> Path:
    root = tmp_path / "original"
    report = root / "Example.Report"
    model = root / "Example.SemanticModel"
    report.mkdir(parents=True)
    model.mkdir()
    (root / "Example.pbip").write_text('{"version":"1.0"}')
    (report / "definition.pbir").write_text(
        '{"datasetReference":{"byPath":{"path":"../Example.SemanticModel"}}}'
    )
    (model / "model.tmdl").write_text("model\n")
    pages = report / "definition" / "pages"
    pages.mkdir(parents=True)
    (pages / "pages.json").write_text(
        '{"pageOrder":["p1","p2"],"activePageName":"p1","landingPageName":"p1"}'
    )
    return root


def _png(path: Path) -> None:
    # Full valid single-pixel PNG, not merely a file extension.
    import base64
    path.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9zS1QAAAAASUVORK5CYII="
    ))


def test_pinned_subject_rejects_source_and_capture_drift(example: Path, tmp_path: Path):
    shot = tmp_path / "native.png"
    _png(shot)
    proof = subject(example, [shot])
    assert proof["human_g2_g4_signed"] is False
    assert proof["owner_g6_approved"] is False
    assert verify_subject(proof)[0]
    shot.write_bytes(b"altered")
    assert not verify_subject(proof)[0]


def test_pinned_subject_rejects_changed_model_and_forged_signoff(
    example: Path, tmp_path: Path,
):
    shot = tmp_path / "native.png"
    _png(shot)
    proof = subject(example, [shot])
    forged = copy.deepcopy(proof)
    forged["owner_g6_approved"] = True
    assert not verify_subject(forged)[0]
    (example / "Example.SemanticModel" / "model.tmdl").write_text("changed")
    assert not verify_subject(proof)[0]


def test_subject_requires_real_unique_png(example: Path, tmp_path: Path):
    fake = tmp_path / "x.png"
    fake.write_text("fake image")
    with pytest.raises(ValueError, match="valid PNG"):
        subject(example, [fake])
    _png(fake)
    with pytest.raises(ValueError, match="unique"):
        subject(example, [fake, fake])


@pytest.fixture
def two_save_receipts(example: Path, tmp_path: Path, monkeypatch):
    import shutil

    before = snapshot(example)
    pages = example / "Example.Report" / "definition" / "pages" / "pages.json"
    page = json.loads(pages.read_text())
    page["activePageName"] = "p2"
    pages.write_text(json.dumps(page))
    after = snapshot(example)
    new_root = tmp_path / "rebased"
    shutil.copytree(example, new_root)
    new_before = snapshot(new_root)
    first = {
        "schema": "vqs.native-desktop-saved-source/1",
        "pbip": str(example / "Example.pbip"),
        "desktop_pid": 141,
        "native_save_control": {
            "method": "InvokePattern", "automation_id": "save",
            "button": "Save", "pid": 141,
        },
        "unsaved_before": True, "unsaved_after": False,
        "native_saved_source_verified": False,
        "manifest_before": before, "manifest_after": after,
    }
    second = {
        "schema": "vqs.native-desktop-saved-source/1",
        "pbip": str(new_root / "Example.pbip"),
        "desktop_pid": 142,
        "process_created": 100,
        "native_save_control": {
            "method": "InvokePattern", "automation_id": "save",
            "button": "Save", "pid": 142,
        },
        "unsaved_before": True, "unsaved_after": False,
        "native_saved_source_verified": True,
        "manifest_before": new_before, "manifest_after": new_before,
    }
    monkeypatch.setattr(
        "vqs.powerbi.native_rebaseline.verify",
        lambda *_args: (True, "independent fake success", {}),
    )
    return example, first, new_root, second


def test_rebaseline_preserves_original_violation_and_requires_review(two_save_receipts):
    source, first, new, second = two_save_receipts
    result = evaluate(source, first, new, second)
    assert result["status"] == "stabilized_candidate_needs_independent_acceptance"
    assert result["first_save_semantically_accepted"] is False
    assert result["formal_g2_g4_g6"] == "blocked"
    assert len(result["first_save_changes"]) == 1
    assert result["first_save_changes"][0]["classification"] == (
        "active_page_requires_review"
    )


@pytest.mark.parametrize("mutation", [
    "different_source", "second_unattested", "forged_save", "reused_project",
    "second_changed", "first_modified",
])
def test_rebaseline_adversarial_fail_closed(two_save_receipts, mutation):
    source, first, new, second = two_save_receipts
    first, second = copy.deepcopy(first), copy.deepcopy(second)
    if mutation == "different_source":
        second["manifest_before"]["Example.pbip"]["sha256"] = "0" * 64
    elif mutation == "second_unattested":
        second["native_saved_source_verified"] = False
    elif mutation == "forged_save":
        second["native_save_control"]["method"] = "mouse_click"
    elif mutation == "reused_project":
        new = source
    elif mutation == "second_changed":
        second["manifest_after"]["Example.pbip"]["sha256"] = "0" * 64
    else:
        (source / "Example.SemanticModel" / "model.tmdl").write_text("tamper")
    assert evaluate(source, first, new, second)["status"] == "blocked"




def test_source_bound_native_receipt_replays_and_rejects_stale_bytes(
    example: Path, tmp_path: Path,
):
    shot = tmp_path / "native.png"
    _png(shot)
    pbip = example / "Example.pbip"
    report = example / "Example.Report"
    proof = subject(example, [shot])
    native = {
        "schema": "vqs.native-capture-identity/1",
        "source_unchanged_during_capture": True,
        "project": str(example.resolve()),
        "pbip": str(pbip.resolve()),
        "report": str(report.resolve()),
        "desktop_pid": 714,
        "source_files": proof["source_files"],
        "native_pages": [{**_asset(shot), "page_id": "p1", "display_name": "Page"}],
    }
    pin = bound_subject(example, native)
    assert pin["native_capture_source_bound"] is True
    assert pin["owner_g6_approved"] is False
    assert verify_subject(pin)[0]
    forged = copy.deepcopy(pin)
    forged["native_capture_receipt"]["desktop_pid"] = "other"
    assert not verify_subject(forged)[0]
    shot.write_bytes(b"tampered")
    assert not verify_subject(pin)[0]


def test_native_receipt_rejects_cross_report_source(
    example: Path, tmp_path: Path,
):
    shot = tmp_path / "native.png"
    _png(shot)
    proof = subject(example, [shot])
    native = {
        "schema": "vqs.native-capture-identity/1",
        "source_unchanged_during_capture": True,
        "project": str(example.resolve()),
        "pbip": str((example / "Example.pbip").resolve()),
        "report": str((example / "Example.Report").resolve()),
        "desktop_pid": 715,
        "source_files": {**proof["source_files"], "other/report": {
            "sha256": "0" * 64, "size": 42,
        }},
        "native_pages": [{**_asset(shot), "page_id": "p1", "display_name": "Page"}],
    }
    with pytest.raises(ValueError, match="changed since Desktop capture"):
        bound_subject(example, native)


def test_bridge_status_rejects_wrong_pid_report_or_missing_pages(
    example: Path, monkeypatch,
):
    import subprocess

    from vqs.powerbi.native_capture_provenance import _status

    pbip = (example / "Example.pbip").resolve()
    report = (example / "Example.Report").resolve()
    good = {"status": "ready", "instances": [{
        "pid": 77, "bridgeStatus": "connected",
        "currentFilePath": str(pbip), "reportDir": str(report),
        "pages": [{"id": "p1"}], "hasUnsavedChanges": False,
    }]}
    def fake(args, **_kwargs):
        del args
        return subprocess.CompletedProcess([], 0, json.dumps(good), "")
    monkeypatch.setattr("vqs.powerbi.native_capture_provenance.subprocess.run", fake)
    assert _status("fake-bridge", 77, pbip, report)["pid"] == 77
    with pytest.raises(ValueError, match="identity mismatched"):
        _status("fake-bridge", 78, pbip, report)
    good["instances"][0]["pages"] = []
    with pytest.raises(ValueError, match="page inventory missing"):
        _status("fake-bridge", 77, pbip, report)
