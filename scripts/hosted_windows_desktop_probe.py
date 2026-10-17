"""Evidence-only probe of GitHub Windows Desktop capabilities.

This deliberately does not install Power BI, authenticate, open a customer
project, request privileged desktop access, or leak runner environment vars.
GUI success requires a real rendered report in a future, separate experiment.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import sys
from pathlib import Path


def _session() -> dict[str, object]:
    if os.name != "nt":
        return {"available": False, "reason": "non_windows"}
    kernel = ctypes.windll.kernel32
    user = ctypes.windll.user32
    pid = kernel.GetCurrentProcessId()
    session = ctypes.c_uint()
    session_ok = kernel.ProcessIdToSessionId(pid, ctypes.byref(session)) != 0
    screen_w = int(user.GetSystemMetrics(0))
    screen_h = int(user.GetSystemMetrics(1))
    # DESKTOP_READOBJECTS: do not request switch/write/desktop interaction.
    input_desktop = user.OpenInputDesktop(0, False, 0x0001)
    has_input_desktop = bool(input_desktop)
    if input_desktop:
        user.CloseDesktop(input_desktop)
    return {
        "available": True,
        "session_id": int(session.value) if session_ok else None,
        "session_0": (session.value == 0) if session_ok else None,
        "virtual_screen": [screen_w, screen_h],
        "minimum_1440x900": screen_w >= 1440 and screen_h >= 900,
        "input_desktop_accessible": has_input_desktop,
        "foreground_window_present": bool(user.GetForegroundWindow()),
    }


def _software() -> dict[str, object]:
    if os.name != "nt":
        return {"powerbi_desktop_installed": False, "webview2_installed": False}
    import winreg

    def registry_keys(*paths: str) -> bool:
        roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        return any(
            _key_exists(root, key) for root in roots for key in paths
        )

    paths = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe",
        Path(os.environ.get("LOCALAPPDATA", "C:/Users/runneradmin/AppData/Local"))
        / "Microsoft" / "Power BI Desktop" / "bin" / "PBIDesktop.exe",
    )
    webview = registry_keys(
        r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F1B0D6F0-0A4E-4C17-93DD-BCA51F5EF0CB}",
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F1B0D6F0-0A4E-4C17-93DD-BCA51F5EF0CB}",
    )
    return {
        "powerbi_desktop_installed": any(path.is_file() for path in paths),
        "webview2_installed": webview,
        "desktop_probe_executable_exists": any(path.is_file() for path in paths),
    }


def _key_exists(root: object, name: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(root, name):
            return True
    except OSError:
        return False


def evaluate() -> dict[str, object]:
    gui = _session()
    software = _software()
    feasible_prerequisites = (
        gui.get("available") is True
        and gui.get("session_0") is False
        and gui.get("minimum_1440x900") is True
        and gui.get("input_desktop_accessible") is True
    )
    return {
        "contract": "vqs.github-hosted-windows-desktop-preflight/1",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "runner_image": os.environ.get("ImageOS", "unknown"),
        "runner_environment": os.environ.get("GITHUB_ACTIONS") == "true",
        "gui": gui,
        "software": software,
        "phase_1_interactive_prerequisites": (
            "candidate" if feasible_prerequisites else "blocked"
        ),
        "powerbi_launch": "NOT_ATTEMPTED",
        "webview2_render": "NOT_ATTEMPTED",
        "pbip_open": "NOT_ATTEMPTED",
        "as_engine_query": "NOT_ATTEMPTED",
        "screenshot": "NOT_ATTEMPTED",
        "conclusion": "preflight_only_not_desktop_render_proof",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit("Refuse to overwrite existing evidence")
    result = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
