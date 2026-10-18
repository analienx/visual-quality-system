"""One-command, source-backed Power BI report triage for actual owners.

Uses the *existing* measured-facts, sealed review and repair synthesis engines,
not a second rule evaluator. This is a read-only diagnostic on the original;
an optional typed plan must still pass candidate/CLI/Desktop gates to apply.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import default_config
from .pipeline import (
    _source_provenance,
    inspect_report,
    merge_review_facts,
    propose_candidates,
    review_report,
)

VERSION = "vqs.actionable-triage/1"
HIGH = frozenset({
    "layout.visuals_within_page", "typography.text_contrast",
    "axis.display_values_not_distinct",
    "encoding.metric_unit_consistency",
    "layout.composition",
})
MEDIUM = frozenset({
    "layout.no_visual_overlap", "axis.category_label_space",
    "typography.format_declaration_consistency",
    "insight.no_duplicate_grain", "insight.no_cross_page_duplicate_grain",
})


def _report_input(source: str, model: str | None) -> tuple[str, str | None]:
    """Resolve one local PBIP report and matching byPath model, read-only."""
    path = Path(source)
    if path.suffix.lower() == ".pbip":
        project = json.loads(path.read_text(encoding="utf-8-sig"))
        artifacts = project.get("artifacts", []) if isinstance(project, dict) else []
        if not isinstance(artifacts, list):
            raise ValueError("PBIP artifacts array is missing")
        names = [a["report"]["path"] for a in artifacts
                 if isinstance(a, dict) and isinstance(a.get("report"), dict)
                 and isinstance(a["report"].get("path"), str)]
        if len(names) != 1:
            raise ValueError("PBIP must identify exactly one local report artifact")
        relative = Path(names[0])
        base = path.parent.resolve()
        if (relative.is_absolute() or ".." in relative.parts
                or relative.suffix.lower() != ".report"):
            raise ValueError("PBIP report reference escapes the project")
        report = (base / relative).resolve()
        if base not in report.parents or not report.is_dir():
            raise ValueError("PBIP local report folder unavailable or outside project")
    else:
        report = path
    if model is not None:
        return str(report), model
    definition = report / "definition.pbir"
    if not definition.is_file():
        return str(report), None
    try:
        ref = json.loads(definition.read_text(encoding="utf-8-sig"))
        model_name = ref["datasetReference"]["byPath"]["path"]
        if not isinstance(model_name, str):
            return str(report), None
        model_root = (report / model_name).resolve()
        if (model_root.suffix.lower() != ".semanticmodel"
                or not (model_root / "definition").is_dir()
                or report.parent.resolve() not in model_root.parents):
            return str(report), None
        return str(report), str(model_root / "definition")
    except (KeyError, ValueError, TypeError, OSError):
        return str(report), None


def _visual_names(report: str, expected_sha: str) -> dict[str, str]:
    """Human-readable page/chart labels with exact PBIR visual IDs preserved."""
    from .pbir import report_context

    context = report_context(report)
    if context.get("source_sha256") != expected_sha:
        raise ValueError("report changed while deriving display names")
    output: dict[str, str] = {}
    for page in context.get("pages", []):
        if not isinstance(page, dict):
            continue
        pid = page.get("id")
        if not isinstance(pid, str):
            continue
        display = page.get("display_name") or pid
        for visual in page.get("visuals", []):
            if not isinstance(visual, dict):
                continue
            vid = visual.get("visual_id")
            kind = visual.get("visual_type") or "visual"
            if isinstance(vid, str):
                output[f"{pid}/{vid}"] = f"{display} / {kind} ({vid})"
    return output


def _priority(check: str, status: str) -> str:
    if status == "blocked":
        return "unverified"
    if check in HIGH:
        return "high"
    if check in MEDIUM:
        return "medium"
    return "review"


def _locations(detail: Any) -> list[str]:
    """Expose honest evidence locations; never invent per-visual provenance."""
    if not isinstance(detail, dict):
        return []
    evidence = detail.get("evidence", detail)
    if not isinstance(evidence, dict):
        return []
    found: set[str] = set()
    rows = []
    for key in ("conflicts", "failures", "pending", "findings"):
        group = evidence.get(key)
        if isinstance(group, list):
            rows.extend(group)
    for item in rows:
        if not isinstance(item, dict):
            continue
        page = item.get("page")
        visual = item.get("visual")
        if isinstance(page, str) and isinstance(visual, str):
            found.add(f"{page}/{visual}")
        elif isinstance(item.get("visuals"), list):
            for member in item["visuals"]:
                if isinstance(member, str):
                    found.add(f"{page}/{member}" if isinstance(page, str) else member)
        else:
            for key in ("cards", "detail_panels"):
                for member in item.get(key, []):
                    visual = member.get("visual") if isinstance(member, dict) else member
                    if isinstance(visual, str) and isinstance(page, str):
                        found.add(f"{page}/{visual}")
    return sorted(found)


def _summary_recommendation(check: str, status: str, detail: dict) -> str:
    e = detail.get("evidence", detail)
    if not isinstance(e, dict):
        return "Review the recorded evidence and identify the affected source visual."
    if status == "blocked":
        reason = str(e.get("reason", "Required measurements are missing"))
        return (f"Needs evidence: {reason}"[:250])
    choices = {
        "layout.visuals_within_page": "Move the proven out-of-canvas visual inside the page.",
        "layout.no_visual_overlap": (
            "Potential visual overlap: inspect actual rendering first; "
            "reposition only if the overlap is unintended."),
        "layout.composition": (
            "Remove redundant slicer caption; size KPI cohorts within 15% "
            "of the canvas and align their paired grid anchors with the "
            "matching detail panels. Edit a disposable candidate, validate "
            "with the Microsoft CLI and inspect a fresh full-canvas render."),
        "typography.text_contrast": "Improve foreground/background contrast; confirm rendered colors.",
        "typography.format_declaration_consistency":
            "Resolve inconsistent styling with measured effective theme values.",
        "insight.no_duplicate_grain":
            "Check whether charts answer distinct analytical questions.",
        "insight.no_cross_page_duplicate_grain":
            "Check whether repeated charts justify cross-page navigation.",
    }
    return choices.get(check, "Inspect the measured discrepancy and the analytical intent.")


def analyze(report: str, model: str | None = None, *,
            run_root: str = ".vqs-runs",
            run_id: str | None = None,
            config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce a prioritized repair/decision queue with zero original writes.

    Can return useful diagnosed failures even when the review verdict is
    blocked for missing rendering evidence. Do not confuse structural
    failures with a completed quality assessment.
    """
    config = config if isinstance(config, dict) else default_config()
    supplied = report
    try:
        report, model = _report_input(report, model)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"contract": VERSION, "status": "blocked",
                "reason": "report project cannot be resolved",
                "blocked_reasons": [str(exc)], "coverage": {},
                "findings": [], "plan": None, "run_id": None}
    inspected = inspect_report(report, model, config)
    if inspected["verdict"] != "pass":
        return {"contract": VERSION, "status": "blocked",
                "reason": "source inspection incomplete",
                "blocked_reasons": inspected.get("blocked_reasons", []),
                "coverage": inspected.get("coverage", {}),
                "findings": [], "plan": None, "run_id": None}
    source = inspected.get("provenance", {})
    reviewed = review_report(report_dir=report, model_dir=model,
                             config=config, run_root=run_root, run_id=run_id)
    if not reviewed.get("run_id") or reviewed.get("run_dir") is None:
        return {"contract": VERSION, "status": "blocked",
                "reason": "review could not produce a sealed run",
                "blocked_reasons": reviewed.get("blocked_reasons", []),
                "coverage": inspected.get("coverage", {}),
                "findings": [], "plan": None, "run_id": None}
    current, issues = _source_provenance(report, model)
    if issues or any(source.get(k) != current.get(k)
                     for k in ("source_sha256", "model_sha256")):
        return {"contract": VERSION, "status": "blocked",
                "reason": "source/model changed during triage",
                "blocked_reasons": issues or ["source/model identity drift"],
                "coverage": inspected.get("coverage", {}),
                "findings": [], "plan": None,
                "run_id": reviewed.get("run_id")}
    try:
        friendly_names = _visual_names(report, current["source_sha256"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"contract": VERSION, "status": "blocked",
                "reason": "report changed before visual identification",
                "blocked_reasons": [str(exc)], "coverage": inspected.get("coverage", {}),
                "findings": [], "plan": None, "run_id": reviewed["run_id"]}
    facts = merge_review_facts(inspected["facts"], config)
    triaged = propose_candidates(run_root, reviewed["run_id"], facts=facts)
    if triaged["verdict"] == "blocked":
        return {"contract": VERSION, "status": "blocked",
                "reason": "sealed findings are not eligible for synthesis",
                "blocked_reasons": triaged.get("blocked_reasons", []),
                "coverage": inspected.get("coverage", {}),
                "findings": [], "plan": None,
                "run_id": reviewed.get("run_id")}
    candidates = triaged.get("candidates", [])
    decisions = triaged.get("decisions", [])
    findings: list[dict[str, Any]] = []
    for finding in reviewed.get("findings", []):
        if not isinstance(finding, dict) or finding.get("status") == "pass":
            continue
        check = str(finding.get("check", "?"))
        status = str(finding.get("status", "blocked"))
        basis = finding.get("evidence_basis", {})
        if not isinstance(basis, dict):
            basis = {}
        matched = [item for item in candidates if item.get("check") == check]
        proposals = [{
            "visual": friendly_names.get(
                f"{item.get('page')}/{item.get('visual')}",
                f"{item.get('page')}/{item.get('visual')}"),
            "path": ".".join(str(part) for part in item.get("path", [])),
            "old": item.get("old"), "new": item.get("new"),
            "reason": item.get("rationale", ""),
        } for item in matched]
        held = [item for item in decisions if item.get("check") == check]
        locations = _locations(basis)
        findings.append({
            "check": check, "status": status,
            "priority": _priority(check, status),
            "locations": locations,
            "visual_labels": [friendly_names.get(location, location)
                              for location in locations],
            "recommendation": _summary_recommendation(check, status, basis),
            "candidate_count": len(matched),
            "proposals": proposals,
            "decision_count": len(held),
            "next_step": ("review a typed candidate" if matched
                          else "capture missing render/semantic evidence"
                          if status == "blocked"
                          else "manual design decision"),
            "decision_reasons": [str(item.get("reason", "")) for item in held][:5],
        })
    order = {"high": 0, "medium": 1, "review": 2, "unverified": 3}
    findings.sort(key=lambda f: (order.get(f["priority"], 4),
                                 f["check"]))
    coverage = inspected.get("coverage", {})
    plan = triaged.get("plan")
    return {
        "contract": VERSION, "status": "diagnosed",
        "report": supplied, "report_dir": report, "model_dir": model,
        "run_id": reviewed["run_id"],
        "run_dir": reviewed.get("run_dir"),
        "review_verdict": reviewed["verdict"],
        "source_sha256": current.get("source_sha256"),
        "model_sha256": current.get("model_sha256"),
        "coverage": coverage,
        "summary": {
            "pages": coverage.get("parsed_pages"),
            "visuals": coverage.get("parsed_visuals"),
            "proven_issues": sum(f["status"] == "fail" for f in findings),
            "needs_evidence": sum(f["status"] == "blocked" for f in findings),
            "typed_candidates": len(candidates),
            "unresolved_decisions": len(decisions),
        },
        "findings": findings, "candidates": candidates,
        "decisions": decisions, "plan": plan,
        "limits": [
            "Static PBIR/source checks only; no populated Desktop render inspected",
            "No DAX query, RLS/user, interaction or analytical-story acceptance",
            "Typed suggestions are NOT applied or vendor-validated by triage",
        ],
    }


def _location_summary(labels: list[str]) -> str:
    """Keep a short readable report while retaining full IDs in JSON."""
    if not labels:
        return "not isolated to a visual"
    shown = ", ".join(labels[:4])
    remaining = len(labels) - 4
    return shown + (f" (+{remaining} more; use --format json)" if remaining > 0 else "")


def markdown(report: dict[str, Any]) -> str:
    """Human-readable backlog, not a full raw internal JSON dump."""
    if report.get("status") != "diagnosed":
        reasons = report.get("blocked_reasons", [])
        return ("# Power BI triage — blocked\n\n" +
                "\n".join(f"- {reason}" for reason in reasons or
                          [report.get("reason", "Unknown problem")]) + "\n")
    s = report["summary"]
    lines = [
        "# Power BI — actionable quality triage",
        "",
        f"**Report:** `{report['report']}`",
        (f"**Measured:** {s['pages']} pages / {s['visuals']} visuals"
        f" · {s['proven_issues']} rule failure(s)"
        f" · {s['needs_evidence']} check(s) needing evidence"),
        (f"**Suggestions:** {s['typed_candidates']} typed candidate edits"
        f" · {s['unresolved_decisions']} remaining decisions"),
        (f"**Review status:** {report['review_verdict']}"
        " (static only; NOT visual approval)"),
        "",
        "## Prioritized work",
    ]
    if not report["findings"]:
        lines.append("No measurable rule failure found. Render and data "
                     "quality remain unverified.")
    for i, f in enumerate(report["findings"], 1):
        lines += [
            (f"{i}. **[{f['priority'].upper()}] {f['check']}**"
            f" — {f['status']}"),
            f"   - {f['recommendation']}",
            f"   - Location: {_location_summary(f['visual_labels'])}",
            (f"   - Next: {f['next_step']};"
            f" {f['candidate_count']} safe-plan proposal(s)"),
        ]
        for proposed in f["proposals"][:3]:
            lines.append(
                f"   - Suggested edit: {proposed['visual']} "
                f"{proposed['path']}: {proposed['old']} → {proposed['new']} "
                "(candidate only; not applied)")
        if len(f["proposals"]) > 3:
            lines.append(f"   - +{len(f['proposals']) - 3} more candidate edits in JSON")
        if f["decision_reasons"]:
            lines.append(f"   - Blocker: {f['decision_reasons'][0]}")
    lines += ["", "## What this cannot prove"]
    lines.extend(f"- {limitation}" for limitation in report["limits"])
    lines += [
        "",
        f"**Sealed review:** `{report['run_id']}`",
        f"**Source SHA-256:** `{report['source_sha256']}`",
        "",
        ("An optional exported plan can be passed to `vqs repair` against "
        "a disposable candidate. It has NOT been applied or approved."),
    ]
    return "\n".join(lines) + "\n"
