"""Disposable-candidate runtime verification (P0-U4 live-fire glue).

The manual operator runbook — open the candidate in Desktop, reload,
screenshot, compare — moves into VQS with one hard boundary: VQS only
ever binds the DISPOSABLE candidate. The original path is never opened,
reloaded, or captured here; a Desktop instance holding the original
refuses with a precise reason instead of being driven.

A bridge port abstracts the live Desktop. ``LocalBridgePort`` shells
to the real ``powerbi-desktop`` binary; anything it cannot do (binary
absent, reload unsupported) raises with the exact Bridge output and
the caller seals ``blocked`` — never a faked pass. Tests inject fake
ports; production capture runs through the U3-hardened
``capture.capture`` (lease, readiness, measured calibration).

Environmental limitation (documented, not invented around): VQS knows
no proven Bridge ``open`` contract, so the owner opens the candidate
in Desktop (or a port that can) and passes ``--pid``; VQS binds that
PID to the exact candidate path, reloads it, captures it, and seals
the evidence. ``reload`` follows the documented ``reload --pid``
runner contract; a Bridge that rejects it blocks precisely.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


class BridgeUnavailable(OSError):
    """No live Desktop capability; the exact missing piece is the message."""


class BridgePort:
    """Live Desktop operations a runtime check may use (duck-typed).

    ``status`` returns the raw Bridge status payload (a dict with an
    ``instances`` list). ``reload`` reloads the PID in place and raises
    OSError carrying the Bridge output when the Bridge refuses.
    """

    def status(self) -> dict[str, Any]:  # pragma: no cover - port contract
        raise NotImplementedError

    def reload(self, pid: int) -> None:  # pragma: no cover - port contract
        raise NotImplementedError


class LocalBridgePort(BridgePort):
    """Subprocess-backed port over the real ``powerbi-desktop`` binary."""

    def __init__(self, binary: str | None = None, timeout: int = 60) -> None:
        resolved = binary or shutil.which("powerbi-desktop")
        if resolved is None:
            raise BridgeUnavailable("powerbi-desktop not on PATH")
        self.binary = resolved
        self.timeout = timeout

    def _run(self, args: list[str]) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                [self.binary, *args], capture_output=True, text=True,
                timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise BridgeUnavailable(
                f"Bridge timed out: {' '.join(args)}") from exc
        except OSError as exc:
            raise BridgeUnavailable(
                f"Bridge unreachable: {exc}") from exc
        return completed.returncode, (
            completed.stdout + completed.stderr).strip()

    def status(self) -> dict[str, Any]:
        code, output = self._run(["status"])
        if code != 0:
            raise BridgeUnavailable(f"Bridge status failed: {output[:300]}")
        try:
            payload = json.loads(output)
        except ValueError as exc:
            raise BridgeUnavailable(
                f"Bridge status is not JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise BridgeUnavailable("Bridge status is not a JSON object")
        return payload

    def reload(self, pid: int) -> None:
        code, output = self._run(["reload", "--pid", str(pid)])
        if code != 0:
            raise BridgeUnavailable(
                f"Bridge reload rejected for PID {pid}: {output[:300]}")


def _same_path(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right))


def bind_candidate_instance(port: BridgePort, original: str,
                            candidate: str, pid: int | None,
                            wait_seconds: int = 60) -> dict[str, Any]:
    """Bind a Desktop instance to the disposable candidate; never original.

    Reuses the capture instance gate (exact PID + canonical path, save
    state proven) against the CANDIDATE path, then refuses outright when
    that instance actually holds the original: driving the original
    from a runtime check is always a refusal, not a fallback.
    """
    from ..capture import select_instance

    if pid is None:
        raise BridgeUnavailable(
            "no Desktop PID given; open the disposable candidate in "
            "Desktop and pass its --pid (the original is never driven)")
    try:
        payload = port.status()
    except OSError as exc:
        raise BridgeUnavailable(f"Bridge status failed: {exc}") from exc
    try:
        instance = select_instance(str(candidate), pid, wait_seconds,
                                   status_payload=payload)
    except (LookupError, TypeError, OSError) as exc:
        raise BridgeUnavailable(
            f"candidate binding failed: {exc}") from exc
    if _same_path(str(instance.get("currentFilePath", "")), original):
        raise BridgeUnavailable(
            f"refusing: Desktop PID {instance.get('pid')} holds the "
            f"original report, not the disposable candidate")
    return instance


def capture_candidate(candidate: str, renders: str, pid: int,
                      scale: int = 2, wait_seconds: int = 60,
                      modeling: Any = None,
                      lease_dir: str | None = None) -> dict[str, Any]:
    """Capture the bound candidate through the hardened capture path."""
    from ..capture import capture

    return capture(candidate, renders, pid=pid, scale=scale,
                   wait_seconds=wait_seconds, modeling=modeling,
                   lease_dir=lease_dir)
