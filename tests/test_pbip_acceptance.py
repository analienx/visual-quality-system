"""Tests for the pbip_acceptance BPA summary reduction (no subprocess)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import pbip_acceptance
from scripts.pbip_acceptance import _summarize_bpa, main


def _violation(rule_id, severity):
    return {"rule_id": rule_id, "rule_name": rule_id.lower(),
            "severity": severity, "page_id": "P1"}


def test_bpa_summary_counts_and_top_rules() -> None:
    payload = {"valid": True, "violations": [
        _violation("PBIR_NO_ALT_TEXT", 1),
        _violation("PBIR_NO_ALT_TEXT", 1),
        _violation("PBIR_HARDCODED_COLOR", 1),
        _violation("PBIR_VISUAL_UNDERSIZED", 2),
        _violation("PBIR_SOMETHING_BAD", 3),
    ]}
    assert _summarize_bpa(payload) == {
        "status": "ok", "error": 1, "warning": 1, "info": 3,
        "top_rules": [{"rule_id": "PBIR_NO_ALT_TEXT", "count": 2},
                      {"rule_id": "PBIR_HARDCODED_COLOR", "count": 1},
                      {"rule_id": "PBIR_SOMETHING_BAD", "count": 1},
                      {"rule_id": "PBIR_VISUAL_UNDERSIZED", "count": 1}]}


def test_bpa_summary_rejects_malformed() -> None:
    assert _summarize_bpa(None)["status"] == "blocked"
    assert _summarize_bpa({"violations": {}})["status"] == "blocked"
    assert _summarize_bpa({"violations": []}) == {
        "status": "ok", "error": 0, "warning": 0, "info": 0, "top_rules": []}


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
    code = main([str(report), "--skip-pbir"])
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
    code = main([str(report), "--skip-pbir"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["check"]["verdict"] == "pass"
    assert summary["verdict"] == "pass"


def test_missing_pbir_degrades_to_skipped(monkeypatch) -> None:
    """Unavailable optional tools preserve offline usability (GOAL 17 slice)."""
    monkeypatch.setattr("scripts.pbip_acceptance.shutil.which",
                        lambda *a, **k: None)
    assert pbip_acceptance._pbir(Path("Example.Report"))["status"] == "skipped"
    assert pbip_acceptance._bpa(Path("Example.Report"))["status"] == "skipped"
