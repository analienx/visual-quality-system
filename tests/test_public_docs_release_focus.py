"""Keep the public homepage focused on the one published package version."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_homepage_latest_release_matches_package_version() -> None:
    version = tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    readme = _read("README.md")
    assert f"## Latest release · v{version}" in readme
    assert f"visual_quality_system-{version}-py3-none-any.whl" in readme
    assert f"docs/RELEASE_NOTES_v{version}.md" in readme
    assert f"https://github.com/analienx/visual-quality-system/releases/tag/v{version}" in readme
    assert "docs/RELEASES.md" in readme
    assert len(re.findall(r"^## Latest release", readme, re.MULTILINE)) == 1
    assert not re.search(r"^## (?:Previous|Older|Past) (?:version|release)", readme,
                         re.MULTILINE | re.IGNORECASE)
    # Older release binaries and descriptions belong to the version index.
    for old in ("v0.1.0", "v0.1.1"):
        assert old not in readme
    assert readme.index("## Latest release") < readme.index("## How VQS works")


def test_release_index_and_docs_point_to_current_release() -> None:
    version = tomllib.loads(_read("pyproject.toml"))["project"]["version"]
    versions = _read("docs/RELEASES.md")
    docs = _read("docs/README.md")
    assert f"### v{version} — latest" in versions
    assert f"RELEASE_NOTES_v{version}.md" in versions
    assert "v0.1.1" in versions and "v0.1.0" in versions
    assert f"latest release (v{version})" in docs
    assert f"RELEASE_NOTES_v{version}.md" in docs
    assert "RELEASES.md" in docs


def test_homepage_preserves_featured_actual_report_gallery() -> None:
    readme = _read("README.md")
    assert "## Real Power BI showcase" in readme
    for family in ("Sunny Palette", "Organic Palette", "Graphite Red",
                   "Indigo Ember", "Petrol & Gold", "Riviera Pop",
                   "Okabe–Ito Night"):
        assert f"### {family}" in readme
    assert 'src="docs/diagrams/vqs-product-loop-mobile.svg"' in readme


def test_owner_adoption_guidance_visible_from_homepage() -> None:
    readme = _read("README.md")
    guide = _read("docs/OWNER_DECISIONS_AND_PR_GATE.md")
    assert 'href="docs/OWNER_DECISIONS_AND_PR_GATE.md"' in readme
    assert "[owner decisions, waivers and adoption](docs/OWNER_DECISIONS_AND_PR_GATE.md)" in readme
    assert "PowerShell" in readme and "Command Prompt" in readme
    assert "PowerShell" in guide and "Command Prompt" in guide


def test_roadmap_retains_scope_and_outcome_evidence_requirements() -> None:
    roadmap = _read("roadmap/README.md")
    for phrase in (
        "Success metric",
        "useful improvements per report",
        "false-positive rate",
        "Demonstration bar",
        "two genuinely unrelated PBIP projects",
        "stale screenshots",
        "independent human G2/G4",
        "owner G6",
        "Retained planning non-goals",
        "theme-family expansion",
        "hosted service",
        "unrestricted autonomous report authoring",
    ):
        assert phrase in roadmap


def test_historical_status_and_privacy_guidance_are_complete() -> None:
    historical = _read("docs/RELEASE_NOTES_2026-10-26.md")
    guide = _read("docs/USER_GUIDE.md")
    assert "Historical record" in historical
    assert "Status as of 26 October 2026" in historical
    assert "For the **current** product-facing state" in historical
    assert "published v0.1.2 release notes" in historical
    assert "use this 26 October summary" not in historical
    assert "Cloud submission of data or images requires explicit owner approval" in guide
    assert "data-handling and privacy policies." in guide
