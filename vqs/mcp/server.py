"""Stdio JSON-RPC transport for the six VQS tools (no third-party deps).

Reads newline-delimited JSON-RPC 2.0 requests from stdin, writes one
response per request to stdout, and exits 0 on EOF. Only JSON-RPC
traffic goes to stdout; nothing is ever logged there. Tool verdicts
(including blocked) are normal results, never transport errors:
``isError`` is reserved for malformed calls the schemas reject.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from vqs import __version__
from vqs.mcp.schemas import TOOL_SPECS, validate_call

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "vqs-mcp"


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one validated tool call through the shared engine."""
    from vqs import pipeline
    from vqs.config import default_config, load_config

    config = default_config()
    config_path = arguments.get("config_path")
    if name in ("vqs_inspect", "vqs_review"):
        config, issues = load_config(config_path)
        if issues:
            return pipeline.blocked_envelope(
                {"vqs_inspect": "vqs.inspect",
                 "vqs_review": "vqs.review"}[name], issues)
    if name == "vqs_inspect":
        return pipeline.inspect_report(arguments["report_dir"],
                                       arguments.get("model_dir"), config)
    if name == "vqs_review":
        params: dict[str, Any] = {"scope": "static", "state": "default",
                                  "run_root": ".vqs-runs"}
        params.update({k: v for k, v in arguments.items()
                       if k in ("report_dir", "model_dir", "facts", "scope",
                                "state", "run_root", "run_id", "resume_from")
                       and v is not None})
        return pipeline.review_report(config=config, **params)
    if name == "vqs_propose":
        return pipeline.propose_candidates(arguments["run_root"],
                                           arguments["run_id"])
    if name == "vqs_repair":
        params = {"plan_path": arguments["plan_path"],
                  "original": arguments["original"],
                  "candidate_root": arguments["candidate_root"]}
        params.update({k: v for k, v in arguments.items()
                       if k in ("run_root", "run_id") and v is not None})
        return pipeline.repair_candidate(**params)
    if name == "vqs_verify":
        params = {k: v for k, v in arguments.items()
                  if k in ("run_root", "run_id", "original", "candidate",
                           "edits", "approved_removals")}
        return pipeline.verify_candidate(**params)
    return pipeline.run_status_report(arguments["run_root"],
                                      arguments["run_id"])


def handle_message(message: Any,
                   session: dict[str, Any] | None = None) -> dict | None:
    """Handle one parsed JSON-RPC message; None for notifications.

    R23: tools/list and tools/call need a live session (initialize
    followed by the initialized notification); without one they are
    rejected with -32002 before touching anything. Session state
    rides the call — this module keeps no session globals.
    """
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    method = message.get("method")
    request_id = message.get("id", None)
    if "id" not in message:
        if session is not None and method == "notifications/initialized":
            session["notified"] = True
        return None  # notification: no response, even for unknown methods
    if method == "initialize":
        params = message.get("params")
        version = params.get("protocolVersion") if isinstance(params, dict) else None
        if version is not None and version != PROTOCOL_VERSION:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": f"Unsupported protocolVersion {version!r}; "
                                         f"server speaks {PROTOCOL_VERSION}"}}
        if session is not None:
            session["initialized"] = True
            if version is not None:
                session["protocolVersion"] = version
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"protocolVersion": PROTOCOL_VERSION,
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": SERVER_NAME,
                                          "version": __version__}}}
    if (method in ("tools/list", "tools/call")
            and (session is None or not session.get("initialized")
                 or not session.get("notified"))):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32002,
                              "message": "Server not initialized; send initialize "
                                         "and notifications/initialized first"}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"tools": [
                    {"name": spec["name"],
                     "description": spec["description"],
                     "inputSchema": spec["inputSchema"]}
                    for spec in TOOL_SPECS]}}
    if method == "tools/call":
        params = message.get("params")
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": "Invalid params"}}
        spec, error = validate_call(params.get("name"),
                                    params.get("arguments", {}))
        if error is not None:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": error}}
        assert spec is not None
        try:
            envelope = _dispatch(spec["name"], params.get("arguments", {}))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32603,
                              "message": f"Internal error: {exc}"}}
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"content": [
                    {"type": "text",
                     "text": json.dumps(envelope, ensure_ascii=False)}]}}
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def serve(reader: Any = None, writer: Any = None) -> int:
    """Serve one stdio session; streams are injectable for tests."""
    reader = sys.stdin if reader is None else reader
    writer = sys.stdout if writer is None else writer
    session: dict[str, Any] = {}
    for line in reader:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            writer.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700,
                           "message": "Parse error"}}) + "\n")
            writer.flush()
            continue
        response = handle_message(message, session)
        if response is not None:
            writer.write(json.dumps(response, ensure_ascii=False) + "\n")
            writer.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Launch the stdio server; argv must be empty (no shell tool, no flags)."""
    if argv:
        sys.stderr.write("vqs-mcp takes no arguments; speak JSON-RPC on stdio\n")
        return 2
    return serve()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
