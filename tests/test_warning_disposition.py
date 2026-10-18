"""Warn only within honestly labeled portable scope."""
from __future__ import annotations

from vqs.powerbi.author import adapter


def test_warning_policy_blocks_unreviewed_production():
    probe = lambda: {"available": True, "version": "0.5.0",
                     "path": "/approved/cli"}
    validator = lambda *a, **kw: {
        "status": "valid", "returncode": 0, "warnings": ["W007: risky"],
        "errors": [], "command": ["/approved/cli", "validate", "cand"],
    }
    strict = adapter.run_backend("cand", policy="microsoft",
                                 assurance="production", prober=probe,
                                 runner=validator)
    assert strict["verdict"] == "blocked"
    assert strict["record"]["warning_policy"]["status"] == "blocked_pending_review"
    bypass = adapter.run_backend("cand", policy="microsoft",
                                 assurance="production", allow_warnings=True,
                                 prober=probe, runner=validator)
    assert bypass["verdict"] == "blocked"
    portable = adapter.run_backend("cand", policy="microsoft",
                                   assurance="portable", allow_warnings=True,
                                   prober=probe, runner=validator)
    assert portable["verdict"] == "pass"
    assert portable["record"]["warning_policy"]["status"] == "legacy_portable_waiver"


def test_malformed_warning_list_blocks_even_with_portable_waiver():
    result = adapter.run_backend(
        "cand", policy="microsoft", allow_warnings=True,
        prober=lambda: {"available": True},
        runner=lambda *a, **kw: {"status": "valid",
                                 "warnings": "not a warning list"})
    assert result["verdict"] == "blocked"
    assert "malformed diagnostic warnings" in result["reason"]
