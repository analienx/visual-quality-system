"""Try raising an ephemeral GitHub-hosted Windows virtual display for Power BI.

Never persists registry changes. Only changes runner VM resolution for
this job. All decisions and errors are written to a small public-safe
diagnostic JSON file.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path


class POINTL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPosition", POINTL),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


def configure() -> dict[str, object]:
    if os.name != "nt":
        return {"status": "unsupported", "reason": "not_windows"}
    u = ctypes.windll.user32
    u.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.POINTER(DEVMODEW)]
    u.EnumDisplaySettingsW.restype = wintypes.BOOL
    u.ChangeDisplaySettingsW.argtypes = [ctypes.POINTER(DEVMODEW), wintypes.DWORD]
    u.ChangeDisplaySettingsW.restype = wintypes.LONG

    def getmode(number: int) -> DEVMODEW | None:
        mode = DEVMODEW()
        mode.dmSize = ctypes.sizeof(DEVMODEW)
        ok = u.EnumDisplaySettingsW(None, number, ctypes.byref(mode))
        return mode if ok else None

    current = getmode(0xFFFFFFFF)
    if current is None:
        return {"status": "blocked", "reason": "unable_to_read_display"}
    before = [int(current.dmPelsWidth), int(current.dmPelsHeight)]
    options: set[tuple[int, int]] = set()
    for index in range(2000):
        mode = getmode(index)
        if mode is None:
            break
        options.add((int(mode.dmPelsWidth), int(mode.dmPelsHeight)))
    targets = [(1920, 1080), (1600, 900), (1440, 900), (1600, 1200)]
    attempts = []
    for width, height in targets:
        choice = getmode(0xFFFFFFFF)
        if choice is None:
            break
        choice.dmFields = 0x00080000 | 0x00100000
        choice.dmPelsWidth = width
        choice.dmPelsHeight = height
        tested = int(u.ChangeDisplaySettingsW(ctypes.byref(choice), 0x00000002))
        applied = None
        if tested == 0:
            applied = int(u.ChangeDisplaySettingsW(ctypes.byref(choice), 0))
        attempts.append({"resolution": [width, height],
                         "test_code": tested, "apply_code": applied})
        after = getmode(0xFFFFFFFF)
        if after and after.dmPelsWidth >= 1440 and after.dmPelsHeight >= 900:
            return {"status": "candidate", "before": before,
                    "after": [int(after.dmPelsWidth), int(after.dmPelsHeight)],
                    "attempts": attempts, "advertised_modes": len(options)}
    after = getmode(0xFFFFFFFF)
    return {"status": "blocked", "before": before,
            "after": [int(after.dmPelsWidth), int(after.dmPelsHeight)] if after else None,
            "attempts": attempts, "advertised_modes": len(options),
            "largest_advertised_modes": [list(x) for x in
                                        sorted(options, key=lambda p: p[0] * p[1],
                                               reverse=True)[:8]]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("Refuse evidence overwrite")
    answer = {"contract": "vqs.hosted-windows-display-resize/1",
              "execution": "ephemeral_guest_only_no_registry_updates",
              "display": configure(), "desktop_render_proven": False}
    args.out.write_text(json.dumps(answer, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(answer, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
