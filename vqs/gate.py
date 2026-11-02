"""Pull-request quality gate: fail only on findings a change introduces.

``vqs gate HEAD --baseline BASE`` reviews both report revisions with the
same deterministic static engine and compares them at *finding subject*
granularity (check + page/visual/cohort/pair — the same identity owner
decisions use), so an existing, already-known issue never blocks an
unrelated pull request while every newly introduced problem does.

* New failing or blocked items fail the gate (exit 1). Missing evidence
  introduced by the change (``coverage:*`` blocks) counts as new.
* Owner waivers from ``--decisions`` (``vqs.decision-answers/1``) remove
  their subjects from the "new" set; they never touch the baseline.
* ``--emit-baseline`` writes a portable ``vqs.gate-baseline/1`` JSON so CI
  can compare against a stored baseline instead of a second checkout.
* ``--sarif`` writes SARIF 2.1.0 for GitHub code scanning (``baselineState``
  new/unchanged), ``--github`` prints workflow error annotations.

Static source evidence only: a green gate is not native Desktop, G2/G4 or
G6 acceptance.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from vqs import __version__

BASELINE_SCHEMA = "vqs.gate-baseline/1"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_GATED = ("fail", "blocked")


def _items(findings: list[dict[str, Any]], facts: Any) -> list[dict[str, Any]]:
    """Subject-level items for every failing/blocked finding."""
    from vqs.repair.decisions import normalize_findings, subject_of
    from vqs.repair.synthesize import synthesize_plan

    out: dict[str, dict[str, Any]] = {}
    for finding in normalize_findings(findings):
        status, check = finding.get("status"), finding.get("check")
        if status not in _GATED or not isinstance(check, str):
            continue
        result = synthesize_plan([finding], facts)
        found = False
        for record in result["candidates"]:
            subject = subject_of(record)
            out.setdefault(subject, {
                "subject": subject, "check": check, "status": status,
                "page": record.get("page"), "visual": record.get("visual"),
                "message": f"{check}: auto-fixable ({record.get('op')}) - "
                           f"{record.get('rationale', '')}"[:600]})
            found = True
        for record in result["decisions"]:
            if record.get("status") == "covered_by_candidate":
                continue
            subject = record.get("subject") or subject_of(record)
            out.setdefault(subject, {
                "subject": subject, "check": check, "status": status,
                "page": record.get("page"), "visual": record.get("visual"),
                "cohort": record.get("cohort"), "pair": record.get("pair"),
                "message": f"{check}: {record.get('reason', '')}"[:600]})
            found = True
        if not found:
            location = finding.get("location")
            location = location if isinstance(location, dict) else {}
            record = {"check": check, "page": location.get("page"),
                      "visual": location.get("visual")}
            subject = subject_of(record)
            out.setdefault(subject, {
                "subject": subject, "check": check, "status": status,
                "page": record["page"], "visual": record["visual"],
                "message": f"{check}: {status}"})
    return sorted(out.values(), key=lambda item: item["subject"])


def evaluate(report: str, model: str | None = None,
             config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Review one report revision; returns items or a blocked reason."""
    from vqs.config import default_config
    from vqs.pipeline import inspect_report, merge_review_facts, review_report
    from vqs.source_paths import resolve_project_input

    config = config if isinstance(config, dict) else default_config()
    try:
        report, model = resolve_project_input(report, model)
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc), "items": []}
    inspected = inspect_report(report, model, config)
    if inspected["verdict"] == "blocked":
        return {"status": "blocked", "report": report, "items": [],
                "reason": "; ".join(inspected["blocked_reasons"]) or "inspect blocked"}
    facts = merge_review_facts(inspected["facts"], config)
    with tempfile.TemporaryDirectory(prefix="vqs-gate-") as runs:
        reviewed = review_report(facts=facts, config=config, run_root=runs)
    findings = reviewed.get("findings") or []
    if reviewed["verdict"] == "blocked" and not findings:
        # A review refused before producing findings proves nothing:
        # an empty item list must not read as "nothing new" (fail open).
        return {"status": "blocked", "report": report, "items": [],
                "reason": "review blocked: " + ("; ".join(
                    reviewed.get("blocked_reasons") or []) or "no findings")}
    return {"status": "ok", "report": report, "verdict": reviewed["verdict"],
            "items": _items(findings, facts)}


def load_baseline(path: Path, config: dict[str, Any] | None = None
                  ) -> dict[str, Any]:
    """A baseline report revision (dir/.pbip) or an emitted baseline JSON."""
    if path.is_file() and path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return {"status": "blocked", "reason": f"baseline unreadable: {exc}",
                    "items": []}
        if (not isinstance(data, dict) or data.get("schema") != BASELINE_SCHEMA
                or not isinstance(data.get("items"), list)
                or any(not isinstance(item, dict)
                       or not isinstance(item.get("subject"), str)
                       for item in data["items"])):
            return {"status": "blocked", "items": [],
                    "reason": f"baseline JSON must be {BASELINE_SCHEMA}"}
        return {"status": "ok", "items": data["items"], "report": data.get("report")}
    # Same rules as the head: a different config would invent "new" and
    # "fixed" findings between identical revisions.
    return evaluate(str(path), None, config)


def compare(head: dict[str, Any], baseline: dict[str, Any] | None,
            waived: list[str] | None = None,
            acknowledged: list[str] | None = None) -> dict[str, Any]:
    """Classify head items as new / unchanged / waived; pure.

    ``waived`` (head-bound) may excuse any failing item. ``acknowledged``
    (base-bound) only excuses failing items the baseline already had.
    """
    known = ({item["subject"] for item in baseline["items"]}
             if baseline is not None else set())
    allowed = set(waived or [])
    prior = set(acknowledged or []) & known
    new, unchanged, excused = [], [], []
    for item in head["items"]:
        if item["status"] == "fail" and (item["subject"] in allowed
                                         or item["subject"] in prior):
            excused.append(item)
        elif baseline is not None and item["subject"] in known:
            unchanged.append(item)
        else:
            new.append(item)
    fixed = sorted(known - {item["subject"] for item in head["items"]})
    return {"new": new, "unchanged": unchanged, "waived": excused,
            "fixed": fixed}


def _artifact(report: str | None, item: dict[str, Any], root: Path) -> str | None:
    if not report:
        return None
    base = Path(report)
    page, visual = item.get("page"), item.get("visual")
    if not page and isinstance(item.get("pair"), list) and item["pair"]:
        first = str(item["pair"][0])
        page, _, visual = first.partition("/") if "/" in first else (None, "", None)
    # Report-wide items (cohorts, model checks) anchor on report.json so
    # code scanning and annotations always point at a real file.
    target = base / "definition" / "report.json"
    if isinstance(page, str) and page:
        target = base / "definition" / "pages" / page
        if isinstance(visual, str) and visual:
            target = target / "visuals" / visual / "visual.json"
        else:
            target = target / "page.json"
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def sarif(result: dict[str, Any], root: Path) -> dict[str, Any]:
    """SARIF 2.1.0 log: new items as errors, unchanged/waived as notes."""
    report = result.get("report")
    rules: dict[str, dict[str, Any]] = {}
    results = []
    for state, items, level in (("new", result["new"], "error"),
                                ("unchanged", result["unchanged"], "note"),
                                ("unchanged", result["waived"], "none")):
        for item in items:
            rules.setdefault(item["check"], {
                "id": item["check"],
                "shortDescription": {"text": item["check"]},
                "helpUri": "https://github.com/analienx/visual-quality-system/blob/main/docs/CLI.md"})
            entry: dict[str, Any] = {
                "ruleId": item["check"], "level": level,
                "baselineState": state,
                "message": {"text": item["message"]
                            + (" (owner waiver)" if level == "none" else "")},
                "partialFingerprints": {"vqsSubject/v1": hashlib.sha256(
                    item["subject"].encode("utf-8")).hexdigest()},
                "properties": {"subject": item["subject"],
                               "status": item["status"]}}
            uri = _artifact(report, item, root)
            if uri:
                entry["locations"] = [{"physicalLocation": {
                    "artifactLocation": {"uri": uri}}}]
            results.append(entry)
    return {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": [{
        "tool": {"driver": {
            "name": "vqs", "version": __version__,
            "informationUri": "https://github.com/analienx/visual-quality-system",
            "rules": [rules[key] for key in sorted(rules)]}},
        "results": results}]}


def github_annotations(result: dict[str, Any], root: Path) -> list[str]:
    def escape(text: str) -> str:
        return (text.replace("%", "%25").replace("\r", "%0D")
                .replace("\n", "%0A"))

    lines = []
    for item in result["new"]:
        uri = _artifact(result.get("report"), item, root)
        where = f" file={escape(uri).replace(',', '%2C')}" if uri else ""
        title = escape(item["check"]).replace(",", "%2C").replace(":", "%3A")
        lines.append(f"::error{where},title={title}::{escape(item['message'])}")
    return lines


def run(head: str, *, baseline: Path | None = None, model: str | None = None,
        decisions: Any = None, config: dict[str, Any] | None = None
        ) -> dict[str, Any]:
    """Full gate: verdict pass (nothing new), fail (new items) or blocked."""
    from vqs.repair.decisions import load as load_answers

    waived: list[str] = []
    if decisions is not None:
        answers, issues = load_answers(decisions)
        if issues:
            return {"tool": "vqs.gate", "verdict": "blocked",
                    "reason": "decision answers rejected: " + "; ".join(issues)}
        assert answers is not None
        waived = [entry["decision_id"] for entry in answers["answers"]
                  if entry["option"] == "accept"]
    head_eval = evaluate(head, model, config)
    if head_eval["status"] != "ok":
        return {"tool": "vqs.gate", "verdict": "blocked",
                "reason": "head: " + head_eval["reason"]}
    base_eval = None
    if baseline is not None:
        base_eval = load_baseline(baseline, config)
        if base_eval["status"] != "ok":
            return {"tool": "vqs.gate", "verdict": "blocked",
                    "reason": "baseline: " + base_eval["reason"]}
    # Waivers name decision ids bound to a reviewed revision; map them to
    # subjects through that revision's own decisions so stale ids do nothing.
    head_matched = _waived_subjects(head_eval, waived)
    # Answers usually come from the owner's run on the *base* (the PR head
    # is the candidate built from them). Those may acknowledge only findings
    # that already existed there and still exist: a new finding did not
    # exist when the owner answered. Stored JSON baselines carry no reviewed
    # source, so they verify nothing and acknowledge nothing.
    base_matched = (_waived_subjects(base_eval, waived)
                    if base_eval is not None and "verdict" in base_eval else {})
    result = compare(head_eval, base_eval, sorted(set(head_matched.values())),
                     acknowledged=sorted(set(base_matched.values())))
    verdict = "fail" if result["new"] else "pass"
    stale = len(set(waived) - set(head_matched) - set(base_matched))
    return {"tool": "vqs.gate", "verdict": verdict,
            "report": head_eval["report"],
            "baseline": (base_eval or {}).get("report"),
            "head_verdict": head_eval["verdict"],
            "counts": {key: len(result[key]) for key in
                       ("new", "unchanged", "waived", "fixed")},
            **result,
            "unmatched_waivers": stale,
            "note": ("static source gate; not native Desktop, G2/G4 or G6 "
                     "acceptance")}


def _waived_subjects(evaluated: dict[str, Any], waived: list[str]
                     ) -> dict[str, str]:
    """``{decision_id: subject}`` for answers bound to this reviewed revision.

    Decision ids embed the exact reviewed source digest, so waivers written
    for another revision match nothing and excuse nothing (fail closed).
    """
    if not waived or not evaluated.get("report"):
        return {}
    from vqs.pbir import source_digest
    from vqs.repair.decisions import decision_id

    try:
        source = source_digest(Path(evaluated["report"]))
    except OSError:
        return {}
    by_id = {decision_id(item["subject"], source): item["subject"]
             for item in evaluated["items"]}
    return {ident: by_id[ident] for ident in waived if ident in by_id}
