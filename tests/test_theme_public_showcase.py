"""Complete 14-family gallery must be real Desktop evidence, not mockups.

Native source screenshots remain private. The 56 public WebP assets are
bound to genuine PBIP candidate/model/palette hashes in checked-in provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FEATURED=("sunny-palette","organic-palette","graphite-red","indigo-ember",
          "petrol-gold","riviera-pop","okabe-ito-night")
PUBLISHED=("executive-overview","products-and-brands")

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/"docs/APPROVED_THEME_SELECTION.json").read_text(
    encoding="utf-8"))["presets"]
SLUGS=tuple(p["slug"] for p in CATALOG)


def test_every_approved_theme_has_both_source_bound_native_modes() -> None:
    proof=json.loads((ROOT/"docs/images/adaptive-showcase/PROVENANCE.json")
                     .read_text(encoding="utf-8"))
    wanted={f"{slug}-{mode}" for slug in SLUGS for mode in ("light","dark")}
    assert len(SLUGS)==14 and len(FEATURED)==7
    assert set(proof["modes"])==wanted
    assert proof["schema"]=="vqs.public-theme-showcase/2"
    assert proof["galleryModes"]==28
    assert proof["displayedPagesPerMode"]==2
    assert proof["rawPagesPerMode"]==5
    assert len(proof["authoringHead"])==40
    for name,item in proof["modes"].items():
        for role in ("sourceDigest","candidateDigest","modelDigest","paletteHash"):
            assert len(item[role])==64,(name,role)
        assert len(item["rawPageSha256"])==5,name
        assert all(len(value)==64 for value in item["rawPageSha256"].values())
        assert len(item["screenshots"])==2
        assert {Path(s["file"]).stem for s in item["screenshots"]}==set(PUBLISHED)
        for image in item["screenshots"]:
            assert image["publicCanvasCropBox"]==[0,264,3315,2140]
            assert image["captureDimensions"]==[3915,2394]
            assert len(image["captureSha256"])==64
            path=ROOT/image["file"]
            assert path.relative_to(ROOT).as_posix().startswith(
                f"docs/images/adaptive-showcase/{name}/")
            b=path.read_bytes()
            assert len(b)>20_000
            assert b[:4]==b"RIFF" and b[8:12]==b"WEBP"
            assert hashlib.sha256(b).hexdigest()==image["webpSha256"]


def test_all_14_families_have_real_color_and_control_swatches() -> None:
    root=ROOT/"docs/images/approved-themes/swatches"
    wanted={f"{slug}-{mode}.svg" for slug in SLUGS
            for mode in ("light","dark")}
    assert {p.name for p in root.glob("*.svg")}==wanted
    for name in wanted:
        s=(root/name).read_text(encoding="utf-8")
        assert s.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert s.count("<rect ")==12
        assert "real theme tokens" in s
        assert "Reporting year" in s and "Selected" in s


def test_homepage_shows_only_curated_seven_and_gallery_has_all_14() -> None:
    readme=(ROOT/"README.md").read_text(encoding="utf-8")
    gallery=(ROOT/"docs/REAL_THEME_SHOWCASE.md").read_text(encoding="utf-8")
    library=(ROOT/"docs/APPROVED_THEME_LIBRARY.md").read_text(encoding="utf-8")
    for slug in SLUGS:
        for mode in ("light","dark"):
            uri=f"docs/images/adaptive-showcase/{slug}-{mode}/executive-overview.webp"
            assert (uri in readme)==(slug in FEATURED),(slug,mode)
            for page in PUBLISHED:
                assert f"{slug}-{mode}/{page}.webp" in gallery
            assert f"{slug}-{mode}.svg" in library
    assert "28 Light/Dark variants" in gallery
    assert "none is a simulated dashboard" in readme
    assert "14 families" in library and "dropdown" in library
    assert "docs/THEME_GALLERY.md" in readme
    assert (ROOT/"docs/README.md").is_file()
