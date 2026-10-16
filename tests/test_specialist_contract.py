"""P2 specialist contract and runtime adapter adversarial checks."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from vqs.review.contracts import (
    SpecialistTask,
    answer_schema,
    validate_answer,
)
from vqs.review.port import ReviewError
from vqs.review.providers.muse import MuseHighSpecialist, _provider_output
from vqs.review.specialists import KPI, TABLE, specialist_for_type


def _task(spec=KPI):
    return SpecialistTask(
        task_id="task-123", source_sha256="a" * 64, bundle_sha256="b" * 64,
        page_id="Markets_drivers", visual_id="market-sales", visual_type="card",
        specialist=spec.code, checks=spec.checks, prompt_version=spec.version,
        page_image_sha256=hashlib.sha256(b"page").hexdigest(),
        crop_image_sha256=hashlib.sha256(b"crop").hexdigest())


def _answer(task, *, verdict="pass", symptom=False):
    return {check: {
        "verdict": verdict, "observed_symptom": symptom,
        "observation": "The card border is visible with full text",
        "visible_evidence": "No truncated glyphs at the card edge",
        "location_hint": "Card's lower boundary",
        "severity_proposal": "high" if symptom else "none",
        "repair_hypothesis": None, "cannot_establish": [],
    } for check in task.checks}


def test_type_specific_contract_and_fixed_schema():
    assert specialist_for_type("cardVisual") is KPI
    assert specialist_for_type("pivotTable") is TABLE
    assert specialist_for_type("map") is None
    task = _task()
    schema = answer_schema(task.checks)
    assert set(schema["required"]) == set(task.checks)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(task.checks)
    assert not any("page_id" in item for item in schema["properties"].values())


@pytest.mark.parametrize("bad", [
    "extra", "missing", "invalid_verdict", "fake_identity", "weak_fail",
    "pass_but_symptom", "bad_unknown", "wrong_type",
])
def test_models_cannot_invent_identity_or_drop_required_checks(bad):
    task = _task()
    response = _answer(task)
    first = task.checks[0]
    if bad == "extra":
        response["irrelevant"] = response[first]
    elif bad == "missing":
        del response[first]
    elif bad == "invalid_verdict":
        response[first]["verdict"] = "fixed"
    elif bad == "fake_identity":
        response[first]["visual_id"] = "made-up"
    elif bad == "weak_fail":
        response[first].update(verdict="fail", observed_symptom=True,
                               visible_evidence="maybe", location_hint="x")
    elif bad == "pass_but_symptom":
        response[first]["observed_symptom"] = True
    elif bad == "bad_unknown":
        response[first]["cannot_establish"] = [""] * 2
    elif bad == "wrong_type":
        response[first]["observed_symptom"] = "true"
    with pytest.raises(ReviewError):
        validate_answer(task, response)


def test_blocked_verdict_retains_visible_symptom_for_confirmation():
    task = _task(TABLE)
    response = _answer(task, verdict="blocked", symptom=True)
    clean = validate_answer(task, response)
    assert all(item["needs_confirmation"] for item in clean.values())


def _real_muse_event_stream(answer, model="muse-pinned"):
    status = {
        "payload_type": "task.lifecycle.status",
        "payload": {"event": {"details": {"facets": [
            {"detail": {"kind": "provider", "model": model}}
        ]}}},
    }
    completed = {
        "payload_type": "run.terminal.completed",
        "payload": {"text": json.dumps(answer)},
    }
    return json.dumps(status) + "\n" + json.dumps(completed)


def test_model_receipt_requires_provider_event_not_llm_assertion():
    task = _task()
    answer = _answer(task)
    with pytest.raises(ReviewError, match="runtime model receipt"):
        _provider_output(json.dumps(answer), "muse-pinned")
    data, receipt = _provider_output(
        _real_muse_event_stream(answer), "muse-pinned")
    assert data == answer
    assert receipt["actual_model"] == "muse-pinned"
    with pytest.raises(ReviewError, match="did not match"):
        _provider_output(
            _real_muse_event_stream(answer, model="wrong"), "muse-pinned")


def test_two_images_tool_disabled_high_effort_model_pinned(tmp_path, monkeypatch):
    task = _task()
    page, crop = tmp_path / "page.png", tmp_path / "crop.png"
    page.write_bytes(b"page")
    crop.write_bytes(b"crop")
    monkeypatch.setenv("VQS_ALLOW_VISION_UPLOAD", "1")
    result = _answer(task, verdict="fail", symptom=True)
    def runner(command, **kwargs):
        assert command.count("--image") == 1
        assert command[command.index("--model") + 1] == "muse-pinned"
        assert command[command.index("--reasoning-effort") + 1] == "high"
        assert "--disable-shell" in command and "--disable-write" in command
        assert "--disable-web-tools" in command and "--no-session-log" in command
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 30
        paths = [Path(command[i + 1]) for i, x in enumerate(command) if x == "--image"]
        assert [p.read_bytes() for p in paths] == [b"crop"]
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        assert set(schema["required"]) == set(task.checks)
        return SimpleNamespace(
            returncode=0,
            stdout=_real_muse_event_stream(result), stderr="")
    provider = MuseHighSpecialist(
        model="muse-pinned", executable="test-muse", timeout_seconds=30,
        runner=runner)
    output = provider.review_task(task, page, crop)
    assert output["receipt"]["actual_model"] == "muse-pinned"
    assert all(v["verdict"] == "fail" for v in output["answer"].values())


def test_no_remote_consent_never_starts_provider(tmp_path, monkeypatch):
    task = _task()
    monkeypatch.delenv("VQS_ALLOW_VISION_UPLOAD", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("provider must not run without permission")
    with pytest.raises(ReviewError, match="not authorized"):
        MuseHighSpecialist(model="muse-pinned", runner=forbidden).review_task(
            task, tmp_path / "missing", tmp_path / "missing")


def test_contributor_needs_separate_permission(tmp_path, monkeypatch):
    task = _task()
    monkeypatch.setenv("VQS_ALLOW_VISION_UPLOAD", "1")
    monkeypatch.delenv("VQS_ALLOW_MUSE_CONTRIBUTOR", raising=False)
    with pytest.raises(ReviewError, match="separate explicit consent"):
        MuseHighSpecialist(model="muse-spark-1.3-contributor").review_task(
            task, tmp_path / "missing", tmp_path / "missing")


def test_malformed_muse_runtime_event_never_crashes_or_attests_model():
    """Unexpected status shapes remain a typed BLOCKED provider outcome."""
    payload = {"payload_type": "task.lifecycle.status",
               "payload": {"event": "not-a-dictionary"}}
    terminal = {"payload_type": "run.terminal.completed",
                "payload": {"text": json.dumps(_answer(_task()))}}
    with pytest.raises(ReviewError, match="runtime model receipt"):
        _provider_output(
            json.dumps(payload) + "\n" + json.dumps(terminal), "muse-pinned")


def test_duplicate_terminal_response_fails_closed_even_with_real_model_event():
    raw = _real_muse_event_stream(_answer(_task()))
    terminal = {"payload_type": "run.terminal.completed",
                "payload": {"text": json.dumps(_answer(_task()))}}
    with pytest.raises(ReviewError, match="exactly one"):
        _provider_output(raw + "\n" + json.dumps(terminal), "muse-pinned")
