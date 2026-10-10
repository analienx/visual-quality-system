"""Regression controls for Microsoft CLI JSON envelopes and pinned skill."""
import json
from pathlib import Path

import pytest

from scripts import report_skill
from vqs.powerbi.author import mscli


def envelope(result="succeeded", errors=0, warnings=0, diagnostics=None):
    return json.dumps({"data": {"result": result, "errorCount": errors,
                                "warningCount": warnings,
                                "diagnostics": diagnostics or {}}})


def diag(severity, msg="broken"):
    return {"CODE": {"severity": severity, "items": [{"message": msg}]}}


def test_clean_minified_json_does_not_false_detect_warning() -> None:
    parsed = mscli._structured(envelope(), 0)
    assert parsed["status"] == "valid"
    assert parsed["warnings"] == []
    assert parsed["errorCount"] == 0


def test_warning_is_structured_and_blocks_without_explicit_consent() -> None:
    parsed = mscli._structured(envelope(
        "succeededWithWarnings", warnings=1,
        diagnostics=diag("warning", "small font")), 0)
    assert parsed["status"] == "valid"
    assert parsed["warnings"] == ["CODE: small font"]


def test_invalid_report_retains_correct_error_counts() -> None:
    parsed = mscli._structured(envelope(
        "failed", errors=1, diagnostics=diag("error")), 1)
    assert parsed["status"] == "invalid"
    assert parsed["errors"] == ["CODE: broken"]


@pytest.mark.parametrize("payload,exit_code", [
    ("", 0),
    ("not json", 0),
    (json.dumps({"data": {"result": "succeeded", "errorCount": 0,
                          "warningCount": 0}}), 1),
    (envelope("succeededWithWarnings", warnings=0), 0),
    (envelope("failed", errors=0), 1),
    (envelope("failed", errors=1), 0),
    (envelope("succeeded", errors=0, warnings=1), 0),
    (envelope("succeeded", errors=1), 0),
    (json.dumps({"error": {"code": "X", "message": "unknown"}}), 1),
    (json.dumps({"data": {"result": "succeeded", "errorCount": True,
                          "warningCount": 0}}), 0),
])
def test_malformed_or_mismatched_cli_output_never_passes(payload, exit_code):
    assert mscli._structured(payload, exit_code)["status"] == "error"


def test_cli_parse_is_based_only_on_stdout(monkeypatch):
    monkeypatch.setattr(mscli.shutil, "which", lambda name: "/usr/bin/cli")
    monkeypatch.setattr(mscli, "_run", lambda *a, **k: {
        "returncode": 0, "stdout": envelope(),
        "stderr": "a warning-like banner is irrelevant", "note": None})
    record = mscli.validate("candidate")
    assert record["status"] == "valid"
    assert not record["warnings"]


def test_skill_snapshot_is_reproducible_and_detects_tampering(tmp_path: Path):
    folder = tmp_path / "skill"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nversion: 1.0.5\n---\n",
                                     encoding="utf-8")
    first = report_skill.snapshot(folder)
    assert first["version"] == "1.0.5"
    (folder / "SKILL.md").write_text("---\nversion: 1.0.6\n---\n",
                                     encoding="utf-8")
    assert report_skill.snapshot(folder)["sha256"] != first["sha256"]


def test_real_vendored_skill_lock_is_consistent():
    assert report_skill.check()["status"] == "pass"


def test_skill_missing_and_tampered_are_blocked(tmp_path: Path):
    assert report_skill.check(skill=tmp_path / "gone",
                              lock_file=tmp_path / "missing")["status"] == "blocked"
    lock = tmp_path / "lock.json"
    real_lock = json.loads(report_skill.LOCK.read_text(encoding="utf-8"))
    real_lock["sha256"] = "0" * 64
    lock.write_text(json.dumps(real_lock), encoding="utf-8")
    assert report_skill.check(lock_file=lock)["status"] == "blocked"


def test_cli_version_preflight_blocks_missing_or_drift(monkeypatch):
    monkeypatch.setattr(report_skill.shutil, "which", lambda _: None)
    assert report_skill.cli_check()["status"] == "blocked"
    monkeypatch.setattr(report_skill.shutil, "which", lambda _: "/fake/tool")

    class Run:
        returncode = 0
        stdout = "0.4.0\n"

    monkeypatch.setattr(report_skill.subprocess, "run", lambda *a, **k: Run())
    rejected = report_skill.cli_check(expected="0.5.0")
    assert rejected["status"] == "blocked"
    assert rejected["found"] == "0.4.0"


def test_skill_lock_checks_cli_package_identity(tmp_path: Path):
    lock = tmp_path / "lock.json"
    actual = json.loads(report_skill.LOCK.read_text(encoding="utf-8"))
    actual["cli_version"] = "999.999.999"
    lock.write_text(json.dumps(actual), encoding="utf-8")
    assert report_skill.check(lock_file=lock)["status"] == "blocked"
