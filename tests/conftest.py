"""Portable unit-test lane: never make behavior depend on host-global CLI PATH.

The test corpus uses intentionally incomplete PBIR fixtures for deterministic
typed writer, undo, ledger and coordinator invariants. This fixture limits
those *unit tests* to the explicitly recorded direct/static validation route.
Tests that exercise Microsoft validation inject their own probe and runner;
the real tool/scaffold verification lives in scripts/authoring_probe.py and
its separate hosted workflow. No production defaults are changed.
"""
import pytest


@pytest.fixture(autouse=True)
def _portable_authoring_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    from vqs.powerbi.author import adapter

    def _offline_probe(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "tool": "powerbi-report-author",
            "package": "@microsoft/powerbi-report-authoring-cli",
            "path": None,
            "version": None,
            "available": False,
            "returncode": None,
            "note": "portable unit-test lane: real CLI isolated",
        }

    monkeypatch.setattr(adapter, "probe", _offline_probe)
