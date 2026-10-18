"""P10 account-free Contoso Shape Map redesign: structural and data invariants."""
from __future__ import annotations

import hashlib
import json
import struct
import zipfile
from pathlib import Path

import pytest

from scripts.migrate_contoso_insights_page import (
    MAP,
    REGION,
    ROOT,
    TARGET_MAP,
    TARGET_REGION,
    migrate,
)

P9 = ROOT / "tests/fixtures/contoso-retail-no-login-shapemap.zip"
P10 = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.zip"
MANIFEST = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.manifest.json"
ORIGINAL_TREE = ROOT / "tests/fixtures/contoso-insights-legacy-tree.json"
OLD_MAP = ROOT / "assets/maps/contoso-sales-country-shapemap-visual.json"


@pytest.fixture()
def original(tmp_path: Path) -> Path:
    project = tmp_path / "original"
    project.mkdir()
    with zipfile.ZipFile(P9) as archive:
        for name in archive.namelist():
            entry = Path(name)
            assert not entry.is_absolute() and ".." not in entry.parts
        archive.extractall(project)
    assert (project / MAP).is_file() and (project / REGION).is_file()
    return project


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_bound_full_project_and_model_unchanged(original: Path, tmp_path: Path):
    source_inventory = {
        p.relative_to(original).as_posix(): _digest(p)
        for p in original.rglob("*") if p.is_file()
    }
    destination = tmp_path / "candidate"
    receipt = migrate(original, destination)
    assert receipt["verdict"] == "candidate_only"
    assert receipt["map_requires_login"] is False
    assert receipt["shape_map_is_preview"] is True
    assert receipt["semantic_model_digest_unchanged"] is True
    assert len(receipt["changed_report_files"]) == 2
    assert set(receipt["changed_report_files"]) == {
        MAP.as_posix(), REGION.as_posix(),
    }
    # Git converts repository JSON LF/CRLF on different runner platforms.
    # Compare the corresponding source/template objects semantically; the
    # authoritative packaged candidate still has a strict byte-for-byte test.
    assert json.loads((destination / MAP).read_text()) == json.loads(TARGET_MAP.read_text())
    assert json.loads((destination / REGION).read_text()) == json.loads(TARGET_REGION.read_text())
    assert json.loads((original / MAP).read_text()) == json.loads(OLD_MAP.read_text())
    assert json.loads((original / REGION).read_text()) == json.loads(ORIGINAL_TREE.read_text())
    for name, sha in source_inventory.items():
        assert _digest(original / name) == sha, "original project mutated"
        if name not in (MAP.as_posix(), REGION.as_posix()):
            assert _digest(destination / name) == sha, "unexpected project/model edit"
    assert len(list((destination / "Contoso Retail.Report/definition/pages").glob(
        "*/page.json"
    ))) == 5
    assert len(list((destination / "Contoso Retail.Report/definition/pages").glob(
        "*/visuals/*/visual.json"
    ))) == 54


def test_packaged_candidate_matches_migration_byte_for_byte(original: Path, tmp_path: Path):
    candidate = tmp_path / "candidate"
    migrate(original, candidate)
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert _digest(P10) == m["sha256"]
    assert m["files"] == 86
    assert m["microsoft_validator"] == {"errors": 0, "warnings": 0}
    assert m["map_type"] == "shapeMap"
    with zipfile.ZipFile(P10) as archive:
        stored = archive.namelist()
        expected = {p.relative_to(candidate).as_posix() for p in candidate.rglob("*")
                    if p.is_file()}
        assert len(stored) == len(expected) == 86
        assert set(stored) == expected
        for name in stored:
            assert archive.read(name) == (candidate / name).read_bytes()


def test_no_antarctica_map_still_has_exact_sales_roles():
    m = json.loads(TARGET_MAP.read_text())
    region = json.loads(TARGET_REGION.read_text())
    assert m["visual"]["visualType"] == "shapeMap"
    assert region["visual"]["visualType"] == "clusteredBarChart"
    assert set(m["visual"]["query"]["queryState"]) == {"Category", "Value"}
    assert (m["visual"]["query"]["queryState"]["Category"]
            ["projections"][0]["field"]["Column"]["Property"]) == "Country"
    assert (m["visual"]["query"]["queryState"]["Value"]
            ["projections"][0]["field"]["Measure"]["Property"]) == "Reporting Year Sales"
    assert (region["visual"]["query"]["queryState"]["Category"]
            ["projections"][0]["field"]["Column"]["Property"]) == "Region"
    assert (region["visual"]["query"]["queryState"]["Y"]
            ["projections"][0]["field"]["Measure"]["Property"]) == "Reporting Year Sales"
    assert len(region["visual"]["query"]["queryState"]["Category"]["projections"]) == 1
    assert "dataPoint" not in region["visual"]["objects"]
    geo = json.loads((ROOT / "assets/maps/world-countries-110m-without-antarctica.topojson")
                     .read_text())
    names = {g["properties"]["name"]
             for g in geo["objects"]["countries"]["geometries"]}
    assert "Antarctica" not in names
    assert {"United States", "Canada", "United Kingdom", "Germany", "Australia"} <= names


@pytest.mark.parametrize("variant", [
    "occupied_target", "wrong_map", "wrong_tree", "no_report",
    "tampered_measure", "tampered_category", "bad_geo",
])
def test_source_tampering_and_unsupported_geography_refused(
    original: Path, tmp_path: Path, monkeypatch, variant: str,
):
    target = tmp_path / "candidate"
    if variant == "occupied_target":
        target.mkdir()
    if variant in ("wrong_map", "tampered_measure", "tampered_category"):
        p = original / MAP
        doc = json.loads(p.read_text())
        if variant == "wrong_map":
            doc["visual"]["visualType"] = "azureMap"
        elif variant == "tampered_measure":
            doc["visual"]["query"]["queryState"]["Value"]["projections"][0][
                "field"]["Measure"]["Property"] = "Other sales"
        else:
            doc["visual"]["query"]["queryState"]["Category"]["projections"][0][
                "field"]["Column"]["Property"] = "Other country"
        p.write_text(json.dumps(doc))
    if variant == "wrong_tree":
        p = original / REGION
        doc = json.loads(p.read_text())
        doc["position"]["height"] = 1
        p.write_text(json.dumps(doc))
    if variant == "no_report":
        (original / MAP).unlink()
    if variant == "bad_geo":
        import scripts.migrate_contoso_insights_page as mod
        wrong = tmp_path / "wrong.topojson"
        wrong.write_text('{"objects":{"countries":{"geometries":[]}}}')
        monkeypatch.setattr(mod, "TOPOLOGY", wrong)
    with pytest.raises((ValueError, FileNotFoundError)):
        migrate(original, target)


def test_official_microsoft_validator_qa(original: Path, tmp_path: Path):
    from vqs.powerbi.author import mscli
    if not mscli.probe().get("available"):
        pytest.skip("Microsoft authoring CLI unavailable")
    candidate = tmp_path / "candidate"
    migrate(original, candidate)
    p9 = mscli.validate(original / "Contoso Retail.Report")
    p10 = mscli.validate(candidate / "Contoso Retail.Report")
    assert p9["errorCount"] == 0 and p9["warningCount"] == 0
    assert p10["status"] == "valid"
    assert p10["errorCount"] == 0 and p10["warningCount"] == 0


def test_exact_independently_captured_canvas_previews_are_attested():
    doc = json.loads((ROOT / "docs/assets/p10-screenshot-provenance.json").read_text())
    assert doc["contract"] == "vqs.p10.page-canvas-screenshot-evidence/1"
    hashes = []
    for label in ("before", "after"):
        entry = doc["screenshots"][label]
        path = ROOT / entry["report_canvas_file"]
        data = path.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", data[16:24]) == (3070, 1746)
        assert hashlib.sha256(data).hexdigest() == entry["report_canvas_sha256"]
        hashes.append(entry["report_canvas_sha256"])
    assert hashes[0] != hashes[1], "comparison screenshots must differ"
