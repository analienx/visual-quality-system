"""Hosted acceptance of all 28 approved Light/Dark VQS theme candidates.

Checks native Microsoft authoring CLI, official theme schema, source
immutability, presentation color tokens, audit and all five Contoso pages.
This is NOT a native screenshot/interaction pass.
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
    contrast_ratio,
    load_palette,
    palette_contrast_check,
    source_digest,
)

FAMILIES = json.loads(
    (REPO / "docs/APPROVED_THEME_SELECTION.json").read_text(encoding="utf-8")
)["presets"]
OUT = Path(sys.argv[1] if len(sys.argv) > 1
           else "theme-approved-library-proof.json")


def main() -> int:
    result = {"schema": "vqs.approved-library.probe/1",
              "expected": 28, "verified": {}, "status": "fail",
              "note": "Native schema/CLI validation, not Power BI Desktop screenshots"}
    try:
        with urllib.request.urlopen(THEME_SCHEMA, timeout=45) as handle:
            schema = json.load(handle)
        Draft7Validator.check_schema(schema)
        validator = Draft7Validator(schema)
        digest = source_digest(REPORT)
        baseline = validate_pbip(PBIP)
        if baseline["code"] != 0:
            raise RuntimeError("original Contoso PBIP authoring validation failed")
        evidence_value = os.environ.get("VQS_APPROVED_EVIDENCE_ROOT", "")
        evidence_root = (Path(evidence_value).resolve()
                         if evidence_value else None)
        if evidence_root and not evidence_root.is_relative_to(REPO):
            raise RuntimeError("evidence output must stay inside checkout")
        with tempfile.TemporaryDirectory(prefix="vqs-approved28-") as tmp:
            for family in FAMILIES:
                for mode in ("dark", "light"):
                    name = family["slug"] + "-" + mode
                    palette = load_palette(mode, None, family["slug"])
                    errors = palette_contrast_check(palette)
                    if len(palette["dataColors"]) != 8:
                        raise ValueError("expected exactly 8 data colors: " + name)
                    chart_bad = [
                        f"{color}: {contrast_ratio(color,palette['surface']):.2f}"
                        for color in palette["dataColors"]
                        if contrast_ratio(color, palette["surface"]) < 3
                    ]
                    if errors or chart_bad:
                        raise ValueError(
                            f"Contrast violation for {name}: {errors}; {chart_bad}")
                    candidate_root = Path(tmp) / name
                    manifest = apply_theme(REPORT, mode, palette, candidate_root)
                    report = candidate_root / REPORT.name
                    theme_file = (report / "StaticResources"
                                  / "RegisteredResources"
                                  / manifest["themeFileName"])
                    theme_doc = json.loads(theme_file.read_text("utf-8"))
                    schema_errors = [
                        f"{list(x.path)} {x.message}"
                        for x in list(validator.iter_errors(theme_doc))[:6]]
                    pbip = next(candidate_root.glob("*.pbip"), None)
                    native = (validate_pbip(pbip) if pbip
                              else {"code": 2, "stdout": "missing PBIP"})
                    audit = audit_candidate(candidate_root)
                    pages = list(report.glob("definition/pages/*/page.json"))
                    valid = (not schema_errors and native["code"] == 0
                             and audit["integrityStatus"] == "pass"
                             and audit["appearanceCoverageStatus"] == "complete"
                             and len(pages) == 5 and source_digest(REPORT) == digest)
                    result["verified"][name] = {
                        "pass": valid,
                        "pages": len(pages),
                        "schemaErrors": schema_errors,
                        "nativeAuthoringCode": native["code"],
                        "authoringOutput": native.get("stdout", "")[-650:],
                        "sourceDigest": manifest["sourceDigest"],
                        "candidateDigest": manifest["candidateDigest"],
                        "auditIntegrity": audit["integrityStatus"],
                        "auditAppearance": audit["appearanceCoverageStatus"],
                        "chartColors": palette["dataColors"],
                        "numericGradient": [
                            palette[k] for k in
                            ("gradientMin", "gradientCenter", "gradientMax")],
                    }
                    print("VALIDATED", name, "PASS" if valid else "FAIL",
                          flush=True)
                    if not valid:
                        raise RuntimeError("Candidate failed native authoring: " + name)
                    if evidence_root is not None:
                        evidence_root.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(candidate_root, evidence_root / name)
        result["status"] = ("pass" if len(result["verified"]) == 28 and
                            all(x["pass"] for x in result["verified"].values())
                            else "fail")
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"],
                          "variants": len(result["verified"]),
                          "error": result.get("error")}), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
