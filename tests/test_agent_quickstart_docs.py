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
    assert "Fix Power BI with an AI agent" in (ROOT / "README.md").read_text(
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


def test_agent_autofix_architecture_matches_existing_engine():
    from vqs.coordinator import STAGE_ORDER

    guide = GUIDE.read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "AGENT_AUTOFIX_ARCHITECTURE.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "AGENT_AUTOFIX_ARCHITECTURE.md" in guide
    assert "AGENT_AUTOFIX_ARCHITECTURE.md" in readme
    assert readme.index("## Fix Power BI with an AI agent") < readme.index(
        "## Real Power BI showcase"
    )
    assert "Agent-first automatic candidate fixing" in (
        ROOT / "docs" / "CLI.md"
    ).read_text(encoding="utf-8")
    assert "mode=repair" in guide and "--mode repair" in guide
    assert "disposable candidate" in guide.lower()
    assert "mermaid" in architecture
    assert "Agent" in architecture and "Coordinator" in architecture
    assert "Microsoft" in architecture and "Desktop Bridge" in architecture
    assert "TMDL" in architecture and "Modeling MCP" in architecture
    assert all(stage in STAGE_ORDER for stage in (
        "inspect", "review", "propose", "repair", "verify", "remeasure", "summary"
    ))
    descriptions = {spec["name"]: spec["description"] for spec in TOOL_SPECS}
    assert "mode=repair" in descriptions["vqs_run"]
    assert "Never overwrites the original" in descriptions["vqs_run"]
    assert "G6" in architecture
