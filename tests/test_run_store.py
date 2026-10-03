"""WP-02 runner tests: crash replay, lock contention, and read-only status.

Acceptance mapping (issue #7, offline subset): interrupted-run replay
preserves events with a blocked (never green) open end; concurrent artifact
claims are refused; `vqs status` reports the ledger without modifying it.
No Desktop, cloud, or Actions are exercised.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.roadmap_report import DEFAULT_LEDGER, summarize
from vqs import run_store
from vqs.cli import main as vqs_main


def test_interrupted_run_replays_all_events_and_stays_blocked(tmp_path: Path) -> None:
    run_dir = run_store.create_run(tmp_path, "run-1", {"artifact": "report-a"})
    run_store.append_event(run_dir, {"kind": "started", "seq": 1})
    run_store.append_event(run_dir, {"kind": "inspect", "seq": 2})
    # Simulated kill: the store object is dropped; a fresh handle replays.
    replayed = run_store.read_events(run_dir)
    assert [event["seq"] for event in replayed] == [1, 2]
    assert run_store.run_status(run_dir) == "blocked"
    run_store.append_event(run_dir, {"kind": "completed", "seq": 3})
    assert run_store.run_status(run_dir) == "completed"
    assert len(run_store.read_events(run_dir)) == 3


def test_concurrent_artifact_claim_refused_and_released(tmp_path: Path) -> None:
    locks = tmp_path / "locks"
    assert run_store.claim_artifact(locks, "PowerBI-pid-1", "agent-a") is True
    assert run_store.claim_artifact(locks, "PowerBI-pid-1", "agent-b") is False
    assert run_store.release_artifact(locks, "PowerBI-pid-1", "agent-b") is False
    assert run_store.release_artifact(locks, "PowerBI-pid-1", "agent-a") is True
    assert run_store.claim_artifact(locks, "PowerBI-pid-1", "agent-b") is True


def test_seal_pins_status_artifacts_and_count(tmp_path: Path) -> None:
    run_dir = run_store.create_run(tmp_path, "run-9", {"spike": "WP-04"})
    run_store.append_event(run_dir, {"kind": "started"})
    run_store.append_event(run_dir, {"kind": "completed", "verdict": "pass"})
    sealed = run_store.seal_run(run_dir, "completed",
                                artifacts={"report.pdf": "p" * 64},
                                environment={"backend": "interactive-word 16.0"})
    assert sealed["status"] == "completed"
    assert sealed["artifacts"] == {"report.pdf": "p" * 64}
    assert sealed["environment"] == {"backend": "interactive-word 16.0"}
    assert sealed["event_count"] == 2
    reread = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert reread == sealed


def test_run_id_traversal_rejected_windows_and_posix(tmp_path: Path) -> None:
    """Supervisor #22 P0-1: run ids can never escape the private root."""
    for bad in ("../escaped", "..\\escaped", "sub/dir", "sub\\dir", "..", ".",
                "/abs", "C:\\abs", "a:b", "", "ok\x00"):
        try:
            run_store.create_run(tmp_path, bad, {})
        except ValueError:
            continue
        raise AssertionError(f"run id accepted: {bad!r}")
    assert list(tmp_path.iterdir()) == []


def test_lock_id_traversal_rejected_windows_and_posix(tmp_path: Path) -> None:
    """Supervisor #22 P0-2: lock ids can never escape the lock directory."""
    locks = tmp_path / "locks"
    for bad in ("../outside", "..\\outside", "a/b", "a\\b", "..", "/abs"):
        try:
            claimed = run_store.claim_artifact(locks, bad, "agent-a")
        except ValueError:
            continue
        raise AssertionError(f"lock id accepted: {bad!r} -> {claimed}")


def test_invalid_terminal_seal_rejected(tmp_path: Path) -> None:
    """Supervisor #22 P0-3: only completed/failed/blocked seal a run."""
    run_dir = run_store.create_run(tmp_path, "run-x", {})
    run_store.append_event(run_dir, {"kind": "started"})
    try:
        run_store.seal_run(run_dir, "active")
    except ValueError:
        pass
    else:
        raise AssertionError("seal_run accepted a non-terminal status")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("sealed") is not True


def test_seal_after_post_terminal_event_rejected(tmp_path: Path) -> None:
    """Supervisor run-store repro 1: the FINAL event must be the terminal one."""
    run_dir = run_store.create_run(tmp_path, "r1", {})
    run_store.append_event(run_dir, {"kind": "started"})
    run_store.append_event(run_dir, {"kind": "completed"})
    run_store.append_event(run_dir, {"kind": "heartbeat"})
    try:
        run_store.seal_run(run_dir, "completed")
    except ValueError:
        pass
    else:
        raise AssertionError("seal accepted a run whose final event is not terminal")
    assert run_store.run_status(run_dir) == "blocked"


def test_append_after_seal_rejected(tmp_path: Path) -> None:
    """Supervisor run-store repro 2: sealed runs are immutable."""
    run_dir = run_store.create_run(tmp_path, "r2", {})
    run_store.append_event(run_dir, {"kind": "started"})
    run_store.append_event(run_dir, {"kind": "completed"})
    sealed = run_store.seal_run(run_dir, "completed")
    assert sealed["sealed"] is True
    try:
        run_store.append_event(run_dir, {"kind": "rogue-after-seal"})
    except ValueError:
        pass
    else:
        raise AssertionError("append_event mutated a sealed run")
    assert run_store.read_events(run_dir)[-1]["kind"] == "completed"


def test_append_after_terminal_event_rejected(tmp_path: Path) -> None:
    run_dir = run_store.create_run(tmp_path, "r3", {})
    run_store.append_event(run_dir, {"kind": "started"})
    run_store.append_event(run_dir, {"kind": "failed"})
    try:
        run_store.append_event(run_dir, {"kind": "heartbeat"})
    except ValueError:
        pass
    else:
        raise AssertionError("events followed terminality without a new attempt")


def test_seal_binds_event_log_digest_and_detects_tampering(tmp_path: Path) -> None:
    run_dir = run_store.create_run(tmp_path, "r4", {})
    run_store.append_event(run_dir, {"kind": "started"})
    run_store.append_event(run_dir, {"kind": "completed"})
    sealed = run_store.seal_run(run_dir, "completed")
    assert len(sealed["events_sha256"]) == 64
    assert run_store.verify_seal(run_dir) == []
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"kind": "forged"}\n')
    problems = run_store.verify_seal(run_dir)
    assert problems, "log tampering after sealing went undetected"


def test_unknown_run_append_raises(tmp_path: Path) -> None:
    try:
        run_store.append_event(tmp_path / "no-such-run", {"kind": "started"})
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError for unknown run")


def test_status_json_matches_ledger_and_touches_nothing(tmp_path: Path, capsys) -> None:
    ledger = Path(DEFAULT_LEDGER)
    before = ledger.read_bytes()
    code = vqs_main(["status", "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out)["next_runnable"] == summarize(
        json.loads(before.decode("utf-8-sig")))["next_runnable"]
    assert ledger.read_bytes() == before
    assert list(tmp_path.iterdir()) == []


def test_status_cli_has_no_source_checkout_imports() -> None:
    """Pin the WP-12 fix: the installed entry point must not need scripts/."""
    root = Path(__file__).resolve().parents[1]
    for module in ("vqs/cli.py", "vqs/ledger.py", "vqs/run_store.py"):
        text = (root / module).read_text(encoding="utf-8")
        assert "from scripts" not in text and "import scripts" not in text, module
    from vqs.ledger import summarize, validate  # noqa: F401


def test_status_rejects_tampered_ledger(tmp_path: Path, capsys) -> None:
    tampered = tmp_path / "work_packages.json"
    data = json.loads(Path(DEFAULT_LEDGER).read_text(encoding="utf-8-sig"))
    data["packages"][0]["state"] = "verified"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    assert vqs_main(["status", "--ledger", str(tampered)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
