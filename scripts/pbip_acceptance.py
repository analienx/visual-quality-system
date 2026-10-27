"""PBIP acceptance runner: measure a report, optionally validate externally.

Runs ``vqs measure`` against a PBIR report (plus optional TMDL model
folder) and, unless ``--skip-external``, Microsoft
``powerbi-report-author validate`` for the same report (R6-E07: the
legacy pbir validate/BPA legs are removed — BPA has no Microsoft
equivalent). Prints a scoped JSON summary. **G0 source checks are not full release
acceptance**: even a clean source and successful Microsoft authoring
validation cannot certify G1/G2/G4/G6. Exit 1 for a failed source check;
exit 2 when source evidence is blocked or higher-gate acceptance is
unverified. Never return release-level pass / exit 0 from this script::

    python scripts/pbip_acceptance.py path/to/Example.Report
    python scripts/pbip_acceptance.py path/to/Example.Report --model path/to/Example.SemanticModel/definition --out summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _report_author(report: Path) -> dict:
    """Run Microsoft `validate`; missing tool degrades to skipped."""
    from vqs.powerbi.author import mscli

    outcome = mscli.validate(report)
    status = outcome["status"]
    if status == "missing":
        return {"status": "skipped",
                "reason": "powerbi-report-author not on PATH"}
    if status == "valid":
        return {"status": "valid", "warnings": outcome["warnings"],
                "detail": outcome["raw_tail"][-500:]}
    if status == "invalid":
        return {"status": "error", "errors": outcome["errors"],
                "warnings": outcome["warnings"],
                "detail": outcome["raw_tail"][-500:]}
    return {"status": "blocked",
            "reason": outcome.get("note") or status,
            "detail": outcome["raw_tail"][-500:]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a G0-only PBIP source acceptance diagnostic.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-external", dest="skip_external",
                        action="store_true",
                        help="Skip the optional Microsoft validation leg")


    args = parser.parse_args(argv)

    import tempfile

    from vqs.pipeline import run_check
    from vqs.powerbi.measure import measure_report

    try:
        facts = measure_report(str(args.report), str(args.model)
                               if args.model else None)
    except OSError as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    with tempfile.TemporaryDirectory(prefix="vqs-accept-") as tmp:
        decided = run_check(facts, Path(tmp), run_id="acceptance")
    check_summary = {"verdict": decided["verdict"],
                     "findings": len(decided.get("findings", []))}
    rules = facts.get("rules", {})
    summary = {"report": str(args.report),
               "model": str(args.model) if args.model else None,
               "check": check_summary,
               "measure": {"sections": sorted(rules),
                           "readings": sum(len(v) for section in rules.values()
                                           if isinstance(section, dict)
                                           for v in section.values()
                                           if isinstance(v, list)),
                           "bindings": len(facts.get("models", [{}])[0].get(
                               "bindings", [])) if facts.get("models") else 0},
               "report_author": {"status": "skipped",
                                 "reason": "--skip-external"}
               if args.skip_external else _report_author(args.report)}
    empty = not rules
    author_status = summary["report_author"]["status"]
    check_bad = check_summary["verdict"] != "pass"
    source_verdict = (
        "blocked" if empty or author_status in ("skipped", "blocked")
        else "fail" if check_bad or author_status == "error"
        else "pass"
    )
    # A source-only pass is real engineering evidence, not a G2/G4/G6
    # release verdict. Avoid the previous misleading JSON pass + exit 0.
    summary["gate"] = "G0"
    summary["scope"] = "static_source_only"
    summary["source_verdict"] = source_verdict
    summary["release_verdict"] = "blocked"
    summary["verdict"] = (
        "blocked" if empty
        else "fail" if check_bad or author_status == "error"
        else "blocked"
    )
    summary["reason"] = (
        "G0-only evidence cannot prove native G1/G2/G4 or independent G6"
        if summary["verdict"] == "blocked" else
        "source check or Microsoft validation failed"
    )
    text = json.dumps(summary, indent=2)
    if args.out is None:
        print(text)
    else:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 1 if summary["verdict"] == "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())