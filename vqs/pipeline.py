"""End-to-end offline check pipeline: measured facts to sealed verdict.

Wires design rules (WP-06, issue #11), story oracles (WP-10, issue #15),
DOCX structure inspection (WP-08 static half, issue #13), and TMDL
model/binding checks (WP-05 subset, issue #10) into one command: load a
measured-facts document, run every requested rule, oracle, document,
and model check, aggregate without coercing ``unknown`` into ``pass``,
and seal the run manifest. Unknown rule IDs, malformed entries, and
missing facts block — never pass, never crash.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from . import design_rules
from .data.tmdl import check_bindings, check_freshness, inventory_model, require_rls_identity
from .document.inspect import inspect_docx
from .run_store import append_event, create_run, seal_run
from .stories.oracles import ambiguity_check, oracle_matches

STATUS_BY_VERDICT = {"pass": "completed", "fail": "failed", "blocked": "blocked"}


def _axis(params: dict[str, Any]) -> dict:
    return design_rules.axis_display_distinctness(
        params.get("numeric_ticks"), params.get("displayed_labels"))


def _contrast(params: dict[str, Any]) -> dict:
    return design_rules.text_contrast(
        params.get("foreground"), params.get("background"),
        large_text=bool(params.get("large_text", False)))


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


def seal_verdict(run_root: Path, run_id: str | None, pipeline_name: str,
               verdict: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Seal a single-verdict run; a duplicate run_id blocks without a run."""
    if verdict not in STATUS_BY_VERDICT:
        verdict = "blocked"
    run_id = run_id or f"{pipeline_name}-{uuid.uuid4().hex[:12]}"
    try:
        run_dir = create_run(Path(run_root), run_id, {"pipeline": pipeline_name})
    except FileExistsError:
        return {"verdict": "blocked", "run_dir": None, "run_id": run_id,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Run already exists: {run_id}"}]}
    append_event(run_dir, {"kind": "started", "checks": pipeline_name})
    terminal = STATUS_BY_VERDICT[verdict]
    append_event(run_dir, {"kind": terminal, "verdict": verdict})
    digest = hashlib.sha256(
        json.dumps(findings, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    manifest = seal_run(run_dir, terminal, artifacts={"verdict_sha256": digest})
    return {"verdict": verdict, "run_dir": str(run_dir), "run_id": run_id,
            "findings": findings, "manifest": manifest}


def run_check(facts: Any, run_root: Path, run_id: str | None = None) -> dict[str, Any]:
    """Run every requested check and seal the manifest; see module docstring."""
    if not isinstance(facts, dict):
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "facts", "status": "blocked",
                              "reason": "Facts document is not an object"}]}
    run_id = run_id or f"check-{uuid.uuid4().hex[:12]}"
    try:
        run_dir = create_run(Path(run_root), run_id, {"pipeline": "vqs.check/1"})
    except FileExistsError:
        return {"verdict": "blocked", "run_dir": None,
                "findings": [{"check": "run_id", "status": "blocked",
                              "reason": f"Run already exists: {run_id}"}]}
    append_event(run_dir, {"kind": "started",
                           "checks": "design_rules+oracles+documents+models"})
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
    manifest = seal_run(run_dir, terminal, artifacts={"verdict_sha256": digest})
    return {"verdict": verdict, "run_dir": str(run_dir), "run_id": run_id,
            "findings": findings, "manifest": manifest}
