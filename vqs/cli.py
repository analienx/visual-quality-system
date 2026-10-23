"""Pre-alpha CLI: source inventory and evidence requests, never release approval."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .evidence import image_evidence, review_template
from .install import package_version
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
    inputs = {"actual": plan,
              "identities": {"original": original,
                             "candidate_root": candidate_root,
                             "approved": approved}}
    return _sealed_exit(seal_verdict(run_root, run_id, "vqs.validate-plan/1",
                                     verdict, findings, inputs=inputs))


def _adjudicate_bundle(bundle_path: Path, run_root: Path, run_id: str | None,
                       transport: Path | None = None,
                       report: Path | None = None) -> int:
    """Adjudicate a review bundle; static checks only, no pixel judgment.

    T09: with --transport-bundle, the transport dir is verified first
    and its authoritative header inventory binds the form: a
    caller-edited source_pages list cannot certify completeness.
    R6-DEC-05/06: the whole verified authority object (render
    bindings, calibration, fixer, bundle identity) is forwarded —
    no field dropping — and --report offers a live inventory
    authority instead. With both, the transport is also staleness-
    bound to the live report. Without either, coverage is unbound
    (blocked): the self-declared list is never trusted.
    """
    from vqs.pipeline import seal_verdict
    from vqs.review.adjudicate import adjudicate_bundle
    from vqs.review.bundle import verify

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if not isinstance(bundle, dict):
        print(json.dumps({"status": "blocked", "reason": "Bundle document is not an object"}))
        return 2
    authority = None
    if transport is not None:
        try:
            checked = verify(str(transport),
                             str(report) if report is not None else None)
        except (OSError, ValueError, TypeError) as exc:
            print(json.dumps({"status": "blocked",
                              "reason": f"Transport invalid: {exc}"}))
            return 2
        authority = checked
    elif report is not None:
        from vqs.pbir import report_context, source_digest

        try:
            info = report_context(report)
            digest = source_digest(report)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({"status": "blocked",
                              "reason": f"Report unreadable: {exc}"}))
            return 2
        authority = {"authority": "live-report/1",
                     "pages": [page["id"] for page in info["pages"]],
                     "source_sha256": digest}
    decided = adjudicate_bundle(bundle, authority)
    if decided["verdict"] == "pass":
        findings = [{"check": "bundle", "status": "pass", "detail": {}}]
    else:
        findings = [{"check": finding.get("rule", "?"),
                     "status": "fail" if finding.get("verdict") == "fail" else "blocked",
                     "detail": finding} for finding in decided["findings"]]
    inputs = {"actual": bundle, "identities": {}}
    return _sealed_exit(seal_verdict(run_root, run_id, "vqs.adjudicate-bundle/1",
                                     decided["verdict"], findings,
                                     inputs=inputs))


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


def _triage(args) -> int:
    """Show actionable source-backed findings with a single command."""
    from vqs.triage import analyze, markdown

    result = analyze(
        str(args.report), str(args.model) if args.model else None,
        run_root=str(args.run_root), run_id=args.run_id)
    if args.plan_out is not None:
        plan = result.get("plan")
        if plan is None:
            print("No safely synthesized typed repair plan.", file=sys.stderr)
        else:
            try:
                args.plan_out.write_text(
                    json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
            except OSError as exc:
                print(f"Cannot save plan: {exc}", file=sys.stderr)
                return 2
    data = (json.dumps(result, indent=2, ensure_ascii=False)
            if args.format == "json" else markdown(result))
    if args.out is None:
        print(data)
    else:
        try:
            args.out.write_text(data + ("" if data.endswith("\n") else "\n"),
                                encoding="utf-8")
        except OSError as exc:
            print(f"Cannot save triage: {exc}", file=sys.stderr)
            return 2
    return 2 if result["status"] == "blocked" else 0


def _premium(args) -> int:
    """Read-only premium-design preflight, never a release verdict."""
    from vqs.pbir import report_context
    from vqs.premium import audit, contract_template, markdown
    from vqs.triage import _report_input

    try:
        report, _model = _report_input(str(args.report), None)
        if args.init_contract is not None:
            template = contract_template(report_context(Path(report)))
            # Contract is owned by the caller; never overwrite existing intent.
            with args.init_contract.open("x", encoding="utf-8") as handle:
                json.dump(template, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            print(f"Design-intent template: {args.init_contract}")
            return 0
        policy = (json.loads(args.contract.read_text(encoding="utf-8-sig"))
                  if args.contract is not None else None)
        result = audit(str(args.report), contract=policy)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    output = (json.dumps(result, indent=2, ensure_ascii=False)
              if args.format == "json" else markdown(result))
    if args.out is not None:
        try:
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(output + ("" if output.endswith("\n") else "\n"))
        except OSError as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc)}))
            return 2
    else:
        print(output)
    return 1 if result["findings"] else 0


def _doctor() -> int:
    """Print the capability report; always exit 0, never gate."""
    from vqs.doctor import report

    print(json.dumps(report(), indent=2, ensure_ascii=False))
    return 0


def _cycles(model: Path) -> int:
    """Run the static acyclicity gate; 0 acyclic, 1 cycles, 2 blocked."""
    from vqs.powerbi.cycles import ModelingError, check_model

    try:
        report = check_model(str(model))
    except (OSError, ModelingError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    if not report.get("tables"):
        print("warning: no tables parsed; acyclic means nothing to "
              "check, not a clean bill", file=sys.stderr)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["acyclic"] else 1


def _capture(report: Path, renders: Path, pid: int | None, scale: int,
             wait_seconds: int, live_data: bool = False) -> int:
    """Capture every page via Bridge; exit 2 with reason when blocked."""
    from vqs.capture import capture

    try:
        manifest = capture(str(report), str(renders), pid=pid,
                           scale=scale, wait_seconds=wait_seconds,
                           live_data=live_data)
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


def _propose(run_root: Path, run_id: str, facts_path: Path | None,
             out: Path | None) -> int:
    """Triage a sealed review run into plan-eligible work items.

    Optional ``--facts`` supplies the measured-facts document the run
    sealed; its digest must match or the run blocks as stale. Optional
    ``--out`` writes the synthesized plan document (for ``vqs repair``);
    with no synthesizable candidate the run refuses instead of writing
    a plan-shaped file.
    """
    from vqs.pipeline import blocked_envelope, propose_candidates

    facts = None
    if facts_path is not None:
        try:
            facts = json.loads(facts_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.propose", [f"unreadable facts file: {exc}"]))
        if not isinstance(facts, dict):
            return _verdict_exit(blocked_envelope(
                "vqs.propose", ["facts file is not an object"]))
    envelope = propose_candidates(str(run_root), run_id, facts)
    if envelope.get("verdict") != "pass":
        return _verdict_exit(envelope)
    if out is not None:
        plan = envelope.get("plan")
        if not isinstance(plan, dict):
            return _verdict_exit(blocked_envelope(
                "vqs.propose",
                [("no synthesizable candidates; decisions are in the "
                  "triage envelope, not a plan file")],
                run_id=run_id,
                run_dir=envelope.get("run_dir")))
        try:
            out.write_text(json.dumps(plan, indent=2,
                                      ensure_ascii=False) + chr(10),
                           encoding="utf-8")
        except OSError as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.propose", [f"{type(exc).__name__}: {exc}"],
                run_id=run_id,
                run_dir=envelope.get("run_dir")))
    return _verdict_exit(envelope)


def _repair(args) -> int:
    """Validate a plan, execute it, and seal the repair run."""
    from vqs.pipeline import repair_candidate

    return _verdict_exit(repair_candidate(
        str(args.plan), args.original, args.candidate_root,
        run_root=str(args.run_root), run_id=args.run_id,
        authoring_backend=args.authoring_backend,
        authoring_assurance=args.authoring_assurance,
        authoring_timeout=args.authoring_timeout,
        authoring_allow_warnings=args.authoring_allow_warnings))


def _verify(args) -> int:
    """Verify a candidate against declared edits (same engine as MCP)."""
    import json

    from vqs.pipeline import blocked_envelope, verify_candidate

    edits = None
    if args.edits is not None:
        try:
            doc = json.loads(Path(args.edits).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.verify", [f"unreadable edits file: {exc}"]))
        edits = doc.get("edits") if isinstance(doc, dict) else doc
    approvals = None
    if args.approved_removals:
        approvals = [p.strip() for p in args.approved_removals.split(",")]
        approvals = [p for p in approvals if p]
    return _verdict_exit(verify_candidate(
        run_root=str(args.run_root) if args.run_root is not None else None,
        run_id=args.run_id, original=args.original,
        candidate=args.candidate, edits=edits,
        approved_removals=approvals))


def _verify_runtime(args) -> int:
    """Verify a sealed candidate live in Desktop (tool vqs.verify-runtime)."""
    from vqs.pipeline import verify_runtime

    return _verdict_exit(verify_runtime(
        run_root=str(args.run_root), run_id=args.run_id, pid=args.pid,
        scale=args.scale, wait_seconds=args.wait_seconds,
        reload_first=not args.no_reload,
        runtime_run_id=args.runtime_run_id, live_data=args.live_data))


def _promote(args) -> int:
    """Promote a verified candidate with owner approval (tool vqs.promote)."""
    from vqs.pipeline import promote_candidate

    return _verdict_exit(promote_candidate(
        run_root=str(args.run_root), run_id=args.run_id,
        owner_approval=args.owner_approval,
        runtime_run_id=args.runtime_run_id,
        backup_dir=(str(args.backup_dir)
                    if args.backup_dir is not None else None),
        desktop_recheck=not args.no_desktop_recheck,
        promote_run_id=args.promote_run_id,
        scope=args.scope))


def _run_status(run_root: Path, run_id: str) -> int:
    """Report a sealed run; same engine as vqs_run_status."""
    from vqs.pipeline import run_status_report

    return _verdict_exit(run_status_report(str(run_root), run_id))


def _run(args) -> int:
    """Run the orchestrated Power BI workflow; same engine as vqs_run."""
    from vqs.coordinator import run_workflow
    from vqs.pipeline import blocked_envelope

    config, issues = _tool_config(args.config)
    if issues:
        return _verdict_exit(blocked_envelope("vqs.run", issues))
    facts = None
    if args.facts is not None:
        try:
            facts = json.loads(args.facts.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.run", [f"unreadable facts file: {exc}"]))
        if not isinstance(facts, dict):
            return _verdict_exit(blocked_envelope(
                "vqs.run", ["facts file is not an object"]))
    envelope = run_workflow(
        report_dir=str(args.report) if args.report is not None else None,
        model_dir=str(args.model) if args.model is not None else None,
        facts=facts, mode=args.mode, scope=args.scope, config=config,
        run_root=str(args.run_root), run_id=args.run_id,
        resume_from=args.resume_from,
        candidate_root=(str(args.candidate_root)
                        if args.candidate_root is not None else None),
        renders_dir=(str(args.renders_dir)
                     if args.renders_dir is not None else None),
        plan_path=str(args.plan) if args.plan is not None else None,
        fixer_id=args.fixer_id, pid=args.pid,
        authoring_backend=args.authoring_backend,
        live_answers=args.live_answers, reviewer=args.reviewer)
    if args.report_out is not None:
        try:
            args.report_out.write_text(
                json.dumps(envelope, indent=2, ensure_ascii=False,
                           default=str) + chr(10), encoding="utf-8")
        except OSError as exc:
            return _verdict_exit(blocked_envelope(
                "vqs.run", [f"{type(exc).__name__}: {exc}"]))
    return _verdict_exit(envelope)


def _compare_authoring(args) -> int:
    """Read-only baseline-versus-candidate Microsoft diagnostic comparison."""
    from vqs.powerbi.author.compare import compare_authoring

    try:
        result = compare_authoring(
            args.baseline_report, args.candidate_report, args.visual)
        if args.out is not None:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, indent=2,
                                        ensure_ascii=False) + "\n")
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _preview_candidate(args) -> int:
    """One action to prepare a private, populated full-project Desktop preview.

    Produces a complete, run-owned candidate PBIP; does not open Desktop,
    claim live data readiness, publish data, or approve the report.
    """
    from .repair.preview import (
        PreviewMaterializationError,
        materialize_populated_preview,
    )

    try:
        result = materialize_populated_preview(
            args.source_pbip, args.typed_candidate_report,
            args.private_out, args.visual)
    except (PreviewMaterializationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


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


def _review_images(args) -> int:
    """Run an external image reviewer, never mint release authority."""
    from vqs.review.bundle import verify
    from vqs.review.port import ReviewError, resolve_reviewer, review_bundle

    if not args.allow_remote_images:
        print(json.dumps({"status": "blocked",
                          "reason": "external vision upload requires explicit "
                                    "--allow-remote-images consent"}))
        return 2
    if args.out is not None and args.out.exists():
        print(json.dumps({"status": "blocked",
                          "reason": "refusing to overwrite existing reviewer output"}))
        return 2
    previous = os.environ.get("VQS_ALLOW_VISION_UPLOAD")
    try:
        authority = verify(str(args.bundle), str(args.report) if args.report else None)
        reviewer, reviewer_id = resolve_reviewer(args.reviewer)
        if reviewer is None or reviewer_id is None:
            raise ReviewError("reviewer capability is required")
        os.environ["VQS_ALLOW_VISION_UPLOAD"] = "1"
        result = review_bundle(
            bundle_dir=str(args.bundle),
            reviewer=reviewer, reviewer_id=reviewer_id,
            fixer_id=authority["fixer_id"])
        output = {"status": "reviewed", "advisory": True,
                  "release_authority": False, **result}
        rendered = json.dumps(output, indent=2, ensure_ascii=False)
        if args.out is not None:
            args.out.write_text(rendered + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, ReviewError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    finally:
        if previous is None:
            os.environ.pop("VQS_ALLOW_VISION_UPLOAD", None)
        else:
            os.environ["VQS_ALLOW_VISION_UPLOAD"] = previous
    print(rendered)
    return {"pass": 0, "fail": 1, "blocked": 2}[result["visual"]]


def _regions(args) -> int:
    """Produce/read source-verified visual crops and bounded pixel QA facts."""
    from vqs.visual.regions import RegionError, build_regions, verify_regions

    try:
        if args.region_action == "audit":
            from vqs.visual.pixel_quality import audit_regions

            policy = (json.loads(args.policy.read_text(encoding="utf-8"))
                      if args.policy is not None else None)
            output = audit_regions(
                str(args.bundle), str(args.output), policy=policy,
                report=str(args.report) if args.report else None)
        elif args.region_action == "verify":
            output = verify_regions(
                str(args.bundle), str(args.output),
                report=str(args.report) if args.report else None)
        elif args.region_action == "plan":
            from vqs.review.bundle import verify as verify_bundle
            from vqs.visual.coverage import coverage_index
            from vqs.visual.layout_graph import page_graph
            from vqs.visual.regions import _inventory
            from vqs.visual.risk import route_signals

            if (args.output.exists() or args.output.is_symlink()
                    or args.output.parent.is_symlink()):
                raise RegionError("refusing existing or symlinked routing plan")
            authority = verify_bundle(
                str(args.bundle),
                str(args.report) if args.report else None)
            inv = _inventory(args.bundle.resolve())
            if inv.get("source_sha256") != authority["source_sha256"]:
                raise RegionError("routing inventory changed from bundle")
            graphs = [page_graph(page) for page in inv["pages"]]
            risks = [route_signals(graph) for graph in graphs]
            coverage = coverage_index(graphs, risks)
            output = {
                "schema": "vqs.visual-routing-evidence/1",
                "source_sha256": authority["source_sha256"],
                "bundle_sha256": authority["bundle_sha256"],
                "review_image_basis": authority["review_image_basis"],
                "page_graphs": graphs,
                "page_risks": risks,
                "coverage": coverage,
                "advisory": True,
                "visual_verdict": "not_run",
            }
            # x mode is exclusive: never overwrite a file created
            # between the path check and open.
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(output, indent=2,
                                        ensure_ascii=False) + "\n")
            output = {"status": "planned", "pages": len(graphs),
                      "visuals": sum(len(g["nodes"]) for g in graphs),
                      "risk_candidates": sum(len(r["signals"]) for r in risks),
                      "routing_index": str(args.output)}
        else:
            selectors = None
            if args.target:
                selectors = []
                for item in args.target:
                    if item.count("/") != 1 or any(
                            not fragment for fragment in item.split("/")):
                        raise RegionError(
                            "target must be exact PAGE_ID/VISUAL_ID")
                    selectors.append(tuple(item.split("/", 1)))
            output = build_regions(
                str(args.bundle), str(args.output), selectors=selectors,
                padding_px=args.padding_px,
                report=str(args.report) if args.report else None)
            output = {"status": "created",
                      "regions": len(output["regions"]),
                      "source_sha256": output["source_sha256"],
                      "bundle_sha256": output["bundle_sha256"],
                      "regions_index": str(args.output / "regions.json")}
    except (RegionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(output, indent=2))
    if args.region_action == "audit":
        return {"fail": 1, "unknown": 2,
                "review_required": 0, "no_pixel_issue_proven": 0}[output["status"]]
    return 0


def _assurance(args) -> int:
    """Re-execute exact pixel QA and expose missing independent release proof."""
    from vqs.quality_assurance import assess_report_readiness

    if args.out is not None and (args.out.exists() or args.out.is_symlink()):
        print(json.dumps({"status": "blocked", "reason": "refusing existing output"}))
        return 2
    try:
        policy = (json.loads(args.policy.read_text(encoding="utf-8"))
                  if args.policy else None)
        oracle = (json.loads(args.oracle.read_text(encoding="utf-8"))
                  if args.oracle else None)
        trace = (json.loads(args.trace.read_text(encoding="utf-8"))
                 if args.trace else None)
        output = assess_report_readiness(
            str(args.bundle), str(args.regions), report=str(args.report),
            pages=args.page, policy=policy, oracle=oracle, trace=trace,
            captures_dir=str(args.captures) if args.captures else None,
            release_scope=args.release_scope)
        result = json.dumps(output, indent=2, ensure_ascii=False)
        if args.out is not None:
            with args.out.open("x", encoding="utf-8") as handle:
                handle.write(result + "\n")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked",
                          "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(result)
    return 1 if output["verdict"] == "fail" else 2


def _write_theme_out(out: Path | None, payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


def _theme(args: argparse.Namespace) -> int:
    """Adaptive theme engine (issue #80); candidate-only writes."""
    from .theme import (
        ThemeError,
        apply_theme,
        audit_candidate,
        inspect_report,
        load_palette,
        palette_contrast_check,
        preview_plan,
    )

    try:
        if args.theme_action == "inspect":
            payload = inspect_report(args.report)
            _write_theme_out(args.out, payload)
            return 0
        if args.theme_action == "audit":
            payload = audit_candidate(args.candidate)
            _write_theme_out(args.out, payload)
            return {"pass": 0, "fail": 1, "unknown": 2}[payload["status"]]
        palette = load_palette(args.mode, args.palette)
        violations = palette_contrast_check(palette)
        if violations:
            payload = {"status": "blocked", "command": args.theme_action,
                       "mode": args.mode,
                       "reason": "palette contrast check failed",
                       "violations": violations}
            _write_theme_out(args.out, payload)
            return 2
        if args.theme_action == "preview":
            payload = preview_plan(args.report, args.mode, palette)
            _write_theme_out(args.out, payload)
            return 0
        if args.theme_action == "apply":
            payload = apply_theme(args.report, args.mode, palette,
                                  args.candidate_root)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0
        print(json.dumps({"status": "blocked",
                          "reason": f"unknown theme action {args.theme_action}"}))
        return 2
    except (ThemeError, OSError, ValueError, KeyError, TypeError) as exc:
        payload = {"status": "blocked",
                   "reason": f"{type(exc).__name__}: {exc}"}
        out = getattr(args, "out", None)
        if out is not None:
            try:
                _write_theme_out(out, payload)
            except OSError:
                print(json.dumps(payload))
        else:
            print(json.dumps(payload))
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vqs", description="Visual Quality System pre-alpha tools")
    parser.add_argument("--version", action="version",
                        version=f"vqs {package_version() or 'unknown'}")
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory", help="Read PBIR definition and bindings; not design approval")
    inventory.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    theme_cmd = commands.add_parser(
        "theme", help="Adaptive Light/Dark theme engine (candidate-only)")
    theme_actions = theme_cmd.add_subparsers(dest="theme_action", required=True)
    theme_inspect = theme_actions.add_parser("inspect", help="Classify every color occurrence")
    theme_inspect.add_argument("report", type=Path, help="*.Report folder or .pbip")
    theme_inspect.add_argument("--out", type=Path, default=None)
    theme_preview = theme_actions.add_parser("preview", help="Read-only re-theme plan")
    theme_preview.add_argument("report", type=Path, help="*.Report folder or .pbip")
    theme_preview.add_argument("--mode", choices=("light", "dark"), required=True)
    theme_preview.add_argument("--palette", type=Path, default=None)
    theme_preview.add_argument("--out", type=Path, default=None)
    theme_apply = theme_actions.add_parser("apply", help="Write a themed candidate project")
    theme_apply.add_argument("report", type=Path, help="*.Report folder or .pbip")
    theme_apply.add_argument("--mode", choices=("light", "dark"), required=True)
    theme_apply.add_argument("--palette", type=Path, default=None)
    theme_apply.add_argument("--candidate-root", type=Path, required=True)
    theme_audit = theme_actions.add_parser("audit", help="Audit a themed candidate")
    theme_audit.add_argument("candidate", type=Path, help="Candidate project, .pbip, or *.Report")
    theme_audit.add_argument("--out", type=Path, default=None)
    triage = commands.add_parser(
        "triage", help="One-command prioritized report diagnosis and repair suggestions")
    triage.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    triage.add_argument("--model", type=Path, default=None,
                        help="Optional semantic model definition path")
    triage.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    triage.add_argument("--run-id", default=None)
    triage.add_argument("--format", choices=("markdown", "json"), default="markdown")
    triage.add_argument("--out", type=Path, default=None)
    triage.add_argument("--plan-out", type=Path, default=None,
                        help="Export source-bound typed repair plan if synthesizable")
    premium = commands.add_parser(
        "premium", help="Source-bound design intent, spacing, title hierarchy and top-three improvements (advisory)")
    premium.add_argument("report", type=Path, help="Enhanced-format .pbip or *.Report folder")
    policy = premium.add_mutually_exclusive_group()
    policy.add_argument("--contract", type=Path,
                        help="Owner-authored source-bound design intent JSON")
    policy.add_argument("--init-contract", type=Path,
                        help="Create a new, unapproved design-intent template; never overwrites")
    premium.add_argument("--format", choices=("markdown", "json"), default="markdown")
    premium.add_argument("--out", type=Path, default=None,
                         help="Write the advisory report to a new file")
    measure = commands.add_parser("measure", help="Emit check-ready facts for a PBIR report")
    measure.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    measure.add_argument("--model", type=Path, default=None,
                         help="Optional *.SemanticModel definition folder")
    measure.add_argument("--out", type=Path, default=None,
                         help="Write facts JSON here instead of stdout")
    cycles = commands.add_parser("cycles", help="Static DAX/M acyclicity gate for a model")
    cycles.add_argument("model", type=Path,
                        help="*.SemanticModel definition folder")
    preview_cmd = commands.add_parser(
        "prepare-preview",
        help="Private complete PBIP candidate with local model cache for Desktop review")
    preview_cmd.add_argument("source_pbip", type=Path,
                             help="Read-only complete source .pbip")
    preview_cmd.add_argument("typed_candidate_report", type=Path,
                             help="Disposable, typed-edited *.Report folder")
    preview_cmd.add_argument("private_out", type=Path,
                             help="New private output root OUTSIDE every Git checkout")
    preview_cmd.add_argument("--visual", action="append", required=True,
                             help="Exact changed relative PBIR visual.json path; repeat")
    compare_cmd = commands.add_parser(
        "compare-authoring",
        help="Read-only paired Microsoft diagnostics; never implies release PASS")
    compare_cmd.add_argument("baseline_report", type=Path)
    compare_cmd.add_argument("candidate_report", type=Path)
    compare_cmd.add_argument("--visual", action="append", required=True,
                             help="Exact PBIR visual.json file changed; repeat")
    compare_cmd.add_argument("--out", type=Path, default=None,
                             help="New private receipt file; refuses overwrite")
    capture_cmd = commands.add_parser("capture", help="Bridge screenshots plus capture manifest")
    capture_cmd.add_argument("report", type=Path, help="Enhanced-format *.Report folder")
    capture_cmd.add_argument("renders", type=Path, help="Output directory for PNGs and manifest")
    capture_cmd.add_argument("--pid", type=int, default=None,
                             help="Target a specific PBIDesktop.exe process")
    capture_cmd.add_argument("--scale", type=int, default=2)
    capture_cmd.add_argument("--wait-seconds", type=int, default=60)
    capture_cmd.add_argument("--live-data", action="store_true",
                             help="Prove populated Microsoft Modeling MCP data "
                                  "on exact Desktop PID (run-owned clones "
                                  "get a transient warm-up render)")
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
    images_cmd = commands.add_parser(
        "review-images",
        help="Advisory independent screenshot review; not release approval")
    images_cmd.add_argument("bundle", type=Path,
                            help="Verified private image bundle")
    images_cmd.add_argument("--reviewer", default="vqs.review.muse:muse_reviewer",
                            help="Independent reviewer provider module:object")
    images_cmd.add_argument("--allow-remote-images", action="store_true",
                            help="Explicitly allow image upload to external model provider")
    images_cmd.add_argument("--report", type=Path, default=None,
                            help="Optional exact source report for staleness check")
    images_cmd.add_argument("--out", type=Path, default=None,
                            help="Write private JSON findings; refuses overwrite")
    regions_cmd = commands.add_parser(
        "regions", help="Derive/verify pixel-exact PBIR-bound visual crop sidecars")
    regions_cmd.add_argument("region_action", choices=("build", "verify", "plan", "audit"))
    regions_cmd.add_argument("bundle", type=Path,
                             help="Existing complete verified review bundle")
    regions_cmd.add_argument("output", type=Path,
                             help="Private derived region directory")
    regions_cmd.add_argument("--report", type=Path, default=None,
                             help="Optional source revision staleness check")
    regions_cmd.add_argument("--target", action="append", default=None,
                             help="Select exact PAGE_ID/VISUAL_ID (repeatable)")
    regions_cmd.add_argument("--padding-px", type=int, default=16,
                             help="Pixel context outside visual bounds, max 128")
    regions_cmd.add_argument("--policy", type=Path, default=None,
                             help="For audit: exact source/bundle-bound content budgets")
    assurance_cmd = commands.add_parser(
        "assurance", help="Recheck full visual crop coverage, pixel quality and UI evidence")
    assurance_cmd.add_argument("bundle", type=Path,
                               help="Verified canvas review bundle")
    assurance_cmd.add_argument("regions", type=Path,
                               help="Pixel-exact source-bound visual sidecar")
    assurance_cmd.add_argument("--report", type=Path, required=True,
                               help="Current report source; never optional")
    assurance_cmd.add_argument("--release-scope", choices=("powerbi-core", "combined"),
                               default="powerbi-core",
                               help="Primary Power BI-only evidence or legacy combined release")
    assurance_cmd.add_argument("--page", action="append", default=None,
                               help="Require coverage of selected page(s), else all")
    assurance_cmd.add_argument("--policy", type=Path, default=None,
                               help="Exact source/bundle-bound pixel policy")
    assurance_cmd.add_argument("--oracle", type=Path, default=None,
                               help="Live current-source All/2023/2024/2025 DAX receipt")
    assurance_cmd.add_argument("--trace", type=Path, default=None,
                               help="Recorded eight-step Desktop UI observations")
    assurance_cmd.add_argument("--captures", type=Path, default=None,
                               help="Private exact screenshot files backing the trace")
    assurance_cmd.add_argument("--out", type=Path, default=None,
                               help="Write private JSON readiness; refuses overwrite")
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
    bundle_cmd.add_argument("--transport-bundle", type=Path, default=None,
                            help="Verified transport bundle dir: its render "
                                 "bindings, calibration, fixer, and inventory "
                                 "bind the form (with --report, also "
                                 "staleness-checked against it)")
    bundle_cmd.add_argument("--report", type=Path, default=None,
                            help="Live *.Report folder as the completeness "
                                 "authority (without either authority, "
                                 "coverage is unbound; with both, the "
                                 "transport is also staleness-checked "
                                 "against it)")
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
    propose_cmd.add_argument("--facts", type=Path, default=None,
                             help="Measured-facts JSON the run sealed; "
                                  "digest must match or the run blocks "
                                  "as stale (enables candidate synthesis)")
    propose_cmd.add_argument("--out", type=Path, default=None,
                             help="Write the synthesized plan document "
                                  "here for vqs repair; refused when no "
                                  "candidate was synthesizable")
    repair_cmd = commands.add_parser("repair", help="Validate then apply a repair plan (tool vqs.repair)")
    repair_cmd.add_argument("plan", type=Path, help="JSON repair-plan document")
    repair_cmd.add_argument("--original", required=True, help="Read-only original source path")
    repair_cmd.add_argument("--candidate-root", required=True, help="Disposable write root")
    repair_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    repair_cmd.add_argument("--run-id", default=None)
    repair_cmd.add_argument("--authoring-backend",
                            choices=("auto", "microsoft", "direct"),
                            default="auto",
                            help="Candidate validation route: Microsoft "
                                 "powerbi-report-author CLI when probed "
                                 "available (auto), always (microsoft), or "
                                 "the explicit direct typed-writer fallback "
                                 "(direct). Microsoft failures never fall "
                                 "back silently.")
    repair_cmd.add_argument("--authoring-assurance",
                            choices=("portable", "production"),
                            default="portable",
                            help=("portable preserves isolated fixture compatibility; "
                                  "production requires approved Microsoft validation "
                                  "and blocks blanket warning waivers"))
    repair_cmd.add_argument("--authoring-timeout", type=int, default=300,
                            help="Seconds for Microsoft validation (default 300)")
    repair_cmd.add_argument("--authoring-allow-warnings", action="store_true",
                            help="Pass despite Microsoft validation warnings "
                                 "(recorded verbatim; default blocks)")
    verify_cmd = commands.add_parser("verify", help="Verify a candidate (tool vqs.verify)")
    verify_cmd.add_argument("--run-root", type=Path, default=None)
    verify_cmd.add_argument("--run-id", default=None)
    verify_cmd.add_argument("--original", default=None)
    verify_cmd.add_argument("--candidate", default=None)
    verify_cmd.add_argument("--edits", type=Path, default=None,
                            help="JSON edits list (or a repair run's repairs.json)")
    verify_cmd.add_argument("--approved-removals", default=None,
                            help="Comma-separated owner-approved page/visual pairs")
    runtime_cmd = commands.add_parser("verify-runtime", help="Verify a sealed candidate live in Desktop (tool vqs.verify-runtime)")
    runtime_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    runtime_cmd.add_argument("--run-id", required=True,
                             help="Sealed completed vqs.repair run id")
    runtime_cmd.add_argument("--pid", type=int, default=None,
                             help="Desktop PID holding the disposable candidate")
    runtime_cmd.add_argument("--scale", type=int, default=2)
    runtime_cmd.add_argument("--live-data", action="store_true",
                             help="Require model-bound populated data evidence "
                                  "with a run-owned warm-up when appropriate")
    runtime_cmd.add_argument("--wait-seconds", type=int, default=60)
    runtime_cmd.add_argument("--no-reload", action="store_true",
                             help="Skip the candidate reload before capture")
    runtime_cmd.add_argument("--runtime-run-id", default=None,
                             help="Sealed id for the runtime run (else generated)")
    promote_cmd = commands.add_parser("promote", help="Promote a verified candidate with owner approval (tool vqs.promote)")
    promote_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    promote_cmd.add_argument("--run-id", required=True,
                             help="Sealed completed vqs.repair run id")
    promote_cmd.add_argument("--owner-approval", required=True,
                             help="Owner consent string (identity and "
                                  "reason); recorded as consent, not "
                                  "identity proof; promotion never "
                                  "overwrites silently")
    promote_cmd.add_argument("--scope", default="static",
                             choices=("static", "desktop", "release"),
                             help="Promotion evidence scope: static "
                                  "promotes on static verification only; "
                                  "desktop needs bound runtime verification "
                                  "plus a passing recheck; release stays "
                                  "blocked without trusted reviewer "
                                  "authority")
    promote_cmd.add_argument("--runtime-run-id", default=None,
                             help="Sealed completed vqs.verify-runtime run to bind")
    promote_cmd.add_argument("--backup-dir", type=Path, default=None,
                             help="Backup path for the preserved original "
                                  "(else <original>.vqs-backup)")
    promote_cmd.add_argument("--no-desktop-recheck", action="store_true",
                             help="Skip the post-promotion Desktop reload/recheck")
    promote_cmd.add_argument("--promote-run-id", default=None,
                             help="Sealed id for the promotion run (else generated)")
    run_status_cmd = commands.add_parser("run-status", help="Report a sealed run (tool vqs.run_status)")
    run_status_cmd.add_argument("run_root", type=Path)
    run_status_cmd.add_argument("run_id")
    run_cmd = commands.add_parser("run", help="Orchestrated Power BI workflow (tool vqs.run)")
    run_cmd.add_argument("report", type=Path, nargs="?",
                         help="Enhanced-format *.Report folder (or --facts)")
    run_cmd.add_argument("--facts", type=Path, default=None,
                         help="JSON measured-facts document (or REPORT)")
    run_cmd.add_argument("--model", type=Path, default=None,
                         help="Optional *.SemanticModel definition folder")
    run_cmd.add_argument("--mode", choices=("review", "propose", "repair"),
                         default="review",
                         help="How far the sequence goes")
    run_cmd.add_argument("--scope", default="static",
                         help="static, desktop, or release (runtime legs "
                              "need Desktop + Bridge or block precisely)")
    run_cmd.add_argument("--config", type=Path, default=None,
                         help="vqs.json project config (else ./vqs.json or defaults)")
    run_cmd.add_argument("--run-root", type=Path, default=Path(".vqs-runs"))
    run_cmd.add_argument("--run-id", default=None)
    run_cmd.add_argument("--resume-from", default=None,
                         help="Resume a coordinator run after revalidating "
                              "sealed provenance")
    run_cmd.add_argument("--candidate-root", type=Path, default=None,
                         help="Disposable repair target (else a run-owned dir)")
    run_cmd.add_argument("--renders-dir", type=Path, default=None,
                         help="Baseline renders dir (else a run-owned dir)")
    run_cmd.add_argument("--plan", type=Path, default=None,
                         help="Owner-authored plan (else the synthesized one)")
    run_cmd.add_argument("--fixer-id", default="vqs-run",
                         help="Fixer identity sealed into review handoffs")
    run_cmd.add_argument("--pid", type=int, default=None,
                         help="Target a specific PBIDesktop.exe process")
    run_cmd.add_argument("--authoring-backend",
                         choices=("auto", "microsoft", "direct"),
                         default="auto")
    run_cmd.add_argument("--live-answers", action="store_true",
                         help="Opt into live DAX answer collection when a "
                              "model is reachable")
    run_cmd.add_argument("--reviewer", default=None,
                         help="Reviewer provider dotted path for visual "
                              "acceptance (runtime handoff blocks without "
                              "one)")
    run_cmd.add_argument("--report-out", type=Path, default=None,
                         help="Write the run envelope JSON here")
    commands.add_parser("mcp", help="Launch the stdio MCP server (tools vqs_*)")
    args = parser.parse_args(argv)
    if args.command == "theme":
        return _theme(args)
    if args.command == "triage":
        return _triage(args)
    if args.command == "premium":
        return _premium(args)
    if args.command == "measure":
        return _measure(args.report, args.model, args.out)
    if args.command == "cycles":
        return _cycles(args.model)
    if args.command == "prepare-preview":
        return _preview_candidate(args)
    if args.command == "compare-authoring":
        return _compare_authoring(args)
    if args.command == "capture":
        return _capture(args.report, args.renders, args.pid, args.scale,
                        args.wait_seconds, args.live_data)
    if args.command == "bundle":
        return _bundle(args.bundle_action, args)
    if args.command == "review-images":
        return _review_images(args)
    if args.command == "regions":
        return _regions(args)
    if args.command == "assurance":
        return _assurance(args)
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
        return _adjudicate_bundle(args.bundle, args.run_root, args.run_id,
                                  args.transport_bundle, args.report)
    if args.command == "inspect":
        return _inspect(args.report, args.model, args.config, args.out)
    if args.command == "review":
        return _review(args)
    if args.command == "propose":
        return _propose(args.run_root, args.run_id, args.facts, args.out)
    if args.command == "repair":
        return _repair(args)
    if args.command == "verify":
        return _verify(args)
    if args.command == "verify-runtime":
        return _verify_runtime(args)
    if args.command == "promote":
        return _promote(args)
    if args.command == "run-status":
        return _run_status(args.run_root, args.run_id)
    if args.command == "run":
        return _run(args)
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
        canvases = {page["id"]: page.get("canvas") for page in info["pages"]}
        pages, issues = image_evidence(args.renders, info["source_sha256"],
                                       expected, canvases=canvases)
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
                                     data_readiness=manifest.get("data_readiness"),
                                     source_pages=expected)
        print(json.dumps(template, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
