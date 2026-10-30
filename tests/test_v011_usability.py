"""v0.1.1: source input, safe summary and dual-era MCP contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vqs.agent_summary import summarize
from vqs.mcp.server import SUPPORTED_VERSIONS, handle_message
from vqs.powerbi.author.skill_attest import (
    APPROVED_FILE_COUNT,
    APPROVED_TREE_SHA256,
    _tree_digest,
)
from vqs.source_paths import resolve_project_input

ROOT = Path(__file__).resolve().parents[1]


def test_vendored_approved_skill_is_byte_for_byte_attested():
    bundled = ROOT / "vqs" / "approved_skill" / "powerbi-report-cli"
    digest, count = _tree_digest(bundled)
    assert (digest, count) == (APPROVED_TREE_SHA256, APPROVED_FILE_COUNT)
    assert (bundled.parent / "powerbi-report-cli-upstream.json").is_file()


def test_public_pbip_path_and_model_are_discovered():
    fixture = ROOT / "examples" / "contoso-retail-verified"
    report, model = resolve_project_input(str(fixture / "Contoso Retail.pbip"))
    assert report.endswith("Contoso Retail.Report")
    assert model is not None
    assert Path(model).name == "definition"
    assert Path(model).parent.name == "Contoso Retail.SemanticModel"
    assert resolve_project_input(str(fixture))[0] == report


def test_ambiguous_project_and_missing_paths_are_not_guessed(tmp_path):
    for name in ("A.Report", "B.Report"):
        (tmp_path / name).mkdir()
    with pytest.raises(ValueError, match="2 report folders"):
        resolve_project_input(str(tmp_path))
    with pytest.raises(ValueError, match="must be an existing"):
        resolve_project_input(str(tmp_path / "missing.pbip"))


def test_decision_facing_summary_never_upgrades_evidence():
    massive = {"tool": "vqs.run", "verdict": "blocked", "run_id": "one",
               "run_dir": "/private/runs/one",
               "blocked_reasons": ["requires native proof"],
               "next_actions": ["review candidate"],
               "evidence": [{"blob": "x" * 110000}],
               "summary": {"outcome": "blocked",
                           "resolved_findings": ["layout.overlap"],
                           "remaining_findings": ["typography.font"],
                           "candidate_status": {"status": "verified",
                                                "candidate": "/private/candidate"},
                           "repair_triage": {"decisions": [
                               {"check": "typography.font",
                                "status": "needs_owner_decision",
                                "reason": "effective font not measured"}]}}}
    result = summarize(massive)
    assert result["verdict"] == "blocked"
    assert result["acceptance"] is False
    assert result["fixed"] == ["layout.overlap"]
    assert len(json.dumps(result)) < 1600


def _modern(method, ident, **kwargs):
    return {"jsonrpc": "2.0", "id": ident, "method": method,
            "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {
                    "name": "vqs-test", "version": "1.0.0"}},
                **kwargs}}


def test_modern_stateless_discovery_and_tool_list():
    discovery = handle_message({"jsonrpc": "2.0", "id": 1,
                                "method": "server/discover"}, None)
    assert discovery["result"]["resultType"] == "complete"
    assert "2026-07-28" in discovery["result"]["supportedVersions"]
    assert "2024-11-05" in SUPPORTED_VERSIONS
    tools = handle_message(_modern("tools/list", 2), None)["result"]
    assert tools["resultType"] == "complete"
    assert tools["cacheScope"] == "public"
    assert any(x["name"] == "vqs_theme" for x in tools["tools"])
    assert all("outputSchema" in x for x in tools["tools"])


def test_modern_structured_result_compacts_but_preserves_verdict(monkeypatch):
    import vqs.coordinator
    monkeypatch.setattr(vqs.coordinator, "run_workflow", lambda **kw: {
        "tool": "vqs.run", "verdict": "blocked", "run_id": "abcd",
        "run_dir": "/private/abcd", "evidence": ["x" * 120000],
        "blocked_reasons": ["no safe edit"],
        "summary": {"outcome": "blocked", "remaining_findings": ["a"]}})
    result = handle_message(_modern(
        "tools/call", 3, name="vqs_run",
        arguments={"run_root": "/private", "mode": "repair",
                   "report_dir": "/report"}), None)["result"]
    assert result["resultType"] == "complete"
    assert result["structuredContent"]["verdict"] == "blocked"
    assert len(result["content"][0]["text"]) < 1200
    assert "x" * 1000 not in result["content"][0]["text"]


def test_legacy_handshake_keeps_full_json_result(monkeypatch):
    import vqs.coordinator
    monkeypatch.setattr(vqs.coordinator, "run_workflow", lambda **kw: {
        "tool": "vqs.run", "verdict": "blocked", "evidence": ["legacy-sentinel"]})
    session = {}
    init = handle_message({"jsonrpc": "2.0", "id": 1,
                           "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05",
                                      "capabilities": {},
                                      "clientInfo": {"name": "test",
                                                     "version": "1"}}}, session)
    assert init["result"]["protocolVersion"] == "2024-11-05"
    handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    response = handle_message({"jsonrpc": "2.0", "id": 2,
                               "method": "tools/call",
                               "params": {"name": "vqs_run",
                                          "arguments": {"run_root": "/private"}}}, session)
    assert "structuredContent" not in response["result"]
    assert json.loads(response["result"]["content"][0]["text"])["evidence"] == [
        "legacy-sentinel"]


def test_theme_mcp_presets_is_source_only():
    from vqs.mcp.server import _dispatch
    result = _dispatch("vqs_theme", {"action": "presets"})
    assert result["status"] == "pass" and result["presets"]


def test_automatic_seeded_overlap_repaired_without_source_write(tmp_path):
    """Real PBIR fixture, actual coordinator and candidate diff, no mocks."""
    import shutil

    from vqs.coordinator import run_workflow
    from vqs.pbir import source_digest

    fixture = ROOT / "examples" / "contoso-retail-verified"
    project = tmp_path / "source-project"
    shutil.copytree(fixture, project)
    report, model = resolve_project_input(str(project / "Contoso Retail.pbip"))
    item = (Path(report) / "definition/pages/Executive_overview/visuals/"
            "card-b8ef7dc2/visual.json")
    original = json.loads(item.read_text(encoding="utf8"))
    original["position"]["x"] = 314  # 6px overlap with its 296px-wide left peer.
    item.write_text(json.dumps(original, indent=2) + "\n", encoding="utf8")
    before = source_digest(report)

    response = run_workflow(report_dir=report, model_dir=model, mode="repair",
                            scope="static", authoring_backend="direct",
                            run_root=str(tmp_path / "runs"),
                            run_id="seeded-overlap")
    summary = response["summary"]
    assert summary["outcome"] == "improved_not_accepted"
    assert "layout.no_visual_overlap" in summary["resolved_findings"]
    assert summary["new_regressions"] == []
    assert summary["candidate_status"]["status"] == "verified"
    assert summary["promotion_status"]["status"] == "not-performed"
    candidate = Path(summary["candidate_status"]["candidate"])
    repaired = json.loads((candidate / item.relative_to(report)).read_text(
        encoding="utf8"))
    assert repaired["position"]["x"] >= 320
    assert source_digest(report) == before
    assert candidate != Path(report)


def test_vqs_fix_cli_accepts_pbip_and_returns_small_result(tmp_path, capsys):
    from vqs.cli import main

    fixture = ROOT / "examples" / "contoso-retail-verified"
    exit_code = main(["fix", str(fixture / "Contoso Retail.pbip"),
                      "--run-root", str(tmp_path), "--run-id", "fix-cli",
                      "--authoring-backend", "direct"])
    output = capsys.readouterr().out
    j = json.loads(output)
    assert exit_code == 2
    assert j["verdict"] == "blocked"
    assert j["candidate"] is None
    assert j["needs_review"]
    assert "evidence" in j and "run_dir" in j
    assert len(output.encode("utf8")) < 6000


def test_mcp_run_resolves_pbip_path(monkeypatch):
    import vqs.coordinator
    from vqs.mcp.server import _dispatch

    received = []

    def fake_workflow(**kwargs):
        received.append(kwargs)
        return {"verdict": "blocked"}

    monkeypatch.setattr(vqs.coordinator, "run_workflow", fake_workflow)
    pbip = ROOT / "examples/contoso-retail-verified/Contoso Retail.pbip"
    _dispatch("vqs_run", {"report_dir": str(pbip), "run_root": "private"})
    assert received
    assert received[0]["report_dir"].endswith("Contoso Retail.Report")
    assert received[0]["model_dir"].endswith("definition")


def test_newer_legacy_handshake_and_structured_response(monkeypatch):
    import vqs.coordinator

    monkeypatch.setattr(vqs.coordinator, "run_workflow", lambda **kw: {
        "tool": "vqs.run", "verdict": "blocked", "summary": {"outcome": "blocked"},
        "evidence": ["x" * 10000]})
    session = {}
    init = handle_message({"jsonrpc": "2.0", "id": 1,
                           "method": "initialize",
                           "params": {"protocolVersion": "2025-11-25",
                                      "capabilities": {},
                                      "clientInfo": {"name": "next-client",
                                                     "version": "1"}}}, session)
    assert init["result"]["protocolVersion"] == "2025-11-25"
    handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    result = handle_message({"jsonrpc": "2.0", "id": 2,
                             "method": "tools/call",
                             "params": {"name": "vqs_run",
                                        "arguments": {"run_root": "private"}}},
                            session)["result"]
    assert result["structuredContent"]["verdict"] == "blocked"
    assert len(result["content"][0]["text"]) < 1200


def test_theme_mcp_apply_refuses_implicit_destination():
    from vqs.mcp.server import _dispatch

    pbip = ROOT / "examples/contoso-retail-verified/Contoso Retail.pbip"
    result = _dispatch("vqs_theme", {"action": "apply",
                                     "report_dir": str(pbip),
                                     "mode": "dark"})
    assert result["verdict"] == "blocked"
    assert "candidate_root" in str(result["blocked_reasons"])


def test_modern_inspect_preserves_facts_not_only_a_summary(monkeypatch):
    import vqs.pipeline
    from vqs.mcp.server import _dispatch

    expected = {"verdict": "pass", "facts": {"bindings": ["important"]}}
    monkeypatch.setattr(vqs.pipeline, "inspect_report",
                        lambda report, model, config: expected)
    report = str(ROOT / "examples/contoso-retail-verified/Contoso Retail.Report")
    assert _dispatch("vqs_inspect", {"report_dir": report}) == expected


def test_vqs_fix_default_run_root_is_user_private():
    import os

    from vqs.cli import _private_run_root

    root = _private_run_root()
    assert root.is_absolute()
    assert root.name == "runs"
    assert root != Path(".vqs-runs")
    if os.name == "nt":
        assert root.parent.name == "VQS"
    else:
        assert root.parent.name == "vqs"


def test_bundled_microsoft_license_notice_is_available():
    from importlib.resources import files

    license_text = (files("vqs").joinpath(
        "approved_skill/MICROSOFT_SKILLS_FOR_FABRIC_LICENSE.txt"
    ).read_text(encoding="utf-8"))
    assert "MIT License" in license_text
    assert "Copyright (c) 2026 Microsoft Corporation" in license_text
    assert "Permission is hereby granted" in license_text
