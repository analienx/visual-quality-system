"""Read-only host probes: tools, Bridge gate, modeling connectivity."""
from __future__ import annotations

import shutil
import subprocess
from typing import Any


def probe_tools() -> dict[str, Any]:
    """Presence evidence for the external CLIs (no install, no claim)."""
    tools = {}
    for name in ("pbir", "powerbi-desktop", "powerbi-modeling-mcp"):
        path = shutil.which(name)
        version = None
        entry: dict[str, Any] = {"path": path, "version": version,
                                 "status": "present" if path else "missing"}
        if name == "powerbi-modeling-mcp":
            # No --version probe: stdio MCP servers answer tools/call, and
            # live connectivity is proven per run via ListLocalInstances.
            entry["version_note"] = ("version probe not attempted for "
                                     "stdio MCP server")
        elif path is not None:
            try:
                completed = subprocess.run(
                    [path, "--version"], capture_output=True, text=True,
                    timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                completed = None
            if completed is not None and completed.returncode == 0:
                lines = (completed.stdout + completed.stderr).strip()
                entry["version"] = (lines.splitlines()[0][:120]
                                    if lines else None)
        tools[name] = entry
    return tools


def probe_bridge_gate(version_text: str | None) -> dict[str, Any]:
    """Judge observed Bridge --version output through the proven gate."""
    from vqs.powerbi.desktop import gate_bridge_version

    if not version_text:
        return {"verdict": "blocked",
                "reason": "no Bridge --version observed on this host"}
    return gate_bridge_version(version_text)


def probe_modeling() -> dict[str, Any]:
    """Attempt a live modeling bind; ambiguity/absence is honest blocked."""
    from vqs.powerbi.modeling import ModelingError, StdioModelingClient

    if shutil.which("powerbi-modeling-mcp") is None:
        return {"verdict": "blocked",
                "reason": "powerbi-modeling-mcp not on PATH"}
    client = StdioModelingClient(timeout=30)
    try:
        bound = client.connect()
    except ModelingError as exc:
        return {"verdict": "blocked", "reason": str(exc)}
    finally:
        client.close()
    return {"verdict": "ready", "bound": bound}


def probe_host() -> dict[str, Any]:
    """Run every read-only probe and return one JSON-serializable verdict."""
    tools = probe_tools()
    bridge = probe_bridge_gate(tools["powerbi-desktop"]["version"])
    modeling = probe_modeling()
    verdict = ("ready" if bridge.get("verdict") == "pass"
               and modeling.get("verdict") == "ready" else "blocked")
    return {"verdict": verdict, "tools": tools,
            "bridge_gate": bridge, "modeling": modeling}
