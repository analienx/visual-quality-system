"""GitHub-hosted exact-SHA verification of both real Contoso theme candidates.

Unlike generic CLI scaffold probes, this validates the themed outputs and the
authoritative October 2026 Microsoft report-theme JSON schema.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from jsonschema import Draft7Validator

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from vqs.theme import (
    THEME_SCHEMA,
    apply_theme,
    audit_candidate,
    load_palette,
    source_digest,
)

REPORT = REPO / "examples" / "contoso-retail" / "Contoso Retail.Report"
PBIP = REPO / "examples" / "contoso-retail" / "Contoso Retail.pbip"


def validate_pbip(pbip: Path) -> dict:
    binary = shutil.which("powerbi-report-author")
    if binary is None:
        raise RuntimeError("Microsoft report authoring CLI is missing")
    command = (["cmd", "/c", binary] if os.name == "nt" else [binary])
    command += ["validate", str(pbip)]
    cp = subprocess.run(command, capture_output=True, text=True, timeout=180,
                        check=False)
    return {"code": cp.returncode, "stdout": cp.stdout[-12000:],
            "stderr": cp.stderr[-3500:]}


def main() -> int:
    result: dict = {"schema": "vqs.theme.integration/1",
                    "oracle": "real-contoso-candidates",
                    "status": "fail", "report": str(REPORT.relative_to(REPO)),
                    "modes": {}}
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "theme-contoso-validation.json")
    try:
        with urllib.request.urlopen(THEME_SCHEMA, timeout=45) as response:
            schema = json.load(response)
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema)
        source_before = source_digest(REPORT)
        base = validate_pbip(PBIP)
        result["baselineAuthoring"] = base
        evidence_value = os.environ.get("VQS_THEME_EVIDENCE_ROOT", "").strip()
        evidence_root = Path(evidence_value).resolve() if evidence_value else None
        if evidence_root is not None and not evidence_root.is_relative_to(REPO):
            raise RuntimeError("theme evidence output must be under repository checkout")
        with tempfile.TemporaryDirectory(prefix="vqs-theme-real-") as root:
            root = Path(root)
            for mode in ("light", "dark"):
                candidate_root = root / mode
                manifest = apply_theme(REPORT, mode, load_palette(mode, None),
                                       candidate_root)
                themed = candidate_root / REPORT.name
                theme_file = (themed / "StaticResources"
                              / "RegisteredResources" / manifest["themeFileName"])
                theme_doc = json.loads(theme_file.read_text(encoding="utf-8"))
                violations = list(validator.iter_errors(theme_doc))
                issue_text = [f"{list(e.path)}: {e.message}" for e in violations[:15]]
                # Every page receives explicit canvas. This was missing on
                # all five baseline Contoso pages.
                page_files = sorted(themed.glob("definition/pages/*/page.json"))
                backgrounds = []
                for page_path in page_files:
                    page = json.loads(page_path.read_text(encoding="utf-8"))
                    bg = page.get("objects", {}).get("background", [])
                    literal = (bg[0]["properties"]["color"]["solid"]["color"]
                               ["expr"]["Literal"]["Value"] if bg else None)
                    backgrounds.append({"page": page_path.parent.name,
                                        "color": literal})
                audit = audit_candidate(candidate_root)
                candidate_pbip = next(candidate_root.glob("*.pbip"), None)
                author = (validate_pbip(candidate_pbip)
                          if candidate_pbip else {"code": None})
                mode_ok = (
                    len(page_files) == 5
                    and all(x["color"] == f"'{load_palette(mode, None)['canvas']}'"
                            for x in backgrounds)
                    and not violations
                    and audit["integrityStatus"] == "pass"
                    and source_digest(REPORT) == source_before
                    and candidate_pbip is not None
                    and (base["code"] != 0 or author["code"] == 0)
                )
                if mode_ok and evidence_root is not None:
                    evidence_root.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(candidate_root, evidence_root / mode)
                result["modes"][mode] = {
                    "pass": mode_ok, "pageBackgrounds": backgrounds,
                    "themeSchemaErrors": issue_text,
                    "authoring": author,
                    "audit": {"status": audit["status"],
                              "integrityStatus": audit["integrityStatus"],
                              "appearanceCoverageStatus":
                                  audit["appearanceCoverageStatus"],
                              "unresolvedCount": len(audit["unresolved"])},
                    "sourceDigest": manifest["sourceDigest"],
                    "candidateDigest": manifest["candidateDigest"],
                }
        if base["code"] != 0:
            result["baselineLimitation"] = (
                "Original Contoso fails native authoring CLI; candidate "
                "status must be independently diagnosed, no fake clean G2.")
        result["status"] = ("pass" if all(
            value["pass"] for value in result["modes"].values()) else "fail")
    except Exception as exc:  # noqa: BLE001 - emit safe hosted failure receipt
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, default=str) + "\n",
                       encoding="utf-8")
        print(json.dumps({"status": result["status"],
                          "modes": {k: v.get("pass") for k, v in
                                    result["modes"].items()},
                          "error": result.get("error"),
                          "baselineLimit": result.get("baselineLimitation")}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
