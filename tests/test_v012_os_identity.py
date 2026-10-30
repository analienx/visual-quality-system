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
    }
    monkeypatch.setattr(
        "vqs.powerbi.native_capture_provenance.shutil.which",
        lambda _: "powershell.exe",
    )
    def command(args, **_kw):
        assert "ProcessId = 77" in args[-1]
        return subprocess.CompletedProcess(args, 0, json.dumps(record), "")
    monkeypatch.setattr(
        "vqs.powerbi.native_capture_provenance.subprocess.run", command,
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
