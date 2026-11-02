"""Answerable owner decisions: structured choices instead of dead ends.

Synthesis never guesses intent. When a finding needs a human choice
(``needs_owner_decision``), this module turns it into a *question* with:

* ``decision_id`` — stable for one exact source revision and finding
  subject. A changed report yields new ids, so stale answers fail closed.
* ``subject`` — revision-independent identity of what was decided
  (check + page/visual/cohort/pair). Waivers follow the subject across
  the repaired candidate, never across a different finding.
* ``options`` — each either ``apply`` (pre-compiled, typed, precondition-
  bound plan operations) or ``waive`` (keep as intentional). Every
  question offers ``accept``; questions with a provable edit also offer
  concrete edits.

An answers document (``vqs.decision-answers/1``) names the source digest
it was written against and one option per decision. :func:`resolve`
validates it against freshly synthesized decisions and returns plan
operations plus waived subjects. Answers authorize *candidate* edits and
scoped waivers only: they are not G2/G4 review, G6 promotion or any
release approval, and they can never waive missing evidence
(``unsupported`` coverage/oracle findings have no options).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .recipes import OWNER_DECISION_PROOF

ANSWERS_SCHEMA = "vqs.decision-answers/1"
ACCEPT = "accept"
_MAX_ANSWERS = 500
_MAX_NOTE = 2000


def subject_of(decision: dict[str, Any]) -> str:
    """Revision-independent identity of the decided finding."""
    parts = [str(decision.get("check", "?"))]
    if decision.get("cohort"):
        parts.append("cohort=" + str(decision["cohort"]))
    pair = decision.get("pair")
    if isinstance(pair, list) and pair:
        parts.append("pair=" + "+".join(sorted(str(item) for item in pair)))
    else:
        for key in ("page", "visual"):
            if decision.get(key):
                parts.append(f"{key}={decision[key]}")
    return "|".join(parts)


def decision_id(subject: str, source_sha256: str | None) -> str:
    material = f"{subject}\n{source_sha256 or 'unbound'}"
    return "dec-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _question(decision: dict[str, Any]) -> str:
    check = str(decision.get("check", "?"))
    if decision.get("cohort"):
        return (f"Which size should every visual in cohort "
                f"{decision['cohort']} use?")
    if isinstance(decision.get("pair"), list):
        names = " and ".join(str(n) for n in decision["pair"])
        if check.startswith("layout."):
            return f"{names} overlap on {decision.get('page', '?')}: move one, or keep the overlay?"
        return f"{names} repeat the same insight grain: intentional?"
    return f"{check}: accept the current design as intentional?"


def annotate(decisions: list[dict[str, Any]],
             source_sha256: str | None) -> list[dict[str, Any]]:
    """Give each owner decision an id, subject, question and options.

    Pre-compiled option operations receive their sealed provenance
    (``owner-decision:<id>:<option>``) here. Non-owner decisions
    (``unsupported``, ``covered_by_candidate``) stay unanswerable.
    """
    out: list[dict[str, Any]] = []
    for item in decisions:
        record = dict(item)
        options = record.pop("_options", None)
        if record.get("status") != "needs_owner_decision":
            out.append(record)
            continue
        subject = subject_of(record)
        ident = decision_id(subject, source_sha256)
        record["subject"] = subject
        record["decision_id"] = ident
        record["question"] = _question(record)
        choices: list[dict[str, Any]] = []
        for option in options if isinstance(options, list) else []:
            ops = []
            for op in option["operations"]:
                op = dict(op)
                if "proof" in op or op.get("type", "").startswith("format."):
                    op["proof"] = f"{OWNER_DECISION_PROOF}{ident}:{option['id']}"
                ops.append(op)
            choices.append({"id": option["id"], "effect": "apply",
                            "label": option["label"], "operations": ops})
        choices.append({"id": ACCEPT, "effect": "waive",
                        "label": "Keep the current design as intentional "
                                 "(owner waiver; recorded, never a pass)",
                        "operations": []})
        record["options"] = choices
        out.append(record)
    return out


def public_view(decision: dict[str, Any]) -> dict[str, Any]:
    """Agent-facing projection: options without bulky operation bodies."""
    view = {key: decision[key] for key in
            ("decision_id", "check", "status", "reason", "page", "visual",
             "cohort", "pair", "question") if key in decision}
    if isinstance(decision.get("options"), list):
        view["options"] = [
            {"id": option["id"], "effect": option["effect"],
             "label": option["label"],
             "edits": len(option.get("operations", []))}
            for option in decision["options"]]
    return view


def template(decisions: list[dict[str, Any]],
             source_sha256: str | None) -> dict[str, Any]:
    """An answers skeleton listing every open question and its options."""
    questions = [public_view(item) for item in decisions
                 if isinstance(item, dict) and item.get("decision_id")]
    return {"schema": ANSWERS_SCHEMA, "source_sha256": source_sha256,
            "owner": "", "answers": [
                {"decision_id": item["decision_id"], "option": "",
                 "question": item.get("question"),
                 "choices": [option["id"] for option in item.get("options", [])]}
                for item in questions]}


def load(document: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Shape-check an answers document; issues block, never guess."""
    if not isinstance(document, dict):
        return None, ["decision answers must be a JSON object"]
    issues = []
    if document.get("schema") != ANSWERS_SCHEMA:
        issues.append(f"decision answers schema must be {ANSWERS_SCHEMA!r}")
    owner = document.get("owner")
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
        issues.append("decision answers need a nonempty owner (who decided)")
    source = document.get("source_sha256")
    if not (isinstance(source, str) and len(source) == 64
            and all(c in "0123456789abcdef" for c in source)):
        issues.append("decision answers must pin the reviewed source_sha256")
    answers = document.get("answers")
    if not isinstance(answers, list) or not answers:
        issues.append("decision answers need a nonempty answers list")
        answers = []
    if len(answers) > _MAX_ANSWERS:
        issues.append("too many decision answers")
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for index, entry in enumerate(answers):
        if not isinstance(entry, dict):
            issues.append(f"answer {index} is not an object")
            continue
        ident, option = entry.get("decision_id"), entry.get("option")
        if not isinstance(ident, str) or not ident.startswith("dec-"):
            issues.append(f"answer {index} has no decision_id")
            continue
        if not isinstance(option, str) or not option:
            # Unanswered template rows are allowed and simply skipped.
            continue
        if ident in seen:
            issues.append(f"decision {ident} answered twice")
            continue
        seen.add(ident)
        note = entry.get("note")
        if note is not None and (not isinstance(note, str)
                                 or len(note) > _MAX_NOTE):
            issues.append(f"answer {index} note must be a short string")
            continue
        clean.append({"decision_id": ident, "option": option,
                      **({"note": note} if note else {})})
    if not clean and not issues:
        issues.append("no decision was answered (every option is empty)")
    if issues:
        return None, issues
    return {"schema": ANSWERS_SCHEMA, "owner": owner.strip(),
            "source_sha256": source, "answers": clean,
            "sha256": hashlib.sha256(json.dumps(
                document, sort_keys=True, ensure_ascii=False,
                default=str).encode("utf-8")).hexdigest()}, []


def resolve(answers: dict[str, Any], decisions: list[dict[str, Any]],
            source_sha256: str | None) -> dict[str, Any]:
    """Bind validated answers to the current decisions.

    Returns ``{"issues", "operations", "waived", "answered"}``. Any stale
    source digest, unknown decision id or unknown option is an issue:
    the caller blocks instead of applying a partial or guessed choice.
    """
    issues: list[str] = []
    if answers.get("source_sha256") != source_sha256:
        return {"issues": [("decision answers were written for a different "
                            "source revision; re-run and answer the current "
                            "decisions")],
                "operations": [], "waived": [], "answered": []}
    by_id = {item["decision_id"]: item for item in decisions
             if isinstance(item, dict) and item.get("decision_id")}
    operations: list[dict[str, Any]] = []
    waived: list[str] = []
    answered: list[dict[str, Any]] = []
    for entry in answers["answers"]:
        decision = by_id.get(entry["decision_id"])
        if decision is None:
            issues.append(f"unknown or stale decision {entry['decision_id']}")
            continue
        option = next((o for o in decision.get("options", [])
                       if o.get("id") == entry["option"]), None)
        if option is None:
            issues.append(f"decision {entry['decision_id']} has no option "
                          f"{entry['option']!r}")
            continue
        record = {"decision_id": decision["decision_id"],
                  "subject": decision["subject"],
                  "check": decision.get("check"),
                  "option": option["id"], "effect": option["effect"],
                  "edits": len(option["operations"]),
                  **({"note": entry["note"]} if entry.get("note") else {})}
        answered.append(record)
        if option["effect"] == "waive":
            waived.append(decision["subject"])
        else:
            operations.extend(dict(op) for op in option["operations"])
    targets: dict[tuple[str, tuple], Any] = {}
    for op in operations:
        key = (op["writes"][0], tuple(op["path"]))
        if key in targets and targets[key] != op.get("value"):
            issues.append("two answered options write different values to "
                          f"{op['writes'][0]} {list(op['path'])}")
        targets[key] = op.get("value")
    return {"issues": issues, "operations": operations,
            "waived": sorted(set(waived)), "answered": answered}


def waived_checks(findings: Any, facts: Any, waived: list[str],
                  source_sha256: str | None = None) -> list[str]:
    """Failing checks whose every owner decision was waived.

    Re-synthesizes decisions for ``findings`` (pure) and waives a check
    only when all of its decisions are ``needs_owner_decision`` with a
    waived subject. Unsupported (missing-evidence) decisions or checks
    that synthesize nothing are never waivable.
    """
    if not waived or not isinstance(findings, list):
        return []
    from .synthesize import synthesize_plan

    # Review envelopes expose rule evidence as ``evidence_basis``; sealed
    # findings artifacts use ``detail``. Synthesis reads ``detail``.
    findings = [
        {**item, "detail": item["evidence_basis"]}
        if (isinstance(item, dict) and "detail" not in item
            and isinstance(item.get("evidence_basis"), dict)) else item
        for item in findings]
    result = synthesize_plan(findings, facts, source_sha256=source_sha256)
    failing = {item.get("check") for item in findings
               if isinstance(item, dict) and item.get("status") == "fail"
               and isinstance(item.get("check"), str)}
    by_check: dict[str, list[dict[str, Any]]] = {}
    for item in result["decisions"]:
        if isinstance(item, dict) and item.get("check") in failing:
            by_check.setdefault(item["check"], []).append(item)
    allowed = set(waived)
    out = []
    for check, items in by_check.items():
        owner = [item for item in items
                 if item.get("status") != "covered_by_candidate"]
        if owner and all(item.get("status") == "needs_owner_decision"
                         and item.get("subject") in allowed
                         for item in owner):
            out.append(check)
    return sorted(out)
