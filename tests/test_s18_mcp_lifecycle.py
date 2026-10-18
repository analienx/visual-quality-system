"""S18: strict MCP lifecycle on the server, tolerant reads on the client.

Server: notifications/initialized before initialize is ignored,
initialize requires protocolVersion/capabilities/clientInfo, every
message needs jsonrpc 2.0, and response/error frames are never
answered. Client: legal interleaved logging/progress frames are
consumed before the matching response under one finite deadline.
"""
import json
import sys
from pathlib import Path

import pytest

from vqs.mcp.server import PROTOCOL_VERSION, handle_message
from vqs.powerbi.modeling import ModelingError, ModelingScope

FAKE = (Path(__file__).resolve().parent / "helpers"
        / "fake_modeling_mcp.py")
ONE_INSTANCE = [{"server": "localhost:52383",
                 "database": "AdventureWorks"}]


def _init(msg_id=1, **overrides) -> dict:
    params = {"protocolVersion": PROTOCOL_VERSION,
              "capabilities": {},
              "clientInfo": {"name": "s18", "version": "0"}}
    params.update(overrides)
    return {"jsonrpc": "2.0", "id": msg_id, "method": "initialize",
            "params": params}


def _initialized() -> dict:
    return {"jsonrpc": "2.0", "method": "notifications/initialized"}


def test_initialized_before_initialize_ignored() -> None:
    """S18: an early initialized notification buys no session."""
    session: dict = {}
    assert handle_message(_initialized(), session) is None
    assert session == {}
    handle_message(_init(), session)
    assert session.get("initialized") is True
    assert session.get("notified") is None
    denied = handle_message({"jsonrpc": "2.0", "id": 2,
                             "method": "tools/list"}, session)
    assert denied.get("error", {}).get("code") == -32002
    assert handle_message(_initialized(), session) is None
    admitted = handle_message({"jsonrpc": "2.0", "id": 3,
                               "method": "tools/list"}, session)
    assert "error" not in admitted


def test_initialize_missing_fields_rejected() -> None:
    """S18: version/capabilities/clientInfo are all required."""
    cases = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        _init(protocolVersion="1999-01-01"),
        _init(capabilities="yes-please"),
        _init(clientInfo={"name": "s18"}),
        _init(clientInfo={"name": "", "version": ""}),
    ]
    for message in cases:
        response = handle_message(message, {})
        assert response.get("error", {}).get("code") == -32602, message


def test_invalid_envelope_rejected() -> None:
    """S18: jsonrpc 2.0 is required; bad notifications stay silent."""
    assert handle_message({"id": 1, "method": "tools/list"},
                          {})["error"]["code"] == -32600
    assert handle_message({"jsonrpc": "1.0", "id": 1,
                           "method": "tools/list"},
                          {})["error"]["code"] == -32600
    odd = handle_message(["not", "a", "dict"], {})
    assert odd["error"]["code"] == -32600
    assert handle_message({"method": "tools/list"}, {}) is None


def test_response_and_error_frames_ignored() -> None:
    """S18: frames without a method are never answered."""
    session: dict = {}
    assert handle_message({"jsonrpc": "2.0", "id": 5,
                           "result": {"ok": True}}, session) is None
    assert handle_message({"jsonrpc": "2.0", "id": 6, "error": {
        "code": -32603, "message": "boom"}}, session) is None
    assert session == {}


def _client(tmp_path: Path, responses: dict, name: str = "script.json",
            **extra):
    from vqs.powerbi.modeling import StdioModelingClient

    script = tmp_path / name
    script.write_text(json.dumps({"responses": responses, **extra}),
                      encoding="utf-8")
    log = tmp_path / f"{name}.log"
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script), str(log)])
    client._vqs_log = log
    return client


def _connected(**extra: object) -> dict:
    base = {"connection_operations/ListLocalInstances": ONE_INSTANCE,
            "connection_operations/Connect": {"connection": "ok"},
            "dax_query_operations/Execute": {"rows": [{"Revenue": 7}]}}
    base.update(extra)
    return base


def test_interleaved_frames_consumed_before_response(
        tmp_path: Path) -> None:
    """S18: progress + foreign-id frames precede the real answer."""
    noise = [
        json.dumps({"jsonrpc": "2.0", "method": "notifications/log",
                    "params": {"level": "info", "data": "warming"}}),
        json.dumps({"jsonrpc": "2.0", "id": "someone-else",
                    "result": {"content": []}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/progress",
                    "params": {"progressToken": 1}}),
    ]
    client = _client(tmp_path, _connected(),
                     notify_before={"dax_query_operations/Execute": noise})
    try:
        answer = client.query_scoped(
            "EVALUATE ROW(\"n\", 1)",
            ModelingScope(model="localhost:52383/AdventureWorks"))
    finally:
        client.close()
    assert answer["rows"] == [{"Revenue": 7}]


def test_endless_notifications_hit_finite_deadline(
        tmp_path: Path) -> None:
    """S18: an endless progress stream still times out and shuts down."""
    from vqs.powerbi.modeling import StdioModelingClient

    script = tmp_path / "flood.json"
    script.write_text(json.dumps({
        "responses": _connected(),
        "notify_forever": ["dax_query_operations/Execute"]}),
        encoding="utf-8")
    client = StdioModelingClient(
        command=[sys.executable, str(FAKE), str(script)], timeout=3)
    try:
        with pytest.raises(ModelingError, match="timed out or closed"):
            client.query_scoped(
                "EVALUATE ROW(\"n\", 1)",
                ModelingScope(model="localhost:52383/AdventureWorks"))
    finally:
        client.close()
