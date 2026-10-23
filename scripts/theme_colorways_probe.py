"""Build and validate proposed dark colorways on real public Contoso PBIP.

GitHub-hosted authoring only. Artifacts are actual disposable PBIP candidates,
not generated illustrative screenshots or source-report edits.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

from jsonschema import Draft7Validator

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.theme_candidate_probe import PBIP, REPORT, validate_pbip
from vqs.theme import (
    THEME_SCHEMA,
    apply_theme,
    audit_candidate,
    load_palette,
    palette_contrast_check,
    source_digest,
)

NAMES = ("dark-graphite-mint", "dark-warm-basalt", "dark-slate-lavender")
PRESETS = REPO / "examples" / "theme-palettes"


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "theme-colorways-proof.json")
    result: dict = {"schema": "vqs.theme.colorways/1", "status": "fail",
                    "source": str(REPORT.relative_to(REPO)), "colorways": {}}
    try:
        with urllib.request.urlopen(THEME_SCHEMA, timeout=45) as response:
            schema = json.load(response)
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema)
        baseline = validate_pbip(PBIP)
        result["baselineAuthoringCode"] = baseline["code"]
        original_digest = source_digest(REPORT)
        evidence = os.environ.get("VQS_THEME_COLORWAY_EVIDENCE_ROOT", "").strip()
        evidence_root = Path(evidence).resolve() if evidence else None
        if evidence_root is not None and not evidence_root.is_relative_to(REPO):
            raise ValueError("colorway artifact root must be within checkout")
        with tempfile.TemporaryDirectory(prefix="vqs-palette-real-") as temporary:
            for name in NAMES:
                palette = load_palette("dark", PRESETS / (name + ".json"))
                issues = palette_contrast_check(palette)
                candidate_root = Path(temporary) / name
                manifest = apply_theme(REPORT, "dark", palette, candidate_root)
                report = candidate_root / REPORT.name
                themed = report / "StaticResources" / "RegisteredResources"
                theme = json.loads((themed / manifest["themeFileName"])
                                   .read_text(encoding="utf-8"))
                schema_issues = [f"{list(err.path)}: {err.message}"
                                 for err in list(validator.iter_errors(theme))[:10]]
                actual_pages = sorted(report.glob("definition/pages/*/page.json"))
                backgrounds = []
                for page_path in actual_pages:
                    obj = json.loads(page_path.read_text(encoding="utf-8"))
                    item = obj.get("objects", {}).get("background", [])
                    value = (item[0]["properties"]["color"]["solid"]["color"]
                             ["expr"]["Literal"]["Value"] if item else None)
                    backgrounds.append(value)
                project = next(candidate_root.glob("*.pbip"), None)
                author = (validate_pbip(project) if project
                          else {"code": None, "stdout": "missing candidate pbip"})
                audit = audit_candidate(candidate_root)
                passed = (not issues and not schema_issues
                          and baseline["code"] == 0 and author["code"] == 0
                          and len(actual_pages) == 5
                          and all(bg == f"'{palette['canvas']}'" for bg in backgrounds)
                          and audit["integrityStatus"] == "pass"
                          and audit["appearanceCoverageStatus"] == "complete"
                          and source_digest(REPORT) == original_digest)
                result["colorways"][name] = {
                    "pass": passed, "palette": name, "canvas": palette["canvas"],
                    "schemaErrors": schema_issues, "paletteContrastErrors": issues,
                    "authoringCode": author["code"],
                    "authoringOutput": author.get("stdout", "")[-2500:],
                    "pages": len(actual_pages), "canvasValues": backgrounds,
                    "integrity": audit["integrityStatus"],
                    "appearance": audit["appearanceCoverageStatus"],
                    "unresolved": len(audit["unresolved"]),
                    "sourceDigest": manifest["sourceDigest"],
                    "candidateDigest": manifest["candidateDigest"],
                }
                if passed and evidence_root is not None:
                    evidence_root.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(candidate_root, evidence_root / name)
        result["status"] = ("pass" if len(result["colorways"]) == len(NAMES)
                            and all(c["pass"] for c in result["colorways"].values())
                            else "fail")
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"],
                          "colorways": {k: v["pass"] for k, v
                                        in result["colorways"].items()},
                          "error": result.get("error")}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
