"""Keep engineering release notes, main README and current GitHub status aligned."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "docs" / "RELEASE_NOTES_2026-10-26.md"
CURRENT_LINK = "docs/RELEASE_NOTES_2026-10-26.md"


def test_current_release_notes_discoverable_and_bounded():
    text = NOTES.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hub = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert CURRENT_LINK in readme
    assert "RELEASE_NOTES_2026-10-26.md" in hub
    assert CURRENT_LINK in changelog.split("## Adaptive themes integrated", 1)[0]
    for number in (81, 82, 83, 85):
        assert f"pull/{number}" in text
    assert "pull/84" in text
    assert "merged PR #84" in text
    assert "Actual consumer migration" in text
    assert "8aade94" in text
    assert "issue #80 closed" in text.lower()
    assert "G2/G4/G6" in text
    assert "not a production release" in text
    assert "GitHub Release" in text
    assert "No candidate from this experiment has been certified" in text


def test_current_theme_notes_explicitly_override_stale_historical_draft_status():
    theme = (ROOT / "docs" / "RELEASE_NOTES_THEME_2026-10-24.md").read_text(
        encoding="utf-8"
    )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert theme.index("Current status (26 October)") < theme.index(
        "Earlier engineering evidence"
    )
    assert "closed" in theme[:1000].lower()
    assert "were explicitly moved to issue #16" in changelog[:3800]


def test_current_release_notes_local_links_resolve():
    for target in re.findall(r"\]\(([^)]+)\)", NOTES.read_text(encoding="utf-8")):
        if target.startswith(("https://", "http://", "#")):
            continue
        file = unquote(target.split("#", 1)[0])
        assert (NOTES.parent / file).is_file(), target