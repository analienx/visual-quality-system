"""Optional stdio MCP server: the same engine behind ``vqs.*`` tools.

Transport-only package (stdlib, no third-party dependencies): JSON-RPC
2.0 over newline-delimited stdio. Tool behavior lives in
:mod:`vqs.pipeline` so CLI and MCP can never disagree; this package
contributes transport names, JSON Schemas, and strict argument
validation. MCP tool names use underscores (``vqs_inspect``) because
the MCP name grammar forbids dots; envelopes carry the canonical
dotted IDs (``vqs.inspect``). There is deliberately no shell tool.
"""
