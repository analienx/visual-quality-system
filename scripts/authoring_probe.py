"""Hosted real-CLI lane for R6-E07 (oracle A07, real-tool leg).

Probes the Microsoft-guided `powerbi-report-author` CLI on PATH and,
when present, runs `validate` against a synthetic .Report project
through the genuine vqs.powerbi.author port (no fakes). The record is
written as JSON and the process always exits 0: a missing tool is a
recorded blocked outcome, never a harness failure. No install is
attempted: the Microsoft reference names no distribution channel, so
guessing a package identity would be a supply-chain risk; absence is
reported with its reproduction instead.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))



SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")


def _synthetic_report(root: Path) -> Path:
    report = root / "synthetic.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    (definition / "pages" / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
        encoding="utf-8")
    (definition / "version.json").write_text(json.dumps(
        {"$schema": ("https://developer.microsoft.com/json-schemas/fabric/"
                    "item/report/definition/versionMetadata/1.0.0/"
                    "schema.json"), "version": "2.0.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps(
        {"$schema": SCHEMA_REPORT, "layoutOptimization": "None",
         "themeCollection": {}}), encoding="utf-8")
    (definition / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(json.dumps({
        "name": "v1",
        "position": {"x": 0, "y": 0, "width": 100, "height": 100, "z": 1},
        "visual": {"visualType": "barChart"}}), encoding="utf-8")
    return report


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("authoring-real-cli.json")
    from vqs.powerbi.author import adapter, mscli

    probed = mscli.probe()
    with tempfile.TemporaryDirectory(prefix="vqs-authoring-") as tmp:
        candidate = _synthetic_report(Path(tmp))
        decided = adapter.run_backend(str(candidate), policy="auto")
    record = {"lane": "authoring-real-cli", "oracle": "A07",
              "probe": probed, "decision": decided,
              "reproduction": {
                  "probe_command": probed["probe_command"],
                  "note": ("PATH probe only; no install attempted — the "
                           "Microsoft reference names no distribution "
                           "channel.")}}
    out.write_text(json.dumps(record, indent=2, sort_keys=True),
                   encoding="utf-8")
    print(f"backend={decided['backend']} verdict={decided['verdict']} "
          f"reason={decided['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
