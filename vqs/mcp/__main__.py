"""Run the stdio MCP server as ``python -m vqs.mcp``."""
import sys

from vqs.mcp.server import main

raise SystemExit(main(sys.argv[1:]))
