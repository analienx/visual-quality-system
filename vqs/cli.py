"""Pre-alpha CLI: source inventory and evidence requests, never release approval."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import image_evidence, review_template
from .pbir import report_context


def _default_ledger() -> Path | None:
    """Locate roadmap/work_packages.json by searching upward from the CWD."""
    candidate = Path.cwd()
    for _ in range(12):
        ledger = candidate / "roadmap" / "work_packages.json"
        if ledger.is_file():
            return ledger
        if candidate.parent == candidate:
            return None
        candidate = candidate.parent
    return None


def _status(ledger: Path | None, format: str) -> int:
    """Print a read-only ledger snapshot; exit 2 when the ledger is invalid."""
    from vqs.ledger import summarize, validate

    path = ledger or _default_ledger()
    if path is None:
        print(json.dumps({"status": "blocked",
                          "reason": "No roadmap/work_packages.json found; pass --ledger"}))
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        errors = validate(data)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if errors:
        print(json.dumps({"status": "blocked", "findings": errors}, indent=2))
        return 2
    summary = summarize(data)
    if format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print(f"Independently verified: {summary['independently_verified']}/"
              f"{summary['initial_release_packages']} initial-release packages; "
              f"deferred: {summary['deferred']}.")
        print(f"Runnable by dependency only: {', '.join(summary['next_runnable']) or 'none'}.")
    return 0


def _check(facts_path: Path, run_root: Path, run_id: str | None) -> int:
    """Run the offline check pipeline; exit 0 pass, 1 fail, 2 blocked."""
    from vqs.pipeline import run_check

    try:
        facts = json.loads(facts_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    result = run_check(facts, run_root, run_id=run_id)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return {"pass": 0, "fail": 1, "blocked": 2}[result["verdict"]]


def _sealed_exit(result: dict) -> int:
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return {"pass": 0, "fail": 1, "blocked": 2}[result["verdict"]]


def _validate_plan(plan_path: Path, original: str, candidate_root: str,
                   approved: str | None, run_root: Path, run_id: str | None) -> int:
    """Validate a repair plan before any execution; issues fail, never pass."""
    from vqs.pipeline import seal_verdict
    from vqs.repair.allowlist import validate_plan

    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if not isinstance(plan, dict):
        print(json.dumps({"status": "blocked", "reason": "Plan document is not an object"}))
        return 2
    issues = validate_plan(plan, original, candidate_root,
                           approved_semantic_change=approved)
    verdict = "pass" if not issues else "fail"
    findings = [{"check": "plan", "status": verdict, "detail": {"issues": issues}}]
    return _sealed_exit(seal_verdict(run_root, run_id, "vqs.validate-plan/1",
                                     verdict, findings))


def _adjudicate_bundle(bundle_path: Path, run_root: Path, run_id: str | None) -> int:
    """Adjudicate a review bundle; static checks only, no pixel judgment."""
    from vqs.pipeline import seal_verdict
    from vqs.review.adjudicate import adjudicate_bundle

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if not isinstance(bundle, dict):
        print(json.dumps({"status": "blocked", "reason": "Bundle document is not an object"}))
        return 2
    decided = adjudicate_bundle(bundle)
    if decided["verdict"] == "pass":
        findings = [{"check": "bundle", "status": "pass", "detail": {}}]
    else:
        findings = [{"check": finding.get("rule", "?"),
                     "status": "fail" if finding.get("verdict") == "fail" else "blocked",
                     "detail": finding} for finding in decided["findings"]]
    return _sealed_exit(seal_verdict(run_root, run_id, "vqs.adjudicate-bundle/1",
                                     decided["verdict"], findings))


def _measure(report: Path, model: Path | None, out: Path | None) -> int:
    """Emit measured facts for a PBIR report; exit 2 when unreadable."""
    from vqs.powerbi.measure import measure_report

    try:
        facts = measure_report(str(report),
                               str(model) if model is not None else None)
    except OSError as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    text = json.dumps(facts, indent=2, ensure_ascii=False)
    if out is None:
        print(text)
    else:
        try:
            out.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"status": "blocked",
                              "reason": f"{type(exc).__name__}: {exc}"}))
            return 2
    return 0


def _doctor() -> int:
    """Print the capability report; always exit 0, never gate."""
    from vqs.doctor import report

    print(json.dumps(report(), indent=2, ensure_ascii=False))
    return 0


def _cycles(model: Path) -> int:
    """Run the static acyclicity gate; 0 acyclic, 1 cycles, 2 blocked."""
    from vqs.powerbi.cycles import check_model

    try:
        report = check_model(str(model))
    except OSError as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if not report.get("tables"):
        print("warning: no tables parsed; acyclic means nothing to "
              "check, not a clean bill", file=sys.stderr)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["acyclic"] else 1


def _capture(report: Path, renders: Path, pid: int | None, scale: int,
             wait_seconds: int) -> int:
    """Capture every page via Bridge; exit 2 with reason when blocked."""
    from vqs.capture import capture

    try:
        manifest = capture(str(report), str(renders), pid=pid,
                           scale=scale, wait_seconds=wait_seconds)
    except (OSError, LookupError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


def _verdict_exit(envelope: dict) -> int:
    """Print a tool envelope; exit 0/1/2 for pass/fail/blocked."""
    print(json.dumps(envelope, indent=2, ensure_ascii=False, default=str))
    return {"pass": 0, "fail": 1, "blocked": 2}[envelope["verdict"]]


def _tool_config(path: Path | None) -> tuple[dict, list[str]]:
    from vqs.config import load_config

    return load_config(path)


def _inspect(report: Path, model: Path | None, config_path: Path | None,
             out: Path | None) -> int:
    """Measure facts for a report; same engine as vqs_inspect."""
    from vqs.pipeline import blocked_envelope, inspect_report

    config, issues = _tool_config(config_path)
    if issues:
        return _verdict_exit(blocked_envelope("vqs.inspect", issues))
    envelope = inspect_report(str(report),
                              str(model) if model is not None else None,
                              config)
    if out is not None:
        try:
            out.write_text(json.dumps(envelope, indent=2,
                                      ensure_ascii=False) + chr(10),
                           encoding="utf-8")
        except OSError as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.inspect", [f"{type(exc).__name__}: {exc}"]))
        return {"pass": 0, "fail": 1, "blocked": 2}[envelope["verdict"]]
    return _verdict_exit(envelope)


def _review(args) -> int:
    """Review sources to a sealed verdict; same engine as vqs_review."""
    from vqs.pipeline import blocked_envelope, render_report, review_report

    config, issues = _tool_config(args.config)
    if issues:
        return _verdict_exit(blocked_envelope("vqs.review", issues))
    facts = None
    if args.facts is not None:
        try:
            facts = json.loads(args.facts.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.review", [f"{type(exc).__name__}: {exc}"]))
    envelope = review_report(
        report_dir=str(args.report) if args.report is not None else None,
        model_dir=str(args.model) if args.model is not None else None,
        facts=facts, scope=args.scope, state=args.state, config=config,
        run_root=str(args.run_root), run_id=args.run_id,
        resume_from=args.resume_from)
    if args.report_out is not None:
        try:
            args.report_out.write_text(render_report(envelope),
                                       encoding="utf-8")
        except OSError as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.review", [f"{type(exc).__name__}: {exc}"]))
    return _verdict_exit(envelope)


def _propose(run_root: Path, run_id: str) -> int:
    """Propose repairs for a run; blocked until the Task 6 engine."""
    from vqs.pipeline import propose_candidates

    return _verdict_exit(propose_candidates(str(run_root), run_id))


def _repair(plan: Path, original: str, candidate_root: str) -> int:
    """Validate a plan, then block: execution needs the Task 6 engine."""
    from vqs.pipeline import repair_candidate

    return _verdict_exit(repair_candidate(str(plan), original,
                                         candidate_root))


def _verify(args) -> int:
    """Verify a candidate; blocked until the Task 6 engine."""
    from vqs.pipeline import verify_candidate

    return _verdict_exit(verify_candidate(
        run_root=str(args.run_root) if args.run_root is not None else None,
        run_id=args.run_id, original=args.original,
        candidate=args.candidate))


def _run_status(run_root: Path, run_id: str) -> int:
    """Report a sealed run; same engine as vqs_run_status."""
    from vqs.pipeline import run_status_report

    return _verdict_exit(run_status_report(str(run_root), run_id))


def _mcp() -> int:
    """Launch the stdio MCP server on this process's stdio."""
    from vqs.mcp.server import serve

    return serve()


def _bundle(action: str, args) -> int:
    """Pack, verify, or unpack a review bundle; exit 2 when invalid."""
    from vqs.review.bundle import pack, unpack, verify

    try:
        if action == "pack":
            result = pack(args.report, args.renders, args.out, args.fixer_id)
        elif action == "verify":
            result = verify(args.bundle, args.report)
        else:
            result = unpack(args.bundle, args.dest)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vqs", description="Visual Quality System pre-alpha tools")
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory", help="Read PBIR definition and bindings; not design approval")
    inventory.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    measure = commands.add_parser("measure", help="Emit check-ready facts for a PBIR report")
    measure.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    measure.add_argument("--model", type=Path, default=None,
                         help="Optional *.SemanticModel definition folder")
    measure.add_argument("--out", type=Path, default=None,
                         help="Write facts JSON here instead of stdout")
    cycles = commands.add_parser("cycles", help="Static DAX/M acyclicity gate for a model")
    cycles.add_argument("model", type=Path,
                        help="*.SemanticModel definition folder")
    capture_cmd = commands.add_parser("capture", help="Bridge screenshots plus capture manifest")
    capture_cmd.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    capture_cmd.add_argument("renders", type=Path, help="Output directory for PNGs and manifest")
    capture_cmd.add_argument("--pid", type=int, default=None,
                             help="Target a specific PBIDesktop.exe process")
    capture_cmd.add_argument("--scale", type=int, default=2)
    capture_cmd.add_argument("--wait-seconds", type=int, default=60)
    bundle_cmd = commands.add_parser("bundle", help="Portable review evidence bundles")
    bundle_actions = bundle_cmd.add_subparsers(dest="bundle_action", required=True)
    pack_cmd = bundle_actions.add_parser("pack", help="Assemble a verified bundle")
    pack_cmd.add_argument("report", help="Enhanced-format *.Report folder")
    pack_cmd.add_argument("renders", help="Renders directory with capture manifest")
    pack_cmd.add_argument("out", help="Bundle output directory (must not exist)")
    pack_cmd.add_argument("--fixer-id", required=True)
    verify_cmd = bundle_actions.add_parser("verify", help="Re-hash and cross-check a bundle")
    verify_cmd.add_argument("bundle", help="Bundle directory")
    verify_cmd.add_argument("--report", default=None,
                            help="Live report folder to check staleness against")
    unpack_cmd = bundle_actions.add_parser("unpack", help="Copy a bundle and verify the copy")
    unpack_cmd.add_argument("bundle", help="Bundle directory")
    unpack_cmd.add_argument("dest", help="Destination directory (must not exist)")
    commands.add_parser("doctor", help="Report external tool capabilities; never installs")
    review = commands.add_parser("request-review", help="Require complete source-bound page images")
    review.add_argument("report", type=Path)
    review.add_argument("renders", type=Path)
    review.add_argument("--fixer-id", required=True)
    status = commands.add_parser("status", help="Read-only ledger snapshot; never modifies it")
    status.add_argument("--format", choices=("markdown", "json"), default="markdown")
    status.add_argument("--ledger", type=Path, default=None)
    check = commands.add_parser("check", help="Run measured facts to a sealed verdict")
    check.add_argument("facts", type=Path, help="JSON measured-facts document")
    check.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    check.add_argument("--run-id", default=None)
    plan_cmd = commands.add_parser("validate-plan", help="Validate a repair plan pre-execution")
    plan_cmd.add_argument("plan", type=Path, help="JSON repair-plan document")
    plan_cmd.add_argument("--original", required=True, help="Read-only original source path")
    plan_cmd.add_argument("--candidate-root", required=True, help="Disposable write root")
    plan_cmd.add_argument("--approve-change", default=None)
    plan_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    plan_cmd.add_argument("--run-id", default=None)
    bundle_cmd = commands.add_parser("adjudicate-bundle", help="Adjudicate a review bundle")
    bundle_cmd.add_argument("bundle", type=Path, help="JSON review-bundle document")
    bundle_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    bundle_cmd.add_argument("--run-id", default=None)
    inspect_cmd = commands.add_parser("inspect", help="Measure check-ready facts (tool vqs.inspect)")
    inspect_cmd.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    inspect_cmd.add_argument("--model", type=Path, default=None,
                             help="Optional *.SemanticModel definition folder")
    inspect_cmd.add_argument("--config", type=Path, default=None,
                             help="vqs.json project config (else ./vqs.json or defaults)")
    inspect_cmd.add_argument("--out", type=Path, default=None,
                             help="Write the envelope JSON here instead of stdout")
    review_cmd = commands.add_parser("review", help="Review sources to a sealed verdict (tool vqs.review)")
    review_cmd.add_argument("report", type=Path, nargs="?",
                            help="Enhanced-format *.Report folder (or --facts)")
    review_cmd.add_argument("--facts", type=Path, default=None,
                            help="JSON measured-facts document (or REPORT)")
    review_cmd.add_argument("--model", type=Path, default=None,
                            help="Optional *.SemanticModel definition folder")
    review_cmd.add_argument("--scope", default="static",
                            help="static, desktop, or release (engine validates)")
    review_cmd.add_argument("--state", default="default",
                            help="Saved state; must be in supported_states")
    review_cmd.add_argument("--config", type=Path, default=None,
                            help="vqs.json project config (else ./vqs.json or defaults)")
    review_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    review_cmd.add_argument("--run-id", default=None)
    review_cmd.add_argument("--resume-from", default=None,
                            help="Resume after revalidating sealed provenance")
    review_cmd.add_argument("--report-out", type=Path, default=None,
                            help="Write a readable local report here")
    propose_cmd = commands.add_parser("propose", help="Propose repairs for a run (tool vqs.propose)")
    propose_cmd.add_argument("--run-root", type=Path, required=True)
    propose_cmd.add_argument("--run-id", required=True)
    repair_cmd = commands.add_parser("repair", help="Validate then apply a repair plan (tool vqs.repair)")
    repair_cmd.add_argument("plan", type=Path, help="JSON repair-plan document")
    repair_cmd.add_argument("--original", required=True, help="Read-only original source path")
    repair_cmd.add_argument("--candidate-root", required=True, help="Disposable write root")
    verify_cmd = commands.add_parser("verify", help="Verify a candidate (tool vqs.verify)")
    verify_cmd.add_argument("--run-root", type=Path, default=None)
    verify_cmd.add_argument("--run-id", default=None)
    verify_cmd.add_argument("--original", default=None)
    verify_cmd.add_argument("--candidate", default=None)
    run_status_cmd = commands.add_parser("run-status", help="Report a sealed run (tool vqs.run_status)")
    run_status_cmd.add_argument("run_root", type=Path)
    run_status_cmd.add_argument("run_id")
    commands.add_parser("mcp", help="Launch the stdio MCP server (tools vqs_*)")
    args = parser.parse_args(argv)
    if args.command == "measure":
        return _measure(args.report, args.model, args.out)
    if args.command == "cycles":
        return _cycles(args.model)
    if args.command == "capture":
        return _capture(args.report, args.renders, args.pid, args.scale,
                        args.wait_seconds)
    if args.command == "bundle":
        return _bundle(args.bundle_action, args)
    if args.command == "doctor":
        return _doctor()
    if args.command == "status":
        return _status(args.ledger, args.format)
    if args.command == "check":
        return _check(args.facts, args.run_root, args.run_id)
    if args.command == "validate-plan":
        return _validate_plan(args.plan, args.original, args.candidate_root,
                              args.approve_change, args.run_root, args.run_id)
    if args.command == "adjudicate-bundle":
        return _adjudicate_bundle(args.bundle, args.run_root, args.run_id)
    if args.command == "inspect":
        return _inspect(args.report, args.model, args.config, args.out)
    if args.command == "review":
        return _review(args)
    if args.command == "propose":
        return _propose(args.run_root, args.run_id)
    if args.command == "repair":
        return _repair(args.plan, args.original, args.candidate_root)
    if args.command == "verify":
        return _verify(args)
    if args.command == "run-status":
        return _run_status(args.run_root, args.run_id)
    if args.command == "mcp":
        return _mcp()
    try:
        info = report_context(args.report)
        if args.command == "inventory":
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0
        manifest = json.loads((args.renders / "capture-manifest.json").read_text(encoding="utf-8-sig"))
        mapping = manifest.get("page_images")
        expected = [page["id"] for page in info["pages"]]
        if (not isinstance(mapping, dict) or set(mapping) != set(expected) or
                any(not isinstance(name, str) or Path(name).name != name or
                    not name.endswith(".png") for name in mapping.values()) or
                len(set(mapping.values())) != len(expected)):
            raise ValueError("Manifest requires a unique page_images entry for every PBIR page ID")
        ordered_files = [mapping[page_id] for page_id in expected]
        pages, issues = image_evidence(args.renders, info["source_sha256"], ordered_files)
        if issues or len(pages) != len(expected):
            print(json.dumps({"status": "blocked", "findings": issues,
                              "reason": "Fresh complete source-bound page renders required"}, indent=2))
            return 2
        for page, page_id in zip(pages, expected, strict=True):
            page["id"] = page_id
            page["visual_inventory"] = [{"id": visual["visual_id"]} for visual in
                                        next(p for p in info["pages"] if p["id"] == page_id)["visuals"]]
        template = review_template("report", info["source_sha256"], pages,
                                     args.fixer_id,
                                     calibration=manifest.get("calibration"),
                                     data_readiness=manifest.get("data_readiness"))
        print(json.dumps(template, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
