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

# R6-DEC-02: seal keys only the producer may emit. Caller-supplied
# values for these are stripped from artifacts/manifest_extra, so
# gate/status/control/pipeline identity can never be smuggled into a
# seal through caller extras.
RESERVED_ARTIFACT_KEYS = frozenset({
    "verdict_sha256", "findings", "envelope_sha256", "gate", "status",
    "control", "observation",
})
RESERVED_MANIFEST_EXTRA_KEYS = frozenset({
    "pipeline", "run_id", "status", "sealed", "sealed_sha256",
    "bindings", "artifacts", "environment", "event_count",
    "events_sha256",
})
# R6-DEC-02: the sole gate static checks can observe. Sealed in
# artifacts.observation; vqs.acceptance pins the same value in
# PRODUCER_GATE_CAPABILITY (agreement covered by R6-E02 tests).
STATIC_OBSERVATION_GATE = "G0"

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _is_hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in _HEX64 for char in value))


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
              config: dict[str, Any] | None = None,
              evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run every requested check and seal the manifest; see module docstring.

    Optional sealed provenance: ``artifacts``/``environment`` merge into
    the sealed manifest (verdict digest always present); ``manifest_extra``
    merges into the run manifest (e.g. resume links). R6-DEC-02:
    reserved seal keys (gate/status/control/pipeline/observation
    identity) are stripped from caller extras — only producer-emitted
    values seal. The seal always carries the producer observation
    (gate G0, actual verdict status, no controls): static checks
    observe source/contract facts only. With ``evidence``
    (``source_sha256`` hex plus optional ``data_scope`` dict), the run
    also emits its G0 evidence envelope under ``<run_root>/objects/``
    and binds the digest in the seal; gate/status always derive from
    the actual verdict, never from caller labels. The result carries
    ``envelope_sha256`` (None without ``evidence``).
    """
    if not isinstance(facts, dict):
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "facts", "status": "blocked",
                              "reason": "Facts document is not an object"}]}
    if evidence is not None and (
            not isinstance(evidence, dict)
            or not _is_hex64(evidence.get("source_sha256"))
            or (evidence.get("data_scope") is not None
                and not isinstance(evidence.get("data_scope"), dict))):
        return {"verdict": "blocked", "run_dir": None, "run_id": run_id,
                "envelope_sha256": None,
                "findings": [{"check": "evidence", "status": "blocked",
                              "reason": "Evidence needs source_sha256 hex "
                                        "plus an optional data_scope object"}]}
    run_id = run_id or f"check-{uuid.uuid4().hex[:12]}"
    manifest = {"pipeline": "vqs.check/1"}
    manifest.update({key: value for key, value in (manifest_extra or {}).items()
                     if key not in RESERVED_MANIFEST_EXTRA_KEYS})
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
    sealed_artifacts = {key: value for key, value in (artifacts or {}).items()
                        if key not in RESERVED_ARTIFACT_KEYS}
    sealed_artifacts["verdict_sha256"] = digest
    sealed_artifacts["observation"] = {
        "gate": STATIC_OBSERVATION_GATE, "status": verdict,
        "controls": [], "input_sha256": _canonical_sha256(facts)}
    # R6-DEC-02: the acceptance contract binds the seal's top-level
    # gate/status/control (run_acceptance reads manifest artifacts, not
    # the nested observation). Caller values were stripped above; the
    # producer always emits the actual gate and actual verdict here, so
    # a genuine observation clears exactly G0 without caller help.
    sealed_artifacts["gate"] = STATIC_OBSERVATION_GATE
    sealed_artifacts["status"] = verdict
    sealed_artifacts["control"] = None
    if findings_sha256 is not None:
        sealed_artifacts["findings"] = {"sha256": findings_sha256,
                                        "path": "findings.json"}
    # R6-DEC-02: the run emits its own G0 envelope (gate/status from
    # the actual verdict only) and binds it in the seal, so a genuine
    # static observation is usable for its narrow capability without
    # any caller-manufactured binding.
    envelope_sha: str | None = None
    if evidence is not None:
        envelope: dict[str, Any] = {
            "source_sha256": evidence["source_sha256"],
            "environment": dict(environment or {}),
            "producer": {"run_id": run_id,
                         "gate": STATIC_OBSERVATION_GATE,
                         "status": verdict, "control": None},
            "result": {"gate": STATIC_OBSERVATION_GATE,
                       "status": verdict},
        }
        if isinstance(evidence.get("data_scope"), dict):
            envelope["data_scope"] = dict(evidence["data_scope"])
        raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
        envelope_sha = hashlib.sha256(raw).hexdigest()
        try:
            objects = Path(run_root) / "objects"
            objects.mkdir(parents=True, exist_ok=True)
            (objects / envelope_sha).write_bytes(raw)
        except OSError as exc:
            findings.append({"check": "evidence", "status": "blocked",
                             "reason": f"cannot emit envelope: {exc}"})
            return {"verdict": "blocked", "run_dir": str(run_dir),
                    "run_id": run_id, "envelope_sha256": None,
                    "findings": findings, "manifest": None}
        sealed_artifacts["envelope_sha256"] = envelope_sha
    bindings = {"input_sha256": _canonical_sha256(facts), "policy_version": POLICY_VERSION, "tool": "vqs.check/1",
                "config_sha256": _canonical_sha256(config) if isinstance(config, dict) else None}
    manifest = seal_run(run_dir, terminal, artifacts=sealed_artifacts,
                        environment=environment, bindings=bindings)
    return {"verdict": verdict, "run_dir": str(run_dir), "run_id": run_id,
            "envelope_sha256": envelope_sha,
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
             run_dir: str | None = None,
             extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return _envelope(tool, "blocked", run_id=run_id, run_dir=run_dir,
                     scope=scope, blocked_reasons=list(reasons),
                     next_actions=list(next_actions or []),
                     provenance=provenance, extra=extra)


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


def merge_review_facts(facts: dict[str, Any],
                       config: dict[str, Any]) -> dict[str, Any]:
    """Merge configured questions/oracles into review facts (deterministic).

    Shared by ``review_report`` and the ``vqs.run`` coordinator so both
    seal the identical merged document and digest. Config oracles pass
    through unfiltered: malformed entries must block in ``_run_oracle``,
    never vanish here.
    """
    merged = dict(facts)
    oracles = list(merged.get("oracles", [])) if isinstance(
        merged.get("oracles", []), list) else []
    questions = config.get("questions", [])
    for question in questions if isinstance(questions, list) else [questions]:
        oracles.append({"question": question} if isinstance(question, str)
                       else question)
    extra_oracles = config.get("oracles", [])
    oracles.extend(extra_oracles if isinstance(extra_oracles, list)
                   else [extra_oracles])
    if oracles:
        merged["oracles"] = oracles
    return merged


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
        if report_dir is None:
            return blocked_envelope(
                "vqs.review",
                [(f"{scope} scope needs a live report_dir; facts alone "
                  "prove no runtime (Task 5, WP-03/WP-07)")],
                scope=scope,
                next_actions=["provide the live report directory"])
        from vqs.coordinator import bridge_present, run_workflow

        if not bridge_present():
            return blocked_envelope(
                "vqs.review",
                [(f"{scope} scope needs the Desktop Bridge "
                  "(powerbi-desktop not found); no runtime evidence can "
                  "be captured (Task 5, WP-03/WP-07)")],
                scope=scope,
                next_actions=["install the Bridge or use static scope"])
        return run_workflow(report_dir=report_dir, model_dir=model_dir,
                            mode="review", scope=scope, config=config,
                            run_root=run_root, run_id=run_id,
                            resume_from=resume_from)
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
    merged = merge_review_facts(facts, config)
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


def propose_candidates(run_root: str, run_id: str,
                       facts: dict[str, Any] | None = None
                       ) -> dict[str, Any]:
    """Triage a sealed review run into plan-eligible work items.

    Reads the sealed findings artifact (never the live sources), so the
    triage provably matches the reviewed verdict. Caller facts are
    accepted only when their digest matches the sealed run: a stale
    finding/source blocks plan generation. Findings VQS can bind safely
    become deterministic typed candidates with a complete plan document;
    everything else becomes needs_owner_decision / unsupported, never a
    guessed value. vqs.repair validates the plan before executing.
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
    artifacts = manifest.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    bindings = manifest.get("bindings")
    bindings = bindings if isinstance(bindings, dict) else {}
    expected = bindings.get("input_sha256") or artifacts.get("facts_sha256")
    if facts is not None:
        if not isinstance(facts, dict):
            return blocked_envelope(
                "vqs.propose", ["facts must be an object"],
                run_id=run_id, run_dir=str(Path(run_root) / run_id))
        if not isinstance(expected, str):
            return blocked_envelope(
                "vqs.propose",
                [(f"run {run_id!r} predates facts binding; "
                  "re-run review to propose")],
                run_id=run_id, run_dir=str(Path(run_root) / run_id))
        if _canonical_sha256(facts) != expected:
            return blocked_envelope(
                "vqs.propose",
                [(f"stale finding/source: supplied facts do not match "
                  f"the sealed run {run_id!r}; re-run review on the "
                  "current sources")],
                run_id=run_id, run_dir=str(Path(run_root) / run_id))
    from vqs.repair.synthesize import synthesize_plan

    source_sha = artifacts.get("source_sha256")
    result = synthesize_plan(
        findings, facts, source_run_id=run_id,
        source_sha256=source_sha if isinstance(source_sha, str) else None,
        facts_sha256=expected if isinstance(expected, str) else None)
    items = [{"check": item.get("check", "?"),
              "status": item.get("status", "unknown"),
              "needs_plan": item.get("status") in ("fail", "blocked")}
             for item in findings if isinstance(item, dict)]
    actionable = sum(1 for item in items if item["needs_plan"])
    plan = result["plan"]
    if plan is not None:
        next_actions = [
            ("apply the synthesized plan with vqs.repair against a "
             "disposable candidate, then vqs.verify"),
            "unresolved findings still need an owner-authored plan"]
    else:
        next_actions = [
            ("author an owner-approved plan for each actionable finding "
             "(no safe automatic candidate was synthesizable)"),
            "execute it with vqs.repair, then vqs.verify"]
    return _envelope("vqs.propose", "pass", run_id=run_id,
                     run_dir=str(Path(run_root) / run_id),
                     findings=[{"check": item["check"],
                                "status": item["status"]} for item in items],
                     evidence=[{"kind": "triage", "run_id": run_id,
                                "items": len(items),
                                "actionable": actionable,
                                "synthesized": len(result["candidates"]),
                                "needs_decision": len(result["decisions"])}],
                     next_actions=next_actions,
                     extra={"work_items": items,
                            "candidates": result["candidates"],
                            "decisions": result["decisions"],
                            "plan": plan})


def _repair_bindings(plan_sha: str) -> dict[str, Any]:
    """Seal bindings for a repair run: plan input, policy, tool."""
    return {"input_sha256": plan_sha, "policy_version": POLICY_VERSION,
            "tool": "vqs.repair/1", "config_sha256": None}


def repair_candidate(plan_path: str, original: str,
                     candidate_root: str, *,
                     run_root: str = ".vqs-runs",
                     run_id: str | None = None,
                     authoring_backend: str = "auto",
                     authoring_timeout: int = 300,
                     authoring_allow_warnings: bool = False) -> dict[str, Any]:
    """Validate a repair plan, execute it, and seal the repair run.

    Validation failures fail here without touching the filesystem.
    Execution refuses half-applied candidates (the engine removes only
    owned partial copies). The sealed run binds the plan, the
    before/after digests, and the applied edits for vqs.verify.
    R6-E07: after the typed apply, the candidate report is validated
    through the selected authoring backend (``auto``/``microsoft``/
    ``direct``); Microsoft validation failures fail or block the
    repair without silent fallback, and the full authoring record is
    sealed plus reported. Schema validation is never Desktop/render
    approval.
    """
    from .repair.allowlist import validate_plan

    for label, value in (("plan_path", plan_path), ("original", original),
                         ("candidate_root", candidate_root)):
        if not isinstance(value, str) or not value:
            return blocked_envelope("vqs.repair", [f"{label} must be a nonempty path"])
    if authoring_backend not in ("auto", "microsoft", "direct"):
        return blocked_envelope(
            "vqs.repair",
            [(f"authoring_backend must be auto, microsoft, or direct, "
              f"got {authoring_backend!r}")])
    if (isinstance(authoring_timeout, bool)
            or not isinstance(authoring_timeout, int)
            or authoring_timeout <= 0):
        return blocked_envelope(
            "vqs.repair",
            [(f"authoring_timeout must be a positive int, "
              f"got {authoring_timeout!r}")])
    if not isinstance(authoring_allow_warnings, bool):
        return blocked_envelope(
            "vqs.repair",
            [("authoring_allow_warnings must be a bool, "
              f"got {authoring_allow_warnings!r}")])
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
    from .powerbi.author import preflight as author_preflight

    toolchain = author_preflight.check(authoring_backend)
    if toolchain["status"] != "pass":
        return blocked_envelope("vqs.repair",
                                [toolchain.get("reason", "authoring preflight blocked")],
                                extra={"authoring_preflight": toolchain})
    return _execute_repair(plan, original, candidate_root, run_root, run_id,
                           authoring_preflight=toolchain,
                           authoring_backend=authoring_backend,
                           authoring_timeout=authoring_timeout,
                           authoring_allow_warnings=authoring_allow_warnings)


def _execute_repair(plan: dict[str, Any], original: str,
                    candidate_root: str, run_root: str,
                    run_id: str | None, *,
                    authoring_preflight: dict[str, Any],
                    authoring_backend: str = "auto",
                    authoring_timeout: int = 300,
                    authoring_allow_warnings: bool = False) -> dict[str, Any]:
    """Run an already-validated plan and seal the outcome; never raises."""
    from .powerbi.author import adapter as author_adapter
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
                        "plan_sha256": plan_sha},
             "authoring_preflight": authoring_preflight})
    except FileExistsError:
        return blocked_envelope("vqs.repair",
                        [f"Run already exists: {rid}"])
    except ValueError as exc:
        return blocked_envelope("vqs.repair",
                        [f"Unusable run id: {exc}"])
    append_event(sealed_run_dir, {"kind": "started",
                                  "plan_sha256": plan_sha})
    try:
        # T10: no missing-model bypass on the public path — a repair
        # either materializes a complete identity-preserving candidate
        # or blocks before mutation; unresolved identity is not
        # equivalence.
        result = apply_plan(plan, original, candidate_root,
                            allow_missing_relocated_model=False)
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
                   "model": result.get("model", {"kind": "absent"}),
                   "workspace": result.get("workspace", {})}
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
    # R6-E07: Microsoft-guided authoring gate. The typed apply above
    # is unchanged; the candidate report is now validated through
    # the selected backend. Microsoft failures fail/block without
    # silent fallback; the candidate is preserved for inspection
    # and the full record is sealed plus reported.
    authoring = author_adapter.run_backend(
        result.get("candidate"), policy=authoring_backend,
        timeout=authoring_timeout,
        allow_warnings=authoring_allow_warnings,
        attestation=authoring_preflight)
    authoring["record"]["preflight"] = authoring_preflight
    if authoring["backend"] != authoring_preflight["validation_provider"]:
        authoring["verdict"] = "blocked"
        authoring["reason"] = "validation provider changed after preflight"
    elif (authoring["backend"] == "microsoft"
          and (authoring["record"].get("version")
               != authoring_preflight.get("cli", {}).get("version")
               or authoring["record"].get("probe", {}).get("path")
               != authoring_preflight.get("probe", {}).get("path"))):
        authoring["verdict"] = "blocked"
        authoring["reason"] = "Microsoft CLI version/path drift after preflight"
    from .powerbi.author.assurance import compose as compose_authoring_assurance

    authoring_assurance = compose_authoring_assurance(authoring_preflight, authoring)
    authoring["record"]["assurance"] = authoring_assurance
    if (authoring["verdict"] == "pass"
            and authoring_preflight["validation_provider"] == "microsoft"
            and authoring_assurance["structural_validation"] != "pass"):
        authoring["verdict"] = "blocked"
        authoring["reason"] = "Microsoft structural assurance not established"
        authoring["record"]["assurance"] = compose_authoring_assurance(
            authoring_preflight, authoring)
    try:
        authoring_bytes = json.dumps(
            authoring["record"], sort_keys=True, ensure_ascii=False,
            default=str).encode("utf-8")
        (sealed_run_dir / "authoring.json").write_bytes(authoring_bytes)
        authoring_sha = hashlib.sha256(authoring_bytes).hexdigest()
    except OSError as exc:
        record = dict(authoring["record"])
        record["seal_note"] = f"authoring record unsealed: {exc}"
        append_event(sealed_run_dir, {"kind": "blocked", "verdict": "blocked"})
        seal_run(sealed_run_dir, "blocked",
                 artifacts={"plan_sha256": plan_sha},
                 bindings=_repair_bindings(plan_sha))
        return blocked_envelope(
            "vqs.repair", [f"cannot persist authoring evidence: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir),
            extra={"authoring": record})
    seal_artifacts = {"plan_sha256": plan_sha,
                      "before": result.get("before"),
                      "after": result.get("after"),
                      "edits": {"sha256": repairs_sha,
                                "path": "repairs.json"},
                      "authoring": {"sha256": authoring_sha,
                                    "path": "authoring.json"}}
    repair_evidence = [{"kind": "sealed_repair", "run_id": rid,
                        "candidate": result.get("candidate"),
                        "before": result.get("before"),
                        "after": result.get("after"),
                        "source_sha256": result.get("source_sha256"),
                        "affected_pages": result.get("affected_pages", []),
                        "edits": len(result.get("edits", []))}]
    repair_provenance = {"plan_sha256": plan_sha, "original": original,
                         "candidate": result.get("candidate")}
    if authoring["verdict"] == "fail":
        append_event(sealed_run_dir, {"kind": "failed", "verdict": "fail"})
        seal_run(sealed_run_dir, "failed", artifacts=seal_artifacts,
                 bindings=_repair_bindings(plan_sha))
        return _envelope(
            "vqs.repair", "fail", run_id=rid, run_dir=str(sealed_run_dir),
            findings=[{"check": "authoring", "status": "fail",
                       "detail": {"reason": authoring["reason"]}}],
            evidence=repair_evidence, provenance=repair_provenance,
            next_actions=[("inspect the preserved candidate and the "
                             "sealed authoring record, fix the cause, and "
                             "retry with a fresh candidate root")],
            extra={"authoring": authoring["record"]})
    if authoring["verdict"] == "blocked":
        append_event(sealed_run_dir, {"kind": "blocked", "verdict": "blocked"})
        seal_run(sealed_run_dir, "blocked", artifacts=seal_artifacts,
                 bindings=_repair_bindings(plan_sha))
        return blocked_envelope(
            "vqs.repair", [f"repair authoring: {authoring['reason']}"],
            run_id=rid, run_dir=str(sealed_run_dir),
            next_actions=[("inspect the preserved candidate and the "
                             "sealed authoring record, then retry")],
            extra={"authoring": authoring["record"]})
    append_event(sealed_run_dir, {"kind": "completed", "verdict": "pass"})
    seal_run(sealed_run_dir, "completed", artifacts=seal_artifacts,
             bindings=_repair_bindings(plan_sha))
    return _envelope(
        "vqs.repair", "pass", run_id=rid, run_dir=str(sealed_run_dir),
        findings=[{"check": "repair", "status": "pass"}],
        evidence=repair_evidence, provenance=repair_provenance,
        next_actions=["verify the candidate with vqs.verify"],
        extra={"authoring": authoring["record"]})


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
    otherwise untouched. T10: a missing candidate model (absent,
    deleted, or unreadable) fails too — unresolved identity is not
    equivalence; only genuinely model-less ("absent") and remote
    pins skip the candidate-side file check.
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
            if candidate_digest is None:
                problems.append(
                    {"rule": "sealed_candidate_model_missing",
                     "detail": "candidate-side model is absent, deleted, "
                               "or unreadable after sealing",
                     "sealed": model_pin.get("digest"),
                     "current": None})
            elif candidate_digest != model_pin.get("digest"):
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


def _sealed_repair_evidence(run_root: str, run_id: str, tool: str
                            ) -> tuple[dict[str, Any] | None,
                                       dict[str, Any] | None]:
    """Load a completed sealed repair run; (evidence, None) or (None, envelope).

    Evidence holds manifest, repairs doc, original, candidate, before,
    after, source_sha256, model, and edits. Anything unproven returns a
    blocked envelope: bad seal, wrong pipeline, unfinished run, or
    unreadable/missing repair evidence.
    """
    manifest, error = _read_manifest(run_root, run_id)
    if error is not None:
        return None, blocked_envelope(tool, [error])
    assert manifest is not None
    seal_findings = verify_seal(Path(run_root) / run_id)
    if seal_findings:
        rule = seal_findings[0].get("rule", "unknown")
        return None, blocked_envelope(
            tool, [f"run {run_id!r} seal invalid: {rule}"])
    if manifest.get("pipeline") != "vqs.repair/1":
        return None, blocked_envelope(
            tool, [(f"run {run_id!r} is not a sealed repair run "
                     f"(pipeline {manifest.get('pipeline')!r}")])
    if manifest.get("status") != "completed":
        return None, blocked_envelope(
            tool, [(f"run {run_id!r} is not a completed repair run "
                    f"(status {manifest.get('status')!r}); only completed "
                    "repairs verify at runtime or promote")])
    repair = manifest.get("repair") or {}
    original = repair.get("original")
    candidate = repair.get("candidate")
    entry = (manifest.get("artifacts") or {}).get("edits")
    if (not isinstance(original, str) or not isinstance(candidate, str)
            or not (isinstance(entry, dict)
                    and isinstance(entry.get("sha256"), str)
                    and isinstance(entry.get("path"), str))):
        return None, blocked_envelope(
            tool, [(f"run {run_id!r} predates verifiable repair evidence; "
                    "re-run repair")])
    try:
        repairs = json.loads((Path(run_root) / run_id / entry["path"]
                              ).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, blocked_envelope(
            tool, [f"run {run_id!r} repair evidence unreadable: {exc}"])
    if not isinstance(repairs, dict) or not isinstance(
            repairs.get("edits"), list):
        return None, blocked_envelope(
            tool, [f"run {run_id!r} repair evidence is not an object"])
    evidence = {"manifest": manifest, "repairs": repairs,
                "original": original, "candidate": candidate,
                "before": repairs.get("before"),
                "after": repairs.get("after"),
                "source_sha256": repairs.get("source_sha256"),
                "model": repairs.get("model", {"kind": "absent"}),
                "edits": repairs.get("edits", [])}
    return evidence, None


def _seal_terminal(run_dir: Path, kind: str, artifacts: dict,
                   bindings: dict) -> None:
    """Append the terminal event and seal; the seal itself never fails here."""
    append_event(run_dir, {"kind": kind})
    seal_run(run_dir, kind, artifacts=artifacts, bindings=bindings)


def verify_runtime(*, run_root: str, run_id: str,
                   pid: int | None = None, scale: int = 2,
                   wait_seconds: int = 60, reload_first: bool = True,
                   bridge: Any = None,
                   runtime_run_id: str | None = None) -> dict[str, Any]:
    """Verify the disposable candidate live in Desktop; never the original.

    Binds the given Desktop PID to the sealed candidate path (exact
    match, save state proven), optionally reloads it, captures it
    through the hardened capture path, and checks the capture against
    the sealed candidate digests. The original path is never opened,
    reloaded, or captured — a Desktop instance holding it refuses.
    Without a live Desktop capability the result is blocked with the
    exact missing piece; nothing is faked. Seals pipeline
    ``vqs.verify-runtime/1`` separately from technical repair evidence.
    """
    from .repair.execute import RepairError, tree_digest
    from .repair.runtime import (
        BridgeUnavailable,
        LocalBridgePort,
        bind_and_reload,
        bind_candidate_instance,
        capture_candidate,
        open_candidate_instance,
        reload_instance,
    )

    tool = "vqs.verify-runtime"
    if not isinstance(run_root, str) or not run_root:
        return blocked_envelope(tool, ["run_root must be a nonempty path"])
    if not isinstance(run_id, str) or not run_id:
        return blocked_envelope(tool, ["run_id must be a nonempty string"])
    if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int)):
        return blocked_envelope(tool, ["pid must be an int Desktop PID"])
    if scale not in (1, 2):
        return blocked_envelope(tool, [f"scale must be 1 or 2, not {scale!r}"])
    if (isinstance(wait_seconds, bool) or not isinstance(wait_seconds, int)
            or wait_seconds <= 0):
        return blocked_envelope(tool, ["wait_seconds must be a positive int"])
    if not isinstance(reload_first, bool):
        return blocked_envelope(tool, ["reload_first must be a bool"])
    if runtime_run_id is not None and (
            not isinstance(runtime_run_id, str) or not runtime_run_id):
        return blocked_envelope(tool, ["runtime_run_id must be a nonempty string"])
    evidence, envelope = _sealed_repair_evidence(run_root, run_id, tool)
    if envelope is not None:
        return envelope
    assert evidence is not None
    original = evidence["original"]
    candidate = evidence["candidate"]
    port = bridge
    if port is None:
        try:
            port = LocalBridgePort()
        except BridgeUnavailable as exc:
            return blocked_envelope(
                tool, [f"no live Desktop capability: {exc}"],
                next_actions=[("open the disposable candidate in Power BI "
                               "Desktop on a Bridge host and retry")],
                provenance={"repair_run": run_id, "candidate": candidate})
    rid = runtime_run_id or f"rt-{uuid.uuid4().hex[:12]}"
    try:
        sealed_run_dir = create_run(
            Path(run_root), rid,
            {"pipeline": "vqs.verify-runtime/1",
             "runtime": {"repair_run": run_id,
                         "candidate": os.path.realpath(candidate),
                         "candidate_digest": evidence["after"]}})
    except FileExistsError:
        return blocked_envelope(tool, [f"Run already exists: {rid}"])
    except ValueError as exc:
        return blocked_envelope(tool, [f"Unusable run id: {exc}"])
    bindings = {"input_sha256": _canonical_sha256(
        {"repair_run": run_id, "candidate": candidate,
         "candidate_digest": evidence["after"]}),
        "policy_version": POLICY_VERSION, "tool": "vqs.verify-runtime/1",
        "config_sha256": None}
    append_event(sealed_run_dir, {"kind": "started", "repair_run": run_id})
    provenance = {"repair_run": run_id, "candidate": candidate}
    owned = False
    if pid is None:
        if not callable(getattr(port, "open", None)):
            _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
            return blocked_envelope(
                tool, [("no Desktop PID given and the port cannot open the "
                        "disposable candidate; open the candidate in "
                        "Desktop and pass its exact --pid (the original "
                        "is never driven)")],
                run_id=rid, run_dir=str(sealed_run_dir),
                next_actions=[("open the disposable candidate in Desktop and "
                               "pass its exact --pid")],
                provenance=provenance)
        try:
            proof = open_candidate_instance(
                port, original, candidate,
                source_digest=evidence["source_sha256"],
                run_lease=rid, wait_seconds=wait_seconds)
        except BridgeUnavailable as exc:
            _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
            return blocked_envelope(
                tool, [f"candidate open failed: {exc}"],
                run_id=rid, run_dir=str(sealed_run_dir), provenance=provenance)
        instance = proof["instance"]
        owned = True
        provenance = {**provenance, "opened_pid": proof["opened_pid"],
                      "owned_by_run": True}
        if reload_first:
            try:
                instance = reload_instance(port, instance)
            except BridgeUnavailable as exc:
                _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
                return blocked_envelope(
                    tool, [str(exc)],
                    run_id=rid, run_dir=str(sealed_run_dir),
                    provenance=provenance)
    else:
        if reload_first:
            try:
                instance = bind_and_reload(port, original, candidate, pid,
                                           wait_seconds)
            except BridgeUnavailable as exc:
                _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
                text = str(exc)
                if not text.startswith((
                        "candidate reload refused",
                        "candidate binding failed")):
                    text = f"candidate binding failed: {text}"
                return blocked_envelope(
                    tool, [text],
                    run_id=rid, run_dir=str(sealed_run_dir),
                    provenance=provenance)
        else:
            try:
                instance = bind_candidate_instance(port, original, candidate,
                                                   pid, wait_seconds)
            except BridgeUnavailable as exc:
                _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
                return blocked_envelope(
                    tool, [f"candidate binding failed: {exc}"],
                    run_id=rid, run_dir=str(sealed_run_dir),
                    next_actions=[("open the disposable candidate in Desktop and "
                                    "pass its exact --pid")],
                    provenance=provenance)
        if reload_first:
            try:
                from .repair.runtime import bind_candidate_instance as rebind

                instance = rebind(port, original, candidate,
                                  int(instance["pid"]), wait_seconds)
            except BridgeUnavailable as exc:
                _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
                return blocked_envelope(
                    tool, [f"candidate binding failed after reload: {exc}"],
                    run_id=rid, run_dir=str(sealed_run_dir),
                    provenance=provenance)
    renders = sealed_run_dir / "renders"
    try:
        manifest = capture_candidate(
            candidate, str(renders), int(instance["pid"]), scale=scale,
            wait_seconds=wait_seconds, owned=owned)
    except (OSError, LookupError) as exc:
        _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
        return blocked_envelope(
            tool, [f"no verified candidate capture: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir), provenance=provenance)
    try:
        current = tree_digest(candidate)
    except RepairError as exc:
        _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
        return blocked_envelope(
            tool, [f"candidate unreadable after capture: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir), provenance=provenance)
    problems = []
    if current != evidence["after"]:
        problems.append({"rule": "runtime_candidate_drift",
                         "sealed": evidence["after"], "current": current})
    if manifest.get("source_sha256") != evidence["source_sha256"]:
        problems.append({"rule": "runtime_source_mismatch",
                         "sealed": evidence["source_sha256"],
                         "current": manifest.get("source_sha256")})
    problems += _sealed_model_problems(evidence["model"], original, candidate)
    runtime_doc = {
        "repair_run": run_id, "candidate": os.path.realpath(candidate),
        "candidate_digest": current,
        "source_sha256": manifest.get("source_sha256"),
        "pid": int(instance["pid"]),
        "owned_by_run": owned,
        "instance": {"report": instance.get("currentFilePath"),
                     "desktop_version": instance.get("desktopVersion")},
        "capture": {"renders": "renders",
                    "manifest_sha256": _canonical_sha256(manifest),
                    "calibration": manifest.get("calibration")},
        "problems": problems}
    try:
        runtime_bytes = json.dumps(runtime_doc, sort_keys=True,
                                   ensure_ascii=False, default=str
                                   ).encode("utf-8")
        (sealed_run_dir / "runtime.json").write_bytes(runtime_bytes)
        runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
        capture_bytes = json.dumps(manifest, sort_keys=True,
                                   ensure_ascii=False, default=str
                                   ).encode("utf-8")
        (sealed_run_dir / "capture-manifest.json").write_bytes(capture_bytes)
        capture_sha = hashlib.sha256(capture_bytes).hexdigest()
    except OSError as exc:
        _seal_terminal(sealed_run_dir, "blocked", {}, bindings)
        return blocked_envelope(
            tool, [f"cannot persist runtime evidence: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir), provenance=provenance)
    artifacts = {"runtime.json": {"sha256": runtime_sha,
                                  "path": "runtime.json"},
                 "capture-manifest.json": {"sha256": capture_sha,
                                           "path": "capture-manifest.json"}}
    if problems:
        _seal_terminal(sealed_run_dir, "failed", artifacts, bindings)
        return _envelope(
            tool, "fail", run_id=rid, run_dir=str(sealed_run_dir),
            findings=[{"check": f"runtime:{p.get('rule', '?')}",
                       "status": "fail", "detail": p} for p in problems],
            evidence=[{"kind": "sealed_runtime", "run_id": rid,
                       "candidate": candidate,
                       "candidate_digest": current}],
            provenance=provenance,
            next_actions=["inspect the problems and re-repair"])
    _seal_terminal(sealed_run_dir, "completed", artifacts, bindings)
    return _envelope(
        tool, "pass", run_id=rid, run_dir=str(sealed_run_dir),
        findings=[{"check": "runtime", "status": "pass"}],
        evidence=[{"kind": "sealed_runtime", "run_id": rid,
                   "candidate": candidate, "candidate_digest": current,
                   "pid": int(instance["pid"])}],
        provenance=provenance,
        next_actions=["promote with vqs.promote and owner approval"])


def promote_candidate(*, run_root: str, run_id: str, owner_approval: str,
                      runtime_run_id: str | None = None,
                      backup_dir: str | None = None,
                      desktop_recheck: bool = True, bridge: Any = None,
                      promote_run_id: str | None = None,
                      scope: str = "static") -> dict[str, Any]:
    """Promote a verified candidate onto the original; never silently.

    The requested promotion scope gates the evidence: static scope
    promotes on static verification only and says so; desktop scope
    needs a completed sealed runtime verification for the exact
    candidate plus a passing post-promotion Desktop recheck; release
    scope additionally needs a trusted reviewer authority bound to
    the exact candidate, and no such mechanism exists yet, so
    release promotion stays blocked however clean the runtime looks.

    Gates in order: explicit owner approval; completed sealed repair;
    original and candidate digests recomputed against the seal (any
    drift refuses); fresh structural verification plus model pin;
    optional runtime record binding (a failed or mismatched runtime
    record refuses); rename-swap with backup preservation; final source
    digest; Desktop reload/recheck when a live capability exists.
    Refusals before the swap seal blocked and touch nothing; a failed
    Desktop recheck after the swap seals failed with the rollback plan.
    Promotion evidence seals separately as ``vqs.promote/1``.
    """
    from .pbir import resolved_model_digest, source_digest
    from .repair.execute import RepairError, tree_digest
    from .repair.promote import PromoteError, swap_original_with_candidate
    from .repair.regress import verify_candidate as compare
    from .repair.runtime import BridgeUnavailable, LocalBridgePort

    tool = "vqs.promote"
    if not isinstance(run_root, str) or not run_root:
        return blocked_envelope(tool, ["run_root must be a nonempty path"])
    if not isinstance(run_id, str) or not run_id:
        return blocked_envelope(tool, ["run_id must be a nonempty string"])
    if (not isinstance(owner_approval, str) or not owner_approval.strip()):
        return blocked_envelope(
            tool, [("owner approval required: promotion never overwrites "
                    "silently; pass --owner-approval with an owner consent "
                    "string (identity plus reason). The string is recorded "
                    "consent, not an authenticated identity proof")])
    if scope not in REVIEW_SCOPES:
        return blocked_envelope(
            tool, [f"scope must be one of {sorted(REVIEW_SCOPES)}, got {scope!r}"])
    if runtime_run_id is not None and (
            not isinstance(runtime_run_id, str) or not runtime_run_id):
        return blocked_envelope(
            tool, ["runtime_run_id must be a nonempty string"])
    if backup_dir is not None and (
            not isinstance(backup_dir, str) or not backup_dir):
        return blocked_envelope(tool, ["backup_dir must be a nonempty path"])
    if not isinstance(desktop_recheck, bool):
        return blocked_envelope(tool, ["desktop_recheck must be a bool"])
    if promote_run_id is not None and (
            not isinstance(promote_run_id, str) or not promote_run_id):
        return blocked_envelope(tool, ["promote_run_id must be a nonempty string"])
    evidence, envelope = _sealed_repair_evidence(run_root, run_id, tool)
    if envelope is not None:
        return envelope
    assert evidence is not None
    original = evidence["original"]
    candidate = evidence["candidate"]
    provenance = {"repair_run": run_id, "original": original,
                  "candidate": candidate}
    try:
        current_original = tree_digest(original)
        current_candidate = tree_digest(candidate)
    except RepairError as exc:
        return blocked_envelope(tool, [f"promotion trees unreadable: {exc}"],
                                provenance=provenance)
    if current_original != evidence["before"]:
        return blocked_envelope(
            tool, [(f"original drifted since repair; promotion refused: "
                    f"{current_original} != {evidence['before']}")],
            provenance=provenance,
            next_actions=["re-run repair against the current original"])
    if current_candidate != evidence["after"]:
        return blocked_envelope(
            tool, [(f"candidate drifted since repair; promotion refused: "
                    f"{current_candidate} != {evidence['after']}")],
            provenance=provenance,
            next_actions=["re-run repair to seal the current candidate"])
    try:
        candidate_source = source_digest(Path(candidate))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return blocked_envelope(
            tool, [f"candidate source unreadable: {exc}"],
            provenance=provenance)
    if candidate_source != evidence["source_sha256"]:
        return blocked_envelope(
            tool, [("candidate source differs from the sealed repair source; "
                    "promotion refused")],
            provenance=provenance)
    try:
        comparison = compare(original, candidate, evidence["edits"], set())
    except Exception as exc:  # noqa: BLE001 - comparison crash blocks
        return blocked_envelope(
            tool, [(f"candidate verification crashed: "
                    f"{type(exc).__name__}: {exc}")],
            provenance=provenance)
    if comparison.get("verdict") != "pass":
        return blocked_envelope(
            tool, [("candidate not verified: "
                    f"{comparison.get('problems', comparison)}")],
            provenance=provenance,
            next_actions=["inspect the problems and re-repair"])
    model_problems = _sealed_model_problems(evidence["model"], original,
                                            candidate)
    if model_problems:
        return blocked_envelope(
            tool, [f"model identity no longer holds: {model_problems}"],
            provenance=provenance)
    runtime_summary: dict[str, Any] = {"status": "not-performed",
                                       "reason": "no runtime verification "
                                                 "bound; static verification "
                                                 "only"}
    if runtime_run_id is not None:
        runtime_manifest, error = _read_manifest(run_root, runtime_run_id)
        if error is not None:
            return blocked_envelope(tool, [error], provenance=provenance)
        assert runtime_manifest is not None
        runtime_seal = verify_seal(Path(run_root) / runtime_run_id)
        if runtime_seal:
            return blocked_envelope(
                tool, [(f"runtime run {runtime_run_id!r} seal invalid: "
                        f"{runtime_seal[0].get('rule', 'unknown')}")],
                provenance=provenance)
        if runtime_manifest.get("pipeline") != "vqs.verify-runtime/1":
            return blocked_envelope(
                tool, [(f"run {runtime_run_id!r} is not a runtime "
                        f"verification "
                        f"(pipeline {runtime_manifest.get('pipeline')!r})")],
                provenance=provenance)
        if runtime_manifest.get("status") != "completed":
            return blocked_envelope(
                tool, [(f"runtime verification {runtime_run_id!r} is "
                        f"{runtime_manifest.get('status')!r}: required "
                        "live regressions are unresolved; re-run runtime "
                        "verification or omit --runtime-run-id to record the "
                        "gap explicitly")],
                provenance=provenance)
        try:
            runtime_doc = json.loads(
                (Path(run_root) / runtime_run_id / "runtime.json"
                 ).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return blocked_envelope(
                tool, [f"runtime evidence unreadable: {exc}"],
                provenance=provenance)
        if not isinstance(runtime_doc, dict) or (
                runtime_doc.get("candidate_digest") != evidence["after"]):
            return blocked_envelope(
                tool, [("runtime verification binds a different candidate; "
                        "promotion refused")],
                provenance=provenance)
        runtime_summary = {"status": "pass", "run_id": runtime_run_id,
                           "candidate_digest": runtime_doc.get(
                               "candidate_digest"),
                           "pid": runtime_doc.get("pid")}
    if scope in ("desktop", "release") and (
            runtime_run_id is None or runtime_summary.get("status") != "pass"):
        return blocked_envelope(
            tool, [(f"{scope} scope needs a completed sealed runtime "
                    "verification bound to the exact candidate; pass "
                    "--runtime-run-id (static promotion records the "
                    "gap explicitly instead)")],
            provenance=provenance)
    if scope == "release":
        return blocked_envelope(
            tool, [("release scope needs reviewer authority bound to "
                    "the exact candidate; no trusted release reviewer "
                    "mechanism is registered, so release promotion "
                    "stays blocked even with clean runtime evidence")],
            provenance=provenance)
    if scope == "desktop":
        if not desktop_recheck:
            return blocked_envelope(
                tool, [("desktop scope needs the post-promotion Desktop "
                        "reload/recheck; do not pass --no-desktop-recheck")],
                provenance=provenance)
        if bridge is None:
            try:
                LocalBridgePort()
            except BridgeUnavailable as exc:
                return blocked_envelope(
                    tool, [(f"desktop scope needs a live Desktop for the "
                            f"post-promotion recheck: {exc}")],
                    provenance=provenance)
    provenance = {**provenance, "scope": scope}
    rid = promote_run_id or f"promote-{uuid.uuid4().hex[:12]}"
    try:
        sealed_run_dir = create_run(
            Path(run_root), rid,
            {"pipeline": "vqs.promote/1",
             "promotion": {"repair_run": run_id,
                           "original": os.path.realpath(original),
                           "candidate": os.path.realpath(candidate)}})
    except FileExistsError:
        return blocked_envelope(tool, [f"Run already exists: {rid}"])
    except ValueError as exc:
        return blocked_envelope(tool, [f"Unusable run id: {exc}"])
    bindings = {"input_sha256": _canonical_sha256(
        {"repair_run": run_id, "candidate_digest": evidence["after"],
         "precondition_digest": evidence["before"],
         "approval": owner_approval, "scope": scope}),
        "policy_version": POLICY_VERSION, "tool": "vqs.promote/1",
        "config_sha256": None}
    append_event(sealed_run_dir, {"kind": "started", "repair_run": run_id})
    backup = backup_dir or f"{os.path.realpath(original)}.vqs-backup"
    try:
        swap = swap_original_with_candidate(
            original=original, candidate=candidate, backup_dir=backup,
            precondition_digest=evidence["before"],
            candidate_digest=evidence["after"])
    except PromoteError as exc:
        partial = isinstance(exc.state, dict) and "state" in exc.state
        kind = "failed" if partial else "blocked"
        _seal_terminal(sealed_run_dir, kind, {}, bindings)
        if partial:
            return _envelope(
                tool, "fail", run_id=rid, run_dir=str(sealed_run_dir),
                findings=[{"check": "promote:swap", "status": "fail",
                           "detail": {"reason": str(exc),
                                      "state": exc.state}}],
                provenance=provenance,
                next_actions=[("inspect the partial state and roll back from "
                             f"{exc.state.get('backup')}")])
        return blocked_envelope(
            tool, [f"promotion refused: {exc}"],
            run_id=rid, run_dir=str(sealed_run_dir), provenance=provenance)
    try:
        final_source = source_digest(Path(swap["final"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _seal_terminal(sealed_run_dir, "failed", {}, bindings)
        return _envelope(
            tool, "fail", run_id=rid, run_dir=str(sealed_run_dir),
            findings=[{"check": "promote:final-source", "status": "fail",
                       "detail": f"promoted original unreadable: {exc}"}],
            provenance=provenance,
            next_actions=[f"roll back from {swap['backup']}"])
    model_current: dict[str, Any] = {"kind": evidence["model"].get("kind")}
    model_ok = True
    if evidence["model"].get("kind") == "byPath":
        try:
            current_model, _rule, _detail = resolved_model_digest(
                swap["final"])
        except Exception as exc:  # noqa: BLE001 - model doubt fails closed
            model_current["error"] = (
                f"model digest unreadable: {type(exc).__name__}: {exc}")
            model_ok = False
        else:
            model_current["digest"] = current_model
            model_ok = current_model == evidence["model"].get("digest")
    elif evidence["model"].get("kind") == "remote":
        model_current["connection"] = evidence["model"].get("connection")
    recheck: dict[str, Any] = {"status": "skipped",
                               "reason": "owner opted out"}
    if desktop_recheck:
        port = bridge
        if port is None:
            try:
                port = LocalBridgePort()
            except BridgeUnavailable as exc:
                port = None
                recheck = {"status": "skipped",
                           "reason": f"no live Desktop capability: {exc}"}
        if port is not None:
            try:
                payload = port.status()
            except OSError as exc:
                recheck = {"status": "failed",
                           "reason": f"Bridge status failed: {exc}"}
            else:
                holder = _instance_holding(payload, swap["final"])
                if holder is None:
                    recheck = {"status": "skipped",
                               "reason": "no Desktop instance holds the "
                                         "promoted report"}
                else:
                    try:
                        port.reload(int(holder["pid"]))
                        rebound = port.status()
                    except OSError as exc:
                        recheck = {"status": "failed",
                                   "reason": f"reload/recheck failed: {exc}"}
                    else:
                        again = _instance_holding(rebound, swap["final"])
                        if again is not None and str(again.get("pid")) == str(
                                holder.get("pid")):
                            recheck = {"status": "pass",
                                       "pid": int(holder["pid"])}
                        else:
                            recheck = {"status": "failed",
                                       "reason": "promoted report not bound "
                                                 "after reload"}
    promotion_doc = {
        "repair_run": run_id,
        "scope": scope,
        "runtime": runtime_summary,
        "owner_approval": owner_approval,
        "original": os.path.realpath(original),
        "candidate": os.path.realpath(candidate),
        "precondition_digest": evidence["before"],
        "candidate_digest": evidence["after"],
        "candidate_source_sha256": evidence["source_sha256"],
        "backup": swap["backup"], "backup_digest": swap["backup_digest"],
        "final": swap["final"], "final_digest": swap["final_digest"],
        "final_source_sha256": final_source,
        "model": {"sealed": evidence["model"], "current": model_current,
                  "match": model_ok},
        "desktop_recheck": recheck,
        "rollback": {
            "steps": [(f"rename {swap['final']} to "
                       f"{swap['final']}.vqs-retired (must not exist)"),
                      f"rename {swap['backup']} to {swap['final']}",
                      (f"verify tree_digest({swap['final']}) == "
                       f"{evidence['before']}")],
            "backup": swap["backup"],
            "precondition_digest": evidence["before"]}}
    try:
        promotion_bytes = json.dumps(promotion_doc, sort_keys=True,
                                     ensure_ascii=False, default=str
                                     ).encode("utf-8")
        (sealed_run_dir / "promotion.json").write_bytes(promotion_bytes)
        promotion_sha = hashlib.sha256(promotion_bytes).hexdigest()
    except OSError as exc:
        _seal_terminal(sealed_run_dir, "failed", {}, bindings)
        return _envelope(
            tool, "fail", run_id=rid, run_dir=str(sealed_run_dir),
            findings=[{"check": "promote:seal", "status": "fail",
                       "detail": f"cannot persist promotion evidence: {exc}"}],
            provenance=provenance,
            next_actions=[f"roll back from {swap['backup']}"])
    artifacts = {"promotion.json": {"sha256": promotion_sha,
                                    "path": "promotion.json"}}
    evidence_rows = [{"kind": "sealed_promotion", "run_id": rid,
                      "original": swap["final"], "backup": swap["backup"],
                      "scope": scope,
                      "final_digest": swap["final_digest"],
                      "final_source_sha256": final_source,
                      "desktop_recheck": recheck.get("status"),
                      "runtime": runtime_summary.get("status")}]
    if (not model_ok or recheck.get("status") == "failed"
            or (scope == "desktop"
                and recheck.get("status") != "pass")):
        _seal_terminal(sealed_run_dir, "failed", artifacts, bindings)
        return _envelope(
            tool, "fail", run_id=rid, run_dir=str(sealed_run_dir),
            findings=[{"check": "promote:corroboration", "status": "fail",
                       "detail": {"model_match": model_ok,
                                  "desktop_recheck": recheck}}],
            evidence=evidence_rows, provenance=provenance,
            next_actions=[(f"inspect the corroboration failure; roll back "
                           f"from {swap['backup']} if needed")])
    _seal_terminal(sealed_run_dir, "completed", artifacts, bindings)
    return _envelope(
        tool, "pass", run_id=rid, run_dir=str(sealed_run_dir),
        findings=[{"check": "promote", "status": "pass"}],
        evidence=evidence_rows, provenance=provenance,
        next_actions=[f"backup preserved at {swap['backup']}"])


def _instance_holding(payload: Any, report: str) -> dict[str, Any] | None:
    """Desktop instance whose report dir is exactly ``report`` (or None)."""
    if not isinstance(payload, dict):
        return None
    instances = payload.get("instances")
    if not isinstance(instances, list):
        return None
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        if os.path.normcase(os.path.abspath(
                str(instance.get("reportDir", "")))) == os.path.normcase(
                    os.path.abspath(report)):
            return instance
    return None


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

