"""Fake powerbi-modeling-mcp stdio server for hermetic client tests.

Usage: fake_modeling_mcp.py SCRIPT_JSON [REQUEST_LOG]
SCRIPT_JSON: {"responses": {"<tool>/<operation>": <payload or
{"__error__": {...}} | {"__raw__": "<line>"} |
{"__sequence__": [<payload per call in order>]} |
{"__text__": "<verbatim content text>"}>}, "sleep": <seconds>,
"strict_handshake": <bool>, "capabilities": {...}}
Responds to tools/call with MCP content blocks; logs every request to
REQUEST_LOG when given. Never touches live models.
strict_handshake: reject tools/call before initialize (default False
keeps legacy scripts working; strict tests opt in explicitly).
"""
import json
import sys
import time


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        script = json.load(handle)
    responses = script.get("responses", {})
    sleep = script.get("sleep", 0)
    strict = script.get("strict_handshake", False)
    capabilities = script.get("capabilities", {"tools": {}})
    initialized = False
    log_path = sys.argv[2] if len(sys.argv) > 2 else None
    stdin = sys.stdin
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        if "id" not in message:
            continue
        rid = message.get("id")
        if message.get("method") == "initialize":
            result: dict = {"protocolVersion": "2024-11-05",
                            "capabilities": dict(capabilities),
                            "serverInfo": {"name": "fake-modeling-mcp",
                                           "version": "0.0.0-test"}}
            initialized = True
            if log_path is not None:
                with open(log_path, "a", encoding="utf-8") as log:
                    log.write(json.dumps(
                        {"tool": "handshake/initialize",
                         "request": {"operation": "initialize"}}) + "\n")
        elif strict and not initialized:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32002,
                           "message": "not initialized"}}) + "\n")
            sys.stdout.flush()
            continue
        elif message.get("method") != "tools/call":
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32601, "message": "Method not found"}})
                + "\n")
            sys.stdout.flush()
            continue
        else:
            params = message.get("params", {})
            tool = params.get("name", "")
            request = (params.get("arguments") or {}).get("request", {})
            operation = request.get("operation", "")
            if log_path is not None:
                with open(log_path, "a", encoding="utf-8") as log:
                    log.write(json.dumps({"tool": tool, "request": request})
                              + "\n")
            key = f"{tool}/{operation}"
            if key not in responses:
                sys.stdout.write(json.dumps(
                    {"jsonrpc": "2.0", "id": rid,
                     "error": {"code": -32602,
                               "message": f"no scripted response for {key}"}})
                    + "\n")
                sys.stdout.flush()
                continue
            scripted = responses[key]
            if isinstance(scripted, dict) and "__sequence__" in scripted:
                queue = scripted["__sequence__"]
                scripted = queue.pop(0) if queue else {}
            if isinstance(scripted, dict) and "__error__" in scripted:
                sys.stdout.write(json.dumps(
                    {"jsonrpc": "2.0", "id": rid,
                     "error": scripted["__error__"]}) + "\n")
                sys.stdout.flush()
                continue
            if isinstance(scripted, dict) and "__raw__" in scripted:
                sys.stdout.write(str(scripted["__raw__"]) + "\n")
                sys.stdout.flush()
                continue
            if isinstance(scripted, dict) and "__text__" in scripted:
                result = {"content": [{"type": "text",
                                       "text": str(scripted["__text__"])}]}
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                             "result": result}) + "\n")
                sys.stdout.flush()
                continue
            if sleep:
                time.sleep(sleep)
            result = {"content": [{"type": "text",
                                   "text": json.dumps(scripted)}]}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                     "result": result}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
