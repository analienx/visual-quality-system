"""No-psutil Windows OS PID attestation and negative source identity cases."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from vqs.powerbi.native_capture_provenance import _os_identity


def test_builtin_windows_pid_identity_requires_exact_pbip(tmp_path: Path, monkeypatch):
    pbip = tmp_path / "My Private Report.pbip"
    pbip.write_text("{}", encoding="utf8")
    pbip = pbip.resolve()
    record = {
        "Name": "PBIDesktop.exe",
        "CommandLine": (
            '"C:/Program Files/Microsoft Power BI Desktop/bin/PBIDesktop.exe" '
            f'"{pbip}"'
        ),
        "Created": "2026-10-30T10:00:00.0000000Z",
        "CreatedMs": 1793440800000,
    }
    monkeypatch.setattr(
        "vqs.powerbi.os_process.shutil.which",
        lambda _: "powershell.exe",
    )
    def command(args, **_kw):
        assert "ProcessId = 77" in args[-1]
        return subprocess.CompletedProcess(args, 0, json.dumps(record), "")
    monkeypatch.setattr(
        "vqs.powerbi.os_process.subprocess.run", command,
    )
    assert _os_identity(77, pbip) == record["Created"]
    record["Name"] = "notepad.exe"
    with pytest.raises(ValueError, match="genuine PBIDesktop"):
        _os_identity(77, pbip)
    record["Name"] = "PBIDesktop.exe"
    record["CommandLine"] = 'PBIDesktop.exe "C:/other.pbip"'
    with pytest.raises(ValueError, match="exact PBIP"):
        _os_identity(77, pbip)
    record["CommandLine"] = (
        f'PBIDesktop.exe "{pbip}" "C:/another.pbip"'
    )
    with pytest.raises(ValueError, match="exact PBIP"):
        _os_identity(77, pbip)


def test_pid_identity_parses_windows_quoting_rules(tmp_path: Path, monkeypatch):
    """Identity uses CommandLineToArgvW rules, not quote-matching regex.

    `_os_identity` used to run its own CIM script and its own
    `re.findall(r'"([^"]+\\.pbip)"|...')`, which cannot implement the
    `\\"` and 2n/2n+1-backslash rules. It now shares
    `vqs.powerbi.os_process`, so one attestation no longer depends on two
    parsers staying in step.
    """
    pbip = (tmp_path / "Quarterly Report.pbip")
    pbip.write_text("{}", encoding="utf8")
    pbip = pbip.resolve()
    # A literal quote inside an earlier argument, escaped Windows-style.
    record = {
        "Name": "PBIDesktop.exe",
        "CommandLine": (
            '"C:/Program Files/Microsoft Power BI Desktop/bin/PBIDesktop.exe" '
            '"--note=say \\"hi\\"" '
            f'"{pbip}"'
        ),
        "Created": "2026-11-04T08:00:00.0000000Z",
        "CreatedMs": 1793440800000,
    }
    monkeypatch.setattr("vqs.powerbi.os_process.shutil.which",
                        lambda _: "powershell.exe")
    monkeypatch.setattr(
        "vqs.powerbi.os_process.subprocess.run",
        lambda args, **_kw: subprocess.CompletedProcess(
            args, 0, json.dumps(record), ""))
    assert _os_identity(77, pbip) == record["Created"]
    # Negative control: a second .pbip argument is still ambiguous.
    record["CommandLine"] = (
        f'PBIDesktop.exe "--note=say \\"hi\\"" "{pbip}" "C:/other.pbip"')
    with pytest.raises(ValueError, match="exact PBIP"):
        _os_identity(77, pbip)
