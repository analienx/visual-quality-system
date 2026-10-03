"""Power BI Desktop spike harness (WP-03, issue #8): probe, never claim.

`desktop_spike_readiness` reports whether this host can attempt a real
Desktop run: binary present, Bridge CLI reachable. A ``ready`` verdict only
permits scheduling the spike under an exclusive host/PID lease — it is not
capture, data, or design approval. `check_target_match` enforces PBI-04:
captures must name the exact PID plus canonical report path; anything else
fails before any pixel is trusted.
"""
from __future__ import annotations

import os
import re

from vqs.adapters.ports import probe_executable, probe_file, readiness

DESKTOP_BINARY = r"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe"

MIN_BRIDGE_VERSION = (1, 0, 0)


def parse_bridge_version(text: str) -> tuple[int, ...] | None:
    """Parse ``major.minor.patch`` from Bridge --version output, else None."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def gate_bridge_version(version_text: str,
                        minimum: tuple[int, ...] = MIN_BRIDGE_VERSION
                        ) -> dict:
    """Block Bridge operations below the proven minimum version.

    Spike #8 proved Bridge 1.0.0; older or unparseable versions fail
    closed with the exact observation, never a claim of capability.
    """
    parsed = parse_bridge_version(version_text)
    if parsed is None:
        return {"verdict": "blocked",
                "reason": "Bridge version unparseable; refusing to run",
                "observed": (version_text or "")[:120]}
    if parsed < minimum:
        return {"verdict": "blocked",
                "reason": f"Bridge {'.'.join(map(str, parsed))} below "
                          f"minimum {'.'.join(map(str, minimum))}",
                "observed": list(parsed)}
    return {"verdict": "pass", "version": list(parsed)}


def desktop_spike_readiness() -> dict:
    """Probe Desktop run capability on this host."""
    capabilities = [
        probe_file("powerbi-desktop-binary", os.path.expandvars(DESKTOP_BINARY)),
        probe_executable("desktop-bridge-cli", "powerbi-desktop", "pbi-desktop-bridge"),
    ]
    return readiness("G1-desktop-spike", capabilities)


def _canonical(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def check_target_match(opened_pid: int, opened_path: str,
                       expected_pid: int, expected_path: str) -> dict:
    """Fail when the capture target is not the exact expected PID and path.

    Paths compare canonically, so equivalent spellings match; anything else
    fails closed and echoes both sides for the evidence record.
    """
    if not isinstance(opened_pid, int) or not isinstance(expected_pid, int):
        return {"verdict": "blocked", "reason": "PID observations required"}
    if not opened_path or not expected_path:
        return {"verdict": "blocked", "reason": "Canonical report paths required"}
    if opened_pid != expected_pid or _canonical(opened_path) != _canonical(expected_path):
        return {"verdict": "fail", "reason": "Capture target is not the expected PID and path",
                "opened": {"pid": opened_pid, "path": opened_path},
                "expected": {"pid": expected_pid, "path": expected_path}}
    return {"verdict": "pass", "pid": opened_pid, "path": opened_path}
