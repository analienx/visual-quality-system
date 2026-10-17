"""No-login Power BI Shape Map: actual Contoso visual migration acceptance."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.migrate_contoso_country_map import (
    MAP_FILE,
    REPO_ROOT,
    migrate,
)

FIXTURES = REPO_ROOT / "tests" / "fixtures"
ARCHIVE = FIXTURES / "contoso-retail-no-login-shapemap.zip"
MANIFEST = FIXTURES / "contoso-retail-no-login-shapemap.manifest.json"
LEGACY = FIXTURES / "contoso-country-legacy-visual.json"


@pytest.fixture
def original(tmp_path: Path) -> Path:
    src = tmp_path / "baseline"
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        assert len(names) > 70
        for name in names:
            entry = Path(name)
            assert not entry.is_absolute() and ".." not in entry.parts
        archive.extractall(src)
    (src / MAP_FILE).write_bytes(LEGACY.read_bytes())
    return src


def test_complete_contoso_shape_map_replacement_is_only_report_delta(original, tmp_path):
    candidate = tmp_path / "renderable"
    source_visual_sha = hashlib.sha256((original / MAP_FILE).read_bytes()).hexdigest()
    source_model = {
        p.relative_to(original).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in original.glob("Contoso Retail.SemanticModel/**/*")
        if p.is_file() and (".pbi" not in p.parts or p.name == "cache.abf")
    }
    receipt = migrate(original, candidate)
    assert receipt["status"] == "candidate_only"
    assert receipt["changed_visual"] == MAP_FILE.as_posix()
    assert receipt["auth"] == "none"
    assert receipt["model"] == "untouched"
    assert source_visual_sha == hashlib.sha256(LEGACY.read_bytes()).hexdigest()
    assert {
        p.relative_to(candidate).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in candidate.glob("Contoso Retail.SemanticModel/**/*") if p.is_file()
    } == source_model
    mapping = json.loads((candidate / MAP_FILE).read_text())
    assert mapping["visual"]["visualType"] == "shapeMap"
    assert mapping["visual"]["query"]["queryState"].keys() == {"Category", "Value"}
    assert len(list((candidate / "Contoso Retail.Report" / "definition"
                     / "pages").glob("*/page.json"))) == 5
    assert len(list((candidate / "Contoso Retail.Report" / "definition"
                     / "pages").glob("*/visuals/*/visual.json"))) == 54


def test_zip_receipt_and_world_asset_still_pinned():
    receipt = json.loads(MANIFEST.read_text())
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == receipt["zip_sha256"]
    assert receipt["microsoft_validation"] == {"errors": 0, "warnings": 0}
    assert receipt["preview_visual"] is True
    assert receipt["map_uses_organizational_sign_in"] is False
    assert set(receipt["countries"]) == {
        "United States", "Canada", "United Kingdom", "Germany", "Australia"}
    assert (REPO_ROOT / "assets/maps/WORLD_ATLAS_LICENSE.txt").is_file()


@pytest.mark.parametrize("variant", [
    "existing", "different_type", "different_role", "different_title",
    "missing", "same_source", "unsafe_geometry",
])
def test_recipe_does_not_guess_unsafe_unknown_report(original, tmp_path, variant, monkeypatch):
    target = tmp_path / "result"
    src = original / MAP_FILE
    if variant == "existing":
        target.mkdir()
    elif variant == "different_type":
        doc = json.loads(src.read_text())
        doc["visual"]["visualType"] = "azureMap"
        src.write_text(json.dumps(doc))
    elif variant == "different_role":
        doc = json.loads(src.read_text())
        doc["visual"]["query"]["queryState"]["Size"]["projections"][0]["field"][
            "Measure"]["Property"] = "Budget Sales"
        src.write_text(json.dumps(doc))
    elif variant == "different_title":
        doc = json.loads(src.read_text())
        doc["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"][
            "expr"]["Literal"]["Value"] = "'Changed'"
        src.write_text(json.dumps(doc))
    elif variant == "missing":
        src.unlink()
    elif variant == "same_source":
        target = original
    elif variant == "unsafe_geometry":
        from scripts import migrate_contoso_country_map as mod
        altered = tmp_path / "bad-map.topojson"
        altered.write_text('{"objects":{"countries":{"geometries":[]}}}')
        monkeypatch.setattr(mod, "WORLD", altered)
    with pytest.raises((ValueError, FileNotFoundError)):
        migrate(original, target)


def test_real_microsoft_validator_accepts_map_with_no_warnings(original, tmp_path):
    from vqs.powerbi.author import mscli
    if not mscli.probe().get("available"):
        pytest.skip("Pinned Microsoft authoring CLI not installed")
    target = tmp_path / "verified"
    migrate(original, target)
    baseline = mscli.validate(original / "Contoso Retail.Report")
    converted = mscli.validate(target / "Contoso Retail.Report")
    assert baseline["errorCount"] == 0
    assert baseline["warningCount"] == 1
    assert converted["status"] == "valid"
    assert converted["errorCount"] == 0
    assert converted["warningCount"] == 0
