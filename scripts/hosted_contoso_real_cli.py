"""Real complete Contoso PBIP oracle on Linux AND Windows GitHub runners.

This is static Microsoft authoring/QVS source acceptance, not Power BI
Desktop rendering or DAX parity. The owner expressly authorized this
public test fixture. Unpack strictly and never execute project scripts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from vqs.pbir import source_digest
from vqs.powerbi.author import mscli

BASE = Path(__file__).resolve().parents[1]
ARCHIVE = BASE / "tests" / "fixtures" / "contoso-retail-complete-p7.zip"
MANIFEST = BASE / "tests" / "fixtures" / "contoso-retail-complete-p7.manifest.json"


def _extract(root: Path) -> tuple[Path, dict]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != manifest["zip_sha256"]:
        raise ValueError("fixture archive source mismatch")
    with zipfile.ZipFile(ARCHIVE) as zipped:
        names = zipped.namelist()
        if len(names) != manifest["file_count"] or len(names) != len(set(names)):
            raise ValueError("fixture inventory mismatch")
        for member in zipped.infolist():
            path = Path(member.filename)
            if (path.is_absolute() or ".." in path.parts
                    or member.is_dir() or member.file_size > 1_000_000):
                raise ValueError("unsafe or unexpected fixture file")
            if (
                member.filename != "Contoso Retail.pbip"
                and (len(path.parts) < 2
                     or path.parts[0] not in ("Contoso Retail.Report",
                                              "Contoso Retail.SemanticModel"))
            ):
                raise ValueError("unrecognized fixture file")
            # Machine-local state was deliberately excluded.
            if (path.parts and ".pbi" in path.parts
                    and path.name != "cache.abf"):
                raise ValueError("machine-local configuration in fixture")
        zipped.extractall(root)
    project = root / "Contoso Retail.Report"
    model = root / "Contoso Retail.SemanticModel"
    if not project.is_dir() or not (model / ".pbi" / "cache.abf").is_file():
        raise ValueError("full model cache missing")
    return project, manifest


def _visual_inventory(report: Path) -> dict:
    pages = sorted((report / "definition" / "pages").glob("*/page.json"))
    visuals = sorted((report / "definition" / "pages").glob("*/visuals/*/visual.json"))
    for filename in pages + visuals:
        if not isinstance(json.loads(filename.read_text(encoding="utf-8")), dict):
            raise TypeError("invalid PBIR object")
    if len(pages) != 5 or len(visuals) != 54:
        raise ValueError("unexpected Contoso visual/page inventory")
    return {"pages": len(pages), "visuals": len(visuals)}


def exercise(out: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="vqs-contoso-hosted-") as tmp:
        root = Path(tmp)
        report, manifest = _extract(root / "baseline")
        visual_inventory = _visual_inventory(report)
        baseline = mscli.validate(report)
        if (baseline["status"] != "valid" or baseline["errorCount"] != 0
                or baseline["warningCount"] != 1):
            raise ValueError("real Microsoft baseline result unexpected")
        # Negative control: structurally corrupt one report visual in an
        # isolated copy. The official CLI MUST reject its JSON.
        candidate = root / "negative"
        shutil.copytree(report.parent, candidate)
        broken = (candidate / "Contoso Retail.Report" / "definition" / "pages"
                  / "Markets_drivers" / "visuals" / "market-sales" / "visual.json")
        broken.write_text('{"name": "bad", invalid', encoding="utf-8")
        negative = mscli.validate(candidate / "Contoso Retail.Report")
        if negative["status"] != "invalid" or not negative["errors"]:
            raise ValueError("Microsoft CLI failed to reject negative PBIR control")
        return {
            "contract": "vqs.hosted-contoso-real-ms-cli/1",
            "fixture_zip_sha256": manifest["zip_sha256"],
            "report_and_model_sha256": source_digest(report),
            "model_cache_included": True,
            "source": visual_inventory,
            "positive": {
                "status": baseline["status"],
                "error_count": baseline["errorCount"],
                "warning_count": baseline["warningCount"],
                "diagnostics": baseline["warnings"],
            },
            "negative": {
                "status": negative["status"],
                "error_count": negative.get("errorCount"),
            },
            "runtime_desktop": "NOT_RUN",
            "model_dax_execution": "NOT_RUN",
            "release_verdict": "blocked",
            "status": "positive_and_negative_microsoft_pbir_oracle_pass",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refuse to overwrite hosted source evidence")
    result = exercise(args.out)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
