"""P1 upgrade helper must be parseable and must never run unattended in CI."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/windows/p1_desktop_upgrade_guarded.ps1"


def test_upgrade_guard_has_explicit_irreversible_action_gates() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$Apply" in source
    assert "[switch]$DiscardDisposableState" in source
    assert "if ($Apply -and -not $DiscardDisposableState)" in source
    assert "if (-not $Apply)" in source
    assert source.index("if (-not $Apply)") < source.index("Stop-Process -Id")
    assert source.index("TargetSessions") < source.index("Copy-Item")
    assert source.index("CompareInventories $original $copy") < source.index("Stop-Process -Id")
    assert source.index("$current = @(TargetSessions)") < source.index("Stop-Process -Id")
    assert "Power BI Desktop is still running: no installer started" in source
    assert "refs/heads/main" not in source
    assert "winget @args" in source
    assert "--force" not in source
    assert "Get-Date -AsUTC" not in source  # Windows PowerShell 5.1 compatible
    # An already installed version MUST not close Desktop sessions.
    assert source.index("if ($installed -ge $target)") < source.index("Stop-Process -Id")
    assert "no processes touched" in source
    assert not re.search(r"(?i)remove-item\s+.*-recurse", source)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell parser available on Windows only")
def test_upgrade_guard_parses_in_windows_powershell() -> None:
    # Parse only: never run the upgrade helper or inspect private devices.
    ps = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -ne 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr