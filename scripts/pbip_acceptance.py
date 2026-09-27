"""PBIP acceptance runner: measure a report, optionally validate with pbir.

Runs ``vqs measure`` against a PBIR report (plus optional TMDL model
folder) and, unless ``--skip-pbir``, ``pbir validate --all`` for the
same report. Prints a JSON summary and exits 0 when the emitter
produces check-ready facts and pbir reports no errors (a missing pbir
is reported as skipped, never a failure — VQS stays usable without
it). Exit 1 on pbir errors, 2 when the report is unreadable::

    python scripts/pbip_acceptance.py path/to/Example.Report
    python scripts/pbip_acceptance.py path/to/Example.Report --model path/to/Example.SemanticModel/definition --out summary.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _pbir(report: Path) -> dict:
    """Run pbir validate --all; missing binary degrades to skipped."""
    if shutil.which("pbir") is None:
        return {"status": "skipped", "reason": "pbir not on PATH"}
    try:
        completed = subprocess.run(
            ["pbir", "validate", report.name, "--all"],
            capture_output=True, text=True, cwd=report.parent, timeout=600,
            check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}
    output = (completed.stdout + completed.stderr).strip()
    tail = "\n".join(output.splitlines()[-3:])
    if completed.returncode != 0:
        return {"status": "error", "detail": tail}
    return {"status": "valid", "detail": tail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accept a PBIP report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--skip-pbir", action="store_true")
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
               "pbir": {"status": "skipped", "reason": "--skip-pbir"}
               if args.skip_pbir else _pbir(args.report)}
    empty = not rules
    pbir_bad = summary["pbir"]["status"] in ("error", "blocked")
    summary["verdict"] = "fail" if (empty or pbir_bad) else "pass"
    text = json.dumps(summary, indent=2)
    if args.out is None:
        print(text)
    else:
        args.out.write_text(text + "\n", encoding="utf-8")
    if empty:
        return 2
    return 1 if pbir_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
