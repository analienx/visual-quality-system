"""Dependency-free Windows process identity (replaces optional psutil)."""
from __future__ import annotations

import json
import subprocess

import pytest

from vqs.powerbi import os_process
from vqs.powerbi.os_process import split_command_line, windows_process


@pytest.mark.parametrize("command,expected", [
    ('"C:\\Program Files\\PBI\\PBIDesktop.exe" "C:\\R\\My Report.pbip"',
     ["C:\\Program Files\\PBI\\PBIDesktop.exe", "C:\\R\\My Report.pbip"]),
    ("PBIDesktop.exe C:\\r\\contosoprobe\\a.pbip",
     ["PBIDesktop.exe", "C:\\r\\contosoprobe\\a.pbip"]),
    ('x.exe "a\\\\" b', ["x.exe", "a\\", "b"]),          # 2n backslashes + quote
    ('x.exe a\\\\\\"b', ["x.exe", 'a\\"b']),              # 2n+1 -> literal quote
    ('x.exe a\\b\\\\c', ["x.exe", "a\\b\\\\c"]),          # plain backslashes
    ('x.exe "a ""quoted"" b"', ["x.exe", 'a "quoted" b']),
    ('  x.exe   one\ttwo  ', ["x.exe", "one", "two"]),
    ('"C:\\a b\\x.exe"', ["C:\\a b\\x.exe"]),
    ("", []),
])
def test_windows_argv_rules(command: str, expected: list[str]) -> None:
    assert split_command_line(command) == expected


def test_process_record_parsed_without_psutil(monkeypatch) -> None:
    record = {"Name": "PBIDesktop.exe",
              "CommandLine": '"C:\\PBI\\PBIDesktop.exe" "C:\\R\\Sales.pbip"',
              "Created": "2026-11-02T05:46:50.0000000+00:00",
              "CreatedMs": 1793598410000}
    monkeypatch.setattr(os_process.shutil, "which", lambda _n: "powershell.exe")

    def run(args, **_kw):
        assert "ProcessId = 42" in args[-1]
        return subprocess.CompletedProcess(args, 0, json.dumps(record), "")

    monkeypatch.setattr(os_process.subprocess, "run", run)
    proc = windows_process(42)
    assert proc["cmdline"] == ["C:\\PBI\\PBIDesktop.exe", "C:\\R\\Sales.pbip"]
    assert proc["create_time"] == 1793598410.0
    assert proc["name"] == "PBIDesktop.exe"


@pytest.mark.parametrize("change", ["missing", "no-shell", "bad-json",
                                    "no-command", "bad-pid"])
def test_process_identity_fails_closed(monkeypatch, change: str) -> None:
    record = {"Name": "PBIDesktop.exe", "CommandLine": "PBIDesktop.exe a.pbip",
              "Created": "x", "CreatedMs": 1}
    monkeypatch.setattr(os_process.shutil, "which",
                        lambda _n: None if change == "no-shell" else "ps")
    if change == "no-command":
        record["CommandLine"] = None

    def run(args, **_kw):
        if change == "missing":
            return subprocess.CompletedProcess(args, 2, "", "")
        text = "{not json" if change == "bad-json" else json.dumps(record)
        return subprocess.CompletedProcess(args, 0, text, "")

    monkeypatch.setattr(os_process.subprocess, "run", run)
    with pytest.raises(OSError):
        windows_process(0 if change == "bad-pid" else 7)


def test_native_save_uses_builtin_identity(tmp_path, monkeypatch) -> None:
    from vqs.powerbi import desktop_native_save

    project = tmp_path / "proj"
    project.mkdir()
    (project / "R.pbip").write_text("{}", encoding="utf8")
    (project / "R.Report").mkdir()
    import os
    import types

    # Module-local "Windows" view; never flip the global os.name (pathlib).
    proxy = types.SimpleNamespace(**{k: getattr(os, k) for k in dir(os)
                                     if not k.startswith("__")})
    proxy.name = "nt"
    monkeypatch.setattr(desktop_native_save, "os", proxy)
    monkeypatch.setattr("vqs.powerbi.os_process.windows_process", lambda pid: {
        "pid": pid, "name": "PBIDesktop.exe",
        "cmdline": ["PBIDesktop.exe", str(project / "r.pbip")],
        "create_time": 123.0, "created_iso": "x"})
    expected_ok = os.name == "nt"  # case-insensitive match only on Windows
    if expected_ok:
        assert desktop_native_save._os_process(project, 5) == 123.0
    else:
        with pytest.raises(ValueError, match="exactly this PBIP"):
            desktop_native_save._os_process(project, 5)
    monkeypatch.setattr("vqs.powerbi.os_process.windows_process", lambda pid: {
        "pid": pid, "name": "PBIDesktop.exe",
        "cmdline": ["PBIDesktop.exe", str(project / "R.pbip")],
        "create_time": 123.0, "created_iso": "x"})
    assert desktop_native_save._os_process(project, 5) == 123.0
