"""Pre-capture hard gate: exact Power BI categorical assignments in all 28 modes.

Run on downloaded GitHub authoring artifacts (no Desktop use):
  python scripts/theme_gallery_color_gate.py PATH_TO_28_CANDIDATES --out proof.json

No screenshot is accepted until this source/provenance gate passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vqs.premium import audit


def verify(candidate_root: Path) -> dict:
    families = json.loads((ROOT/"docs/APPROVED_THEME_SELECTION.json").read_text(
        encoding="utf-8"))["presets"]
    modes = [(p["slug"], mode) for p in families for mode in ("light", "dark")]
    found = {p.name for p in candidate_root.glob("*/Contoso Retail.Report")
             if p.is_dir()}
    expected = {f"{name}-{mode}" for name, mode in modes}
    # Each candidate directory is named <slug>-<mode>; the report is within.
    found = {p.parent.name for p in candidate_root.glob(
        "*/Contoso Retail.Report") if p.is_dir()}
    if found != expected:
        raise ValueError(f"expected 28 candidates; missing={sorted(expected-found)}, "
                         f"unexpected={sorted(found-expected)}")
    output = {"schema": "vqs.native-gallery.preflight/1", "modes": {},
              "checked": 0, "failures": 0, "status": "fail"}
    for slug, mode in modes:
        key = f"{slug}-{mode}"
        report = candidate_root/key/"Contoso Retail.Report"
        source = candidate_root/key/"theme-manifest.json"
        if not source.is_file():
            raise ValueError(f"missing source provenance for {key}")
        manifest = json.loads(source.read_text(encoding="utf-8"))
        findings = audit(str(report))["findings"]
        failures = [f for f in findings
                    if f["rule"] in ("color.category_series_collision",
                                     "color.category_wildcard_shared_fill",
                                                "color.category_conditional_shared_status",
                                                "color.category_unscoped_default")]
        output["modes"][key] = {
            "sourceDigest": manifest["sourceDigest"],
            "paletteHash": manifest["paletteHash"],
            "candidateDigest": manifest["candidateDigest"],
            "modelDigest": manifest["modelDigest"],
            "failedCharts": [{"page": f["page_id"],
                              "visuals": f["visual_ids"],
                              "rule": f["rule"],
                              "evidence": f["evidence"]}
                             for f in failures],
            "status": "fail" if failures else "pass"}
        output["checked"] += 1
        output["failures"] += len(failures)
        print("QVS_CATEGORY_GATE", key, "FAIL" if failures else "PASS",
              len(failures), flush=True)
    output["status"] = ("pass" if output["checked"] == 28
                        and output["failures"] == 0 else "fail")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_root", type=Path)
    parser.add_argument("--out", type=Path, default=Path("category-preflight.json"))
    args = parser.parse_args()
    try:
        result = verify(args.candidate_root)
    except (OSError, ValueError, KeyError) as exc:
        result = {"schema": "vqs.native-gallery.preflight/1", "status": "fail",
                  "error": f"{type(exc).__name__}: {exc}"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print("FINAL_CATEGORY_GATE", result["status"],flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
