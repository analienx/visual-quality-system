"""Guided output must be complete and safe to copy into its target shell."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from vqs.agent_summary import _shell_quote, summarize


def _envelope(run_dir: str, repair_id: str = "repair-1") -> dict:
    return {"run_dir": run_dir, "summary": {
        "candidate_status": {"status": "verified"},
        "child_runs": {"repair": {"run_id": repair_id}},
    }}


@pytest.mark.skipif(os.name != "nt" or shutil.which("powershell.exe") is None,
                    reason="Windows PowerShell required")
@pytest.mark.parametrize("repair_id", ["repair-1", "id '$(throw 'bad') & č"])
def test_windows_adopt_command_preserves_path_as_one_literal_argument(tmp_path, repair_id):
    # The payload only raises if it is wrongly evaluated; it does not write
    # files or execute the real promotion command.
    root = tmp_path / "O'Brien $(throw 'unexpected expansion') & č"
    envelope = _envelope(str(root / "run-1"), repair_id)
    command = summarize(envelope)["adopt"]["command"].replace("<who: why>", "owner: test")
    script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
              "function vqs { $args | ConvertTo-Json -Compress }; " + command)
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    arguments = json.loads(result.stdout)
    assert arguments == ["promote", "--run-root", str(root), "--run-id", repair_id,
                         "--owner-approval", "owner: test", "--scope", "static"]


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell hosts required")
@pytest.mark.parametrize("host", ["powershell.exe", "pwsh.exe"])
@pytest.mark.parametrize("where", ["root", "run_id"])
@pytest.mark.parametrize("quote", ["'", "\u2018", "\u2019", "\u201a", "\u201b", "'\u2018\u2019\u201a\u201b'"])
def test_powershell_smart_quotes_cannot_escape_adoption_arguments(tmp_path, host, where, quote):
    if not shutil.which(host):
        pytest.skip(f"{host} is not installed")
    payload = f"cut{quote}; Write-Output VQS_INJECTION_EXECUTED; #"
    root = tmp_path / (payload if where == "root" else "safe root")
    run_id = payload if where == "run_id" else "repair-1"
    command = summarize(_envelope(str(root / "run-1"), run_id))["adopt"]["command"]
    command = command.replace("<who: why>", "owner: test")
    script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
              "function vqs { $args | ConvertTo-Json -Compress }; " + command)
    result = subprocess.run([host, "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=30, check=False)
    assert "VQS_INJECTION_EXECUTED\n" not in result.stdout
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "promote", "--run-root", str(root), "--run-id", run_id,
        "--owner-approval", "owner: test", "--scope", "static"]


@pytest.mark.parametrize("value", ["plain", "space path", "O'Brien", "$HOME/$(throw)",
                                   "`literal` & ; č", "line\nnext", ""])
def test_posix_quoting_preserves_exact_argument(value):
    assert shlex.split(_shell_quote(value, windows=False)) == [value]


@pytest.mark.skipif(os.name == "nt" or not Path("/bin/sh").is_file(),
                    reason="POSIX shell required")
def test_posix_adopt_command_round_trips_through_shell(tmp_path):
    root = tmp_path / "O'Brien $(exit 97) & č"
    command = summarize(_envelope(str(root / "run-1")))["adopt"]["command"]
    command = command.replace("<who: why>", "owner: test")
    script = "vqs() { printf '%s\\0' \"$@\"; }\n" + command
    result = subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("\0")[:-1] == [
        "promote", "--run-root", str(root), "--run-id", "repair-1",
        "--owner-approval", "owner: test", "--scope", "static"]


def _questions(count: int) -> list[dict]:
    return [{"status": "needs_owner_decision", "decision_id": f"q-{i}",
             "question": f"Question {i}?", "options": [
                 {"id": "accept", "label": "Keep", "effect": "waive"},
                 {"id": "change", "label": "Change", "effect": "apply"}]}
            for i in range(count)]


def test_owner_questions_are_never_silently_truncated():
    """Either every question is shown with its options, or overflow says so.

    Owner questions are mandatory content: a subset would invite an answer
    based on less than the decision covers. When they fit, all of them
    appear; when they cannot, the result refuses to be answered from rather
    than quietly dropping some.
    """
    envelope = _envelope("/tmp/runs/run-1")
    envelope["summary"]["repair_triage"] = {"decisions": _questions(6)}
    fits = summarize(envelope)
    assert "compact_overflow" not in fits
    assert [item["decision_id"] for item in fits["needs_review"]] == [
        f"q-{i}" for i in range(6)]
    assert all([option["id"] for option in item["options"]] == ["accept", "change"]
               for item in fits["needs_review"])

    # More than the budget can hold: explicit overflow, no partial subset.
    envelope["summary"]["repair_triage"] = {"decisions": _questions(17)}
    over = summarize(envelope)
    assert over["needs_review"] == []
    assert over["compact_overflow"]["owner_decisions_pending"] == 17
    assert "Do not answer from this output" in (
        over["compact_overflow"]["next_action"])


def test_declared_changes_are_shown_in_order_and_omissions_counted():
    """Changes are optional diagnostics: trimmed deterministically, counted.

    They are no longer capped at an arbitrary 50; they are trimmed only as
    far as the byte budget requires, from the tail, and whatever went is
    reported so the reader knows to consult the full result.
    """
    envelope = _envelope(str(Path("runs") / "run-1"))
    envelope["plan"] = {"operations": [
        {"type": "spacing.adjust", "selector": {"page": "P", "visual": f"v-{i}"},
         "path": ["visual", "objects", "position"], "old": i, "value": i + 1}
        for i in range(75)]}
    result = summarize(envelope)
    changes = result["changes"]
    # A prefix, in the original order, never a reordered or sampled subset.
    assert [item["visual"] for item in changes] == [
        f"v-{i}" for i in range(len(changes))]
    assert result["omitted"]["changes"] == 75 - len(changes)
    assert len(changes) + result["omitted"]["changes"] == 75


# --- compact byte budget: owner questions are mandatory ----------------

def _printed_bytes(result: dict) -> int:
    """Exactly what the CLI writes: serialized form plus print's newline."""
    return len(json.dumps(result, indent=2, ensure_ascii=False,
                          default=str).encode("utf-8")) + 1


def _budget_envelope(*, changes: int, decisions: int, question: str = "",
              reason: str = "", diagnostics: int = 12) -> dict:
    question = question or "Which size should cohort pivotTable/c{i} use?"
    reason = reason or ("cohort pivotTable/c{i}: explicit visual-size "
                        "declarations diverge; the PBIR does not prove which "
                        "design size is correct")
    return {
        "tool": "vqs.run", "verdict": "blocked", "run_id": "r",
        "run_dir": "/tmp/runs/r",
        "blocked_reasons": [f"blocked reason {i}" for i in range(diagnostics)],
        "next_actions": [f"next action {i}" for i in range(diagnostics)],
        "plan": {"operations": [{
            "type": "format.declare_explicit",
            "selector": {"page": f"Page_{i}", "visual": f"visual-{i:08x}"},
            "path": ["visual", "objects", "columnHeaders", 0, "properties",
                     "fontSize", "expr", "Literal", "Value"],
            "old": None, "value": "10D"} for i in range(changes)]},
        "summary": {
            "outcome": "blocked", "acceptance": False,
            "candidate_status": {"status": "none", "candidate": None},
            "resolved_findings": [f"check.fixed_{i}" for i in range(diagnostics)],
            "remaining_findings": [f"check.left_{i}" for i in range(diagnostics)],
            "repair_triage": {"decision_source_sha256": "a" * 64,
                "decisions": [{
                    "status": "needs_owner_decision",
                    "decision_id": f"dec-{i:016x}",
                    "check": "typography.format_declaration_consistency",
                    "question": question.format(i=i),
                    "reason": reason.format(i=i),
                    "cohort": f"pivotTable/c{i}",
                    "options": [
                        {"id": "size:10D", "label": f"Use 10 across c{i}",
                         "effect": "apply"},
                        {"id": "accept", "label": "Keep as intentional",
                         "effect": "waive"}],
                } for i in range(decisions)]},
        },
    }


def test_oversized_diagnostics_are_trimmed_and_the_omission_reported():
    """Optional diagnostics give way; owner questions and options never do."""
    result = summarize(_budget_envelope(changes=120, decisions=3, diagnostics=60))
    assert _printed_bytes(result) <= 6000
    assert "compact_overflow" not in result
    # Every owner question survives, with its options intact.
    assert len(result["needs_review"]) == 3
    for item in result["needs_review"]:
        assert item["question"] and item["reason"]
        assert [o["id"] for o in item["options"]] == ["size:10D", "accept"]
    # What went is counted, not silently dropped.
    assert result["omitted"]
    assert result["omitted"].get("changes", 0) > 0
    assert all(count > 0 for count in result["omitted"].values())


def test_budget_counts_encoded_bytes_not_characters():
    """Non-ASCII costs what it costs on the wire."""
    wide = ("Kterou velikost má použít vizuál v kohortě pivotTable/c{i}? "
            "日本語のテキストも含まれます — ゼロ幅ではありません")
    result = summarize(_budget_envelope(changes=90, decisions=3, question=wide,
                                 diagnostics=40))
    serialized = json.dumps(result, indent=2, ensure_ascii=False,
                            default=str)
    assert len(serialized.encode("utf-8")) > len(serialized)  # multi-byte
    assert _printed_bytes(result) <= 6000
    assert len(result["needs_review"]) == 3
    assert "日本語" in result["needs_review"][0]["question"]


def test_a_single_oversized_diagnostic_entry_is_trimmed():
    envelope = _budget_envelope(changes=2, decisions=2, diagnostics=1)
    envelope["blocked_reasons"] = ["x" * 9000, "second reason"]
    result = summarize(envelope)
    assert _printed_bytes(result) <= 6000
    assert result["omitted"].get("blocked_reasons", 0) >= 1
    assert len(result["needs_review"]) == 2


def test_owner_decisions_over_budget_overflow_instead_of_truncating():
    """Mandatory content that cannot fit must refuse to be answered from."""
    result = summarize(_budget_envelope(changes=0, decisions=4,
                                 reason="ó" * 1200))
    assert _printed_bytes(result) <= 6000
    overflow = result["compact_overflow"]
    assert overflow["owner_decisions_pending"] == 4
    assert overflow["budget_bytes"] == 6000
    assert overflow["required_bytes"] > 6000
    assert "--report-out" in overflow["next_action"]
    assert "Do not answer from this output" in overflow["next_action"]
    # No partial questions: a subset would invite an under-informed answer.
    assert result["needs_review"] == []
    # The run stays awaiting owner review rather than reading as settled.
    assert result["verdict"] == "blocked"
    assert result["outcome"] == "blocked"
    assert result["acceptance"] is False
    assert result["promotion_performed"] is False


def test_trimming_is_deterministic():
    envelope = _budget_envelope(changes=120, decisions=3, diagnostics=60)
    first, second = summarize(envelope), summarize(envelope)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_answered_runs_give_up_the_question_echo_before_the_record():
    """Unanswered questions are mandatory; answered ones are a redundant echo.

    On an answered run the questions have served their purpose, and the
    answered record plus the resulting changes are what the owner reads.
    Trimming the echo first keeps `changes` and `waived` intact, which was
    the whole point of reporting the run.
    """
    # Sized so pure diagnostics alone cannot pay for the budget, which is
    # what makes the question echo the next thing to go.
    envelope = _budget_envelope(changes=7, decisions=9, diagnostics=20)
    envelope["summary"]["owner_decisions"] = {"answered": [
        {"decision_id": f"dec-{i:016x}", "option": "size:10D",
         "effect": "apply", "edits": 2} for i in range(9)]}
    envelope["summary"]["waived_findings"] = ["insight.no_cross_page_duplicate_grain"]
    result = summarize(envelope)
    assert _printed_bytes(result) <= 6000
    assert "compact_overflow" not in result
    # The record of what was decided and done survives...
    assert len(result["changes"]) == 7
    assert result["waived"] == ["insight.no_cross_page_duplicate_grain"]
    assert len(result["owner_decisions"]) == 9
    # ...and the already-answered question echo is what paid for it.
    assert result["omitted"].get("needs_review", 0) > 0


def test_a_modest_overflow_keeps_what_the_repair_achieved():
    """`fixed` is the result of the run, not commentary on it.

    Regression guard. An earlier ordering treated `fixed` as a pure
    diagnostic and gave it up first, so a repair that was barely over
    budget reported an empty `fixed` list while still claiming a verified
    candidate -- i.e. the output denied the very repair it had performed.
    The clean-wheel runner caught it; no unit test did.

    A result only slightly over budget must pay out of restatable
    guidance and keep the record of what was repaired.
    """
    envelope = _budget_envelope(changes=20, decisions=2, diagnostics=30)
    result = summarize(envelope)
    assert _printed_bytes(result) <= 6000
    assert "compact_overflow" not in result
    # Guidance paid for the budget, and said so.
    assert result["omitted"]
    assert set(result["omitted"]) & {"next_actions", "remaining",
                                     "blocked_reasons"}
    # What the repair achieved survived whole.
    assert result["fixed"] == [f"check.fixed_{i}" for i in range(30)]
    assert "fixed" not in result["omitted"]
    # Surviving changes stay decision-ready: whole entries, never halves.
    for change in result["changes"]:
        assert {"page", "visual", "property", "op", "from", "to"} <= set(change)


def test_restatable_guidance_is_given_up_before_regressions():
    """A regression is a safety signal, not advice; it outranks guidance."""
    envelope = _budget_envelope(changes=4, decisions=2, diagnostics=30)
    envelope["summary"]["new_regressions"] = ["layout.no_visual_overlap"]
    # The compact view shows at most 8 next actions; make those 8 expensive.
    envelope["next_actions"] = [f"next action {i}: " + "detail " * 40
                                for i in range(8)]
    result = summarize(envelope)
    assert _printed_bytes(result) <= 6000
    assert result["omitted"].get("next_actions", 0) > 0
    assert result["regressions"] == ["layout.no_visual_overlap"]
    assert "regressions" not in result["omitted"]
