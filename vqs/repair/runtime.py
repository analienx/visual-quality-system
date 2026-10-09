"""Disposable-candidate runtime verification (P0-U4 live-fire glue).

The manual operator runbook — open the candidate in Desktop, reload,
screenshot, compare — moves into VQS with one hard boundary: VQS only
ever opens and binds the DISPOSABLE candidate. The original path is
never opened, reloaded, or captured here; a Desktop instance holding
the original refuses with a precise reason instead of being driven.

A bridge port abstracts the live Desktop. ``LocalBridgePort`` shells
to the real ``powerbi-desktop`` binary (1.0.0 contract: ``open
<report>`` opens a PBIP/PBIX then waits for bridge status;
``reload --pid`` reloads in place); anything it cannot do (binary
absent, open/reload rejected) raises with the exact Bridge output and
the caller seals ``blocked`` — never a faked pass. Tests inject fake
ports; production capture runs through the U3-hardened
``capture.capture`` (lease, readiness, measured calibration).

Candidate lifecycle: VQS opens the disposable candidate itself via
the port (``open_candidate_instance``), binds the newly observed
instance by exact candidate path (never by assumption), then reloads
and captures that exact PID. An owner-provided ``--pid`` stays
supported as a user-owned instance under the strict save-state
policy; it never grants VQS the right to open or reload anything
else.
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

    def open(self, report: str, timeout: int = 60) -> None:  # pragma: no cover
        """Open a PBIP/PBIX file, waiting for bridge status (1.0.0 ``open``)."""
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

    def open(self, report: str, timeout: int = 60) -> None:
        code, output = self._run(["open", report, "--timeout", str(timeout)])
        if code != 0:
            raise BridgeUnavailable(
                f"Bridge open rejected for {report}: {output[:300]}")

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


def _report_file_for_candidate(candidate: str) -> str:
    """Resolve the openable PBIP/PBIX file beside a candidate report dir.

    The Bridge ``open`` contract takes a PBIP/PBIX file, while repair
    works on the extracted ``<name>.Report`` tree. The openable file
    is the same-stem ``.pbip``/``.pbix`` sibling; anything else (a
    missing sibling, a bare directory) names the exact gap instead of
    guessing what Desktop should open.
    """
    parent = os.path.dirname(os.path.abspath(candidate))
    base = os.path.basename(os.path.abspath(candidate))
    stem = base
    for suffix in (".Report", ".report"):
        if base.endswith(suffix):
            stem = base[: -len(suffix)]
            break
    for ext in (".pbip", ".pbix"):
        report_file = os.path.join(parent, stem + ext)
        if os.path.isfile(report_file):
            return report_file
    raise BridgeUnavailable(
        f"no openable PBIP/PBIX beside the disposable candidate {candidate}; "
        "open the candidate in Desktop and pass its exact --pid")


def open_candidate_instance(port: BridgePort, original: str, candidate: str, *,
                            source_digest: str, run_lease: str,
                            wait_seconds: int = 60,
                            timeout: int = 60) -> dict[str, Any]:
    """Open the disposable candidate via the port and bind the new instance.

    Snapshots pre-open PIDs, opens the candidate PBIP/PBIX through the
    port, then binds the newly observed instance holding the exact
    candidate path — never by assumption, never the original. The
    returned ownership proof (opened PID + candidate path + source
    digest + run lease) is what lets the run-owned save-state policy
    tolerate a lying hasUnsavedChanges flag; user-owned instances
    never get that leniency.
    """
    from ..capture import select_instance
    from ..pbir import source_digest as _source_digest

    candidate_real = os.path.realpath(candidate)
    if _same_path(candidate_real, original):
        raise BridgeUnavailable(
            "refusing: the candidate resolves to the original report; "
            "VQS never opens the original")
    report_file = _report_file_for_candidate(candidate)
    try:
        current_source = _source_digest(candidate)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BridgeUnavailable(
            f"candidate source unreadable before open: {exc}") from exc
    if current_source != source_digest:
        raise BridgeUnavailable(
            "candidate source drifted before open; refusing to open "
            "stale bytes")
    opener = getattr(port, "open", None)
    if not callable(opener):
        raise BridgeUnavailable(
            "port cannot open the disposable candidate; open it in "
            "Desktop and pass its exact --pid")
    try:
        before = port.status()
    except OSError as exc:
        raise BridgeUnavailable(f"Bridge status failed: {exc}") from exc
    before_pids = {str(item.get("pid")) for item in before.get("instances", [])
                   if isinstance(item, dict)}
    try:
        opener(report_file, timeout=timeout)
    except (BridgeUnavailable, OSError, TypeError) as exc:
        raise BridgeUnavailable(f"Bridge open rejected: {exc}") from exc
    try:
        after = port.status()
    except OSError as exc:
        raise BridgeUnavailable(
            f"Bridge status failed after open: {exc}") from exc
    holder = None
    for item in after.get("instances", []):
        if (isinstance(item, dict) and _same_path(
                str(item.get("reportDir", "")), candidate)):
            holder = item
            break
    if holder is None:
        raise BridgeUnavailable(
            "opened candidate did not bind: no Desktop instance holds "
            f"the candidate path {candidate} after open")
    try:
        instance = select_instance(candidate, holder.get("pid"),
                                   wait_seconds, status_payload=after,
                                   owned_candidate=True)
    except (LookupError, TypeError, OSError) as exc:
        raise BridgeUnavailable(
            f"opened candidate did not bind: {exc}") from exc
    if _same_path(str(instance.get("currentFilePath", "")), original):
        raise BridgeUnavailable(
            f"refusing: Desktop PID {instance.get('pid')} holds the "
            f"original report, not the disposable candidate")
    if str(instance.get("pid")) in before_pids:
        raise BridgeUnavailable(
            "Bridge open bound a pre-existing instance instead of a "
            f"freshly opened candidate (PID {instance.get('pid')}); "
            "refusing an ownership claim VQS cannot prove")
    return {"instance": instance, "owned": True,
            "opened_pid": instance.get("pid"), "candidate": candidate_real,
            "source_digest": source_digest, "run_lease": run_lease}


def reload_instance(port: BridgePort, instance: dict[str, Any]
                    ) -> dict[str, Any]:
    """Reload an already-bound candidate PID; shared reload step.

    Used after either bind path (owner-provided PID or run-opened
    instance) so reload behavior cannot drift between callers.
    """
    try:
        port.reload(int(instance["pid"]))
    except (BridgeUnavailable, OSError) as exc:
        raise BridgeUnavailable(
            f"candidate reload refused: {exc}") from exc
    return instance


def bind_and_reload(port: BridgePort, original: str, candidate: str,
                    pid: int, wait_seconds: int = 60) -> dict[str, Any]:
    """Bind an owner-provided PID to the candidate and reload it in place.

    The single shared bind/reload implementation used by runtime
    verification and the coordinator reload stage — no weaker
    duplicate live path. Raises BridgeUnavailable with the exact
    missing piece; never a faked pass.
    """
    instance = bind_candidate_instance(port, original, candidate, pid,
                                       wait_seconds)
    return reload_instance(port, instance)


def capture_candidate(candidate: str, renders: str, pid: int,
                      scale: int = 2, wait_seconds: int = 60,
                      modeling: Any = None,
                      lease_dir: str | None = None,
                      owned: bool = False) -> dict[str, Any]:
    """Capture the bound candidate through the hardened capture path.

    ``owned`` may only pass True for a run-opened instance (see
    ``open_candidate_instance``); user-owned instances keep the
    strict save-state refusal.
    """
    from ..capture import capture

    return capture(candidate, renders, pid=pid, scale=scale,
                   wait_seconds=wait_seconds, modeling=modeling,
                   lease_dir=lease_dir, owned_candidate=owned)
