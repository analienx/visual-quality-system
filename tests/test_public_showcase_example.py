"""Public README image provenance must match an ACTUAL checked-in PBIP.

These source-only checks run in Linux/macOS/Windows CI, without Power BI Desktop,
private data, model-cache binaries or optional image-generation services.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from vqs.pbir import report_context, source_digest

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "contoso-retail"
REPORT = EXAMPLE / "Contoso Retail.Report"
MODEL = EXAMPLE / "Contoso Retail.SemanticModel"
GALLERY = REPO / "docs" / "media" / "showcase"
EXPECTED_REPORT = "0e94efc38bd1ec852e4e079afb13b626ec586d5a9506ea607f691dfffa60c847"
EXPECTED_MODEL = "30040bd3b229fc8507d30cf58e30d393b5b65e9317b2159f3066772aa715ae3f"
PAGES = {
    "Executive_overview": "executive-overview.webp",
    "Products_brands": "products-brands.webp",
    "Stores_customers": "stores-customers.webp",
    "Markets_drivers": "markets-drivers.webp",
    "d9bc3b8f90439bcc": "deep-dive-map.webp",
}


def test_readme_showcase_is_the_exact_committed_pbip_not_a_fixture():
    assert (EXAMPLE / "Contoso Retail.pbip").is_file()
    assert (MODEL / "definition.pbism").is_file()
    assert source_digest(REPORT) == EXPECTED_REPORT
    context = report_context(REPORT)
    assert {p["id"] for p in context["pages"]} == set(PAGES)
    assert len(context["pages"]) == 5
    assert sum(len(p["visuals"]) for p in context["pages"]) == 54
    assert all(tuple(p["canvas"]) == (1280, 720) for p in context["pages"])
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "examples/contoso-retail/Contoso%20Retail.pbip" in readme
    assert "examples/contoso-retail/README.md" in readme


def test_embedded_model_matches_the_rendered_fixture_and_has_no_external_sources():
    tmdls = sorted(MODEL.glob("definition/tables/*.tmdl"))
    assert len(tmdls) == 12
    for table in tmdls:
        content = table.read_text(encoding="utf-8")
        assert "partition " in content and " = m" in content
        assert "mode: import" in content
        lower = content.lower()
        assert not any(x in lower for x in (
            "file.contents(", "web.contents(", "sql.database(",
            "sharepoint.files(", "odata.feed(", "c:\\users\\"))
    semantic_files = sorted(
        (p for p in MODEL.rglob("*") if p.is_file()
         and p.suffix.lower() in {".tmdl", ".pbism"}),
        key=lambda p: p.relative_to(EXAMPLE).as_posix(),
    )
    h = sha256()
    for path in semantic_files:
        h.update(path.relative_to(EXAMPLE).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    assert h.hexdigest() == EXPECTED_MODEL
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "*.abf" in ignore and "**/.pbi/" in ignore


def test_all_five_readme_images_match_public_provenance():
    root_readme = (REPO / "README.md").read_text(encoding="utf-8")
    example_readme = (EXAMPLE / "README.md").read_text(encoding="utf-8")
    provenance = (GALLERY / "ASSET_PROVENANCE.md").read_text(encoding="utf-8")
    assert EXPECTED_REPORT in provenance
    assert EXPECTED_REPORT in example_readme
    assert EXPECTED_MODEL in example_readme
    assert "Contoso%20Retail.pbip" in provenance
    for page_id, filename in PAGES.items():
        asset = GALLERY / filename
        assert asset.is_file()
        body = asset.read_bytes()
        assert body[:4] == b"RIFF" and body[8:12] == b"WEBP"
        assert len(body) < 150_000
        assert sha256(body).hexdigest() in provenance
        assert filename in root_readme and filename in example_readme
        assert page_id in provenance
