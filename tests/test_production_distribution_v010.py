"""Public package distribution is versioned; it must never self-certify reports."""
from __future__ import annotations

import tomllib
from pathlib import Path

import vqs

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_consistency_and_supported_entrypoints():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    assert project["name"] == "visual-quality-system"
    assert project["version"] == vqs.__version__ == "0.1.0"
    assert project["requires-python"] == ">=3.11"
    assert project["scripts"]["vqs"] == "vqs.cli:main"
    assert project["scripts"]["vqs-mcp"] == "vqs.mcp.server:main"


def test_release_is_scoped_and_preserves_unapproved_report_acceptance():
    release = (ROOT / "docs/PRODUCTION_DISTRIBUTION_v0.1.0.md").read_text(
        encoding="utf-8"
    )
    lower = release.lower()
    for required in (
        "source-only", "candidate", "wheel", "source archive",
        "shape map", "tooltip", "g2/g4", "g6", "no hosted web service",
        "independent", "rollback", "not",
    ):
        assert required in lower
    assert "report-level g6 policy has passed" in lower
    assert "**not** a claim" in lower
    assert "v0.1.0" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "PRODUCTION_DISTRIBUTION_v0.1.0.md" in (
        ROOT / "README.md"
    ).read_text(encoding="utf-8")
    assert "v0.1.0" in (ROOT / "docs/CONSUMER_INTEGRATION.md").read_text(
        encoding="utf-8"
    )


def test_existing_report_acceptance_gate_is_not_waived_by_distribution():
    acceptance = (ROOT / "docs/ACCEPTANCE_MATRIX.md").read_text(encoding="utf-8")
    assert "G6 independent acceptance" in acceptance
    assert "no independent reviewer or owner promotion publisher is registered" in acceptance
    assert "blocked/not_run/unknown" in acceptance
    # The final fixture is public, but an independent human has not certified G2/G4.
    proven = (ROOT / "docs/media/contoso-verified/PROVENANCE.json").read_text(
        encoding="utf-8"
    )
    assert '"owner_G6": false' in proven
    assert '"distinct_human_review": false' in proven
