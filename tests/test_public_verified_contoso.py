"""Public fictional Contoso source+native Desktop image custody.

Distinct from the historical 14-theme sample and no Windows/Desktop required.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from vqs.evidence import png_size
from vqs.pbir import report_context, source_digest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "contoso-retail-verified"
GALLERY = ROOT / "docs" / "media" / "contoso-verified"
META = json.loads((GALLERY / "PROVENANCE.json").read_text(encoding="utf-8"))
SHA_NORMALIZED = "b6422f15db3b66dd598c0f21ba537bff0fe5323aaec577adb0293577dff48bc6"
SHA_EXACT_NATIVE = "1ec835399a51eb50bd53558124e1ac2d503d7addb6238bae749f6f5eafdd0ce0"
SHA_NATIVE_ARCHIVE = "64c5174690a6cbd611587d6b5467e6dab5b03eb743e53d8870e1844437f62ae1"
PAGES = {
    "Executive overview": "Executive_overview",
    "Products & brands": "Products_brands",
    "Stores & customers": "Stores_customers",
    "Markets & drivers": "Markets_drivers",
    "Deep-dive insights": "d9bc3b8f90439bcc",
}


def test_verified_contoso_public_pbip_is_a_distinct_exact_source_revision():
    assert (EXAMPLE / "Contoso Retail.pbip").is_file()
    assert source_digest(EXAMPLE / "Contoso Retail.Report") == SHA_NORMALIZED
    assert META["normalized_source_sha256"] == SHA_NORMALIZED
    assert META["exact_tested_source_sha256"] == SHA_EXACT_NATIVE
    assert META["exact_tested_source_sha256"] != META["normalized_source_sha256"]
    assert META["source_normalization_changes"] == [
        "Contoso Retail.Report/definition.pbir", "Contoso Retail.pbip"
    ]
    ctx = report_context(EXAMPLE / "Contoso Retail.Report")
    assert {p["id"] for p in ctx["pages"]} == set(PAGES.values())
    assert len(ctx["pages"]) == 5
    assert sum(len(p["visuals"]) for p in ctx["pages"]) == 54
    assert all(tuple(p["canvas"]) == (1280, 720) for p in ctx["pages"])
    assert META["native_capture"]["page_count"] == len(PAGES) == 5
    assert META["normalization_validation"]["microsoft_report_author"] == {
        "errors": 0, "warnings": 0, "status": "succeeded"
    }
    assert META["owner_G6"] is False and META["distinct_human_review"] is False


def test_native_archive_contains_the_same_model_and_only_schema_metadata_differs():
    zfile = EXAMPLE / "evidence" / "strict-native-source.zip"
    assert hashlib.sha256(zfile.read_bytes()).hexdigest() == SHA_NATIVE_ARCHIVE
    assert META["exact_tested_source_zip_sha256"] == SHA_NATIVE_ARCHIVE
    with zipfile.ZipFile(zfile) as z:
        native_names = set(z.namelist())
        disk = {
            p.relative_to(EXAMPLE).as_posix() for p in EXAMPLE.rglob("*")
            if p.is_file() and p.name not in {"README.md", ".gitattributes"}
            and not p.relative_to(EXAMPLE).as_posix().startswith("evidence/")
        }
        assert native_names == disk
        different = sorted(
            name for name in native_names
            if z.read(name) != (EXAMPLE / name).read_bytes()
        )
        assert different == META["source_normalization_changes"]
        assert not any("localSettings" in f or "editorSettings" in f for f in native_names)
        # The ZIP is a true native source capture, not a substituted HTML/render.
        assert all(n.startswith(("Contoso Retail.Report/", "Contoso Retail.SemanticModel/"))
                   or n == "Contoso Retail.pbip" for n in native_names)
    attr = (EXAMPLE / ".gitattributes").read_text(encoding="utf-8")
    assert "*.json -text" in attr and "*.tmdl -text" in attr
    assert "*.pbip -text" in attr and "*.pbir -text" in attr
    assert not list(EXAMPLE.rglob("localSettings.json"))
    assert not list(EXAMPLE.rglob("editorSettings.json"))


def test_public_fictional_model_has_no_external_or_private_user_sources():
    model = EXAMPLE / "Contoso Retail.SemanticModel"
    cache = model / ".pbi" / "cache.abf"
    assert cache.is_file() and cache.stat().st_size == META["model"]["cache_bytes"] == 198018
    content = cache.read_bytes().lower()
    for private_string in (b"jakub", b"holasek", b"organon", b"corporate spend",
                           b"client_secret", b"access_token", b"\\users\\"):
        assert private_string not in content
    tmdls = sorted((model / "definition" / "tables").glob("*.tmdl"))
    assert len(tmdls) == META["model"]["fictional_m_partitions"] == 12
    for path in tmdls:
        text = path.read_text(encoding="utf-8").lower()
        assert "partition " in text and "= m" in text and "mode: import" in text
        for forbidden in ("web.contents(", "file.contents(", "sql.database(",
                          "sharepoint.files(", "odata.feed(", "c:\\users\\"):
            assert forbidden not in text
    for path in EXAMPLE.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".pbip", ".pbir", ".tmdl"}:
            text = path.read_text(encoding="utf-8-sig")
            assert not re.search(r"gh[pousr]_[A-Za-z0-9]{24,}", text)
            assert not re.search(r"sk-[A-Za-z0-9]{25,}", text)


def test_five_native_pngs_and_public_webps_are_exact_hash_bound():
    pages = META["capture_references"]
    assert len(pages) == 5
    assert {p["name"]: p["page_id"] for p in pages} == PAGES
    assert "Shape Map country-specific click" in META["unsupported_not_claimed"]
    assert "true contextual Tooltip hover" in META["unsupported_not_claimed"]
    for entry in pages:
        raw = ROOT / entry["raw_png"]
        preview = ROOT / entry["preview"]
        assert raw.is_file() and preview.is_file()
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == entry["raw_sha256"]
        assert hashlib.sha256(preview.read_bytes()).hexdigest() == entry["webp_sha256"]
        assert list(png_size(raw)) == entry["native_dimensions"] == [3472, 1976]
        assert entry["public_report_crop"] == [0, 205, 2894, 1833]
        assert entry["preview_dimensions"] == [1600, 900]
        body = preview.read_bytes()
        assert body[:4] == b"RIFF" and body[8:12] == b"WEBP"
        assert len(body) < 200_000
    assert META["behavior"]["native_year_region_actions"] == 8
    assert META["behavior"]["read_only_baseline"] == 1
    assert META["behavior"]["local_model_dax_4_kpi"] == "pass"
    assert META["owner_G6"] is False


def test_docs_explain_two_separate_contoso_sources_and_no_fake_release():
    homepage = (ROOT / "README.md").read_text(encoding="utf-8")
    showcase = (ROOT / "docs/VERIFIED_CONTOSO_SHOWCASE.md").read_text(encoding="utf-8")
    handoff = (EXAMPLE / "README.md").read_text(encoding="utf-8")
    historical = (ROOT / "examples/contoso-retail/README.md").read_text(encoding="utf-8")
    assert "examples/contoso-retail-verified/Contoso%20Retail.pbip" in homepage
    assert "docs/VERIFIED_CONTOSO_SHOWCASE.md" in homepage
    assert "historical" in historical.lower()
    assert "separate historical" in handoff
    assert "not a signed production release" in showcase.lower()
    for entry in META["capture_references"]:
        assert entry["preview"].replace("docs/", "") in showcase
    assert "14-family" in showcase
    assert "human" in showcase.lower()
