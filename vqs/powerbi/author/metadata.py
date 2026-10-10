"""Read-only, source-bound Microsoft report metadata capability port (W04).

Queries are allowlisted, fully typed CLI commands. They never read, write or
launch a report. Results are schema-checked and digest-bound, not evidence that
a proposed PBIR mutation is correct. A later compiler consumes these receipts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from . import mscli

CONTRACT = "vqs.microsoft-metadata/1"
MAX_STDOUT_BYTES = 512_000
MAX_TIMEOUT = 60
TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,79}$")
COMMANDS: dict[str, tuple[str, ...]] = {
    "catalog.describe": ("catalog", "describe"),
    "formatting.describe_property": ("formatting", "describe-property"),
    "formatting.describe_object": ("formatting", "describe-object"),
    "formatting.effective_properties": ("formatting", "effective-properties"),
}
ARG_COUNTS = {
    "catalog.describe": 1,
    "formatting.describe_property": 3,
    "formatting.describe_object": 2,
    "formatting.effective_properties": 1,
}
Runner = Callable[[list[str], int], dict[str, Any]]


def _blocked(capability: str, reason: str) -> dict[str, Any]:
    return {"contract": CONTRACT, "capability": capability,
            "status": "blocked", "reason": reason,
            "source": "microsoft_cli", "mutates_report": False}


def query(
    attestation: dict[str, Any],
    capability: str,
    *names: str,
    runner: Runner | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Lookup allowlisted CLI capability using the preflight-pinned binary.

    SHA-256 binds structured metadata and exact tool invocation.
    Unknown/invalid response shapes fail closed; CLI errors cannot
    masquerade as supported formatting for a future repair compiler.
    """
    if capability not in COMMANDS or len(names) != ARG_COUNTS.get(capability):
        return _blocked(capability, "unsupported Microsoft metadata capability")
    if any(not isinstance(n, str) or not TOKEN.fullmatch(n) for n in names):
        return _blocked(capability, "invalid visual/object/property identifier")
    if (isinstance(timeout, bool) or not isinstance(timeout, int)
            or not 1 <= timeout <= MAX_TIMEOUT):
        return _blocked(capability, "metadata timeout outside approved bounds")
    if (not isinstance(attestation, dict)
            or attestation.get("status") != "pass"
            or attestation.get("validation_provider") != "microsoft"
            or attestation.get("assurance") != "microsoft_structural_only"
            or not isinstance(attestation.get("cli"), dict)
            or not isinstance(attestation.get("probe"), dict)):
        return _blocked(capability, "missing approved Microsoft toolchain preflight")
    cli = attestation["cli"]
    path = cli.get("path")
    version = cli.get("version")
    if (not isinstance(path, str) or not path
            or cli.get("status") != "pass"
            or attestation["probe"].get("path") != path
            or attestation["probe"].get("version") != version):
        return _blocked(capability, "Microsoft executable identity mismatch")
    argv = [path, *COMMANDS[capability], *names]
    try:
        result = (runner or mscli._run)(argv, timeout)
        if not isinstance(result, dict):
            raise TypeError("CLI metadata runner returned a non-object")
        if result.get("returncode") != 0:
            return _blocked(capability, "metadata command failed or was refused")
        stdout = result.get("stdout")
        if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_STDOUT_BYTES:
            return _blocked(capability, "oversized or missing metadata JSON")
        envelope = json.loads(stdout)
        if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), dict):
            return _blocked(capability, "CLI response missing structured data")
        data = envelope["data"]
        if data.get("visualType") != names[0]:
            return _blocked(capability, "metadata visual type differs from request")
        if capability == "formatting.describe_property":
            prop = data.get("property")
            if (data.get("objectName") != names[1]
                    or data.get("propertyName") != names[2]
                    or not isinstance(prop, dict)
                    or not isinstance(prop.get("type"), str)):
                return _blocked(capability, "missing or mismatched formatting property metadata")
        if capability == "catalog.describe" and (
                not isinstance(data.get("roles"), dict)
                or not isinstance(data.get("requiredRoles"), list)
                or not isinstance(data.get("deprecated"), bool)):
            return _blocked(capability, "catalog lacks essential role/deprecation fields")
        if capability in ("formatting.describe_object", "formatting.effective_properties") and (
                not data or (capability == "formatting.describe_object"
                             and data.get("objectName") != names[1])):
            return _blocked(capability, "formatting metadata incomplete")
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        return _blocked(capability, f"metadata probe malformed: {type(exc).__name__}")
    record = {"capability": capability, "command": argv,
              "cli_version": version, "data": data}
    digest = hashlib.sha256(json.dumps(record, sort_keys=True,
                                       ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"contract": CONTRACT, "capability": capability,
            "status": "pass", "source": "microsoft_cli",
            "mutates_report": False, "command": argv,
            "version": version, "data": data, "sha256": digest}
