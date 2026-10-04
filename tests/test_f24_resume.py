"""F24: resume/status must validate run IDs, confinement, and full sealed records."""

from __future__ import annotations

import json
from pathlib import Path

from vqs.pipeline import review_report, run_status_report


def _sealed_run(root: Path, run_id: str = "r1") -> str:
    run_root = str(root / "runs")
    envelope = review_report(facts={"rules": {}}, run_root=run_root, run_id=run_id)
    assert envelope["run_dir"] is not None
    return run_root


def _blocked(envelope: dict) -> bool:
    # Resume/status blocks never seal a new run, so run_dir stays None.
    return envelope["verdict"] == "blocked"


def test_f24_run_id_traversal_and_absolute_blocked(tmp_path: Path) -> None:
    run_root = _sealed_run(tmp_path)
    for bad_id in ("../..", "../../evil", str(tmp_path / "runs" / "r1")):
        resumed = review_report(facts={"rules": {}}, run_root=run_root,
                                run_id="x", resume_from=bad_id)
        assert resumed["verdict"] == "blocked", bad_id
        status = run_status_report(run_root=run_root, run_id=bad_id)
        assert status["verdict"] == "blocked", bad_id
        assert "run_id" in " ".join(status["blocked_reasons"]) or "run_dir" in " ".join(status["blocked_reasons"])


def test_f24_malformed_prior_manifest_blocked(tmp_path: Path) -> None:
    run_root = _sealed_run(tmp_path)
    (tmp_path / "runs" / "r1" / "manifest.json").write_text("{not-json", encoding="utf-8")
    resumed = review_report(facts={"rules": {}}, run_root=run_root, run_id="x", resume_from="r1")
    assert resumed["verdict"] == "blocked"
    status = run_status_report(run_root=run_root, run_id="r1")
    assert status["verdict"] == "blocked"


def test_f24_forged_prior_artifact_blocked(tmp_path: Path) -> None:
    run_root = _sealed_run(tmp_path)
    manifest_path = tmp_path / "runs" / "r1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["facts_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    resumed = review_report(facts={"rules": {}}, run_root=run_root, run_id="x", resume_from="r1")
    assert _blocked(resumed)
    assert any("seal" in reason for reason in resumed["blocked_reasons"])
    status = run_status_report(run_root=run_root, run_id="r1")
    assert status["verdict"] == "blocked"
    assert any("seal" in reason for reason in status["blocked_reasons"])


def test_f24_post_seal_event_mutation_blocked(tmp_path: Path) -> None:
    run_root = _sealed_run(tmp_path)
    events_path = tmp_path / "runs" / "r1" / "events.jsonl"
    with open(events_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "completed"}) + "\n")
    resumed = review_report(facts={"rules": {}}, run_root=run_root, run_id="x", resume_from="r1")
    assert _blocked(resumed)
    assert any("seal" in reason for reason in resumed["blocked_reasons"])
    status = run_status_report(run_root=run_root, run_id="r1")
    assert status["verdict"] == "blocked"


def test_f24_post_seal_metadata_mutation_blocked(tmp_path: Path) -> None:
    run_root = _sealed_run(tmp_path)
    manifest_path = tmp_path / "runs" / "r1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pipeline"] = "evil/9"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    resumed = review_report(facts={"rules": {}}, run_root=run_root, run_id="x", resume_from="r1")
    assert _blocked(resumed)
    status = run_status_report(run_root=run_root, run_id="r1")
    assert status["verdict"] == "blocked"


def test_f24_cli_resume_and_status_block(capsys, tmp_path: Path) -> None:
    from vqs.cli import main as vqs_main

    run_root = _sealed_run(tmp_path)
    manifest_path = tmp_path / "runs" / "r1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pipeline"] = "evil/9"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps({"rules": {}}), encoding="utf-8")
    rc = vqs_main(["review", "--facts", str(facts_path), "--run-root", run_root,
                   "--run-id", "cli2", "--resume-from", "r1"])
    assert rc == 2
    assert vqs_main(["run-status", run_root, "r1"]) == 2
    assert vqs_main(["review", "--facts", str(facts_path), "--run-root", run_root,
                     "--run-id", "cli3", "--resume-from", "../.."]) == 2
    assert vqs_main(["run-status", run_root, "../.."]) == 2
    capsys.readouterr()


def test_f24_mcp_resume_and_status_block(tmp_path: Path) -> None:
    from vqs.mcp.server import handle_message

    run_root = _sealed_run(tmp_path)
    manifest_path = tmp_path / "runs" / "r1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pipeline"] = "evil/9"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    from vqs.mcp.server import PROTOCOL_VERSION as _PROTOCOL_VERSION

    _session_state: dict = {}
    handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": _PROTOCOL_VERSION,
                               "capabilities": {},
                               "clientInfo": {"name": "f24",
                                              "version": "0"}}},
                   _session_state)
    handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"},
                   _session_state)

    def call(name: str, arguments: dict, msg_id: int = 1) -> dict:
        return handle_message({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments}},
                   _session_state)

    def envelope_of(response: dict) -> dict:
        assert "error" not in response
        return json.loads(response["result"]["content"][0]["text"])

    resume = envelope_of(call("vqs_review", {"facts": {"rules": {}}, "run_root": run_root,
                                             "run_id": "mcp2", "resume_from": "r1"}, 11))
    assert _blocked(resume)
    status = envelope_of(call("vqs_run_status", {"run_root": run_root, "run_id": "r1"}, 12))
    assert status["verdict"] == "blocked"
    traversal = envelope_of(call("vqs_review", {"facts": {"rules": {}}, "run_root": run_root,
                                                "run_id": "mcp3", "resume_from": "../.."}, 13))
    assert traversal["verdict"] == "blocked"
