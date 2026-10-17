"""Replace exactly the verified Contoso Bing map with its no-login Shape Map.

This never mutates the original. It rejects unknown source PBIPs and never
accepts warnings/success based solely on a visualType rename.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_FILE = Path(
    "Contoso Retail.Report/definition/pages/d9bc3b8f90439bcc/"
    "visuals/sales-by-country/visual.json"
)
TEMPLATE = REPO_ROOT / "assets/maps/contoso-sales-country-shapemap-visual.json"
WORLD = REPO_ROOT / "assets/maps/world-countries-110m-vqs.topojson"
EXPECTED_SOURCE_HASH = None  # map exact hash is read from trusted source fixture below
SOURCE_TEMPLATE = REPO_ROOT / "tests/fixtures/contoso-country-legacy-visual.json"
PINNED_WORLD_COMMIT = "3c3120cae5c50cf37f611446c76b258cf40bc1fe"


def _check_role(document: dict, role: str, kind: str,
                entity: str, property_name: str) -> dict:
    entries = document["visual"]["query"]["queryState"][role]["projections"]
    if len(entries) != 1:
        raise ValueError(f"{role} must have one projection")
    field = entries[0]["field"][kind]
    if (field["Expression"]["SourceRef"]["Entity"] != entity
            or field["Property"] != property_name):
        raise ValueError(f"{role} semantic binding drift")
    return entries[0]


def _verify(from_doc: dict, to_doc: dict) -> None:
    if (from_doc["name"] != "sales-by-country"
            or from_doc["visual"]["visualType"] != "map"
            or to_doc["visual"]["visualType"] != "shapeMap"
            or from_doc["position"] != to_doc["position"]):
        raise ValueError("unexpected source/target map identity")
    a = _check_role(from_doc, "Category", "Column", "Dim Store", "Country")
    b = _check_role(from_doc, "Size", "Measure", "Fact Sales",
                    "Reporting Year Sales")
    if (to_doc["visual"]["query"]["queryState"] !=
            {"Category": {"projections": [a]},
             "Value": {"projections": [b]}}):
        raise ValueError("candidate changed map semantic bindings")
    shape = to_doc["visual"]["objects"]["shape"][0]["properties"]
    url = shape["mapUrl"]["expr"]["Literal"]["Value"]
    if PINNED_WORLD_COMMIT not in url or "raw.githubusercontent.com" not in url:
        raise ValueError("untrusted or mutable geography URL")
    geo = json.loads(WORLD.read_text(encoding="utf-8"))
    countries = {
        item["properties"]["name"]
        for item in geo["objects"]["countries"]["geometries"]
    }
    if not {"United States", "Canada", "United Kingdom",
            "Germany", "Australia"} <= countries:
        raise ValueError("map geography lost a Contoso region")


def _inventory(folder: Path) -> dict[str, str]:
    return {
        item.relative_to(folder).as_posix():
            hashlib.sha256(item.read_bytes()).hexdigest()
        for item in folder.rglob("*") if item.is_file() and not item.is_symlink()
    }


def migrate(original: Path, candidate: Path) -> dict:
    if candidate.exists():
        raise ValueError("refuse to overwrite candidate")
    if not (original / MAP_FILE).is_file():
        raise ValueError("not the expected Contoso PBIP folder")
    if original.resolve() == candidate.resolve():
        raise ValueError("cannot modify original")
    source = (original / MAP_FILE).read_bytes()
    expected_source = SOURCE_TEMPLATE.read_bytes()
    if json.loads(source) != json.loads(expected_source):
        raise ValueError("original map differs from pinned P7 baseline")
    before_doc = json.loads(source)
    after_doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    _verify(before_doc, after_doc)
    # Avoid carrying local workspace state or authentication.
    for path in original.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(original)
        if path.is_symlink() or ".." in rel.parts:
            raise ValueError("untrusted source entry")
        if ".pbi" in rel.parts and path.name != "cache.abf":
            continue
        if (rel.parts[0] not in ("Contoso Retail.Report",
                                "Contoso Retail.SemanticModel")
                and rel.name != "Contoso Retail.pbip"):
            continue
        dest = candidate / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    changed = candidate / MAP_FILE
    changed.write_bytes(TEMPLATE.read_bytes())
    original_inventory = _inventory(original)
    final_inventory = _inventory(candidate)
    # Only count common report and model source files. Machine-local settings
    # deliberately omitted from the candidate and cannot be classified as
    # surprise report changes.
    differences = [
        key for key in final_inventory
        if original_inventory.get(key) != final_inventory[key]
    ]
    if differences != [MAP_FILE.as_posix()]:
        raise ValueError(f"unexpected candidate mutations: {differences}")
    return {
        "status": "candidate_only",
        "changed_visual": MAP_FILE.as_posix(),
        "unchanged_source_files": len(final_inventory) - 1,
        "shape_map_preview": True,
        "auth": "none",
        "model": "untouched",
        "release": "requires independent runtime review",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path, help="Containing .pbip project directory")
    parser.add_argument("candidate", type=Path, help="Must not exist yet")
    args = parser.parse_args()
    print(json.dumps(migrate(args.original, args.candidate), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
