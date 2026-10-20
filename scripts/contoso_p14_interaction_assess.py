"""Assess private Deep Dive interaction captures against live DAX receipts.

Example on the same Windows host, after an independent operator performs the
documented UI actions and records screenshot/visible-value evidence:

  python -m scripts.contoso_p14_interaction_assess <Report-folder> \
      --oracle <private-p11-oracle.json> --trace <private-ui-trace.json> \
      --captures <private-captures-dir> --output <new-private-audit.json>

This deliberately exits nonzero even for numerically consistent caller-entered
traces: without an authenticated Desktop click witness, UI acceptance BLOCKS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from vqs.pbir import source_digest
from vqs.powerbi.interaction_audit import (
    assess_recorded_trace,
    inspect_deep_dive_contract,
)


def run(report: Path, oracle: dict, trace: dict, captures: Path) -> dict:
    try:
        current = source_digest(report)
    except (OSError, ValueError) as exc:
        return {"evidence_consistency": "blocked", "interactive": "blocked",
                "reason": f"current PBIR source unreadable: {exc}"}
    if (not isinstance(trace, dict) or not isinstance(oracle, dict)
            or current != trace.get("source_sha256")
            or current != oracle.get("source_sha256")):
        return {"evidence_consistency": "fail", "interactive": "blocked",
                "reason": "live report source digest differs from recorded oracle/UI"}
    structure = inspect_deep_dive_contract(report)
    if structure["structural"] != "pass":
        return {"evidence_consistency": structure["structural"],
                "interactive": "blocked", "pbir_contract": structure,
                "reason": "Deep Dive PBIR interaction structure unverified"}
    result = assess_recorded_trace(oracle, trace, captures)
    result["pbir_contract"] = structure
    result["drill"] = structure["region_bar_drill"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite a private interaction audit")
    try:
        oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
        trace = json.loads(args.trace.read_text(encoding="utf-8"))
        result = run(args.report, oracle, trace, args.captures)
    except (OSError, ValueError) as exc:
        result = {"evidence_consistency": "blocked", "interactive": "blocked",
                  "reason": f"interaction inputs could not be verified: {exc}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"evidence_consistency": result["evidence_consistency"],
                      "interactive": result["interactive"],
                      "output": str(args.output)}, indent=2))
    return 1 if result["evidence_consistency"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())
