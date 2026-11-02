"""Dependency-free Windows process identity for Desktop attestation.

Reads ``Win32_Process`` through built-in PowerShell CIM (no psutil, which
is not a VQS dependency and is absent on clean installs and CI runners) and
splits the command line with the Windows C runtime argv rules, so a quoted
PBIP path with spaces, ``\\"`` escapes or launch-time casing is recovered
exactly as ``PBIDesktop.exe`` received it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

_SCRIPT = (
    '$p=Get-CimInstance Win32_Process -Filter "ProcessId = {pid}";'
    "if ($null -eq $p) {{ exit 2 }};"
    "$t=[DateTimeOffset]::new($p.CreationDate.ToUniversalTime());"
    "[pscustomobject]@{{Name=$p.Name;CommandLine=$p.CommandLine;"
    'Created=$t.ToString("o");CreatedMs=$t.ToUnixTimeMilliseconds()}}'
    " | ConvertTo-Json -Compress"
)


def split_command_line(command: str) -> list[str]:
    """Split like ``CommandLineToArgvW``/MSVCRT (2008+) for argv[1:].

    2n backslashes before a quote give n backslashes and toggle quoting;
    2n+1 give n backslashes and a literal quote; other backslashes are
    literal; ``""`` inside quotes is a literal quote. argv[0] (the
    executable) ends at the first unquoted whitespace and never escapes.
    """
    args: list[str] = []
    index, length = 0, len(command)
    while index < length and command[index] in " \t":
        index += 1
    if index >= length:
        return args
    # argv[0]: quotes delimit, backslashes are literal.
    current, quoted = [], False
    while index < length:
        char = command[index]
        if char == '"':
            quoted = not quoted
        elif char in " \t" and not quoted:
            break
        else:
            current.append(char)
        index += 1
    args.append("".join(current))
    while True:
        while index < length and command[index] in " \t":
            index += 1
        if index >= length:
            return args
        current, quoted = [], False
        while index < length:
            char = command[index]
            if char == "\\":
                run = 0
                while index < length and command[index] == "\\":
                    run += 1
                    index += 1
                if index < length and command[index] == '"':
                    current.append("\\" * (run // 2))
                    if run % 2:
                        current.append('"')
                        index += 1
                    continue
                current.append("\\" * run)
                continue
            if char == '"':
                if quoted and index + 1 < length and command[index + 1] == '"':
                    current.append('"')
                    index += 2
                    continue
                quoted = not quoted
                index += 1
                continue
            if char in " \t" and not quoted:
                break
            current.append(char)
            index += 1
        args.append("".join(current))


def windows_process(pid: int) -> dict[str, Any]:
    """``{pid, name, cmdline, create_time, created_iso}`` or ``OSError``."""
    if type(pid) is not int or pid <= 0:
        raise OSError("invalid Desktop PID")
    shell = shutil.which("powershell.exe")
    if not shell:
        raise OSError("built-in Windows PowerShell is unavailable")
    try:
        probe = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command",
             _SCRIPT.format(pid=pid)],
            capture_output=True, text=True, encoding="utf-8-sig",
            errors="replace", timeout=25, check=False)
    except subprocess.TimeoutExpired as exc:
        raise OSError("Windows process query timed out") from exc
    if probe.returncode:
        raise OSError(f"no Windows process with PID {pid}")
    try:
        record = json.loads(probe.stdout)
    except ValueError as exc:
        raise OSError("Windows process query returned malformed JSON") from exc
    if not isinstance(record, dict):
        raise OSError("Windows process query returned no record")
    name, command = record.get("Name"), record.get("CommandLine")
    created_ms, created_iso = record.get("CreatedMs"), record.get("Created")
    if (not isinstance(name, str) or not isinstance(command, str)
            or type(created_ms) is not int or created_ms <= 0
            or not isinstance(created_iso, str)):
        raise OSError("Windows process identity incomplete (name/command/creation)")
    return {"pid": pid, "name": name, "cmdline": split_command_line(command),
            "create_time": created_ms / 1000.0, "created_iso": created_iso}
