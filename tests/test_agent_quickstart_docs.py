"""Keep the human-facing agent quickstart aligned with the live MCP contract."""
from __future__ import annotations

import json
import re
from pathlib import Path

from vqs.mcp.schemas import TOOL_SPECS

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "AI_AGENT_QUICKSTART.md"


def test_quickstart_is_discoverable_from_readme_and_docs_hub():
    assert GUIDE.is_file()
    assert "AI_AGENT_QUICKSTART.md" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "AI_AGENT_QUICKSTART.md" in (ROOT / "docs" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "Use VQS with an AI agent" in (ROOT / "README.md").read_text(
        encoding="utf-8"
    )


def test_both_documented_mcp_config_shapes_launch_real_server():
    guide = GUIDE.read_text(encoding="utf-8")
    sections = re.findall(r"```json\n(.*?)\n```", guide, re.DOTALL)
    assert len(sections) == 2
    for section, section_name in zip(sections, ("mcpServers", "servers")):
        configuration = json.loads(section)
        entry = configuration[section_name]["vqs"]
        assert entry["command"] == "python"
        assert entry["args"] == ["-m", "vqs.mcp"]
    assert "vqs_theme" not in {spec["name"] for spec in TOOL_SPECS}


def test_documented_mcp_tools_exist_and_links_resolve():
    guide = GUIDE.read_text(encoding="utf-8")
    actual = {spec["name"] for spec in TOOL_SPECS}
    assert {"vqs_inspect", "vqs_review", "vqs_run", "vqs_propose",
            "vqs_repair", "vqs_verify"}.issubset(actual)
    assert all(f"`{name}`" in guide for name in actual if name in (
        "vqs_inspect", "vqs_review", "vqs_run", "vqs_propose",
        "vqs_repair", "vqs_verify"
    ))
    for target in re.findall(r"\]\(([^)]+\.md)(?:#[^)]*)?\)", guide):
        assert (GUIDE.parent / target).exists(), target
    assert "blocked" in guide and "owner" in guide.lower()
