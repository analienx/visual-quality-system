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


def test_all_owner_questions_are_visible():
    decisions = [{"status": "needs_owner_decision", "decision_id": f"q-{i}",
                  "question": f"Question {i}?", "options": [
                      {"id": "accept", "label": "Keep", "effect": "waive"},
                      {"id": "change", "label": "Change", "effect": "apply"}]}
                 for i in range(17)]
    envelope = _envelope("/tmp/runs/run-1")
    envelope["summary"]["repair_triage"] = {"decisions": decisions}
    visible = summarize(envelope)["needs_review"]
    assert [item["decision_id"] for item in visible] == [f"q-{i}" for i in range(17)]
    assert all([option["id"] for option in item["options"]] == ["accept", "change"]
               for item in visible)


def test_all_declared_changes_are_visible():
    envelope = _envelope(str(Path("runs") / "run-1"))
    envelope["plan"] = {"operations": [
        {"type": "spacing.adjust", "selector": {"page": "P", "visual": f"v-{i}"},
         "path": ["visual", "objects", "position"], "old": i, "value": i + 1}
        for i in range(75)]}
    changes = summarize(envelope)["changes"]
    assert [item["visual"] for item in changes] == [f"v-{i}" for i in range(75)]
