"""F05 RED: modeling transport must use the documented startup + lifecycle.

The client launches the bare default binary and sends tools/call
without MCP initialize/initialized negotiation or capability checks.
The strict protocol fixture rejects all of that; every test below is
RED until the M3 transport fix lands.

Documented launch mode: powerbi-modeling-mcp --start (Microsoft
powerbi-modeling-mcp README); missing launcher stays an environmental
blocker (ModelingError), never a reason to weaken the protocol.
"""
import json
import sys
from pathlib import Path

import pytest

from vqs.powerbi.modeling import StdioModelingClient

FAKE = Path(__file__).resolve().parent / "helpers" / "fake_modeling_mcp.py"

ONE_INSTANCE = [{"server": "localhost:52383", "database": "AdventureWorks"}]


def _client(tmp_path: Path, responses: dict, **extra) -> StdioModelingClient:
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / "requests.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])
    client._vqs_log = log  # test-only handle, never read by vqs/*
    return client


def _logged(client: StdioModelingClient) -> list[dict]:
    log = client._vqs_log
    if not log.exists():
        return []
    return [json.loads(line) for line in
            log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _connected(responses: dict | None = None) -> dict:
    scripted = {"connection_operations/ListLocalInstances": ONE_INSTANCE,
                "connection_operations/Connect": {"connection": "ok"}}
    scripted.update(responses or {})
    return scripted


def test_f05_default_command_uses_documented_start_flag() -> None:
    """RED: default launch must pass the documented --start flag."""
    client = StdioModelingClient()
    try:
        assert "--start" in client._command
    finally:
        client.close()


def test_f05_strict_server_accepts_client_lifecycle(tmp_path: Path) -> None:
    """RED: full connect works against a strict initialize-first server."""
    client = _client(tmp_path, _connected(), strict_handshake=True)
    try:
        bound = client.connect()
    finally:
        client.close()
    assert bound["model"] == "localhost:52383/AdventureWorks"


def test_f05_initialize_precedes_first_tool_call(tmp_path: Path) -> None:
    """RED: the wire log shows initialize before any tools/call."""
    client = _client(tmp_path, _connected(), strict_handshake=True)
    try:
        client.connect()
    finally:
        client.close()
    kinds = ["handshake" if entry.get("tool", "").startswith("handshake")
             else "call" for entry in _logged(client)]
    assert "handshake" in kinds
    assert kinds.index("handshake") < kinds.index("call")


def test_f05_missing_tools_capability_refuses(tmp_path: Path) -> None:
    """RED: a server negotiating no tools capability must be refused."""
    client = _client(tmp_path, _connected(), capabilities={})
    try:
        with pytest.raises(Exception, match="capabilit"):
            client.connect()
    finally:
        client.close()
