"""Tool schemas and strict argument validation for the MCP server."""
from __future__ import annotations

from typing import Any

TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {"name": "vqs_inspect", "tool": "vqs.inspect",
     "description": "Measure check-ready facts for a PBIR report.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "report_dir": {"type": "string"},
             "model_dir": {"type": ["string", "null"]},
             "config_path": {"type": ["string", "null"]}},
         "required": ["report_dir"],
         "additionalProperties": False}},
    {"name": "vqs_review", "tool": "vqs.review",
     "description": "Review measured sources to a sealed verdict.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "report_dir": {"type": ["string", "null"]},
             "model_dir": {"type": ["string", "null"]},
             "facts": {"type": ["object", "null"]},
             "scope": {"type": "string", "enum": ["static", "desktop",
                                                 "release"]},
             "state": {"type": "string"},
             "config_path": {"type": ["string", "null"]},
             "run_root": {"type": "string"},
             "run_id": {"type": ["string", "null"]},
             "resume_from": {"type": ["string", "null"]}},
         "required": [],
         "additionalProperties": False}},
    {"name": "vqs_propose", "tool": "vqs.propose",
     "description": "Triage a sealed review run into typed candidates.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "run_root": {"type": "string"},
             "run_id": {"type": "string"},
             "facts": {"type": ["object", "null"]}},
         "required": ["run_root", "run_id"],
         "additionalProperties": False}},
    {"name": "vqs_repair", "tool": "vqs.repair",
     "description": "Validate a repair plan, execute it, and seal the run.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "plan_path": {"type": "string"},
             "original": {"type": "string"},
             "candidate_root": {"type": "string"},
             "run_root": {"type": ["string", "null"]},
             "run_id": {"type": ["string", "null"]}},
         "required": ["plan_path", "original", "candidate_root"],
         "additionalProperties": False}},
    {"name": "vqs_verify", "tool": "vqs.verify",
     "description": "Verify a candidate differs solely by declared edits.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "run_root": {"type": ["string", "null"]},
             "run_id": {"type": ["string", "null"]},
             "original": {"type": ["string", "null"]},
             "candidate": {"type": ["string", "null"]},
             "edits": {"type": ["array", "null"],
                        "items": {"type": "object"}},
             "approved_removals": {"type": ["array", "null"],
                                  "items": {"type": "string"}}},
         "required": [],
         "additionalProperties": False}},
    {"name": "vqs_run_status", "tool": "vqs.run_status",
     "description": "Report a sealed run's status and event trail.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "run_root": {"type": "string"},
             "run_id": {"type": "string"}},
         "required": ["run_root", "run_id"],
         "additionalProperties": False}},
    {"name": "vqs_verify_runtime", "tool": "vqs.verify-runtime",
     "description": "Verify a sealed repair candidate live in Desktop; never the original.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "run_root": {"type": "string"},
             "run_id": {"type": "string"},
             "pid": {"type": ["integer", "null"]},
             "scale": {"type": "integer"},
             "wait_seconds": {"type": "integer"},
             "reload_first": {"type": "boolean"},
             "runtime_run_id": {"type": ["string", "null"]}},
         "required": ["run_root", "run_id"],
         "additionalProperties": False}},
    {"name": "vqs_promote", "tool": "vqs.promote",
     "description": "Promote a verified candidate onto the original with owner approval.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "run_root": {"type": "string"},
             "run_id": {"type": "string"},
             "owner_approval": {"type": "string"},
             "runtime_run_id": {"type": ["string", "null"]},
             "backup_dir": {"type": ["string", "null"]},
             "desktop_recheck": {"type": "boolean"},
             "promote_run_id": {"type": ["string", "null"]}},
         "required": ["run_root", "run_id", "owner_approval"],
         "additionalProperties": False}},
    {"name": "vqs_run", "tool": "vqs.run",
     "description": "Run the orchestrated Power BI workflow.",
     "inputSchema": {
         "type": "object",
         "properties": {
             "report_dir": {"type": ["string", "null"]},
             "model_dir": {"type": ["string", "null"]},
             "facts": {"type": ["object", "null"]},
             "mode": {"type": "string",
                      "enum": ["review", "propose", "repair"]},
             "scope": {"type": "string",
                       "enum": ["static", "desktop", "release"]},
             "config_path": {"type": ["string", "null"]},
             "run_root": {"type": "string"},
             "run_id": {"type": ["string", "null"]},
             "resume_from": {"type": ["string", "null"]},
             "candidate_root": {"type": ["string", "null"]},
             "plan_path": {"type": ["string", "null"]},
             "fixer_id": {"type": ["string", "null"]},
             "reviewer": {"type": ["string", "null"]}},
         "required": ["run_root"],
         "additionalProperties": False}},
)

_BY_NAME = {spec["name"]: spec for spec in TOOL_SPECS}


def _matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_matches(value, item) for item in expected)
    if expected == "string":
        return isinstance(value, str)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    return True


def validate_call(name: Any, arguments: Any) -> tuple[dict | None, str | None]:
    """Validate a tools/call; (spec, None) or (None, error message)."""
    if not isinstance(name, str) or name not in _BY_NAME:
        return None, f"unknown tool: {name!r}"
    if not isinstance(arguments, dict):
        return None, "arguments must be an object"
    schema = _BY_NAME[name]["inputSchema"]
    for key in arguments:
        if key not in schema["properties"]:
            return None, f"unknown argument: {key!r}"
    for key in schema.get("required", []):
        if key not in arguments:
            return None, f"missing argument: {key!r}"
    for key, value in arguments.items():
        prop = schema["properties"][key]
        if not _matches(value, prop.get("type", "string")):
            return None, f"argument {key!r} has the wrong type"
        if "enum" in prop and value not in prop["enum"]:
            return None, f"argument {key!r} is not an allowed value"
        items = prop.get("items")
        if (isinstance(value, list) and isinstance(items, dict)
                and any(not _matches(item, items.get("type", "string"))
                        for item in value)):
            return None, f"argument {key!r} has a wrongly typed element"
    return _BY_NAME[name], None
