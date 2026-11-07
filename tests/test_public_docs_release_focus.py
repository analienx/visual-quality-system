"""Keep the public homepage focused on the one published package version."""
from pathlib import Path
import re
import tomllib


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
    assert f"**v{version} — latest**" in versions
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
