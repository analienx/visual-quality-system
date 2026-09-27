"""Tests for the pbip_acceptance BPA summary reduction (no subprocess)."""
from __future__ import annotations

from scripts.pbip_acceptance import _summarize_bpa


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
