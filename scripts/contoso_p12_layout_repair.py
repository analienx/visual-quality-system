"""Produce a compact, two-column-aligned P12 Contoso candidate from P10.

The archived screenshot-bound P10 is immutable. This recipe changes exactly
eight Deep-dive report visual definitions: one slicer, four KPI cards, and
three detail panels. It does not edit semantic model, fields, interactions,
format strings, measures, the original PBIP, or any running Desktop process.

Run with an unoccupied output path, then use the official Microsoft authoring
CLI to validate and render the new project before claiming visual acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from vqs.design_rules import layout_composition
from vqs.pbir import read_report_files
from vqs.visual.composition import composition_facts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.zip"
MANIFEST = ROOT / "tests/fixtures/contoso-retail-polished-insights-p10.manifest.json"
PAGE = "d9bc3b8f90439bcc"
VISUALS = Path("Contoso Retail.Report/definition/pages") / PAGE / "visuals"

# Explicit page-grid contract, all units in the original 1280 x 720 PBIR
# canvas. KPI pairs span the exact columns of the detail panels below.
POSITIONS = {
    "slicer-year": {"x": 960, "y": 20, "width": 296, "height": 80},
    "card-sales": {"x": 24, "y": 120, "width": 296, "height": 104},
    "card-units": {"x": 336, "y": 120, "width": 296, "height": 104},
    "card-yoy": {"x": 648, "y": 120, "width": 296, "height": 104},
    "card-gm": {"x": 960, "y": 120, "width": 296, "height": 104},
    "sales-by-country": {"x": 24, "y": 240, "width": 608, "height": 456},
    "sales-by-channel": {"x": 648, "y": 240, "width": 608, "height": 196},
    "what-drives-sales": {"x": 648, "y": 452, "width": 608, "height": 244},
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(destination: Path) -> dict:
    """Extract verified P10, repair only declared layout, and prove no drift."""
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite candidate: {destination}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if _sha(FIXTURE) != manifest["sha256"]:
        raise ValueError("screenshot-bound P10 fixture checksum mismatch")
    with zipfile.ZipFile(FIXTURE) as archive:
        members = archive.namelist()
        if len(members) != manifest["files"]:
            raise ValueError("P10 fixture inventory mismatch")
        for name in members:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("unsafe P10 fixture entry")
        destination.mkdir(parents=True)
        archive.extractall(destination)
        original = {name: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in members}
    changes = []
    for visual_id, rect in POSITIONS.items():
        path = destination / VISUALS / visual_id / "visual.json"
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        if doc.get("name") != visual_id:
            raise ValueError(f"unexpected P10 visual identity: {visual_id}")
        old = doc.get("position", {})
        if not isinstance(old, dict):
            raise ValueError(f"missing P10 visual geometry: {visual_id}")
        old.update(rect)
        if visual_id == "slicer-year":
            vco = doc["visual"]["visualContainerObjects"]
            title = vco["title"][0]["properties"]
            if title["text"]["expr"]["Literal"]["Value"] != "'Year'":
                raise ValueError("unexpected year slicer title")
            if (doc["visual"]["objects"]["header"][0]["properties"]["text"]
                    ["expr"]["Literal"]["Value"] != "'Reporting year'"):
                raise ValueError("unexpected year slicer header")
            # Preserve the meaningful field caption; remove the duplicate
            # container heading, not the interactive dropdown or its query.
            title["show"]["expr"]["Literal"]["Value"] = "false"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        changes.append(path.relative_to(destination).as_posix())
    unchanged = 0
    for name, expected in original.items():
        actual = _sha(destination / name)
        if name in changes:
            if actual == expected:
                raise ValueError(f"planned report layout change absent: {name}")
        elif actual != expected:
            raise ValueError(f"out-of-scope source change: {name}")
        else:
            unchanged += 1
    report = destination / "Contoso Retail.Report"
    verdict = layout_composition(composition_facts(read_report_files(report)))
    if verdict["status"] != "pass":
        raise ValueError(f"candidate layout policy not clean: {verdict}")
    return {"verdict": "candidate_only", "source_p10_sha256": manifest["sha256"],
            "changed_report_files": changes, "unchanged_files": unchanged,
            "semantic_model_unchanged": True,
            "layout_composition": verdict["status"],
            "requires_official_validation_and_full_canvas_render": True,
            "candidate": str(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh candidate project directory, never the original")
    args = parser.parse_args()
    print(json.dumps(migrate(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
