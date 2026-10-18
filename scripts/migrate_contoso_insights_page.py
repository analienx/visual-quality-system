"""P10: reproducible, source-bound polished Contoso Insights page migration.

Takes the verified P9 Contoso full project and creates a NEW P10 candidate.
Exactly two report visuals may differ; original and semantic model untouched.
No sign-in or Azure Maps needed. Geography is pinned to a public commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path("Contoso Retail.Report/definition/pages/d9bc3b8f90439bcc/visuals")
MAP = PAGE / "sales-by-country/visual.json"
REGION = PAGE / "what-drives-sales/visual.json"
SOURCE_MAP = ROOT / "assets/maps/contoso-sales-country-shapemap-visual.json"
SOURCE_TREE = ROOT / "tests/fixtures/contoso-insights-legacy-tree.json"
TARGET_MAP = ROOT / "assets/pbir/p10-country-sales-shapemap.json"
TARGET_REGION = ROOT / "assets/pbir/p10-regional-sales-bar.json"
TOPOLOGY = ROOT / "assets/maps/world-countries-110m-without-antarctica.topojson"
PINNED_GEO_COMMIT = "eb172bc4bbfaea2f072fdecc8c1fe74851390bf4"


def _json(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise TypeError(f"not a JSON object: {path.name}")
    return result


def _check(original: Path) -> None:
    if not all((original / name).is_dir() for name in (
        "Contoso Retail.Report", "Contoso Retail.SemanticModel"
    )):
        raise ValueError("expected complete Contoso Report and SemanticModel")
    if not (original / "Contoso Retail.pbip").is_file():
        raise ValueError("expected Contoso PBIP entrypoint")
    if _json(original / MAP) != _json(SOURCE_MAP):
        raise ValueError("map diverges from pinned P9 visual; no blind conversion")
    if _json(original / REGION) != _json(SOURCE_TREE):
        raise ValueError("tree diverges from verified baseline; no blind replacement")
    old_map = _json(SOURCE_MAP)
    m = _json(TARGET_MAP)
    tree = _json(SOURCE_TREE)
    bar = _json(TARGET_REGION)
    assert old_map["visual"]["visualType"] == m["visual"]["visualType"] == "shapeMap"
    assert tree["visual"]["visualType"] == "decompositionTreeVisual"
    assert bar["visual"]["visualType"] == "clusteredBarChart"
    assert old_map["visual"]["query"]["queryState"] == m["visual"]["query"]["queryState"]
    assert m["name"] == old_map["name"] and bar["name"] == tree["name"]
    for key in ("x", "y", "width", "height"):
        if (m["position"][key] != tree["position"][key]
                or bar["position"][key] != old_map["position"][key]):
            raise ValueError("P10 tile geometry drift")
    reg = tree["visual"]["query"]["queryState"]["ExplainBy"]["projections"][0]["field"]
    barq = bar["visual"]["query"]["queryState"]
    if barq["Category"]["projections"][0]["field"] != reg:
        raise ValueError("Region dimension changed")
    measure = old_map["visual"]["query"]["queryState"]["Value"]["projections"][0]["field"]
    if barq["Y"]["projections"][0]["field"] != measure:
        raise ValueError("Reporting Year Sales measure changed")
    url = m["visual"]["objects"]["shape"][0]["properties"]["mapUrl"]["expr"]["Literal"]["Value"]
    if PINNED_GEO_COMMIT not in url or not url.startswith("'https://raw.githubusercontent.com/"):
        raise ValueError("unapproved geography URL")
    geography = _json(TOPOLOGY)
    names = {g["properties"]["name"]
             for g in geography["objects"]["countries"]["geometries"]}
    if ("Antarctica" in names or not {
        "United States", "Canada", "United Kingdom", "Germany", "Australia"
    } <= names):
        raise ValueError("unapproved topology contents")
    if "dataPoint" in bar["visual"]["objects"]:
        raise ValueError("gradient/legend not cleaned up")
    if len(barq["Category"]["projections"]) != 1:
        raise ValueError("hierarchy chart must not flatten multiple axis fields")


def _inventory(folder: Path) -> dict[str, str]:
    return {
        x.relative_to(folder).as_posix(): hashlib.sha256(x.read_bytes()).hexdigest()
        for x in folder.rglob("*") if x.is_file() and not x.is_symlink()
    }


def _deterministic_template_bytes(path: Path) -> bytes:
    """Preserve the Windows-authored, evidence-bound fixture on every OS.

    Git normally checks out text JSON with CRLF on Windows and LF on Linux.
    The screenshot-verified P10 fixture was authored with CRLF. Normalize
    only our two replacement visual templates so independent Linux/Windows
    runs regenerate the *identical bytes*, not just structurally equal JSON.
    """
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return raw.replace(b"\n", b"\r\n")


def migrate(original: Path, candidate: Path) -> dict[str, object]:
    original = original.resolve()
    candidate = candidate.resolve()
    if candidate.exists() or candidate == original or original in candidate.parents:
        raise ValueError("candidate must be a new separate directory")
    _check(original)
    # Validate all paths before writing anything, including symlinks in folders.
    for item in original.rglob("*"):
        if item.is_symlink():
            raise ValueError("symlink present in source")
    supported_top = {
        "Contoso Retail.pbip", "Contoso Retail.Report",
        "Contoso Retail.SemanticModel",
    }
    for file in original.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(original)
        if rel.parts[0] not in supported_top:
            continue
        if ".pbi" in rel.parts and file.name != "cache.abf":
            continue
        dest = candidate / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, dest)
    (candidate / MAP).write_bytes(_deterministic_template_bytes(TARGET_MAP))
    (candidate / REGION).write_bytes(_deterministic_template_bytes(TARGET_REGION))
    before = _inventory(original)
    after = _inventory(candidate)
    changes = sorted(key for key in after if before.get(key) != after[key])
    if changes != sorted((MAP.as_posix(), REGION.as_posix())):
        raise ValueError(f"unintended candidate change: {changes}")
    if (len(list((candidate / "Contoso Retail.Report/definition/pages")
                 .glob("*/page.json"))) != 5
            or len(list((candidate / "Contoso Retail.Report/definition/pages")
                        .glob("*/visuals/*/visual.json"))) != 54):
        raise ValueError("unexpected page/visual inventory")
    return {
        "verdict": "candidate_only",
        "changed_report_files": changes,
        "unchanged_files": len(after) - len(changes),
        "semantic_model_digest_unchanged": all(
            after.get(key) == sha for key, sha in before.items()
            if key.startswith("Contoso Retail.SemanticModel/")
            and key in after
        ),
        "geography_no_antarctica": True,
        "map_requires_login": False,
        "map_requires_public_github_network": True,
        "shape_map_is_preview": True,
        "decomposition_tree_replaced_on_this_page": True,
        "release": "requires independent review and interaction validation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.original, args.candidate), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
