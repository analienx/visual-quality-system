"""Public gallery is reproducible and free from unbacked marketing claims.

The original native PNG files are deliberately private. Public WebP bytes
are sealed by SHA-256 in the checked-in provenance manifest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEATURED = ("sunny-palette", "organic-palette", "graphite-red")
PAGES = ("executive-overview", "products-and-brands", "deep-dive-insights")


def test_showcase_has_exclusively_six_real_native_source_modes() -> None:
    manifest = json.loads((ROOT / "docs/images/adaptive-showcase/PROVENANCE.json").read_text(
        encoding="utf-8"))
    expected = {f"{slug}-{mode}" for slug in FEATURED for mode in ("dark", "light")}
    assert set(manifest["modes"]) == expected
    assert manifest["schema"] == "vqs.public-theme-showcase/1"
    assert len(manifest["authoringHead"]) == 40
    for name, item in manifest["modes"].items():
        assert item["sourceDigest"] and len(item["sourceDigest"]) == 64
        assert item["candidateDigest"] and len(item["candidateDigest"]) == 64
        assert item["modelDigest"] and len(item["modelDigest"]) == 64
        assert item["paletteHash"] and len(item["paletteHash"]) == 64
        assert len(item["screenshots"]) == len(PAGES)
        assert {Path(s["file"]).stem for s in item["screenshots"]} == set(PAGES)
        for screenshot in item["screenshots"]:
            assert screenshot["publicCanvasCropBox"] == [0, 264, 3315, 2140]
            assert screenshot["captureDimensions"] == [3915, 2394]
            assert len(screenshot["captureSha256"]) == 64
            path = ROOT / screenshot["file"]
            assert path.relative_to(ROOT).as_posix().startswith(
                f"docs/images/adaptive-showcase/{name}/")
            content = path.read_bytes()
            assert len(content) >= 20_000
            assert content[:4] == b"RIFF" and content[8:12] == b"WEBP"
            assert hashlib.sha256(content).hexdigest() == screenshot["webpSha256"]


def test_every_remaining_palette_has_two_real_token_swatches() -> None:
    data = json.loads((ROOT / "docs/APPROVED_THEME_SELECTION.json").read_text(
        encoding="utf-8"))
    assert len(data["presets"]) == 14
    slugs = {x["slug"] for x in data["presets"]}
    assert set(FEATURED).issubset(slugs)
    chip_dir = ROOT / "docs/images/approved-themes/swatches"
    expected = {f"{slug}-{mode}.svg" for slug in slugs - set(FEATURED)
                for mode in ("light", "dark")}
    assert {p.name for p in chip_dir.glob("*.svg")} == expected
    for name in expected:
        content = (chip_dir / name).read_text(encoding="utf-8")
        assert content.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert content.count("<rect ") == 10
        assert "actual theme tokens" in content


def test_readme_links_to_truthful_showcase_and_documentation() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    gallery = (ROOT / "docs/REAL_THEME_SHOWCASE.md").read_text(encoding="utf-8")
    library = (ROOT / "docs/APPROVED_THEME_LIBRARY.md").read_text(encoding="utf-8")
    for slug in FEATURED:
        for mode in ("light", "dark"):
            image = f"docs/images/adaptive-showcase/{slug}-{mode}/executive-overview.webp"
            assert image in readme
            for page in PAGES:
                assert f"{slug}-{mode}/{page}.webp" in gallery
    assert (ROOT / "docs/README.md").is_file()
    assert "none is a simulated dashboard" in readme
    assert "color swatches" in library
    assert "28" in library and "14" in library
