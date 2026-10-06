"""Single orchestrated Power BI workflow (P0-U2): ``vqs run`` / ``vqs_run``.

One coordinator owns the whole static-plus-runtime sequence on the
shared engine (inspect -> static review -> live readiness -> baseline
capture -> safe proposal -> candidate repair -> verify -> candidate
reload -> answer regression -> affected-page recapture -> visual review
handoff -> remeasure -> summary) instead of duplicating logic in every
caller. Modes select how far the sequence goes (review | propose |
repair); scopes select whether runtime legs are requested (static |
desktop | release). Every stage records pass / fail / blocked /
not_run with its evidence: out-of-scope legs are not_run, requested
but unavailable capability is blocked with the exact missing piece,
never a guess. Resume revalidates sealed provenance before reusing
any prior stage.

P0-U5 outcome semantics: stages describe execution, while the sealed
summary additionally exposes quality_before / quality_after,
resolved / remaining / new findings, candidate status, promotion
status (always not-performed: the coordinator never promotes), and an
outcome (accepted / improved_not_accepted / not_accepted / regressed /
no_safe_fix / blocked / failed). Envelope pass requires the requested
acceptance scope to pass; a stage pass never implies quality
acceptance.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

TOOL_ID = "vqs.run"

MODES = ("review", "propose", "repair")
SCOPES = ("static", "desktop", "release")
RUNTIME_SCOPES = ("desktop", "release")

STAGE_ORDER = ("inspect", "review", "readiness", "baseline_capture",
               "answers_baseline", "propose", "repair", "verify",
               "candidate_reload", "answer_regression", "recapture",
               "handoff", "remeasure", "summary")


def bridge_present() -> bool:
    """Desktop Bridge CLI probe (monkeypatch point for adapter tests)."""
    return shutil.which("powerbi-desktop") is not None


def modeling_present() -> bool:
    """Modeling MCP launcher probe (monkeypatch point for adapter tests)."""
    return shutil.which("powerbi-modeling-mcp") is not None


def _stage(name: str, status: str, reason: str = "",
           run_id: str | None = None, run_dir: str | None = None,
           evidence: Any = None) -> dict[str, Any]:
    """One stage ledger entry; status is pass/fail/blocked/not_run."""
    record: dict[str, Any] = {"stage": name, "status": status}
    if reason:
        record["reason"] = reason
    if run_id is not None:
        record["run_id"] = run_id
    if run_dir is not None:
        record["run_dir"] = run_dir
    if evidence is not None:
        record["evidence"] = evidence
    return record


def _child_id(run_id: str, stage: str) -> str:
    """Deterministic child run id; resume mints fresh ones per run."""
    return f"{run_id}-{stage}"


def _unsupported_scope_answers(questions: Any) -> tuple[list[dict], list[dict]]:
    """Split DAX questions into supported and fail-closed unsupported ones.

    Questions whose scope carries non-empty filters/period stay
    fail-closed until supported; malformed entries block as well.
    """
    if not isinstance(questions, list):
        return [], [{"id": "?", "verdict": "blocked",
                     "reason": "dax questions must be a list"}]
    supported: list[dict] = []
    held: list[dict] = []
    for position, question in enumerate(questions):
        qid = (str(question.get("id", f"question-{position}"))
               if isinstance(question, dict) else f"question-{position}")
        if not isinstance(question, dict):
            held.append({"id": qid, "verdict": "blocked",
                         "reason": "malformed oracle question"})
            continue
        scope = question.get("scope", {})
        if not isinstance(scope, dict):
            held.append({"id": qid, "verdict": "blocked",
                         "reason": "question scope is not an object"})
            continue
        if scope.get("filters") or scope.get("period"):
            held.append({"id": qid, "verdict": "blocked",
                         "reason": "non-empty filters/period remain "
                                   "fail-closed until supported"})
            continue
        if not isinstance(question.get("dax"), str) or not question["dax"]:
            held.append({"id": qid, "verdict": "blocked",
                         "reason": "question needs a DAX string"})
            continue
        supported.append({"id": qid, "dax": question["dax"],
                          "scope": scope})
    return supported, held


def _open_run(run_root: str, run_id: str | None,
              manifest: dict[str, Any]) -> tuple[Any, Any]:
    """Create the coordinator run dir; (run_dir, rid) or (None, blocked)."""
    from vqs.pipeline import blocked_envelope
    from vqs.run_store import create_run

    rid = run_id or f"run-{uuid.uuid4().hex[:12]}"
    try:
        run_dir = create_run(Path(run_root), rid, manifest)
    except FileExistsError:
        return None, blocked_envelope(
            TOOL_ID, [f"Run already exists: {rid}"])
    except ValueError as exc:
        return None, blocked_envelope(TOOL_ID, [f"Unusable run id: {exc}"])
    return run_dir, rid


def _provenance(report_dir: str | None, model_dir: str | None,
                facts: dict | None, config: dict) -> tuple[dict, dict | None]:
    """Source/model/config digests for resume comparison."""
    from vqs.pipeline import _canonical_sha256, _source_provenance

    provenance, _issues = _source_provenance(report_dir, model_dir)
    digest = {"source_sha256": provenance.get("source_sha256"),
              "model_sha256": provenance.get("model_sha256"),
              "facts_sha256": (_canonical_sha256(facts)
                               if isinstance(facts, dict) else None),
              "config_sha256": _canonical_sha256(config)}
    return provenance, digest


def _optional_file_sha(path: str | None) -> str | None:
    """SHA-256 of an optional file; None when absent or unreadable."""
    if not isinstance(path, str) or not path:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _load_resume(run_root: str, resume_from: str) -> tuple[dict | None, str | None]:
    """Load a prior coordinator manifest; (manifest, None) or (None, error)."""
    from vqs.pipeline import _read_manifest
    from vqs.run_store import verify_seal

    manifest, error = _read_manifest(run_root, resume_from)
    if error is not None:
        return None, error
    assert manifest is not None
    if manifest.get("pipeline") != "vqs.run/1":
        return None, (f"run {resume_from!r} is not a coordinator run "
                      f"(pipeline {manifest.get('pipeline')!r})")
    if verify_seal(Path(run_root) / resume_from):
        return None, f"prior run {resume_from!r} seal invalid"
    try:
        stages = json.loads((Path(run_root) / resume_from / "stages.json"
                             ).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"prior run {resume_from!r} stages unreadable: {exc}"
    if not isinstance(stages, list):
        return None, f"prior run {resume_from!r} stages are not a list"
    manifest = dict(manifest)
    manifest["_stages"] = stages
    return manifest, None


def _adoptable(stage: str, record: dict, ctx: dict) -> bool:
    """Resume may reuse a passed stage only after revalidation."""
    from vqs.pipeline import _read_manifest
    from vqs.run_store import verify_seal

    if not isinstance(record, dict) or record.get("status") != "pass":
        return False
    run_root = ctx["run_root"]
    if stage == "inspect":
        return True
    if stage in ("review", "remeasure"):
        if not isinstance(record.get("run_id"), str):
            return False
        run_dir = record.get("run_dir")
        if not isinstance(run_dir, str):
            return False
        if verify_seal(Path(run_dir)):
            return False
        manifest, error = _read_manifest(run_root,
                                         Path(run_dir).name)
        if error is not None:
            return False
        assert manifest is not None
        bindings = manifest.get("bindings")
        bindings = bindings if isinstance(bindings, dict) else {}
        if stage == "review":
            return bindings.get("input_sha256") == ctx["merged_sha256"]
        return True
    if stage == "repair":
        if not isinstance(record.get("run_id"), str):
            return False
        run_dir = record.get("run_dir")
        if not isinstance(run_dir, str):
            return False
        if verify_seal(Path(run_dir)):
            return False
        evidence = record.get("evidence")
        candidate = (evidence.get("candidate")
                     if isinstance(evidence, dict) else None)
        return isinstance(candidate, str) and Path(candidate).exists()
    if stage in ("baseline_capture", "recapture"):
        evidence = record.get("evidence")
        renders = (evidence.get("renders")
                   if isinstance(evidence, dict) else None)
        if not isinstance(renders, str):
            return False
        try:
            manifest_doc = json.loads(
                (Path(renders) / "capture-manifest.json").read_text(
                    encoding="utf-8-sig"))
        except (OSError, ValueError):
            return False
        return (isinstance(manifest_doc, dict)
                and manifest_doc.get("source_sha256")
                == ctx["digest"]["source_sha256"])
    if stage == "answers_baseline":
        evidence = record.get("evidence")
        path = evidence.get("answers_path") if isinstance(
            evidence, dict) else None
        return isinstance(path, str) and Path(path).is_file()
    return False


def run_workflow(*, report_dir: str | None = None,
                 model_dir: str | None = None,
                 facts: dict | None = None,
                 mode: str = "review", scope: str = "static",
                 config: dict | None = None,
                 run_root: str = ".vqs-runs",
                 run_id: str | None = None,
                 resume_from: str | None = None,
                 candidate_root: str | None = None,
                 renders_dir: str | None = None,
                 plan_path: str | None = None,
                 fixer_id: str = "vqs-run",
                 pid: int | None = None,
                 authoring_backend: str = "auto",
                 live_answers: bool = False,
                 dax_questions: list | None = None,
                 modeling: Any = None,
                 reviewer: Any = None) -> dict[str, Any]:
    """Run the orchestrated Power BI workflow; never raises on bad input.

    Returns a ``vqs.run`` envelope whose ``stages`` ledger records every
    step with its evidence. See the module docstring for the sequence.
    """
    from vqs.config import default_config
    from vqs.pipeline import blocked_envelope, inspect_report, merge_review_facts, review_report
    from vqs.run_store import append_event

    if mode not in MODES:
        return blocked_envelope(TOOL_ID, [
            f"mode must be one of {', '.join(MODES)}, got {mode!r}"])
    if scope not in SCOPES:
        return blocked_envelope(TOOL_ID, [
            f"scope must be one of {', '.join(SCOPES)}, got {scope!r}"])
    if not isinstance(run_root, str) or not run_root:
        return blocked_envelope(TOOL_ID, ["run_root must be a nonempty path"])
    if report_dir is None and facts is None:
        return blocked_envelope(TOOL_ID, ["provide report_dir or facts"])
    if report_dir is not None and not isinstance(report_dir, str):
        return blocked_envelope(TOOL_ID, ["report_dir must be a string path"])
    if facts is not None and not isinstance(facts, dict):
        return blocked_envelope(TOOL_ID, ["facts must be an object"])
    runtime = scope in RUNTIME_SCOPES
    config = config if isinstance(config, dict) else default_config()

    _provenance_map, digest = _provenance(report_dir, model_dir, facts,
                                         config)
    prior: dict | None = None
    if resume_from is not None:
        prior, error = _load_resume(run_root, resume_from)
        if error is not None:
            return blocked_envelope(TOOL_ID, [error])
        assert prior is not None
        sealed_params = prior.get("params")
        sealed_params = (sealed_params if isinstance(sealed_params, dict)
                         else {})
        live = {"mode": mode, "scope": scope, "report_dir": report_dir,
                "model_dir": model_dir,
                "facts_sha256": digest["facts_sha256"],
                "source_sha256": digest["source_sha256"],
                "model_sha256": digest["model_sha256"],
                "config_sha256": digest["config_sha256"],
                "candidate_root": candidate_root,
                "plan_path": plan_path,
                "plan_sha256": _optional_file_sha(plan_path),
                "authoring_backend": authoring_backend,
                "fixer_id": fixer_id}
        changed = sorted(name for name, value in live.items()
                         if sealed_params.get(name) != value)
        if changed:
            return blocked_envelope(
                TOOL_ID, [(f"provenance changed since {resume_from!r}: "
                           f"{', '.join(changed)}; refusing blind resume")])
    adopted = {record["stage"]: record for record in
               (prior.get("_stages", []) if prior else [])
               if isinstance(record, dict) and isinstance(
                   record.get("stage"), str)}
    manifest = {"pipeline": "vqs.run/1",
                "params": {"mode": mode, "scope": scope,
                           "report_dir": report_dir,
                           "model_dir": model_dir,
                           "facts_sha256": digest["facts_sha256"],
                           "source_sha256": digest["source_sha256"],
                           "model_sha256": digest["model_sha256"],
                           "config_sha256": digest["config_sha256"],
                           "candidate_root": candidate_root,
                           "plan_path": plan_path,
                           "plan_sha256": _optional_file_sha(plan_path),
                           "authoring_backend": authoring_backend,
                           "fixer_id": fixer_id},
                "resumed_from": resume_from}
    run_dir, rid = _open_run(run_root, run_id, manifest)
    if run_dir is None:
        return rid
    ctx: dict[str, Any] = {"run_root": run_root, "digest": digest,
                           "merged_sha256": None}
    stages: list[dict] = []
    state: dict[str, Any] = {"adopted": adopted}

    def record(entry: dict) -> dict:
        stages.append(entry)
        append_event(run_dir, {"kind": "stage", **entry})
        return entry

    def adopted_record(name: str) -> dict | None:
        record_ = adopted.get(name)
        if record_ is not None and _adoptable(name, record_, ctx):
            return record(record_)
        return None

    append_event(run_dir, {"kind": "started", "mode": mode, "scope": scope})
    # -- inspect -------------------------------------------------------
    # Measuring is pure source reading: always re-run for report runs so
    # the facts object exists for the merge below; adopt only caller
    # facts runs (identical digests already prove the inputs).
    entry = adopted_record("inspect") if report_dir is None else None
    if entry is None:
        if report_dir is not None:
            inspected = inspect_report(report_dir, model_dir, config)
            if inspected["verdict"] == "blocked":
                record(_stage("inspect", "blocked",
                              "; ".join(inspected["blocked_reasons"])
                              or "inspect blocked",
                              evidence={"coverage": inspected["coverage"]}))
                return _finish(run_dir, rid, stages, state, mode, scope,
                               run_root)
            state["facts"] = inspected["facts"]
            state["coverage"] = inspected["coverage"]
            entry = record(_stage("inspect", "pass", evidence={
                "coverage": inspected["coverage"]}))
        else:
            assert isinstance(facts, dict)
            state["facts"] = facts
            state["coverage"] = facts.get("coverage", {})
            entry = record(_stage("inspect", "pass",
                                  reason="caller facts",
                                  evidence={"coverage": state["coverage"]
                                            if isinstance(
                                                state["coverage"], dict)
                                            else {}}))
    else:
        state["facts"] = facts if isinstance(facts, dict) else None
    merged = merge_review_facts(state["facts"], config)
    ctx["merged_sha256"] = hashlib.sha256(json.dumps(
        merged, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8")).hexdigest()
    state["merged"] = merged
    # -- review (static verdict; runtime legs are separate stages) -----
    entry = adopted_record("review")
    if entry is None:
        reviewed = review_report(facts=merged, config=config,
                                 run_root=run_root,
                                 run_id=_child_id(rid, "review"))
        state["review_id"] = reviewed.get("run_id")
        state["review_dir"] = reviewed.get("run_dir")
        state["review_verdict"] = reviewed["verdict"]
        state["review_coverage"] = reviewed.get("coverage", {})
        state["review_findings"] = reviewed.get("findings", [])
        if reviewed["verdict"] == "blocked":
            record(_stage("review", "blocked",
                          "; ".join(reviewed["blocked_reasons"])
                          or "review blocked",
                          run_id=reviewed.get("run_id"),
                          run_dir=reviewed.get("run_dir")))
            return _finish(run_dir, rid, stages, state, mode, scope,
                           run_root)
        record(_stage("review", "pass",
                      reason=f"static verdict {reviewed['verdict']}",
                      run_id=reviewed.get("run_id"),
                      run_dir=reviewed.get("run_dir"),
                      evidence={"verdict": reviewed["verdict"],
                                "findings": reviewed.get("findings", [])}))
    else:
        state["review_id"] = entry.get("run_id")
        state["review_dir"] = entry.get("run_dir")
        evidence = entry.get("evidence")
        state["review_verdict"] = (evidence.get("verdict")
                                   if isinstance(evidence, dict) else None)
        state["review_findings"] = (evidence.get("findings")
                                    if isinstance(evidence, dict) else None)
    # -- readiness (runtime scopes only) --------------------------------
    if not runtime:
        record(_stage("readiness", "not_run",
                      reason="static scope requests no live runtime"))
        state["ready"] = False
    else:
        from vqs.powerbi.desktop import desktop_spike_readiness

        if not config.get("data_permissions", {}).get(
                "allow_desktop", False):
            record(_stage(
                "readiness", "blocked",
                reason="desktop/release scope needs "
                       "data_permissions.allow_desktop"))
            state["ready"] = False
        else:
            readiness = desktop_spike_readiness()
            missing = readiness.get("missing", [])
            missing = [str(item) for item in missing
                       if isinstance(missing, list)]
            if readiness.get("verdict") != "ready":
                record(_stage(
                    "readiness", "blocked",
                    reason=("live runtime unavailable: "
                            + ", ".join(missing)
                            or "readiness blocked"),
                    evidence={"readiness": readiness}))
                state["ready"] = False
            else:
                state["ready"] = True
                record(_stage("readiness", "pass", evidence={
                    "readiness": readiness}))
    return _runtime_sequence(
        run_dir, rid, stages, state, ctx, record,
        {"report_dir": report_dir, "model_dir": model_dir,
         "mode": mode, "scope": scope, "runtime": runtime,
         "config": config, "run_root": run_root,
         "candidate_root": candidate_root, "renders_dir": renders_dir,
         "plan_path": plan_path,
         "fixer_id": fixer_id, "pid": pid,
         "authoring_backend": authoring_backend,
         "live_answers": live_answers, "dax_questions": dax_questions,
         "modeling": modeling, "reviewer": reviewer})


def _capture_stage(name: str, report: str, renders: str, pid: int | None,
                   record: Any, adopted: dict, ctx: dict) -> dict:
    """Attempt a real Bridge capture; BLOCKED with the exact refusal."""
    from vqs.capture import capture

    prior = adopted.get(name)
    if prior is not None and _adoptable(name, prior, ctx):
        return record(prior)
    try:
        manifest = capture(report, renders, pid=pid)
    except (OSError, LookupError, ValueError, TypeError) as exc:
        return record(_stage(name, "blocked",
                             f"{type(exc).__name__}: {exc}"))
    return record(_stage(name, "pass", run_dir=None,
                         evidence={"renders": renders,
                                   "source_sha256": manifest.get(
                                       "source_sha256"),
                                   "pages": sorted((manifest.get(
                                       "page_images") or {}).keys())}))


def _connect_modeling(params: dict) -> tuple[Any, bool, Any]:
    """Connect the live model; (client, owned, proof) or raise."""
    from vqs.powerbi.modeling import StdioModelingClient

    client = params["modeling"]
    if client is None:
        client = StdioModelingClient()
        return client, True, client.connect()
    return client, False, client.connect()


def _answers_collect(questions: list, client: Any) -> dict:
    """Collect supported DAX questions; unsupported stay fail-closed.

    The port reports per-question ``observed`` rows; anything else
    (port blocks, held-back scopes) blocks the collection.
    """
    from vqs.repair.answers import collect_answers

    supported, held = _unsupported_scope_answers(questions)
    collected: dict[str, Any] = {}
    if supported:
        try:
            result = collect_answers(client, supported)
        except (ValueError, TypeError, AttributeError) as exc:
            return {"verdict": "blocked",
                    "reason": f"answer collection failed: {exc}",
                    "held": held}
        collected = result if isinstance(result, dict) else {}
    merged = dict(collected)
    for item in held:
        merged[item["id"]] = {"verdict": "blocked",
                              "reason": item["reason"]}
    bad = sorted(qid for qid, item in merged.items()
                 if not (isinstance(item, dict)
                         and item.get("verdict") == "observed"
                         and isinstance(item.get("rows"), list)))
    if bad:
        return {"verdict": "blocked",
                "reason": "answer evidence incomplete: "
                          + ", ".join(bad),
                "questions": merged}
    return {"verdict": "pass", "questions": merged}


def _answers_baseline(params: dict, record: Any, adopted: dict,
                      ctx: dict, run_dir: Any) -> dict:
    """Live answer baseline; fail-closed without a reachable model."""
    questions = params["dax_questions"]
    if not questions:
        return record(_stage("answers_baseline", "not_run",
                             reason="no DAX questions configured"))
    if not params["runtime"]:
        return record(_stage("answers_baseline", "blocked",
                             reason="static scope has no live model"))
    prior = adopted.get("answers_baseline")
    if prior is not None and _adoptable("answers_baseline", prior, ctx):
        return record(prior)
    if not modeling_present():
        return record(_stage(
            "answers_baseline", "blocked",
            reason="answer collection needs the modeling MCP launcher "
                   "(powerbi-modeling-mcp) on PATH"))
    if not params["live_answers"]:
        return record(_stage(
            "answers_baseline", "blocked",
            reason="live answer collection needs explicit live_answers "
                   "opt-in"))
    if not isinstance(questions, list):
        return record(_stage("answers_baseline", "blocked",
                             reason="dax questions must be a list"))
    client: Any = None
    owned = False
    try:
        from vqs.powerbi.modeling import ModelingError

        try:
            client, owned, proof = _connect_modeling(params)
        except (ModelingError, OSError, ValueError) as exc:
            return record(_stage(
                "answers_baseline", "blocked",
                reason=f"no reachable live model: {exc}"))
        result = _answers_collect(questions, client)
        if result["verdict"] != "pass":
            return record(_stage("answers_baseline", "blocked",
                                 reason=result["reason"],
                                 evidence={"proof": proof,
                                           "questions": result.get(
                                               "questions", {})}))
        path = run_dir / "answers-baseline.json"
        try:
            path.write_text(json.dumps(result, indent=2,
                                       ensure_ascii=False, default=str)
                            + "\n", encoding="utf-8")
        except OSError as exc:
            return record(_stage(
                "answers_baseline", "blocked",
                reason=f"cannot persist answer evidence: {exc}"))
        return record(_stage("answers_baseline", "pass", evidence={
            "answers_path": str(path), "proof": proof,
            "questions": result["questions"]}))
    finally:
        if owned:
            try:
                client.close()
            except (OSError, ValueError, AttributeError):
                pass


def _runtime_sequence(run_dir: Any, rid: str, stages: list,
                      state: dict, ctx: dict, record: Any,
                      params: dict) -> dict:
    """Capture, propose, repair, verify, reload, recapture, handoff, remeasure."""
    from vqs.pipeline import propose_candidates, repair_candidate

    mode, runtime = params["mode"], params["runtime"]
    run_root = params["run_root"]
    adopted = state["adopted"]
    report_dir = params["report_dir"]

    # -- baseline capture (runtime only, needs readiness) ---------------
    if not runtime:
        record(_stage("baseline_capture", "not_run",
                      reason="static scope requests no live runtime"))
    elif not state.get("ready"):
        record(_stage("baseline_capture", "not_run",
                      reason="readiness did not pass"))
    elif report_dir is None:
        record(_stage("baseline_capture", "blocked",
                      reason="capture needs a report directory"))
    else:
        renders = params["renders_dir"] or str(run_dir / "renders-baseline")
        state["baseline_renders"] = renders
        _capture_stage("baseline_capture", report_dir, renders,
                       params["pid"], record, adopted, ctx)
    # -- answers baseline (propose/repair modes) ------------------------
    if mode == "review":
        record(_stage("answers_baseline", "not_run",
                      reason="answers baseline belongs to propose/repair "
                             "modes"))
    else:
        entry = _answers_baseline(params, record, adopted, ctx, run_dir)
        state["answers_path"] = ((entry.get("evidence") or {}).get(
            "answers_path") if isinstance(entry.get("evidence"), dict)
            else None)
    # -- propose (propose/repair modes) ----------------------------------
    if mode == "review":
        record(_stage("propose", "not_run",
                      reason="review mode stops after the static verdict"))
        state["plan"] = None
    else:
        triage = propose_candidates(run_root, state["review_id"],
                                    state["merged"])
        if triage["verdict"] == "blocked":
            record(_stage("propose", "blocked",
                          "; ".join(triage["blocked_reasons"])
                          or "propose blocked",
                          run_id=triage.get("run_id"),
                          run_dir=triage.get("run_dir")))
            return _finish(run_dir, rid, stages, state, mode,
                           params["scope"], run_root)
        state["triage"] = triage
        state["plan"] = triage.get("plan")
        record(_stage("propose", "pass",
                      reason=(f"{len(triage.get('candidates', []))} "
                              "candidate(s); "
                              f"{len(triage.get('decisions', []))} "
                              "decision(s)"),
                      run_id=triage.get("run_id"),
                      run_dir=triage.get("run_dir"),
                      evidence={"candidates": triage.get("candidates", []),
                                "decisions": triage.get("decisions", [])}))
    # -- repair (repair mode, needs a plan and a report directory) ------
    # An adopted sealed repair is reused (verify below revalidates it)
    # instead of re-executing against an occupied candidate root.
    prior_repair = adopted.get("repair")
    if mode != "repair":
        record(_stage("repair", "not_run",
                      reason=f"{mode} mode stops before repair"))
    elif (prior_repair is not None
            and _adoptable("repair", prior_repair, ctx)):
        evidence = prior_repair.get("evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        state["repair_id"] = prior_repair.get("run_id")
        state["repair_dir"] = prior_repair.get("run_dir")
        state["candidate"] = evidence.get("candidate")
        record(prior_repair)
    elif report_dir is None:
        record(_stage("repair", "blocked",
                      reason="repair needs a report directory"))
    else:
        plan = state.get("plan")
        plan_file = run_dir / "plan.json"
        if params["plan_path"] is not None:
            try:
                plan = json.loads(Path(params["plan_path"]).read_text(
                    encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                plan = None
                record(_stage("repair", "blocked",
                              reason=f"unreadable owner plan: {exc}"))
                return _finish(run_dir, rid, stages, state, mode,
                               params["scope"], run_root)
        if not isinstance(plan, dict):
            record(_stage("repair", "blocked",
                          reason="no synthesized candidate and no owner "
                                 "plan; author a plan or run propose mode"))
            return _finish(run_dir, rid, stages, state, mode,
                           params["scope"], run_root)
        try:
            plan_file.write_text(json.dumps(plan, indent=2,
                                            ensure_ascii=False) + "\n",
                                 encoding="utf-8")
        except OSError as exc:
            record(_stage("repair", "blocked",
                          reason=f"cannot persist plan: {exc}"))
            return _finish(run_dir, rid, stages, state, mode,
                           params["scope"], run_root)
        state["plan"] = plan
        candidate = params["candidate_root"] or str(run_dir / "candidate")
        repaired = repair_candidate(
            str(plan_file), report_dir, candidate, run_root=run_root,
            run_id=_child_id(rid, "repair"),
            authoring_backend=params["authoring_backend"])
        state["repair_id"] = repaired.get("run_id")
        state["repair_dir"] = repaired.get("run_dir")
        if repaired["verdict"] == "blocked":
            record(_stage("repair", "blocked",
                          "; ".join(repaired["blocked_reasons"])
                          or "repair blocked",
                          run_id=repaired.get("run_id"),
                          run_dir=repaired.get("run_dir")))
            return _finish(run_dir, rid, stages, state, mode,
                           params["scope"], run_root)
        if repaired["verdict"] == "fail":
            record(_stage("repair", "fail",
                          "repair refused the plan",
                          run_id=repaired.get("run_id"),
                          run_dir=repaired.get("run_dir"),
                          evidence={"findings": repaired.get("findings",
                                                            [])}))
            return _finish(run_dir, rid, stages, state, mode,
                           params["scope"], run_root)
        state["candidate"] = candidate
        record(_stage("repair", "pass",
                      run_id=repaired.get("run_id"),
                      run_dir=repaired.get("run_dir"),
                      evidence={"candidate": candidate,
                                "affected_pages": (
                                    repaired.get("evidence") or [{}])[0].get(
                                        "affected_pages", [])}))
    return _verify_sequence(run_dir, rid, stages, state, ctx, record,
                            params)


def _verify_sequence(run_dir: Any, rid: str, stages: list,
                     state: dict, ctx: dict, record: Any,
                     params: dict) -> dict:
    """Verify, reload, regress answers, recapture, hand off, remeasure."""
    from vqs.pipeline import verify_candidate

    mode, runtime = params["mode"], params["runtime"]
    run_root = params["run_root"]
    adopted = state["adopted"]

    def adopted_record(name: str) -> dict | None:
        record_ = adopted.get(name)
        if record_ is not None and _adoptable(name, record_, ctx):
            return record(record_)
        return None

    repaired = state.get("repair_id") is not None and any(
        entry["stage"] == "repair" and entry["status"] == "pass"
        for entry in stages)
    verified = False
    # -- verify (repair mode, revalidates adopted repairs too) ----------
    if mode != "repair":
        record(_stage("verify", "not_run",
                      reason=f"{mode} mode stops before verify"))
    elif not repaired:
        record(_stage("verify", "not_run",
                      reason="repair did not pass"))
    else:
        checked = verify_candidate(run_root=run_root,
                                   run_id=state["repair_id"])
        if checked["verdict"] == "blocked":
            record(_stage("verify", "blocked",
                          "; ".join(checked["blocked_reasons"])
                          or "verify blocked",
                          run_id=checked.get("run_id"),
                          run_dir=checked.get("run_dir")))
        elif checked["verdict"] == "fail":
            record(_stage("verify", "fail",
                          "candidate differs beyond the declared edits",
                          run_id=checked.get("run_id"),
                          run_dir=checked.get("run_dir"),
                          evidence={"findings": checked.get("findings",
                                                           [])}))
        else:
            verified = True
            record(_stage("verify", "pass",
                          run_id=checked.get("run_id"),
                          run_dir=checked.get("run_dir")))
    state["verified"] = verified
    # -- candidate reload (runtime only, needs a verified candidate) ----
    if mode != "repair":
        record(_stage("candidate_reload", "not_run",
                      reason=f"{mode} mode stops before reload"))
    elif not runtime:
        record(_stage("candidate_reload", "not_run",
                      reason="static scope requests no live runtime"))
    elif not verified:
        record(_stage("candidate_reload", "not_run",
                      reason="candidate did not verify"))
    else:
        from vqs.capture import select_instance

        try:
            instance = select_instance(state["candidate"],
                                       params["pid"], 10)
        except (OSError, LookupError, ValueError, TypeError) as exc:
            record(_stage("candidate_reload", "blocked",
                          reason=f"{type(exc).__name__}: {exc}. Open the "
                                 "disposable candidate in Desktop (or wire "
                                 "an open adapter) and resume."))
        else:
            record(_stage("candidate_reload", "pass", evidence={
                "pid": instance.get("pid")}))
    # -- answer regression (repair mode, needs a baseline) --------------
    if mode != "repair":
        record(_stage("answer_regression", "not_run",
                      reason=f"{mode} mode stops before regression"))
    elif not verified:
        record(_stage("answer_regression", "not_run",
                      reason="candidate did not verify"))
    elif not state.get("answers_path"):
        record(_stage("answer_regression", "not_run",
                      reason="no baseline answers to regress"))
    else:
        record(_answer_regression(params, state, run_dir))
    # -- recapture (runtime only, needs a verified candidate) ------------
    if mode != "repair":
        record(_stage("recapture", "not_run",
                      reason=f"{mode} mode stops before recapture"))
    elif not runtime:
        record(_stage("recapture", "not_run",
                      reason="static scope requests no live runtime"))
    elif not verified:
        record(_stage("recapture", "not_run",
                      reason="candidate did not verify"))
    else:
        renders = str(run_dir / "renders-candidate")
        state["candidate_renders"] = renders
        _capture_stage("recapture", state["candidate"], renders,
                       params["pid"], record, adopted, ctx)
    # -- visual review handoff -------------------------------------------
    if not runtime:
        record(_stage("handoff", "not_run",
                      reason="static scope requests no visual evidence"))
    else:
        renders = state.get("candidate_renders") or state.get(
            "baseline_renders")
        if renders is None:
            record(_stage("handoff", "blocked",
                          reason="no renders to hand off"))
        elif params["report_dir"] is None and state.get(
                "candidate_renders") is None:
            record(_stage("handoff", "blocked",
                          reason="handoff needs the report directory"))
        else:
            record(_handoff_stage(params, state, renders, run_dir,
                                 str(run_dir / "handoff-bundle")))
    # -- remeasure (repair mode, static re-review of the candidate) -----
    if mode != "repair":
        record(_stage("remeasure", "not_run",
                      reason=f"{mode} mode stops before remeasure"))
    elif not state.get("candidate"):
        record(_stage("remeasure", "not_run",
                      reason="no candidate to remeasure"))
    else:
        from vqs.pipeline import review_report

        entry = adopted_record("remeasure")
        if entry is None:
            again = review_report(
                report_dir=state["candidate"],
                run_root=run_root, run_id=_child_id(rid, "remeasure"))
            state["quality_after"] = again["verdict"]
            state["remeasure_findings"] = again.get("findings", [])
            if again["verdict"] == "blocked":
                record(_stage("remeasure", "blocked",
                              "; ".join(again["blocked_reasons"])
                              or "remeasure blocked",
                              run_id=again.get("run_id"),
                              run_dir=again.get("run_dir")))
            else:
                record(_stage("remeasure", "pass",
                              reason=(f"quality_after={again['verdict']} "
                                      "(execution only, not acceptance)"),
                              run_id=again.get("run_id"),
                              run_dir=again.get("run_dir"),
                              evidence={"verdict": again["verdict"],
                                        "findings": again.get("findings",
                                                              [])}))
        else:
            evidence = entry.get("evidence")
            state["quality_after"] = (evidence.get("verdict")
                                      if isinstance(evidence, dict)
                                      else None)
            state["remeasure_findings"] = (evidence.get("findings")
                                           if isinstance(evidence, dict)
                                           else None)
    return _finish(run_dir, rid, stages, state, mode, params["scope"],
                   run_root)


def _handoff_stage(params: dict, state: dict, renders: str,
                   run_dir: Any, out: str) -> dict:
    """Pack the visual bundle and obtain reviewer observations (P0-U6).

    The bundle stays packable directly as a debugging escape hatch,
    but the coordinator handoff additionally requires a configured
    reviewer provider: the port consumes the verified bundle and its
    typed observations seal into reviewer.json (bound by the run seal
    via the recorded sha). A missing reviewer, a refusing port, or a
    malformed observation blocks the handoff loudly; observations that
    evaluate cleanly record visual acceptance, while failing
    observations keep the stage green (delivery completed) and fail
    visual acceptance as quality evidence, never as execution.
    """
    from vqs.review.bundle import pack
    from vqs.review.port import ReviewError, resolve_reviewer, review_bundle

    source = (state["candidate"]
              if state.get("candidate_renders") else
              params["report_dir"])
    try:
        bundle = pack(source, renders, out, params["fixer_id"])
    except (OSError, ValueError, TypeError) as exc:
        return _stage("handoff", "blocked",
                      reason=f"{type(exc).__name__}: {exc}")
    try:
        reviewer, reviewer_id = resolve_reviewer(params.get("reviewer"))
    except ReviewError as exc:
        return _stage("handoff", "blocked", reason=f"reviewer refused: {exc}",
                      evidence={"bundle": out, "manifest": bundle})
    if reviewer is None:
        return _stage(
            "handoff", "blocked",
            reason=("no reviewer capability: visual acceptance blocked; "
                    "pass an explicit reviewer provider (--reviewer) or "
                    "use vqs request-review as a debugging escape hatch"),
            evidence={"bundle": out, "manifest": bundle})
    assert reviewer_id is not None
    try:
        record_doc = review_bundle(
            bundle_dir=out, reviewer=reviewer,
            reviewer_id=reviewer_id, fixer_id=params["fixer_id"])
    except ReviewError as exc:
        return _stage("handoff", "blocked", reason=f"reviewer refused: {exc}",
                      evidence={"bundle": out, "manifest": bundle,
                                "reviewer": reviewer_id})
    if record_doc["visual"] == "blocked":
        return _stage("handoff", "blocked",
                      reason="reviewer could not evaluate the renders",
                      evidence={"bundle": out, "manifest": bundle,
                                "reviewer": reviewer_id})
    try:
        reviewer_path = Path(run_dir) / "reviewer.json"
        reviewer_bytes = json.dumps(record_doc, indent=2,
                                    ensure_ascii=False,
                                    default=str).encode("utf-8")
        reviewer_path.write_bytes(reviewer_bytes)
        reviewer_sha = hashlib.sha256(reviewer_bytes).hexdigest()
    except OSError as exc:
        return _stage("handoff", "blocked",
                      reason=f"cannot persist reviewer evidence: {exc}",
                      evidence={"bundle": out, "manifest": bundle,
                                "reviewer": reviewer_id})
    return _stage("handoff", "pass", evidence={
        "bundle": out, "manifest": bundle, "reviewer": reviewer_id,
        "reviewer_evidence": "reviewer.json",
        "reviewer_sha256": reviewer_sha,
        "observations": record_doc["observations"],
        "visual_acceptance": record_doc["visual"]})


def _answer_regression(params: dict, state: dict, run_dir: Any) -> dict:
    """Re-collect answers after repair and compare rows identically."""
    from vqs.repair.answers import answers_preserved

    try:
        baseline = json.loads(Path(state["answers_path"]).read_text(
            encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError) as exc:
        return _stage("answer_regression", "blocked",
                      reason=f"baseline answers unreadable: {exc}")
    questions = (baseline.get("questions")
                 if isinstance(baseline, dict) else None)
    if not isinstance(questions, dict):
        return _stage("answer_regression", "blocked",
                      reason="baseline answers hold no questions map")
    client: Any = None
    owned = False
    try:
        from vqs.powerbi.modeling import ModelingError

        try:
            client, owned, _proof = _connect_modeling(params)
        except (ModelingError, OSError, ValueError) as exc:
            return _stage("answer_regression", "blocked",
                          reason=f"no reachable live model: {exc}")
        asked = [{"id": qid, "dax": item.get("dax", ""),
                  "scope": item.get("scope", {})}
                 for qid, item in questions.items()
                 if isinstance(item, dict)
                 and item.get("verdict") == "observed"]
        result = _answers_collect(asked, client)
        if result["verdict"] != "pass":
            return _stage("answer_regression", "blocked",
                          reason=result["reason"])
        drifted: list[str] = []
        for qid, item in result["questions"].items():
            before = questions.get(qid, {})
            scope_text = json.dumps(before.get("scope", {}), sort_keys=True,
                                    ensure_ascii=False, default=str)
            compared = answers_preserved(
                scope_text, scope_text, before.get("rows"),
                item.get("rows"))
            if compared.get("verdict") != "pass":
                drifted.append(qid)
        if drifted:
            return _stage("answer_regression", "fail",
                          reason="answer regression: "
                                 + ", ".join(sorted(drifted)),
                          evidence={"questions": result["questions"]})
        path = run_dir / "answers-regression.json"
        try:
            path.write_text(json.dumps(result, indent=2,
                                       ensure_ascii=False, default=str)
                            + "\n", encoding="utf-8")
        except OSError as exc:
            return _stage("answer_regression", "blocked",
                          reason=f"cannot persist regression evidence: {exc}")
        return _stage("answer_regression", "pass", evidence={
            "answers_path": str(path),
            "questions": result["questions"]})
    finally:
        if owned:
            try:
                client.close()
            except (OSError, ValueError, AttributeError):
                pass


def _finding_states(findings: Any) -> tuple[dict[str, str], bool]:
    """Map check id to status; complete only for a well-formed list."""
    if not isinstance(findings, list):
        return {}, False
    states: dict[str, str] = {}
    for item in findings:
        if not isinstance(item, dict):
            return {}, False
        check, status = item.get("check"), item.get("status")
        if not isinstance(check, str) or not isinstance(status, str):
            return {}, False
        states[check] = status
    return states, True


def _reconcile_quality(before: Any, after: Any) -> dict[str, Any]:
    """Reconcile quality findings across remeasure (pure, P0-U5).

    resolved = failing before and passing after; remaining = still
    failing; new = proven pass before and failing after (strict
    regressions only — unevaluated checks never count as new). When
    either side is missing or malformed the lists stay empty and
    complete is False: unknown quality is reported, never zeroed.
    """
    before_states, before_ok = _finding_states(before)
    after_states, after_ok = _finding_states(after)
    if not (before_ok and after_ok):
        return {"resolved": [], "remaining": [], "new": [],
                "complete": False}
    if after_states == {} and before_states != {}:
        return {"resolved": [], "remaining": [], "new": [],
                "complete": False}
    before_fail = {check for check, status in before_states.items()
                   if status == "fail"}
    after_fail = {check for check, status in after_states.items()
                  if status == "fail"}
    after_pass = {check for check, status in after_states.items()
                  if status == "pass"}
    before_pass = {check for check, status in before_states.items()
                   if status == "pass"}
    return {"resolved": sorted(before_fail & after_pass),
            "remaining": sorted(after_fail),
            "new": sorted(after_fail & before_pass),
            "complete": True}


def _candidate_status(stages: list) -> dict[str, Any]:
    """Candidate lifecycle from the stage ledger (pure, P0-U5)."""
    by_stage = {entry["stage"]: entry for entry in stages
                if isinstance(entry, dict)
                and isinstance(entry.get("stage"), str)}
    repair = by_stage.get("repair")
    if repair is None or repair.get("status") == "not_run":
        return {"status": "none", "run_id": None, "candidate": None}
    evidence = repair.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    status = repair.get("status")
    if status == "blocked":
        return {"status": "blocked", "run_id": repair.get("run_id"),
                "candidate": evidence.get("candidate")}
    if status == "fail":
        return {"status": "failed", "run_id": repair.get("run_id"),
                "candidate": evidence.get("candidate")}
    verify = by_stage.get("verify")
    verify_status = (verify.get("status") if isinstance(verify, dict)
                     else "not_run")
    if verify_status == "pass":
        return {"status": "verified", "run_id": repair.get("run_id"),
                "candidate": evidence.get("candidate")}
    if verify_status == "fail":
        return {"status": "failed-verification",
                "run_id": repair.get("run_id"),
                "candidate": evidence.get("candidate")}
    return {"status": "applied-unverified",
            "run_id": repair.get("run_id"),
            "candidate": evidence.get("candidate")}


OUTCOMES = ("accepted", "improved_not_accepted", "not_accepted",
            "regressed", "no_safe_fix", "blocked", "failed")


def _acceptance(mode: str, *, review_verdict: Any, quality_after: Any,
                candidates: int, regression_failed: bool,
                visual: str = "not_run", runtime: bool = False) -> bool:
    """The requested acceptance scope actually passed (pure, P0-U5/U6).

    review asks "is the report good"; propose asks "produce safe fixes"
    (a clean report needs none); repair asks "fix the report" (the
    remeasured candidate meets the bar with no same-task regression).
    Runtime scopes additionally require visual acceptance from the
    reviewer port; a static run has no visual evidence to accept.
    """
    visual_ok = visual in ("pass", "not_run")
    if mode == "review":
        return review_verdict == "pass" and visual_ok
    if mode == "propose":
        return (review_verdict == "pass" or candidates > 0) and visual_ok
    if visual == "not_run":
        visual_ok = not runtime
    return (quality_after == "pass" and not regression_failed and visual_ok)


def _decide_outcome(*, mode: str, execution: str, acceptance: bool,
                    resolved: list, new: list,
                    candidates: int) -> str:
    """Outcome name from execution, acceptance, and quality delta."""
    if execution == "blocked":
        return "blocked"
    if execution == "fail":
        return "failed"
    if acceptance:
        return "accepted"
    if new:
        return "regressed"
    if resolved:
        return "improved_not_accepted"
    if mode == "propose" and candidates == 0:
        return "no_safe_fix"
    return "not_accepted"


def _next_actions(verdict: str, rid: str, scope: str,
                  summary: dict) -> list[str]:
    """Operator guidance for the coordinator outcome (P0-U5)."""
    outcome = summary.get("outcome", "")
    if verdict == "pass":
        actions = [("acceptance scope passed; sealed evidence supports the "
                    "verdict")]
        if scope in RUNTIME_SCOPES:
            actions.append("hand the sealed bundle to the independent "
                           "reviewer (fixer/reviewer separation holds)")
        return actions
    if verdict == "blocked":
        return [(f"resolve blocked stage(s): "
                 f"{', '.join(summary['blocked_stages'])}"),
                f"resume with vqs run --resume-from {rid}"]
    if outcome == "regressed":
        return [(f"new regressions introduced: "
                 f"{', '.join(summary['new_regressions'])}; roll back to the "
                 "sealed candidate state and re-repair")]
    if outcome == "improved_not_accepted":
        return [(f"remaining findings need owner decisions or another "
                 f"repair round: {', '.join(summary['remaining_findings'])}"),
                "execution pass is never quality acceptance"]
    if outcome == "no_safe_fix":
        return [("no finding admits a source-provable safe fix; owner "
                 "decision required")]
    if outcome == "not_accepted":
        return [("quality findings remain and nothing improved; owner "
                 "decision required")]
    return [(f"address failed stage(s): "
              f"{', '.join(summary['failed_stages'])}")]


def _finish(run_dir: Any, rid: str, stages: list, state: dict,
            mode: str, scope: str, run_root: str) -> dict:
    """Seal the ledger and return the vqs.run envelope; never raises."""
    from vqs.pipeline import _envelope, blocked_envelope
    from vqs.run_store import append_event, seal_run

    after_findings = state.get("remeasure_findings")
    if after_findings is None:
        after_findings = state.get("review_findings")
    reconcile = _reconcile_quality(state.get("review_findings"),
                                   after_findings)
    candidate_state = _candidate_status(stages)
    propose_entry = next((entry for entry in stages
                          if isinstance(entry, dict)
                          and entry.get("stage") == "propose"), {})
    propose_evidence = (propose_entry.get("evidence")
                        if isinstance(propose_entry, dict) else None)
    proposed = (propose_evidence.get("candidates")
                if isinstance(propose_evidence, dict) else [])
    candidate_count = len(proposed) if isinstance(proposed, list) else 0
    regression_failed = any(
        isinstance(entry, dict) and entry.get("stage") == "answer_regression"
        and entry.get("status") == "fail" for entry in stages)
    handoff = next((entry for entry in stages
                    if isinstance(entry, dict)
                    and entry.get("stage") == "handoff"), {})
    handoff = handoff if isinstance(handoff, dict) else {}
    handoff_evidence = (handoff.get("evidence")
                        if isinstance(handoff.get("evidence"), dict) else {})
    if handoff.get("status") == "pass":
        visual_acceptance = {
            "status": ("pass"
                       if handoff_evidence.get("visual_acceptance") == "pass"
                       else "fail"),
            "reason": ("reviewer observations evaluate cleanly"
                       if handoff_evidence.get("visual_acceptance") == "pass"
                       else "reviewer observations report visual findings"),
            "reviewer": handoff_evidence.get("reviewer")}
        reviewer_fails = [
            f"reviewer:{item.get('page_id')}:{item.get('check')}"
            for item in handoff_evidence.get("observations", [])
            if isinstance(item, dict) and item.get("verdict") == "fail"]
    elif handoff.get("status") == "blocked":
        visual_acceptance = {
            "status": "blocked",
            "reason": handoff.get("reason", "handoff blocked"),
            "reviewer": handoff_evidence.get("reviewer")}
        reviewer_fails = []
    else:
        visual_acceptance = {
            "status": "not_run",
            "reason": "static scope requests no visual evidence",
            "reviewer": None}
        reviewer_fails = []
    reconcile["remaining"] = sorted(set(reconcile["remaining"])
                                    | set(reviewer_fails))
    acceptance = _acceptance(
        mode, review_verdict=state.get("review_verdict"),
        quality_after=state.get("quality_after"),
        candidates=candidate_count, regression_failed=regression_failed,
        visual=visual_acceptance["status"],
        runtime=scope in RUNTIME_SCOPES)
    summary = {
        "mode": mode, "scope": scope,
        "review_verdict": state.get("review_verdict"),
        "quality_before": state.get("review_verdict"),
        "quality_after": state.get("quality_after"),
        "resolved_findings": reconcile["resolved"],
        "remaining_findings": reconcile["remaining"],
        "new_regressions": reconcile["new"],
        "findings_complete": reconcile["complete"],
        "candidates_proposed": candidate_count,
        "candidate_status": candidate_state,
        "promotion_status": {
            "status": "not-performed",
            "reason": ("the coordinator never promotes; promotion is "
                       "owner-explicit via vqs.promote after independent "
                       "acceptance")},
        "visual_acceptance": visual_acceptance,
        "blocked_stages": [entry["stage"] for entry in stages
                           if entry["status"] == "blocked"],
        "failed_stages": [entry["stage"] for entry in stages
                          if entry["status"] == "fail"],
        "child_runs": {entry["stage"]: {"run_id": entry.get("run_id"),
                                        "run_dir": entry.get("run_dir")}
                       for entry in stages if entry.get("run_id")},
        "candidate": state.get("candidate"),
        "acceptance": acceptance,
        "note": ("stages describe execution; outcome and acceptance "
                 "describe report quality. Envelope pass requires the "
                 "requested acceptance scope to pass; a stage pass never "
                 "implies quality acceptance")}

    # -- summary (always recorded) --------------------------------------
    terminal = [entry for entry in stages
                if entry["status"] in ("fail", "blocked")]
    if any(entry["status"] == "fail" for entry in terminal):
        execution = "fail"
    elif terminal:
        execution = "blocked"
    else:
        execution = "pass"
    outcome = _decide_outcome(
        mode=mode, execution=execution, acceptance=acceptance,
        resolved=reconcile["resolved"], new=reconcile["new"],
        candidates=candidate_count)
    summary["outcome"] = outcome
    verdict = "pass" if (execution == "pass" and acceptance) else execution
    if execution == "pass" and not acceptance:
        verdict = "fail"
    record = _stage("summary", verdict,
                    reason=(f"outcome={outcome}; "
                            + ("; ".join(summary["blocked_stages"]
                                         + summary["failed_stages"])
                               or f"{mode}/{scope} workflow {verdict}")),
                    evidence={"summary": summary["blocked_stages"],
                              "outcome": outcome})
    stages.append(record)
    try:
        append_event(run_dir, {"kind": "stage", **record})
        stages_path = run_dir / "stages.json"
        stages_bytes = json.dumps(stages, indent=2, ensure_ascii=False,
                                  default=str).encode("utf-8")
        stages_path.write_bytes(stages_bytes)
        stages_sha = hashlib.sha256(stages_bytes).hexdigest()
    except OSError as exc:
        return blocked_envelope(
            TOOL_ID, [f"cannot persist stage ledger: {exc}"],
            run_id=rid, run_dir=str(run_dir))
    terminal_event = {"pass": "completed", "fail": "failed",
                      "blocked": "blocked"}[verdict]
    try:
        append_event(run_dir, {"kind": terminal_event, "verdict": verdict})
        seal_run(
            run_dir, terminal_event,
            artifacts={"stages": {"sha256": stages_sha,
                                  "path": "stages.json"}},
            bindings={"tool": "vqs.run/1"})
    except ValueError as exc:
        return blocked_envelope(TOOL_ID, [f"cannot seal ledger: {exc}"],
                                run_id=rid, run_dir=str(run_dir))
    findings = [{"check": f"stage:{entry['stage']}",
                 "status": entry["status"],
                 "detail": {key: value for key, value in entry.items()
                            if key != "stage"}}
                for entry in stages if entry["status"] != "not_run"]
    findings.append({"check": "outcome", "status": verdict,
                     "detail": {"outcome": outcome,
                                "acceptance": acceptance}})
    coverage = state.get("review_coverage", {})
    return _envelope(
        TOOL_ID, verdict, run_id=rid, run_dir=str(run_dir), scope=scope,
        coverage=coverage if isinstance(coverage, dict) else {},
        findings=findings,
        evidence=[{"kind": "stage_ledger", "run_id": rid,
                   "stages": len(stages)}],
        blocked_reasons=[f"{entry['stage']}: {entry.get('reason', '')}"
                         for entry in stages
                         if entry["status"] == "blocked"],
        next_actions=_next_actions(verdict, rid, scope, summary),
        provenance={"coordinator_run_id": rid},
        extra={"stages": stages, "summary": summary,
               "plan": state.get("plan"),
               "review_verdict": state.get("review_verdict"),
               "quality_after": state.get("quality_after"),
               "outcome": outcome})
