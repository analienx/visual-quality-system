"""Stdio JSON-RPC transport for VQS agent tools (no third-party deps).

Reads newline-delimited JSON-RPC 2.0 requests from stdin, writes one
response per request to stdout, and exits 0 on EOF. Only JSON-RPC
traffic goes to stdout; nothing is ever logged there. Tool verdicts
(including blocked) are normal results, never transport errors:
``isError`` is reserved for malformed calls the schemas reject.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from vqs import __version__
from vqs.mcp.schemas import OUTPUT_SCHEMA, TOOL_SPECS, validate_call

PROTOCOL_VERSION = "2024-11-05"
LEGACY_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
MODERN_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = (*LEGACY_VERSIONS, MODERN_VERSION)
VERSION_META = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_META = "io.modelcontextprotocol/clientCapabilities"
SERVER_META = "io.modelcontextprotocol/serverInfo"
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
    if name == "vqs_theme":
        from vqs.theme import (
            apply_theme,
            audit_candidate,
            inspect_report,
            load_palette,
            palette_contrast_check,
            palette_presets,
            preview_plan,
        )

        action = arguments["action"]
        if action == "presets":
            return {"status": "pass", "presets": list(palette_presets()),
                    "default": "executive-blue", "modes": ["light", "dark"]}
        report = arguments.get("report_dir")
        if not isinstance(report, str) or not report:
            return pipeline.blocked_envelope("vqs.theme",
                                              ["report_dir required for " + action])
        if action == "audit":
            return audit_candidate(Path(report))
        if action == "inspect":
            return inspect_report(Path(report))
        if action not in ("preview", "apply"):
            return pipeline.blocked_envelope("vqs.theme", ["invalid theme action"])
        mode = arguments.get("mode")
        if mode not in ("light", "dark"):
            return pipeline.blocked_envelope("vqs.theme", ["mode light/dark required"])
        palette_path = arguments.get("palette_path")
        preset = arguments.get("palette_preset")
        if palette_path and preset:
            return pipeline.blocked_envelope("vqs.theme",
                                              ["choose palette_preset or palette_path"])
        palette = load_palette(mode, Path(palette_path) if palette_path else None,
                               preset or "executive-blue")
        violations = palette_contrast_check(palette)
        if violations:
            return {"status": "blocked", "violations": violations,
                    "reason": "palette contrast check failed"}
        if action == "preview":
            return preview_plan(Path(report), mode, palette)
        root = arguments.get("candidate_root")
        if not isinstance(root, str) or not root:
            return pipeline.blocked_envelope("vqs.theme",
                                              ["apply requires explicit candidate_root"])
        return apply_theme(Path(report), mode, palette, Path(root))
    if name == "vqs_inspect":
        from vqs.source_paths import resolve_project_input

        report, model = arguments["report_dir"], arguments.get("model_dir")
        if Path(report).exists():
            try:
                report, model = resolve_project_input(report, model)
            except ValueError as exc:
                return pipeline.blocked_envelope("vqs.inspect", [str(exc)])
        return pipeline.inspect_report(report, model, config)
    if name == "vqs_review":
        params: dict[str, Any] = {"scope": "static", "state": "default",
                                  "run_root": ".vqs-runs"}
        params.update({k: v for k, v in arguments.items()
                       if k in ("report_dir", "model_dir", "facts", "scope",
                                "state", "run_root", "run_id", "resume_from")
                       and v is not None})
        if (isinstance(params.get("report_dir"), str)
                and Path(params["report_dir"]).exists()):
            from vqs.source_paths import resolve_project_input

            try:
                params["report_dir"], params["model_dir"] = resolve_project_input(
                    params["report_dir"], params.get("model_dir"))
            except ValueError as exc:
                return pipeline.blocked_envelope("vqs.review", [str(exc)])
        return pipeline.review_report(config=config, **params)
    if name == "vqs_propose":
        params_propose: dict[str, Any] = {"run_root": arguments["run_root"],
                                          "run_id": arguments["run_id"]}
        if arguments.get("facts") is not None:
            params_propose["facts"] = arguments["facts"]
        return pipeline.propose_candidates(**params_propose)
    if name == "vqs_repair":
        params = {"plan_path": arguments["plan_path"],
                  "original": arguments["original"],
                  "candidate_root": arguments["candidate_root"]}
        params.update({k: v for k, v in arguments.items()
                       if k in ("run_root", "run_id", "authoring_backend",
                                "authoring_timeout", "authoring_allow_warnings",
                                "authoring_assurance")
                       and v is not None})
        return pipeline.repair_candidate(**params)
    if name == "vqs_verify":
        params = {k: v for k, v in arguments.items()
                  if k in ("run_root", "run_id", "original", "candidate",
                           "edits", "approved_removals")}
        return pipeline.verify_candidate(**params)
    if name == "vqs_verify_runtime":
        params = {k: v for k, v in arguments.items()
                  if k in ("run_root", "run_id", "pid", "scale",
                           "wait_seconds", "reload_first", "runtime_run_id")
                  and v is not None}
        return pipeline.verify_runtime(**params)
    if name == "vqs_promote":
        params = {k: v for k, v in arguments.items()
                  if k in ("run_root", "run_id", "owner_approval",
                           "runtime_run_id", "backup_dir", "desktop_recheck",
                           "promote_run_id", "scope")
                  and v is not None}
        return pipeline.promote_candidate(**params)
    if name == "vqs_run":
        from vqs.coordinator import run_workflow

        run_params: dict[str, Any] = {"mode": "review", "scope": "static",
                                      "run_root": arguments["run_root"]}
        run_params.update({k: v for k, v in arguments.items()
                           if k in ("report_dir", "model_dir", "facts",
                                    "mode", "scope", "run_id",
                                    "resume_from", "candidate_root",
                                    "plan_path", "fixer_id", "reviewer",
                                    "pid", "renders_dir", "authoring_backend",
                                    "live_answers")
                           and v is not None})
        config, issues = load_config(arguments.get("config_path"))
        if issues:
            return pipeline.blocked_envelope("vqs.run", issues)
        if (isinstance(run_params.get("report_dir"), str)
                and Path(run_params["report_dir"]).exists()):
            from vqs.source_paths import resolve_project_input

            try:
                run_params["report_dir"], run_params["model_dir"] = resolve_project_input(
                    run_params["report_dir"], run_params.get("model_dir"))
            except ValueError as exc:
                return pipeline.blocked_envelope("vqs.run", [str(exc)])
        return run_workflow(config=config, **run_params)
    return pipeline.run_status_report(arguments["run_root"],
                                      arguments["run_id"])


def _compact_result(envelope: dict[str, Any]) -> dict[str, Any]:
    from vqs.agent_summary import summarize

    if envelope.get("tool") == "vqs.run":
        return summarize(envelope)
    if envelope.get("tool") == "vqs.review":
        compact = {key: envelope[key] for key in
                   ("tool", "verdict", "run_id", "run_dir", "blocked_reasons",
                    "next_actions", "coverage") if key in envelope}
        compact["findings"] = [
            {key: finding[key] for key in
             ("check", "status", "severity", "location") if key in finding}
            for finding in envelope.get("findings", [])[:50]
            if isinstance(finding, dict)]
        compact["evidence"] = ("Full sealed review evidence remains in run_dir; "
                               "no human acceptance is implied")
        return compact
    # Inspect, proposal, repair, verification and themes are explicitly
    # requested tools. Do not silently strip required plans/edits/measurements.
    # Only the high-level coordinator and reviewer have a compact default.
    return envelope


def _modern_request(message: dict[str, Any]) -> tuple[bool, str | None]:
    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    if not isinstance(meta, dict) or VERSION_META not in meta:
        return False, None
    requested = meta.get(VERSION_META)
    if requested != MODERN_VERSION:
        return True, requested if isinstance(requested, str) else str(requested)
    if not isinstance(meta.get(CAPABILITIES_META), dict):
        return True, "invalid_client_capabilities"
    info = meta.get("io.modelcontextprotocol/clientInfo")
    if (not isinstance(info, dict)
            or not isinstance(info.get("name"), str)
            or not info["name"].strip()
            or not isinstance(info.get("version"), str)
            or not info["version"].strip()):
        return True, "invalid_client_info"
    return True, None


def _server_identity() -> dict[str, str]:
    return {"name": SERVER_NAME, "version": __version__}


def handle_message(message: Any,
                   session: dict[str, Any] | None = None) -> dict | None:
    """Handle one parsed JSON-RPC message; None for notifications and
    response/error frames (S18: strict lifecycle order and envelope).

    R23: tools/list and tools/call need a live session (initialize
    followed by the initialized notification); without one they are
    rejected with -32002 before touching anything. Session state
    rides the call — this module keeps no session globals.
    """
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    if message.get("jsonrpc") != "2.0":
        if "id" not in message:
            return None  # invalid notification: ignore, never answer
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32600, "message": "Invalid Request"}}
    if "method" not in message:
        return None  # response/error frame: never answer, no side effects
    method = message.get("method")
    request_id = message.get("id", None)
    modern, modern_error = _modern_request(message)
    if method == "server/discover":
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"resultType": "complete",
                           "supportedVersions": list(SUPPORTED_VERSIONS),
                           "capabilities": {"tools": {}},
                           "instructions": ("Use vqs_run mode=repair for supported safe "
                                            "candidates. Never auto-promote; inspect "
                                            "blocked reasons and source provenance."),
                           "ttlMs": 300000, "cacheScope": "public",
                           "_meta": {SERVER_META: _server_identity()}}}
    if modern and modern_error is not None:
        if modern_error in ("invalid_client_capabilities", "invalid_client_info"):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": modern_error}}
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32022,
                          "message": "Unsupported protocol version",
                          "data": {"requested": modern_error,
                                   "supported": list(SUPPORTED_VERSIONS)}}}
    if "id" not in message:
        if (session is not None and method == "notifications/initialized"
                and session.get("initialized")):
            session["notified"] = True
        return None  # notification: no response, even for unknown methods
    if method == "initialize":
        params = message.get("params")
        version = params.get("protocolVersion") if isinstance(params, dict) else None
        fields = params if isinstance(params, dict) else {}
        client_info = fields.get("clientInfo")
        if version not in LEGACY_VERSIONS:
            # Preserve the conservative fail-closed legacy handshake.
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": f"Unsupported protocolVersion {version!r}; "
                                         f"supported: {', '.join(LEGACY_VERSIONS)}"}}
        name = client_info.get("name") if isinstance(client_info, dict) else None
        version_text = (client_info.get("version")
                        if isinstance(client_info, dict) else None)
        if (not isinstance(fields.get("capabilities"), dict)
                or not isinstance(client_info, dict)
                or not isinstance(name, str) or not name.strip()
                or not isinstance(version_text, str)
                or not version_text.strip()):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602,
                              "message": "initialize requires capabilities "
                                         "and clientInfo {name, version} "
                                         "as nonempty strings"}}
        if session is not None:
            session["initialized"] = True
            session["protocolVersion"] = version
            session["clientInfo"] = {"name": client_info["name"],
                                     "version": client_info["version"]}
        return {"jsonrpc": "2.0", "id": request_id,
                "result": {"protocolVersion": version,
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": SERVER_NAME,
                                          "version": __version__}}}
    if (method in ("tools/list", "tools/call")
            and not modern
            and (session is None or not session.get("initialized")
                 or not session.get("notified"))):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32002,
                              "message": "Server not initialized; send initialize "
                                         "and notifications/initialized first"}}
    if method == "tools/list":
        negotiated = (MODERN_VERSION if modern
                      else session.get("protocolVersion", "2024-11-05")
                      if session is not None else "2024-11-05")
        include_output = negotiated in ("2025-06-18", "2025-11-25",
                                        MODERN_VERSION)
        listed = [{"name": spec["name"],
                   "description": spec["description"],
                   "inputSchema": spec["inputSchema"],
                   **({"outputSchema": OUTPUT_SCHEMA} if include_output else {})}
                  for spec in TOOL_SPECS]
        result: dict[str, Any] = {"tools": listed}
        if modern:
            result.update(resultType="complete", ttlMs=300000,
                          cacheScope="public",
                          _meta={SERVER_META: _server_identity()})
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
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
        negotiated = (MODERN_VERSION if modern else
                      session.get("protocolVersion", "2024-11-05")
                      if session is not None else "2024-11-05")
        compact = negotiated in ("2025-06-18", "2025-11-25",
                                 MODERN_VERSION)
        output = _compact_result(envelope) if compact else envelope
        result: dict[str, Any] = {"content": [
            {"type": "text", "text": json.dumps(output, ensure_ascii=False)}]}
        if compact:
            result["structuredContent"] = output
        if modern:
            result.update(resultType="complete",
                          _meta={SERVER_META: _server_identity()})
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
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
