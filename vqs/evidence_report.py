"""Present a sealed coordinator stage ledger without granting acceptance."""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from .pbir import source_inventory
from .pipeline import _model_digest
from .run_store import _has_link, _resolve_artifact, _validate_name, digest_bytes, read_events, verify_seal

# json.dumps escapes C0 controls but leaves these raw: DEL and C1 controls
# (U+009B is an 8-bit CSI), bidirectional overrides/isolates and other
# invisible format characters, line/paragraph separators, surrogates,
# private-use and unassigned code points. Report-derived text (page, visual
# and option names) reaches the owner's terminal through this report.
_UNSAFE = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"})


def _literal(value: str) -> str:
    """Keep control characters in evidence from becoming terminal commands.

    Also escapes characters that can reorder or hide what the owner reads,
    so an option label cannot visually impersonate another option.
    """
    return "".join(
        (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        if unicodedata.category(char) in _UNSAFE else char
        for char in json.dumps(value, ensure_ascii=False))


def _states(stage: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(stage, dict) or stage.get("status") != "pass":
        return None
    evidence = stage.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("verdict") not in ("pass", "fail"):
        return None
    findings = evidence.get("findings")
    if not isinstance(findings, list) or not findings:
        return None
    states: dict[str, str] = {}
    for item in findings:
        if not isinstance(item, dict):
            return None
        check, status = item.get("check"), item.get("status")
        if not isinstance(check, str) or not check or status not in ("pass", "fail") or check in states:
            return None
        states[check] = status
    if evidence["verdict"] != ("fail" if "fail" in states.values() else "pass"):
        return None
    return states


def _decisions(stage: dict[str, Any] | None) -> list[dict[str, Any]]:
    if stage is None or stage.get("status") != "pass":
        return []
    evidence = stage.get("evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("decisions"), list):
        raise TypeError("propose evidence has no decision list")
    out = []
    for item in evidence["decisions"]:
        if not isinstance(item, dict):
            raise TypeError("malformed decision record")
        if item.get("status") != "needs_owner_decision":
            continue
        if (not isinstance(item.get("decision_id"), str) or not item["decision_id"]
                or not isinstance(item.get("question"), str) or not item["question"]
                or not isinstance(item.get("options"), list) or not item["options"]):
            raise ValueError("malformed owner decision")
        for option in item["options"]:
            if (not isinstance(option, dict)
                    or any(not isinstance(option.get(key), str) or not option[key]
                           for key in ("id", "label", "effect"))):
                raise ValueError("malformed owner decision option")
        out.append(item)
    return out


def _check_source(params: dict[str, Any]) -> None:
    report, expected = params.get("report_dir"), params.get("source_sha256")
    if (not isinstance(report, str) or not report or not isinstance(expected, str)
            or not Path(report).is_dir()):
        raise ValueError("current source report or recorded source digest unavailable")
    inventory = source_inventory(Path(report))
    if not inventory["report_files"] or inventory["issues"] or inventory["digest"] != expected:
        raise ValueError("source report is stale or its referenced model is unavailable")
    model = params.get("model_dir")
    if model is None and params.get("model_sha256") is not None:
        raise ValueError("recorded source model path is unavailable")
    if (model is not None and
            (not isinstance(model, str) or not isinstance(params.get("model_sha256"), str)
             or _model_digest(model) != params["model_sha256"])):
        raise ValueError("source model is stale or unavailable")


def render(root: Path, run_id: str) -> tuple[str, list[Path]]:
    """Render facts from a consistent sealed run; hashes are not signatures."""
    _validate_name(run_id, "run_id")
    run = root / run_id
    manifest_path, events_path = run / "manifest.json", run / "events.jsonl"
    absolute_root = root.absolute()
    if any(_has_link(path) for path in (absolute_root, *absolute_root.parents, run, manifest_path, events_path)):
        raise ValueError("run root, run, manifest or event log is a link")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"run manifest unreadable: {exc}") from exc
    if (not isinstance(manifest, dict) or manifest.get("run_id") != run_id
            or manifest.get("pipeline") != "vqs.run/1"
            or not isinstance(manifest.get("bindings"), dict)
            or manifest["bindings"].get("tool") != "vqs.run/1"
            or not isinstance(manifest.get("params"), dict)):
        raise ValueError("not a matching vqs.run/1 coordinator manifest")
    params = manifest["params"]
    if params.get("mode") not in ("review", "propose", "repair") or params.get("scope") not in (
            "static", "desktop", "release"):
        raise ValueError("run mode or scope is missing or unsupported")
    artifacts = manifest.get("artifacts")
    entry = artifacts.get("stages") if isinstance(artifacts, dict) else None
    if (not isinstance(entry, dict) or entry.get("path") != "stages.json"
            or not isinstance(entry.get("sha256"), str)):
        raise ValueError("sealed stage ledger binding missing")
    stage_path = _resolve_artifact(run, entry["path"])
    if stage_path is None:
        raise ValueError("sealed stage ledger path is unsafe")
    problems = verify_seal(run)
    if problems:
        raise ValueError("run seal failed: " + ", ".join(str(p.get("rule")) for p in problems))
    _check_source(params)
    try:
        stage_bytes = stage_path.read_bytes()
        if digest_bytes(stage_bytes) != entry["sha256"]:
            raise ValueError("stage ledger digest mismatch")
        stages = json.loads(stage_bytes.decode("utf-8"))
        events = read_events(run)
        recorded_stages = [{key: value for key, value in event.items() if key != "kind"}
                           for event in events if event.get("kind") == "stage"]
        if stages != recorded_stages:
            raise ValueError("stage ledger disagrees with the event log")
        if manifest_path.read_bytes() != manifest_bytes or verify_seal(run):
            raise ValueError("run changed during evidence reading")
        _check_source(params)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"stage ledger unreadable or inconsistent: {exc}") from exc
    if not isinstance(stages, list) or not stages:
        raise ValueError("stage ledger must be a nonempty list")
    by_name: dict[str, dict[str, Any]] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            raise TypeError("malformed stage")
        name, status = stage.get("stage"), stage.get("status")
        if (not isinstance(name, str) or not name or name in by_name
                or status not in ("pass", "fail", "blocked", "not_run")
                or ("reason" in stage and not isinstance(stage["reason"], str))):
            raise ValueError("invalid or duplicate stage")
        by_name[name] = stage
    terminal = {"completed": "pass", "failed": "fail", "blocked": "blocked"}
    summary = by_name.get("summary")
    run_status = manifest.get("status")
    if (not isinstance(run_status, str) or run_status not in terminal
            or not isinstance(summary, dict) or summary.get("status") != terminal[run_status]
            or stages[-1] is not summary):
        raise ValueError("summary stage does not match terminal run status")
    summary_evidence = summary.get("evidence")
    if not isinstance(summary_evidence, dict) or not isinstance(summary_evidence.get("outcome"), str):
        raise TypeError("summary outcome missing")
    decisions = _decisions(by_name.get("propose"))
    lines = ["VQS evidence report (recorded stage evidence)",
             f"Run: {_literal(run_id)}; mode: {_literal(params['mode'])}; scope: {_literal(params['scope'])}",
             f"Current source SHA-256: {_literal(params['source_sha256'])}",
             f"Run status: {_literal(manifest['status'])}; recorded outcome: {_literal(summary_evidence['outcome'])}",
             "Integrity: hashes checked; this is not a signature or independent review.",
             "Scope: stage execution is not independent native G2/G4 or owner G6 acceptance.",
             "", "Before and after:"]
    before, after = _states(by_name.get("review")), _states(by_name.get("remeasure"))
    for label, name in (("Before", "review"), ("After", "remeasure")):
        stage = by_name.get(name, {})
        item = stage.get("evidence")
        verdict = item.get("verdict") if isinstance(item, dict) else None
        recorded = _literal(verdict) if isinstance(verdict, str) else "unknown"
        lines.append(f"  {label} review verdict (recorded): {recorded}")
    if before is None or after is None or set(before) != set(after):
        lines.append("  Comparison unknown: complete comparable before/after findings are unavailable.")
    else:
        resolved = sorted(k for k in before if before[k] == "fail" and after[k] == "pass")
        remaining = sorted(k for k in after if after[k] == "fail")
        regressions = sorted(k for k in before if before[k] == "pass" and after[k] == "fail")
        for label, values in (("Resolved", resolved), ("Remaining", remaining), ("New regressions", regressions)):
            lines.append(f"  {label}: " + (", ".join(_literal(v) for v in values) if values else "none recorded"))
    lines.extend(["", "Owner decisions:"])
    if not decisions:
        lines.append("  No answerable owner questions recorded in the available propose stage.")
    for decision in decisions:
        lines.append(f"  {_literal(decision['decision_id'])}: {_literal(decision['question'])}")
        for option in decision["options"]:
            lines.append(f"    {_literal(option['id'])} ({_literal(option['effect'])}): {_literal(option['label'])}")
    lines.extend(["", "Recorded stages:"])
    for stage in stages:
        reason = f" — {_literal(stage['reason'])}" if stage.get("reason") else ""
        lines.append(f"  {_literal(stage['stage'])}: {stage['status']}{reason}")
    repair = by_name.get("repair", {})
    evidence = repair.get("evidence") if isinstance(repair.get("evidence"), dict) else {}
    candidate = evidence.get("candidate")
    lines.extend(["", "Candidate and adoption:",
                  "  Candidate: " + (_literal(candidate) if isinstance(candidate, str) else "not recorded"),
                  "  Changes are not fully bound by this ledger; inspect the underlying evidence.",
                  "  Candidate content and rendered states are not revalidated by this report.",
                  "  Promotion is a separate owner-authorized action; this report does not promote.",
                  f"  Private run evidence: {_literal(str(run))}",
                  "  The returned envelope is not established by this stage-ledger report."])
    # A new output anywhere in the original project can alter its source or
    # model inventory, even if it is outside the *.Report folder itself.
    protected = [run, Path(params["report_dir"]).parent]
    for path in (params.get("model_dir"), candidate):
        if isinstance(path, str) and path:
            protected.append(Path(path).parent)
    return "\n".join(lines) + "\n", protected
