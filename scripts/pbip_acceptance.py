"""PBIP acceptance runner: measure a report, optionally validate with pbir.

Runs ``vqs measure`` against a PBIR report (plus optional TMDL model
folder) and, unless ``--skip-pbir``, ``pbir validate --all`` for the
same report. Prints a JSON summary and exits 0 when the emitter
produces check-ready facts, the offline check passes, and pbir reports
no errors (a missing pbir is reported as skipped, never a failure —
VQS stays usable without it). Exit 1 when the check fails or pbir
reports errors, 2 when the report is unreadable::

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


def _summarize_bpa(payload: object) -> dict:
    """Reduce `pbir bpa run -o json` to counts plus top rule ids."""
    if not isinstance(payload, dict):
        return {"status": "blocked", "reason": "unparseable bpa output"}
    violations = payload.get("violations", [])
    if not isinstance(violations, list):
        return {"status": "blocked", "reason": "bpa violations are not a list"}
    counts = {"error": 0, "warning": 0, "info": 0}
    rules: dict[str, int] = {}
    for item in violations:
        if not isinstance(item, dict):
            continue
        severity = item.get("severity", 0)
        if severity >= 3:
            counts["error"] += 1
        elif severity == 2:
            counts["warning"] += 1
        else:
            counts["info"] += 1
        rule_id = item.get("rule_id", "?")
        rules[str(rule_id)] = rules.get(str(rule_id), 0) + 1
    top = sorted(rules.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {"status": "ok", **counts,
            "top_rules": [{"rule_id": rule_id, "count": count}
                          for rule_id, count in top]}


def _bpa(report: Path) -> dict:
    """Run pbir BPA; missing binary degrades to skipped, never failure."""
    if shutil.which("pbir") is None:
        return {"status": "skipped", "reason": "pbir not on PATH"}
    try:
        completed = subprocess.run(
            ["pbir", "bpa", "run", str(report), "-o", "json"],
            capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}
    try:
        payload = json.loads(completed.stdout)
    except ValueError as exc:
        return {"status": "blocked", "reason": f"bpa output is not JSON: {exc}"}
    return _summarize_bpa(payload)


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
               if args.skip_pbir else _pbir(args.report),
               "bpa": {"status": "skipped", "reason": "--skip-pbir"}
               if args.skip_pbir else _bpa(args.report)}
    empty = not rules
    pbir_bad = summary["pbir"]["status"] in ("error", "blocked")
    check_bad = check_summary["verdict"] != "pass"
    summary["verdict"] = "fail" if (empty or pbir_bad or check_bad) else "pass"
    text = json.dumps(summary, indent=2)
    if args.out is None:
        print(text)
    else:
        args.out.write_text(text + "\n", encoding="utf-8")
    if empty:
        return 2
    return 1 if (pbir_bad or check_bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
