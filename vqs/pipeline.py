"""End-to-end offline check pipeline: measured facts to sealed verdict.

Wires design rules (WP-06, issue #11), story oracles (WP-10, issue #15),
DOCX structure inspection (WP-08 static half, issue #13), and TMDL
model/binding checks (WP-05 subset, issue #10) into one command: load a
measured-facts document, run every requested rule, oracle, document,
and model check, aggregate without coercing ``unknown`` into ``pass``,
and seal the run manifest. Unknown rule IDs, malformed entries, and
missing facts block — never pass, never crash.

The tool engine below (``inspect_report``, ``review_report``,
``propose_candidates``, ``repair_candidate``, ``verify_candidate``,
``run_status_report``, ``render_report``) is the one local engine
behind both the CLI and the optional stdio MCP server: same functions,
same envelope, same verdicts. Engine entry points never raise on bad
input; they return blocked envelopes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from . import design_rules
from .data.tmdl import check_bindings, check_freshness, inventory_model, require_rls_identity
from .document.inspect import inspect_docx
from .policy import POLICY_VERSION
from .run_store import append_event, create_run, seal_run, verify_seal
from .stories.oracles import ambiguity_check, oracle_matches

STATUS_BY_VERDICT = {"pass": "completed", "fail": "failed", "blocked": "blocked"}


def _axis(params: dict[str, Any]) -> dict:
    return design_rules.axis_display_distinctness(
        params.get("numeric_ticks"), params.get("displayed_labels"))


def _contrast(params: dict[str, Any]) -> dict:
    readings = params.get("readings")
    if isinstance(readings, list):
        readings = [reading for reading in readings
                    if isinstance(reading, dict)]
    else:
        readings = None
    return design_rules.text_contrast(
        params.get("foreground"), params.get("background"),
        large_text=bool(params.get("large_text", False)),
        readings=readings)


def _catspace(params: dict[str, Any]) -> dict:
    return design_rules.category_axis_space(
        params.get("label_widths_px"), params.get("available_width_px"),
        gap_px=params.get("gap_px", 8))


def _palette(params: dict[str, Any]) -> dict:
    return design_rules.palette_semantic_consistency(
        params.get("assignments"), params.get("declared_overrides"))


def _units(params: dict[str, Any]) -> dict:
    return design_rules.cross_page_metric_units(params.get("readings"))


def _consistency(params: dict[str, Any]) -> dict:
    return design_rules.format_declaration_consistency(params.get("readings"))


def _dup_grain(params: dict[str, Any]) -> dict:
    return design_rules.insight_no_duplicate_grain(params.get("visuals"))


def _tree_dims(params: dict[str, Any]) -> dict:
    return design_rules.decomposition_tree_dimensions(params.get("trees"))


def _map_binding(params: dict[str, Any]) -> dict:
    return design_rules.map_location_binding(params.get("maps"))


def _xdup_grain(params: dict[str, Any]) -> dict:
    return design_rules.insight_no_cross_page_duplicate_grain(
        params.get("visuals"))


def _overlap(params: dict[str, Any]) -> dict:
    return design_rules.layout_no_visual_overlap(params.get("visuals"))


def _within_page(params: dict[str, Any]) -> dict:
    return design_rules.layout_visuals_within_page(params.get("pages"))


def _map_labels(params: dict[str, Any]) -> dict:
    return design_rules.chart_map_location_labels(params.get("maps"))


RULES = {
    "axis.display_values_not_distinct": _axis,
    "typography.text_contrast": _contrast,
    "axis.category_label_space": _catspace,
    "palette.semantic_consistency": _palette,
    "encoding.metric_unit_consistency": _units,
    "typography.format_declaration_consistency": _consistency,
    "insight.no_duplicate_grain": _dup_grain,
    "chart.decomposition_tree_dimensions": _tree_dims,
    "chart.map_location_binding": _map_binding,
    "insight.no_cross_page_duplicate_grain": _xdup_grain,
    "layout.no_visual_overlap": _overlap,
    "layout.visuals_within_page": _within_page,
    "chart.map_location_labels": _map_labels,
}


def _normalize(status: str) -> str:
    """Map rule/oracle outcomes onto pass/fail/blocked; unknowns block."""
    if status == "pass" or status == "answerable":
        return "pass"
    if status == "fail":
        return "fail"
    return "blocked"


def _run_oracle(entry: Any) -> dict:
    if not isinstance(entry, dict):
        return {"verdict": "blocked", "reason": "Oracle entry is not an object"}
    try:
        if "question" in entry:
            return ambiguity_check(entry.get("question"), entry.get("known_measures"),
                                   entry.get("known_targets"))
        if "oracle_scope" in entry or "run_scope" in entry:
            return oracle_matches(entry.get("oracle_scope", ""), entry.get("run_scope", ""))
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return {"verdict": "blocked", "reason": f"Unusable oracle entry: {type(exc).__name__}"}
    return {"verdict": "blocked", "reason": "Oracle entry names no question or scope pair"}


def _run_rule(runner: Any, rule_id: str, params: Any) -> dict:
    """Run one rule; unusable params block instead of raising."""
    if runner is None or not isinstance(params, dict):
        return {"rule_id": rule_id, "status": "unknown",
                "evidence": {"reason": "Unknown rule or non-object params"}}
    try:
        return runner(params)
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return {"rule_id": rule_id, "status": "unknown",
                "evidence": {"reason": f"Unusable rule params: {type(exc).__name__}"}}


def _run_document(entry: Any) -> dict:
    """Inspect one DOCX; structural issues fail, unreadable input blocks.

    DOC-01 boundary: this is well-formedness only, never pagination
    acceptance — same limit as vqs.document.inspect.
    """
    if not isinstance(entry, dict) or not entry.get("path"):
        return {"verdict": "blocked", "reason": "Document entry needs a path"}
    try:
        report = inspect_docx(Path(entry["path"]))
    except (OSError, ValueError, TypeError) as exc:
        return {"verdict": "blocked",
                "reason": f"Unreadable document: {type(exc).__name__}"}
    if report.get("issues"):
        return {"verdict": "fail", "issues": report["issues"],
                "inventory": report.get("inventory", {})}
    return {"verdict": "pass", "inventory": report.get("inventory", {})}


def _run_model(entry: Any) -> dict:
    """Check one semantic-model entry; see module docstring for the mapping.

    Inventory availability problems (missing/unreadable model) block;
    malformed declarations, unresolvable bindings, and stale snapshots
    fail; measures without expressions block for a live authorized query.
    An entry that verifies nothing blocks instead of passing vacuously.
    """
    if not isinstance(entry, dict) or not entry.get("model_dir"):
        return {"verdict": "blocked", "reason": "Model entry needs a model_dir"}
    try:
        inventory = inventory_model(Path(entry["model_dir"]))
    except (OSError, ValueError, TypeError) as exc:
        return {"verdict": "blocked",
                "reason": f"Unreadable model: {type(exc).__name__}"}
    checks: list[dict[str, Any]] = []
    for issue in inventory.get("issues", []):
        blocked = issue.get("rule") in ("no_model", "unreadable_model_file")
        checks.append({"rule": issue.get("rule", "?"),
                       "status": "blocked" if blocked else "fail",
                       "detail": issue})
    bindings = entry.get("bindings", [])
    if not isinstance(bindings, list):
        return {"verdict": "blocked", "reason": "Model bindings are not a list",
                "checks": checks}
    checks.extend(check_bindings(bindings, inventory))
    freshness = entry.get("freshness")
    if freshness is not None:
        if not isinstance(freshness, dict):
            return {"verdict": "blocked",
                    "reason": "Model freshness is not an object", "checks": checks}
        checks.append(check_freshness(str(freshness.get("bound_sha256", "")),
                                      str(freshness.get("current_sha256", "")),
                                      str(freshness.get("label", "model"))))
    if "rls_role" in entry:
        checks.append(require_rls_identity(entry.get("rls_role", "")))
    if not checks:
        return {"verdict": "blocked", "reason": "Model entry verifies nothing",
                "checks": []}
    if any(check.get("status") == "fail" for check in checks):
        return {"verdict": "fail", "checks": checks}
    if any(check.get("status") != "pass" for check in checks):
        return {"verdict": "blocked", "checks": checks}
    return {"verdict": "pass", "checks": checks}


def _canonical_sha256(payload: Any) -> str:
    """SHA256 over canonical JSON bytes (F18 seal input binding)."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

def seal_verdict(run_root: Path, run_id: str | None, pipeline_name: str,
               verdict: str, findings: list[dict[str, Any]],
               inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Seal a single-verdict run; a duplicate run_id blocks without a run.

    R10: when ``inputs`` (the canonical actual input document plus
    applicable identities) is supplied, it persists verbatim as
    ``input.json`` and the seal binds its digest, so changing any
    material input changes the binding even when the summary is held
    constant. Without inputs the legacy findings-only binding stands.
    """
    if verdict not in STATUS_BY_VERDICT:
        verdict = "blocked"
    run_id = run_id or f"{pipeline_name}-{uuid.uuid4().hex[:12]}".replace("/", "-")
    try:
        run_dir = create_run(Path(run_root), run_id, {"pipeline": pipeline_name})
    except FileExistsError:
        return {"verdict": "blocked", "run_dir": None, "run_id": run_id,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Run already exists: {run_id}"}]}
    except ValueError as exc:
        return {"verdict": "blocked", "run_dir": None, "run_id": run_id,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Unusable run id: {exc}"}]}
    append_event(run_dir, {"kind": "started", "checks": pipeline_name})
    terminal = STATUS_BY_VERDICT[verdict]
    append_event(run_dir, {"kind": terminal, "verdict": verdict})
    digest = hashlib.sha256(
        json.dumps(findings, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    artifacts: dict[str, Any] = {"verdict_sha256": digest}
    if inputs is None:
        sealed_input = {"pipeline": pipeline_name, "verdict": verdict, "findings": findings}
        bindings = {"input_sha256": _canonical_sha256(sealed_input), "policy_version": POLICY_VERSION, "tool": pipeline_name}
    else:
        stored = dict(inputs)
        payload = json.dumps(stored, sort_keys=True, ensure_ascii=False).encode("utf-8")
        (run_dir / "input.json").write_bytes(payload)
        input_sha = hashlib.sha256(payload).hexdigest()
        bindings = {"input_sha256": input_sha, "policy_version": POLICY_VERSION, "tool": pipeline_name}
        artifacts["input"] = {"sha256": input_sha, "path": "input.json"}
    manifest = seal_run(run_dir, terminal, artifacts=artifacts, bindings=bindings)
    return {"verdict": verdict, "run_dir": str(run_dir), "run_id": run_id,
            "findings": findings, "manifest": manifest}


_NON_BLOCKING_COVERAGE = frozenset({
    "model_reference_absent",
    # D01: the legacy index is honored in full; the flag is provenance,
    # not a gap.
    "legacy_pages_index",
})


def _coverage_location(issue: dict) -> str:
    parts = [str(issue[key]) for key in ("page", "visual") if issue.get(key)]
    return "/".join(parts)


def _blocking_coverage(issues: Any) -> list[dict]:
    """Coverage issues that must block approval (F09).

    Absence of a model claim is informative, not a defect; every other
    coverage issue (malformed/missing sources, unproven geometry,
    dangling references) blocks with its source IDs.
    """
    if not isinstance(issues, list):
        return []
    return [issue for issue in issues
            if isinstance(issue, dict)
            and issue.get("rule") not in _NON_BLOCKING_COVERAGE]


def _coverage_reason(issue: dict) -> str:
    location = _coverage_location(issue)
    where = f" at {location}" if location else ""
    return f"{issue.get('rule', 'unknown')}{where} blocks approval"


def run_check(facts: Any, run_root: Path, run_id: str | None = None,
              artifacts: dict[str, Any] | None = None,
              environment: dict[str, Any] | None = None,
              manifest_extra: dict[str, Any] | None = None,
              config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run every requested check and seal the manifest; see module docstring.

    Optional sealed provenance: ``artifacts``/``environment`` merge into
    the sealed manifest (verdict digest always present); ``manifest_extra``
    merges into the run manifest (e.g. resume links). All default to the
    historical behavior.
    """
    if not isinstance(facts, dict):
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "facts", "status": "blocked",
                              "reason": "Facts document is not an object"}]}
    run_id = run_id or f"check-{uuid.uuid4().hex[:12]}"
    manifest = {"pipeline": "vqs.check/1"}
    manifest.update(manifest_extra or {})
    try:
        run_dir = create_run(Path(run_root), run_id, manifest)
    except FileExistsError:
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Run already exists: {run_id}"}]}
    except ValueError as exc:
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Unusable run id: {exc}"}]}
    append_event(run_dir, {"kind": "started",
                           "checks": "design_rules+oracles+documents+models+coverage"})
    findings: list[dict[str, Any]] = []
    rules = facts.get("rules", {})
    if not isinstance(rules, dict):
        findings.append({"check": "rules", "status": "blocked",
                         "reason": "facts.rules is not an object"})
        rules = {}
    for rule_id, params in rules.items():
        detail = _run_rule(RULES.get(rule_id), rule_id, params)
        status = _normalize(detail.get("status", "unknown"))
        findings.append({"check": rule_id, "status": status, "detail": detail})
        append_event(run_dir, {"kind": "checked", "check": rule_id, "status": status})
    oracles = facts.get("oracles", [])
    if not isinstance(oracles, list):
        findings.append({"check": "oracles", "status": "blocked",
                         "reason": "facts.oracles is not a list"})
        oracles = []
    for index, entry in enumerate(oracles):
        detail = _run_oracle(entry)
        status = _normalize(detail.get("verdict", "blocked"))
        findings.append({"check": f"oracle:{index}", "status": status, "detail": detail})
        append_event(run_dir, {"kind": "checked", "check": f"oracle:{index}",
                               "status": status})
    documents = facts.get("documents", [])
    if not isinstance(documents, list):
        findings.append({"check": "documents", "status": "blocked",
                         "reason": "facts.documents is not a list"})
        documents = []
    for index, entry in enumerate(documents):
        detail = _run_document(entry)
        status = _normalize(detail.get("verdict", "blocked"))
        findings.append({"check": f"document:{index}", "status": status,
                         "detail": detail})
        append_event(run_dir, {"kind": "checked", "check": f"document:{index}",
                               "status": status})
    models = facts.get("models", [])
    if not isinstance(models, list):
        findings.append({"check": "models", "status": "blocked",
                         "reason": "facts.models is not a list"})
        models = []
    for index, entry in enumerate(models):
        detail = _run_model(entry)
        status = _normalize(detail.get("verdict", "blocked"))
        findings.append({"check": f"model:{index}", "status": status,
                         "detail": detail})
        append_event(run_dir, {"kind": "checked", "check": f"model:{index}",
                               "status": status})
    coverage = facts.get("coverage", {})
    raw_issues = (coverage.get("issues", [])
                  if isinstance(coverage, dict) else [])
    if not isinstance(raw_issues, list):
        findings.append({"check": "coverage", "status": "blocked",
                         "reason": "facts.coverage.issues is not a list"})
    else:
        for issue in raw_issues:
            if not isinstance(issue, dict):
                findings.append({"check": "coverage", "status": "blocked",
                                 "reason": "coverage issue is not an object"})
                continue
            if issue.get("rule") in _NON_BLOCKING_COVERAGE:
                continue
            rule = issue.get("rule", "unknown")
            findings.append({"check": f"coverage:{rule}", "status": "blocked",
                             "reason": _coverage_reason(issue),
                             "detail": issue})
            append_event(run_dir, {"kind": "checked",
                                   "check": f"coverage:{rule}",
                                   "status": "blocked"})
    findings_sha256: str | None = None
    try:
        findings_bytes = json.dumps(findings, sort_keys=True,
                                   ensure_ascii=False, default=str).encode("utf-8")
        (run_dir / "findings.json").write_bytes(findings_bytes)
        findings_sha256 = hashlib.sha256(findings_bytes).hexdigest()
    except OSError as exc:
        findings.append({"check": "findings", "status": "blocked",
                         "reason": f"cannot persist findings: {exc}"})
    if any(finding["status"] == "fail" for finding in findings):
        verdict = "fail"
    elif (not findings or
          any(finding["status"] == "blocked" for finding in findings)):
        verdict = "blocked"
    else:
        verdict = "pass"
    terminal = STATUS_BY_VERDICT[verdict]
    append_event(run_dir, {"kind": terminal, "verdict": verdict})
    digest = hashlib.sha256(
        json.dumps(findings, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    sealed_artifacts = dict(artifacts or {})
    sealed_artifacts.setdefault("verdict_sha256", digest)
    if findings_sha256 is not None:
        sealed_artifacts["findings"] = {"sha256": findings_sha256,
                                        "path": "findings.json"}
    bindings = {"input_sha256": _canonical_sha256(facts), "policy_version": POLICY_VERSION, "tool": "vqs.check/1",
                "config_sha256": _canonical_sha256(config) if isinstance(config, dict) else None}
    manifest = seal_run(run_dir, terminal, artifacts=sealed_artifacts,
                        environment=environment, bindings=bindings)
    return {"verdict": verdict, "run_dir": str(run_dir), "run_id": run_id,
            "findings": findings, "manifest": manifest}


TOOL_SCHEMA_VERSION = "vqs.tool/1"

TOOL_IDS = ("vqs.inspect", "vqs.review", "vqs.propose", "vqs.repair",
            "vqs.verify", "vqs.run_status")

REVIEW_SCOPES = ("static", "desktop", "release")

_SEVERITY = {"fail": "error", "blocked": "warning", "pass": "info"}


def _atomic_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Adapt a pipeline finding to the atomic tool shape.

    Severity follows the status (fail/error, blocked/warning,
    pass/info); location carries page/visual only when the evidence
    proves them; ``recipes`` stays empty until the repair lane
    supplies supported recipes — never invented here.
    """
    status = finding.get("status", "blocked")
    detail = finding.get("detail")
    detail = detail if isinstance(detail, dict) else {}
    evidence = detail.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    page = detail.get("page", evidence.get("page"))
    visual = detail.get("visual", evidence.get("visual"))
    visuals = detail.get("visuals", evidence.get("visuals"))
    location: dict[str, Any] = {}
    if isinstance(page, str) and page:
        location["page"] = page
    if isinstance(visual, str) and visual:
        location["visual"] = visual
    if isinstance(visuals, list) and visuals:
        location["visuals"] = [v for v in visuals if isinstance(v, str)]
    return {"check": finding.get("check", "?"),
            "status": status if status in _SEVERITY else "blocked",
            "severity": _SEVERITY.get(status, "warning"),
            "location": location or None,
            "evidence_basis": detail,
            "recipes": []}


def _envelope(tool: str, verdict: str, *,
              run_id: str | None = None, run_dir: str | None = None,
              scope: str = "static",
              coverage: dict[str, Any] | None = None,
              findings: list[dict[str, Any]] | None = None,
              evidence: list[dict[str, Any]] | None = None,
              blocked_reasons: list[str] | None = None,
              next_actions: list[str] | None = None,
              provenance: dict[str, Any] | None = None,
              extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the standard tool envelope shared by CLI and MCP."""
    doc: dict[str, Any] = {
        "schema_version": TOOL_SCHEMA_VERSION,
        "tool": tool,
        "run_id": run_id,
        "run_dir": run_dir,
        "scope": scope,
        "verdict": verdict if verdict in ("pass", "fail", "blocked") else "blocked",
        "coverage": coverage if isinstance(coverage, dict) else {},
        "findings": [_atomic_finding(f) if isinstance(f, dict) else
                     {"check": "?", "status": "blocked", "severity": "warning",
                      "location": None, "evidence_basis": {},
                      "recipes": []} for f in (findings or [])],
        "evidence": evidence or [],
        "blocked_reasons": blocked_reasons or [],
        "next_actions": next_actions or [],
        "provenance": provenance if isinstance(provenance, dict) else {},
    }
    doc.update(extra or {})
    return doc


def blocked_envelope(tool: str, reasons: list[str], *,
             scope: str = "static",
             next_actions: list[str] | None = None,
             provenance: dict[str, Any] | None = None,
             run_id: str | None = None,
             run_dir: str | None = None) -> dict[str, Any]:
    return _envelope(tool, "blocked", run_id=run_id, run_dir=run_dir,
                     scope=scope, blocked_reasons=list(reasons),
                     next_actions=list(next_actions or []),
                     provenance=provenance)


def _model_digest(model_dir: str | None) -> str | None:
    """Hash sorted TMDL bytes under a model dir; None when absent/empty."""
    if not model_dir:
        return None
    try:
        root = Path(model_dir)
        files = sorted(p for p in root.rglob("*.tmdl") if p.is_file()
                       and not p.is_symlink())
    except OSError:
        return None
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        try:
            content = path.read_bytes()
        except OSError:
            return None
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _source_provenance(report_dir: str | None,
                       model_dir: str | None) -> tuple[dict[str, Any], list[str]]:
    """Provenance digests for report/model sources; (provenance, issues)."""
    provenance: dict[str, Any] = {"source_sha256": None,
                                  "model_sha256": None}
    issues: list[str] = []
    if report_dir:
        try:
            from .pbir import source_digest

            provenance["source_sha256"] = source_digest(Path(report_dir))
        except OSError as exc:
            issues.append(f"unreadable report: {type(exc).__name__}: {exc}")
    if model_dir:
        digest = _model_digest(model_dir)
        if digest is None:
            issues.append(f"unreadable model: {model_dir}")
        provenance["model_sha256"] = digest
    return provenance, issues


def _require_report_or_facts(report_dir: Any, facts: Any) -> str | None:
    if (report_dir is None) == (facts is None):
        return "provide exactly one of report_dir or facts"
    if report_dir is not None and not isinstance(report_dir, str):
        return "report_dir must be a string path"
    if facts is not None and not isinstance(facts, dict):
        return "facts must be an object"
    return None


def inspect_report(report_dir: str, model_dir: str | None = None,
                   config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Measure check-ready facts for a report; envelope with ``facts``.

    ``config`` supplies provenance context only (no rule thresholds in
    this lane). Never raises on bad input.
    """
    from .config import default_config
    from .powerbi.measure import measure_report

    config = config if isinstance(config, dict) else default_config()
    if not isinstance(report_dir, str) or not report_dir:
        return blocked_envelope("vqs.inspect", ["report_dir must be a nonempty path"])
    if model_dir is not None and not isinstance(model_dir, str):
        return blocked_envelope("vqs.inspect", ["model_dir must be a string path"])
    provenance, issues = _source_provenance(report_dir, model_dir)
    if issues:
        return blocked_envelope("vqs.inspect", issues, provenance=provenance,
                        next_actions=["fix the unreadable sources and retry"])
    try:
        facts = measure_report(report_dir, model_dir)
    except (OSError, ValueError) as exc:
        return blocked_envelope("vqs.inspect", [f"unreadable report: {exc}"],
                        provenance=provenance,
                        next_actions=["fix the unreadable sources and retry"])
    provenance["config_schema"] = (config or {}).get("schema_version")
    coverage = facts.get("coverage", {})
    raw_issues = (coverage.get("issues", [])
                  if isinstance(coverage, dict) else [])
    blockers = _blocking_coverage(raw_issues)
    if blockers:
        parsed = (coverage.get("parsed_pages", "?"),
                  coverage.get("parsed_visuals", "?"))
        reasons = [
            (f"coverage: {parsed[0]} pages / {parsed[1]} visuals measured; "
             f"{len(blockers)} blocking coverage issues"),
            *(_coverage_reason(issue) for issue in blockers)]
        blocked = blocked_envelope(
            "vqs.inspect", reasons, provenance=provenance,
            next_actions=["fix the coverage gaps and retry"])
        blocked["facts"] = facts
        blocked["coverage"] = coverage if isinstance(coverage, dict) else {}
        return blocked
    return _envelope("vqs.inspect", "pass",
                     coverage=facts.get("coverage", {}),
                     provenance=provenance,
                     next_actions=["review the facts with vqs.review"],
                     extra={"facts": facts})


def _check_scope(scope: Any, state: Any,
                 config: dict[str, Any]) -> str | None:
    if scope not in REVIEW_SCOPES:
        return f"scope must be one of {', '.join(REVIEW_SCOPES)}"
    states = config.get("supported_states", ["default"])
    if state not in states:
        return f"state {state!r} is not in supported_states {states!r}"
    if state != "default":
        return (f"state {state!r} has no implemented semantics; "
                "only the default state is supported")
    return None


def _run_id_error(run_id: object) -> str | None:
    """Reject run IDs that are not confined single segments (F24)."""
    if not isinstance(run_id, str) or not run_id or "\x00" in run_id:
        return f"run_id must be a nonempty string: {run_id!r}"
    if ("/" in run_id or "\\" in run_id or ":" in run_id
            or run_id in (".", "..") or Path(run_id).name != run_id
            or Path(run_id).is_absolute()):
        return f"run_id escapes the run root: {run_id!r}"
    return None

def _read_manifest(run_root: str, run_id: str) -> tuple[dict | None, str | None]:
    problem = _run_id_error(run_id)
    if problem is not None:
        return None, problem
    try:
        root = Path(run_root).resolve()
        run_dir = (Path(run_root) / run_id).resolve()
    except OSError as exc:
        return None, f"unknown run {run_id!r}: {type(exc).__name__}"
    if run_dir != root and root not in run_dir.parents:
        return None, f"run {run_id!r} escapes the run root"
    try:
        text = (run_dir / "manifest.json").read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        return None, f"unknown run {run_id!r}: {type(exc).__name__}"
    if not isinstance(data, dict):
        return None, f"run manifest is not an object: {run_id!r}"
    return data, None


def review_report(*, report_dir: str | None = None,
                  model_dir: str | None = None,
                  facts: dict[str, Any] | None = None,
                  scope: str = "static", state: str = "default",
                  config: dict[str, Any] | None = None,
                  run_root: str = ".vqs-runs",
                  run_id: str | None = None,
                  resume_from: str | None = None) -> dict[str, Any]:
    """Review measured sources to a sealed verdict; static scope is live.

    ``desktop``/``release`` scopes honestly block (runtime adapters are
    Task 5); ``resume_from`` revalidates sealed provenance before a fresh
    run and reports changed dependencies instead of resuming blind.
    Never raises on bad input.
    """
    from .config import default_config

    config = config if isinstance(config, dict) else default_config()
    problem = _require_report_or_facts(report_dir, facts)
    if problem is not None:
        return blocked_envelope("vqs.review", [problem])
    scope_problem = _check_scope(scope, state, config)
    if scope_problem is not None:
        return blocked_envelope("vqs.review", [scope_problem])
    if scope in ("desktop", "release"):
        if not config.get("data_permissions", {}).get("allow_desktop", False):
            return blocked_envelope(
                "vqs.review",
                [f"{scope} scope needs data_permissions.allow_desktop"],
                scope=scope,
                next_actions=["grant desktop permission in vqs.json or use static scope"])
        return blocked_envelope(
            "vqs.review",
            [f"{scope} scope needs runtime adapters (Task 5, WP-03/WP-07)"],
            scope=scope,
            next_actions=["use static scope until adapters land"])
    provenance: dict[str, Any] = {"source_sha256": None,
                                  "model_sha256": None,
                                  "config_schema": config.get("schema_version")}
    if facts is None:
        assert report_dir is not None
        provenance, issues = _source_provenance(report_dir, model_dir)
        provenance["config_schema"] = config.get("schema_version")
        if issues:
            return blocked_envelope("vqs.review", issues, provenance=provenance,
                            next_actions=["fix the unreadable sources and retry"])
        inspected = inspect_report(report_dir, model_dir, config)
        if inspected["verdict"] == "blocked":
            inspected["tool"] = "vqs.review"
            return inspected
        facts = inspected["facts"]
    merged = dict(facts)
    oracles = list(merged.get("oracles", [])) if isinstance(
        merged.get("oracles", []), list) else []
    questions = config.get("questions", [])
    for question in questions if isinstance(questions, list) else [questions]:
        oracles.append({"question": question} if isinstance(question, str)
                       else question)
    # Config oracles pass through unfiltered: malformed entries must
    # block in _run_oracle, never vanish here.
    extra_oracles = config.get("oracles", [])
    oracles.extend(extra_oracles if isinstance(extra_oracles, list)
                   else [extra_oracles])
    if oracles:
        merged["oracles"] = oracles
    provenance["facts_sha256"] = hashlib.sha256(json.dumps(
        merged, sort_keys=True, ensure_ascii=False, default=str).encode(
            "utf-8")).hexdigest()
    if resume_from is not None:
        prior, error = _read_manifest(run_root, resume_from)
        if error is not None:
            return blocked_envelope("vqs.review", [error], provenance=provenance)
        sealed = (prior.get("artifacts") or {}) if isinstance(prior, dict) else {}
        if not isinstance(sealed, dict) or "source_sha256" not in sealed:
            return blocked_envelope(
                "vqs.review",
                [f"prior run {resume_from!r} has no sealed provenance"],
                provenance=provenance)
        seal_findings = verify_seal(Path(run_root) / resume_from)
        if seal_findings:
            rule = seal_findings[0].get("rule", "unknown")
            return blocked_envelope(
                "vqs.review",
                [f"prior run {resume_from!r} seal invalid: {rule}"],
                provenance=provenance)
        if "facts_sha256" not in sealed:
            return blocked_envelope(
                "vqs.review",
                [f"prior run {resume_from!r} has no sealed facts digest"],
                provenance=provenance)
        changed = [name for name in ("source_sha256", "model_sha256",
                                     "facts_sha256")
                   if sealed.get(name) != provenance.get(name)]
        if changed:
            return blocked_envelope(
                "vqs.review",
                [(f"provenance changed since {resume_from!r}: "
                 f"{', '.join(changed)}; refusing blind resume")],
                provenance=provenance,
                next_actions=["re-run without resume_from to accept the new sources"])
        prior_bindings = prior.get("bindings") or {}
        if not isinstance(prior_bindings, dict) or not prior_bindings.get("config_sha256"):
            return blocked_envelope(
                "vqs.review",
                [f"prior run {resume_from!r} has no sealed config binding"],
                provenance=provenance)
        if prior_bindings.get("config_sha256") != _canonical_sha256(config):
            return blocked_envelope(
                "vqs.review",
                [(f"effective config changed since {resume_from!r}; "
                  "refusing blind resume")],
                provenance=provenance,
                next_actions=["re-run without resume_from to accept the new config"])
    manifest_extra = {"resumed_from": resume_from} if resume_from else None
    result = run_check(merged, Path(run_root), run_id,
                       artifacts={"source_sha256": provenance["source_sha256"],
                                  "model_sha256": provenance["model_sha256"],
                                  "facts_sha256": provenance["facts_sha256"]},
                       manifest_extra=manifest_extra, config=config)
    if result["verdict"] == "blocked" and result.get("run_dir") is None:
        return blocked_envelope("vqs.review",
                        [f.get("reason", f.get("check", "?"))
                         for f in result.get("findings", [])],
                        provenance=provenance)
    manifest = result.get("manifest", {})
    evidence = [{"kind": "sealed_run", "run_id": result.get("run_id"),
                 "verdict_sha256": (manifest.get("artifacts") or {}).get(
                     "verdict_sha256")}]
    return _envelope("vqs.review", result["verdict"],
                     run_id=result.get("run_id"),
                     run_dir=result.get("run_dir"), scope=scope,
                     coverage=merged.get("coverage", {}),
                     findings=result.get("findings", []),
                     evidence=evidence, provenance=provenance,
                     next_actions=["inspect run detail with vqs.run_status"])


def run_status_report(run_root: str, run_id: str) -> dict[str, Any]:
    """Report a sealed run's status, verdict, and event trail; never raises."""
    from .run_store import read_events, run_status

    if not isinstance(run_root, str) or not isinstance(run_id, str):
        return blocked_envelope("vqs.run_status",
                        ["run_root and run_id must be strings"])
    run_dir = Path(run_root) / run_id
    manifest, error = _read_manifest(run_root, run_id)
    if error is not None:
        return blocked_envelope("vqs.run_status", [error])
    seal_findings = verify_seal(run_dir)
    if seal_findings:
        rule = seal_findings[0].get("rule", "unknown")
        return blocked_envelope("vqs.run_status", [f"run {run_id!r} seal invalid: {rule}"])
    try:
        events = read_events(run_dir)
        status = run_status(run_dir)
    except (OSError, ValueError) as exc:
        return blocked_envelope("vqs.run_status",
                        [f"unreadable run {run_id!r}: {exc}"])
    verdict = None
    for event in reversed(events):
        if isinstance(event, dict) and event.get("kind") in (
                "completed", "failed", "blocked"):
            verdict = event.get("verdict", status)
            break
    verdict = verdict if verdict in ("pass", "fail", "blocked") else "blocked"
    return _envelope("vqs.run_status", verdict, run_id=run_id,
                     run_dir=str(run_dir),
                     evidence=[{"kind": "sealed_run", "run_id": run_id,
                                "verdict_sha256": (manifest.get("artifacts")
                                                   or {}).get("verdict_sha256")}],
                     provenance={"manifest": manifest},
                     extra={"status": status, "event_count": len(events),
                            "events": events[-20:]})


def propose_candidates(run_root: str, run_id: str) -> dict[str, Any]:
    """Triage a sealed review run into plan-eligible work items.

    Reads the sealed findings artifact (never the live sources), so the
    triage provably matches the reviewed verdict. There is no automatic
    plan author: each actionable item needs an owner-authored plan that
    vqs.repair validates before executing.
    """
    manifest, error = _read_manifest(run_root, run_id)
    if error is not None:
        return blocked_envelope("vqs.propose", [error])
    assert manifest is not None
    seal_findings = verify_seal(Path(run_root) / run_id)
    if seal_findings:
        rule = seal_findings[0].get("rule", "unknown")
        return blocked_envelope("vqs.propose",
                        [f"run {run_id!r} seal invalid: {rule}"])
    if manifest.get("pipeline") != "vqs.check/1":
        return blocked_envelope(
            "vqs.propose",
            [(f"run {run_id!r} is not a sealed review run "
              f"(pipeline {manifest.get('pipeline')!r})")],
            run_id=run_id, run_dir=str(Path(run_root) / run_id))
    entry = (manifest.get("artifacts") or {}).get("findings")
    if not (isinstance(entry, dict)
            and isinstance(entry.get("sha256"), str)
            and isinstance(entry.get("path"), str)):
        return blocked_envelope(
            "vqs.propose",
            [(f"run {run_id!r} predates persisted findings; "
              "re-run review to propose")],
            run_id=run_id, run_dir=str(Path(run_root) / run_id))
    try:
        findings = json.loads((Path(run_root) / run_id / entry["path"]
                               ).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return blocked_envelope(
            "vqs.propose",
            [f"run {run_id!r} findings unreadable: {exc}"],
            run_id=run_id, run_dir=str(Path(run_root) / run_id))
    if not isinstance(findings, list):
        return blocked_envelope("vqs.propose",
                        [f"run {run_id!r} findings are not a list"],
                        run_id=run_id,
                        run_dir=str(Path(run_root) / run_id))
    items = [{"check": item.get("check", "?"),
              "status": item.get("status", "unknown"),
              "needs_plan": item.get("status") in ("fail", "blocked")}
             for item in findings if isinstance(item, dict)]
    actionable = sum(1 for item in items if item["needs_plan"])
    return _envelope("vqs.propose", "pass", run_id=run_id,
                     run_dir=str(Path(run_root) / run_id),
                     findings=[{"check": item["check"],
                                "status": item["status"]} for item in items],
                     evidence=[{"kind": "triage", "run_id": run_id,
                                "items": len(items),
                                "actionable": actionable}],
                     next_actions=[
                         ("author an owner-approved plan for each actionable "
                          "finding (no automatic plan author is implemented)"),
                         "execute it with vqs.repair, then vqs.verify"],
                     extra={"work_items": items, "candidates": []})


def _repair_bindings(plan_sha: str) -> dict[str, Any]:
    """Seal bindings for a repair run: plan input, policy, tool."""
    return {"input_sha256": plan_sha, "policy_version": POLICY_VERSION,
            "tool": "vqs.repair/1", "config_sha256": None}


def repair_candidate(plan_path: str, original: str,
                     candidate_root: str, *,
                     run_root: str = ".vqs-runs",
                     run_id: str | None = None) -> dict[str, Any]:
    """Validate a repair plan, execute it, and seal the repair run.

    Validation failures fail here without touching the filesystem.
    Execution refuses half-applied candidates (the engine removes only
    owned partial copies). The sealed run binds the plan, the
    before/after digests, and the applied edits for vqs.verify.
    """
    from .repair.allowlist import validate_plan

    for label, value in (("plan_path", plan_path), ("original", original),
                         ("candidate_root", candidate_root)):
        if not isinstance(value, str) or not value:
            return blocked_envelope("vqs.repair", [f"{label} must be a nonempty path"])
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return blocked_envelope("vqs.repair", [f"unreadable plan: {exc}"])
    if not isinstance(plan, dict):
        return blocked_envelope("vqs.repair", ["plan document is not an object"])
    try:
        issues = validate_plan(plan, original, candidate_root)
    except (OSError, ValueError, TypeError) as exc:
        return blocked_envelope("vqs.repair", [f"plan validation failed: {exc}"])
    if issues:
        return _envelope("vqs.repair", "fail",
                         findings=[{"check": "plan", "status": "fail",
                                    "detail": {"issues": issues}}],
                         blocked_reasons=[],
                         next_actions=["fix the plan issues and retry"])
    return _execute_repair(plan, original, candidate_root, run_root, run_id)


def _execute_repair(plan: dict[str, Any], original: str,
                    candidate_root: str, run_root: str,
                    run_id: str | None) -> dict[str, Any]:
    """Run an already-validated plan and seal the outcome; never raises."""
    from .repair.execute import apply_plan

    if not isinstance(run_root, str) or not run_root:
        return blocked_envelope("vqs.repair",
                        ["run_root must be a nonempty path"])
    if run_id is not None and (not isinstance(run_id, str) or not run_id):
        return blocked_envelope("vqs.repair",
                        ["run_id must be a nonempty string"])
    rid = run_id or f"repair-{uuid.uuid4().hex[:12]}"
    plan_sha = _canonical_sha256(plan)
    try:
        sealed_run_dir = create_run(
            Path(run_root), rid,
            {"pipeline": "vqs.repair/1",
             "repair": {"original": os.path.realpath(original),
                        "candidate": os.path.realpath(candidate_root),
                        "plan_sha256": plan_sha}})
    except FileExistsError:
        return blocked_envelope("vqs.repair",
                        [f"Run already exists: {rid}"])
    except ValueError as exc:
        return blocked_envelope("vqs.repair",
                        [f"Unusable run id: {exc}"])
    append_event(sealed_run_dir, {"kind": "started",
                                  "plan_sha256": plan_sha})
    try:
        result = apply_plan(plan, original, candidate_root,
                            allow_missing_relocated_model=True)
    except Exception as exc:  # noqa: BLE001 - engine crash seals blocked
        append_event(sealed_run_dir, {"kind": "blocked", "verdict": "blocked"})
        seal_run(sealed_run_dir, "blocked",
                 artifacts={"plan_sha256": plan_sha},
                 bindings=_repair_bindings(plan_sha))
        return blocked_envelope(
            "vqs.repair",
            [f"repair execution crashed: {type(exc).__name__}: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir))
    if result.get("verdict") != "applied":
        append_event(sealed_run_dir, {"kind": "blocked", "verdict": "blocked"})
        seal_run(sealed_run_dir, "blocked",
                 artifacts={"plan_sha256": plan_sha},
                 bindings=_repair_bindings(plan_sha))
        stage = result.get("stage", "?")
        detail = result.get("reason")
        if detail is None:
            detail = json.dumps(result.get("issues", []), default=str)
        return blocked_envelope(
            "vqs.repair", [f"repair {stage}: {detail}"],
            run_id=rid, run_dir=str(sealed_run_dir),
            next_actions=[("fix the refusal cause and retry with a fresh "
                           "candidate root")])
    repairs_doc = {"edits": result.get("edits", []),
                   "affected_pages": result.get("affected_pages", []),
                   "before": result.get("before"),
                   "after": result.get("after"),
                   "source_sha256": result.get("source_sha256"),
                   "model": result.get("model", {"kind": "absent"})}
    try:
        repairs_bytes = json.dumps(repairs_doc, sort_keys=True,
                                   ensure_ascii=False, default=str).encode("utf-8")
        (sealed_run_dir / "repairs.json").write_bytes(repairs_bytes)
        repairs_sha = hashlib.sha256(repairs_bytes).hexdigest()
    except OSError as exc:
        shutil.rmtree(candidate_root, ignore_errors=True)
        append_event(sealed_run_dir, {"kind": "blocked", "verdict": "blocked"})
        seal_run(sealed_run_dir, "blocked",
                 artifacts={"plan_sha256": plan_sha},
                 bindings=_repair_bindings(plan_sha))
        return blocked_envelope(
            "vqs.repair", [f"cannot persist repair evidence: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir))
    append_event(sealed_run_dir, {"kind": "completed", "verdict": "pass"})
    seal_run(sealed_run_dir, "completed",
             artifacts={"plan_sha256": plan_sha,
                        "before": result.get("before"),
                        "after": result.get("after"),
                        "edits": {"sha256": repairs_sha,
                                  "path": "repairs.json"}},
             bindings=_repair_bindings(plan_sha))
    return _envelope(
        "vqs.repair", "pass", run_id=rid, run_dir=str(sealed_run_dir),
        findings=[{"check": "repair", "status": "pass"}],
        evidence=[{"kind": "sealed_repair", "run_id": rid,
                   "candidate": result.get("candidate"),
                   "before": result.get("before"),
                   "after": result.get("after"),
                   "source_sha256": result.get("source_sha256"),
                   "affected_pages": result.get("affected_pages", []),
                   "edits": len(result.get("edits", []))}],
        provenance={"plan_sha256": plan_sha, "original": original,
                    "candidate": result.get("candidate")},
        next_actions=["verify the candidate with vqs.verify"])


def _sealed_tree_problems(repairs: dict[str, Any], original: str,
                          candidate: str) -> list[dict]:
    """Current trees must still match the sealed before/after digests."""
    from .repair.execute import RepairError, tree_digest

    problems = []
    for side, path, key in (("original", original, "before"),
                            ("candidate", candidate, "after")):
        pinned = repairs.get(key)
        if not isinstance(pinned, str):
            problems.append({"rule": "sealed_identity_missing",
                             "side": side, "detail": f"no sealed {key} digest"})
            continue
        try:
            current = tree_digest(path)
        except RepairError as exc:
            problems.append({"rule": "sealed_identity_unreadable",
                             "side": side, "detail": str(exc)})
            continue
        if current != pinned:
            problems.append({"rule": "sealed_identity_mismatch",
                             "side": side, "sealed": pinned,
                             "current": current})
    return problems


def _sealed_model_problems(model_pin: Any, original: str,
                           candidate: str | None = None) -> list[dict]:
    """The sealed model identity must still hold (R19/D12).

    S16: both sides are rechecked — the original pin as before,
    plus the candidate-side model for byPath pins. A candidate
    model that appears or drifts after sealing (planted sibling
    models, post-apply edits) fails even when both trees are
    otherwise untouched; a still-absent candidate model stays
    legal under the relocation missing-model allowance.
    """
    from .pbir import resolved_model_digest
    from .repair.execute import RepairError, bypath_claim

    if not isinstance(model_pin, dict) or model_pin.get("kind") in (
            None, "absent"):
        return []
    problems: list[dict] = []
    if model_pin.get("kind") == "remote":
        try:
            _target, connection = bypath_claim(Path(original))
        except RepairError as exc:
            return [{"rule": "sealed_model_unresolvable",
                     "detail": str(exc)}]
        if connection != model_pin.get("connection"):
            problems.append({"rule": "sealed_model_mismatch",
                             "detail": "remote model claim changed since "
                                       "repair"})
        return problems
    if model_pin.get("kind") == "byPath":
        digest, rule, detail = resolved_model_digest(original)
        if digest != model_pin.get("digest"):
            problems.append({"rule": "sealed_model_mismatch",
                             "resolution": rule, "detail": detail,
                             "sealed": model_pin.get("digest"),
                             "current": digest})
        if candidate:
            candidate_digest, _rule, _detail = resolved_model_digest(
                candidate)
            if (candidate_digest is not None
                    and candidate_digest != model_pin.get("digest")):
                problems.append(
                    {"rule": "sealed_candidate_model_mismatch",
                     "detail": "candidate-side model appeared or drifted "
                               "after sealing",
                     "sealed": model_pin.get("digest"),
                     "current": candidate_digest})
        return problems
    return [{"rule": "sealed_model_unknown",
             "detail": f"unknown model pin kind: {model_pin.get('kind')!r}"}]


def _answers_problems(answers: Any) -> list[dict]:
    """Recorded answer rows must still match (R19 answers evidence)."""
    from .repair.answers import answers_preserved

    if answers is None:
        return []
    if not isinstance(answers, dict) or not isinstance(
            answers.get("questions"), dict):
        return [{"rule": "answers_evidence_malformed",
                 "detail": "answers must hold a questions object"}]
    problems = []
    for qid, question in answers["questions"].items():
        if not isinstance(question, dict):
            problems.append({"rule": "answers_evidence_malformed",
                             "question": qid,
                             "detail": "question evidence is not an object"})
            continue
        rows_before = question.get("rows_before")
        rows_after = question.get("rows_after")
        scope = question.get("scope")
        tolerance = question.get("tolerance")
        ordered = question.get("ordered", False)
        shape_ok = (
            isinstance(rows_before, list)
            and isinstance(rows_after, list)
            and isinstance(scope, dict)
            and isinstance(question.get("dax_sha256"), str)
            and (tolerance is None or isinstance(tolerance, dict))
            and isinstance(ordered, bool))
        if not shape_ok:
            problems.append({"rule": "answers_evidence_malformed",
                             "question": qid,
                             "detail": "question needs dax_sha256 str, "
                                       "scope object, rows_before/after "
                                       "lists, tolerance object|null, "
                                       "ordered bool"})
            continue
        scope_json = json.dumps(scope, sort_keys=True, ensure_ascii=False,
                                default=str)
        verdict = answers_preserved(scope_json, scope_json, rows_before,
                                    rows_after, tolerance, ordered)
        if verdict.get("verdict") != "pass":
            problems.append({"rule": "answer_rows_changed",
                             "question": qid,
                             "reason": verdict.get("reason",
                                                   "repair changed answers")})
    return problems


def _fail_problems(problems: list[dict], original: Any,
                   candidate: Any) -> dict[str, Any]:
    return _envelope(
        "vqs.verify", "fail",
        findings=[{"check": f"verify:{p.get('rule', '?')}",
                   "status": "fail", "detail": p}
                  for p in problems if isinstance(p, dict)],
        blocked_reasons=[],
        provenance={"original": original, "candidate": candidate},
        next_actions=["inspect the problems and re-repair"])


def verify_candidate(*, run_root: str | None = None,
                     run_id: str | None = None,
                     original: str | None = None,
                     candidate: str | None = None,
                     edits: list | None = None,
                     approved_removals: list[str] | None = None,
                     answers: dict | None = None
                     ) -> dict[str, Any]:
    """Verify a candidate differs solely by its declared edits.

    Either verify a sealed vqs.repair run (``run_root`` + ``run_id``)
    or compare explicit paths (``original`` + ``candidate`` + ``edits``).
    ``approved_removals`` holds owner-approved "page/visual" pairs.
    ``answers`` optionally carries recorded answer evidence
    (``{"questions": {qid: {dax_sha256, scope, rows_before/after,
    tolerance, ordered}}}``); any drifted answer fails. Sealed runs
    additionally re-check the sealed before/after tree digests and the
    pinned model identity against the current trees.
    """
    from .repair.regress import verify_candidate as compare

    sealed_repairs: dict[str, Any] | None = None
    approvals: set[str] | None = None
    if approved_removals is not None:
        if (not isinstance(approved_removals, list)
                or not all(isinstance(x, str)
                           for x in approved_removals)):
            return blocked_envelope("vqs.verify",
                            ["approved_removals must be a list of strings"])
        approvals = set(approved_removals)
    if run_id is not None:
        if not isinstance(run_root, str):
            return blocked_envelope("vqs.verify",
                            ["run_root must be a string when run_id is given"])
        manifest, error = _read_manifest(run_root, run_id)
        if error is not None:
            return blocked_envelope("vqs.verify", [error])
        assert manifest is not None
        seal_findings = verify_seal(Path(run_root) / run_id)
        if seal_findings:
            rule = seal_findings[0].get("rule", "unknown")
            return blocked_envelope("vqs.verify",
                            [f"run {run_id!r} seal invalid: {rule}"])
        if manifest.get("pipeline") != "vqs.repair/1":
            return blocked_envelope(
                "vqs.verify",
                [(f"run {run_id!r} is not a sealed repair run "
                  f"(pipeline {manifest.get('pipeline')!r})")])
        repair = manifest.get("repair") or {}
        original = repair.get("original")
        candidate = repair.get("candidate")
        entry = (manifest.get("artifacts") or {}).get("edits")
        if (not isinstance(original, str)
                or not isinstance(candidate, str)
                or not (isinstance(entry, dict)
                        and isinstance(entry.get("sha256"), str)
                        and isinstance(entry.get("path"), str))):
            return blocked_envelope(
                "vqs.verify",
                [(f"run {run_id!r} predates verifiable repair evidence; "
                  "re-run repair to verify")])
        try:
            repairs = json.loads((Path(run_root) / run_id / entry["path"]
                                  ).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return blocked_envelope(
                "vqs.verify",
                [f"run {run_id!r} repair evidence unreadable: {exc}"])
        edits = repairs.get("edits") if isinstance(repairs, dict) else None
        sealed_repairs = repairs if isinstance(repairs, dict) else None
    elif not (isinstance(original, str) and isinstance(candidate, str)):
        return blocked_envelope("vqs.verify",
                        ["provide run_id or original+candidate paths"])
    if not isinstance(edits, list):
        return blocked_envelope(
            "vqs.verify",
            ["provide the declared edits list to verify against"],
            next_actions=[("verify a sealed repair run, or pass the repair "
                           "edits explicitly")])
    if sealed_repairs is not None:
        identity = _sealed_tree_problems(sealed_repairs, original, candidate)
        if identity:
            return _fail_problems(identity, original, candidate)
    try:
        result = compare(original, candidate, edits, approvals)
    except Exception as exc:  # noqa: BLE001 - comparison crash blocks
        return blocked_envelope("vqs.verify",
                        [f"verification crashed: {type(exc).__name__}: {exc}"])
    if result.get("verdict") != "pass":
        problems = result.get("problems", [])
        return _fail_problems(problems, original, candidate)
    if sealed_repairs is not None:
        model_problems = _sealed_model_problems(sealed_repairs.get("model"),
                                                original, candidate)
        if model_problems:
            return _fail_problems(model_problems, original, candidate)
    answer_problems = _answers_problems(answers)
    if answer_problems:
        return _fail_problems(answer_problems, original, candidate)
    return _envelope(
        "vqs.verify", "pass",
        findings=[{"check": "verify", "status": "pass"}],
        evidence=[{"kind": "verification",
                   "checks": result.get("checks", [])}],
        provenance={"original": original, "candidate": candidate})


def render_report(envelope: dict[str, Any]) -> str:
    """Render a readable local report from a tool envelope; never raises."""
    try:
        if not isinstance(envelope, dict):
            raise TypeError("envelope is not an object")
        lines = [(f"# VQS {envelope.get('tool', '?')} — "
                  f"{envelope.get('verdict', '?')}"),
                 "",
                 (f"schema: {envelope.get('schema_version', '?')}  "
                  f"scope: {envelope.get('scope', '?')}  "
                  f"run: {envelope.get('run_id', 'none')}")]
        provenance = envelope.get("provenance", {})
        if isinstance(provenance, dict) and provenance:
            lines.append("provenance: " + ", ".join(
                f"{k}={v}" for k, v in sorted(provenance.items())
                if k != "manifest" and k != "config_schema"))
        lines += ["", "## Findings"]
        findings = envelope.get("findings", [])
        if not findings:
            lines.append("(none)")
        for item in findings if isinstance(findings, list) else []:
            if not isinstance(item, dict):
                continue
            location = item.get("location") or {}
            where = "/".join(str(location.get(k, "")) for k in
                             ("page", "visual") if location.get(k))
            lines.append(f"- [{item.get('status', '?')}] "
                         f"{item.get('check', '?')}"
                         f"{' @ ' + where if where else ''} "
                         f"(severity {item.get('severity', '?')})")
        lines += ["", "## Coverage"]
        coverage = envelope.get("coverage", {})
        lines.append(json.dumps(coverage, indent=2, ensure_ascii=False)
                     if coverage else "(none recorded)")
        lines += ["", "## Blocked reasons"]
        reasons = envelope.get("blocked_reasons", [])
        lines.append(chr(10).join(f"- {r}" for r in reasons) if reasons
                     else "(none)")
        lines += ["", "## Next actions"]
        actions = envelope.get("next_actions", [])
        lines.append(chr(10).join(f"- {a}" for a in actions) if actions
                     else "(none)")
        lines += ["", "## Diffs", "(none recorded — no candidate supplied)"]
        return chr(10).join(lines) + chr(10)
    except (TypeError, ValueError, AttributeError) as exc:
        return f"# VQS report unavailable: {exc}\n"

