"""Tests for the pbip_acceptance external-validation mapping (no subprocess)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pbip_acceptance import _report_author, main


# R6-E07: BPA has no Microsoft equivalent and is removed; the script
# maps the Microsoft validate port onto the summary instead.
def _outcome(status, **extra):
    base = {"tool": "powerbi-report-author", "command": ["x"],
            "status": status, "returncode": 0 if status == "valid" else 1,
            "errors": [], "warnings": [], "raw_tail": "tail", "note": None}
    base.update(extra)
    return base


def test_report_author_maps_valid_and_invalid(monkeypatch) -> None:
    monkeypatch.setattr("vqs.powerbi.author.mscli.validate",
                        lambda *a, **k: _outcome("valid"))
    assert _report_author(Path("Example.Report"))["status"] == "valid"
    monkeypatch.setattr("vqs.powerbi.author.mscli.validate",
                        lambda *a, **k: _outcome("invalid", errors=["E1"]))
    result = _report_author(Path("Example.Report"))
    assert result["status"] == "error"
    assert result["errors"] == ["E1"]


def test_report_author_missing_and_blocked(monkeypatch) -> None:
    monkeypatch.setattr("vqs.powerbi.author.mscli.validate",
                        lambda *a, **k: _outcome("missing"))
    assert _report_author(Path("Example.Report"))["status"] == "skipped"
    monkeypatch.setattr("vqs.powerbi.author.mscli.validate",
                        lambda *a, **k: _outcome("timeout", note="timeout"))
    assert _report_author(Path("Example.Report"))["status"] == "blocked"


def _facts(failing: bool) -> dict:
    run_scope = "scope-b" if failing else "scope-a"
    return {
        "rules": {"typography.text_contrast":
                  {"foreground": "#ffffff", "background": "#000000"}},
        "oracles": [{"oracle_scope": "scope-a", "run_scope": run_scope}],
    }


def test_check_fail_produces_overall_fail_and_exit_1(tmp_path: Path, capsys,
                                                     monkeypatch) -> None:
    """Supervisor #22 P0-4: the recorded check verdict drives the outcome."""
    report = tmp_path / "Example.Report"
    report.mkdir()
    monkeypatch.setattr("vqs.powerbi.measure.measure_report",
                        lambda *a, **k: _facts(failing=True))
    code = main([str(report), "--skip-external"])
    assert code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["check"]["verdict"] == "fail"
    assert summary["verdict"] == "fail"


def test_check_pass_keeps_overall_pass_and_exit_0(tmp_path: Path, capsys,
                                                 monkeypatch) -> None:
    report = tmp_path / "Example.Report"
    report.mkdir()
    monkeypatch.setattr("vqs.powerbi.measure.measure_report",
                        lambda *a, **k: _facts(failing=False))
    code = main([str(report), "--skip-external"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["check"]["verdict"] == "pass"
    assert summary["verdict"] == "pass"


def test_skip_pbir_flag_is_gone(tmp_path: Path, capsys,
                                     monkeypatch) -> None:
    """Item 37: no pbir.tools hook remains; the old flag is rejected."""
    report = tmp_path / "Example.Report"
    report.mkdir()
    monkeypatch.setattr("vqs.powerbi.measure.measure_report",
                        lambda *a, **k: _facts(failing=False))
    with pytest.raises(SystemExit):
        main([str(report), "--skip-pbir"])
    code = main([str(report), "--skip-external"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["report_author"]["status"] == "skipped"
