"""P0-U4: runtime candidate verification + owner-controlled promotion.

Real sealed repair runs (honest pipeline seals, no hand-built runs)
drive production verify_runtime()/promote_candidate(). The only faked
layer is the Bridge transport/port (recording every path it touches);
PNG bytes are genuinely encoded and decoded. The original is never
promoted without explicit approval, exact digests, backup, and seals.
"""
import json
import os
import struct
import zlib
from pathlib import Path

import pytest

from vqs import capture as capture_module
from vqs.pipeline import promote_candidate, repair_candidate, verify_runtime
from vqs.repair.execute import tree_digest
from vqs.repair.promote import PromoteError, rollback_promotion
from vqs.run_store import verify_seal

SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                 "report/definition/report/3.3.0/schema.json")
SCHEMA_INDEX = ("https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definition/pagesMetadata/1.1.0/schema.json")
VISUAL_REL = "definition/pages/P1/visuals/v1/visual.json"
LEAF = ["visual", "objects", "categoryAxis", 0, "properties",
        "labelPrecision", "expr", "Literal", "Value"]
PID = 4242


def _visual(value: str) -> dict:
    return {
        "name": "v1",
        "position": {"x": 0, "y": 0, "width": 100, "height": 100,
                     "z": 1},
        "visual": {
            "visualType": "barChart",
            "objects": {"categoryAxis": [{"properties": {
                "labelPrecision": {"expr": {"Literal": {
                    "Value": value}}}}}]}}}


def _project(root: Path, name: str, value: str = "3") -> tuple[Path, Path]:
    proj = root / name
    report = proj / "original.Report"
    visual_dir = report / "definition" / "pages" / "P1" / "visuals" / "v1"
    visual_dir.mkdir(parents=True)
    definition = report / "definition"
    (definition / "pages" / "pages.json").write_text(
        json.dumps({"$schema": SCHEMA_INDEX, "pageOrder": ["P1"]}),
        encoding="utf-8")
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": ["P1"]}), encoding="utf-8")
    (definition / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}),
        encoding="utf-8")
    (definition / "report.json").write_text(json.dumps({
        "$schema": SCHEMA_REPORT, "layoutOptimization": "None",
        "themeCollection": {}}), encoding="utf-8")
    (report / "definition.pbir").write_text(json.dumps(
        {"datasetReference": {"byPath":
                              {"path": "../Model.SemanticModel"}}}),
        encoding="utf-8")
    (definition / "pages" / "P1" / "page.json").write_text(
        json.dumps({"displayName": "P1", "width": 1280, "height": 720}),
        encoding="utf-8")
    (visual_dir / "visual.json").write_text(
        json.dumps(_visual("2")), encoding="utf-8")
    tables = proj / "Model.SemanticModel" / "tables"
    tables.mkdir(parents=True)
    (tables / "T.tmdl").write_text("table T\n", encoding="utf-8")
    plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "P1", "visual": "v1"},
        "target": "visual", "path": list(LEAF), "value": value,
        "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}
    (proj / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return proj, report


def _sealed_repair(root: Path, name: str, run_id: str,
                   value: str = "3") -> tuple[dict, Path, Path]:
    proj, report = _project(root, name, value)
    cand = proj / f"cand-{run_id}"
    envelope = repair_candidate(str(proj / "plan.json"), str(report),
                                str(cand), run_root=str(root / "runs"),
                                run_id=run_id)
    assert envelope["verdict"] == "pass", envelope
    return envelope, report, cand


def _png(width: int, height: int) -> bytes:
    """Genuine 8-bit RGB PNG, left/right halves (never blank)."""
    left = width // 2
    row = b"\x00" + b"\x10\x20\x30" * left + b"\x40\x50\x60" * (width - left)
    body = zlib.compress(row * height)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", body) + chunk(b"IEND", b""))


class _FakePort:
    """Recording Bridge port; serves scripted instances, optional reload refusal."""

    def __init__(self, candidate: Path, current_file: Path | None = None,
                 fail_reload: bool = False, fail_status: bool = False) -> None:
        self.candidate = os.path.realpath(candidate)
        if current_file is None:
            self.current_file = self.candidate
        else:
            self.current_file = os.path.realpath(current_file)
        self.fail_reload = fail_reload
        self.fail_status = fail_status
        self.status_calls = 0
        self.reloaded: list[int] = []

    def status(self) -> dict:
        self.status_calls += 1
        if self.fail_status:
            raise OSError("Bridge down")
        return {"instances": [{
            "pid": PID, "currentFilePath": str(self.current_file),
            "reportDir": str(self.candidate), "hasUnsavedChanges": False,
            "desktopVersion": "2.0-test"}]}

    def reload(self, pid: int) -> None:
        self.reloaded.append(pid)
        if self.fail_reload:
            raise OSError("Bridge reload rejected for PID 4242: nope")


def _fake_capture(monkeypatch: pytest.MonkeyPatch, candidate: Path,
                  png: bytes | None = None,
                  viewport: str | None = "2560x1440@2x") -> None:
    """Bridge transport double for capture.capture (version/status/shots)."""
    shot = png if png is not None else _png(2560, 1440)
    held = os.path.realpath(candidate)

    def _fake(args: list[str], timeout: int) -> tuple[int, str]:
        if args == ["--version"]:
            return 0, "powerbi-desktop 1.0.0"
        if args == ["status"]:
            return 0, json.dumps({"instances": [{
                "pid": PID, "currentFilePath": held,
                "reportDir": held, "hasUnsavedChanges": False,
                "desktopVersion": "2.0-test"}]})
        assert args[0] == "screenshot-all"
        outdir = Path(args[args.index("--output-dir") + 1])
        target = outdir / "shot-P1.png"
        target.write_bytes(shot)
        entry: dict = {"pageId": "P1", "outputPath": str(target)}
        if viewport is not None:
            entry["viewport"] = viewport
        return 0, json.dumps({"screenshots": [entry]})

    monkeypatch.setattr(capture_module, "_bridge", _fake)


def _passing_runtime(monkeypatch: pytest.MonkeyPatch, root: Path,
                     run_id: str = "rep1",
                     runtime_id: str = "rt1") -> tuple[dict, Path, Path, dict]:
    envelope, report, cand = _sealed_repair(root, "proj", run_id)
    _fake_capture(monkeypatch, cand)
    port = _FakePort(cand)
    result = verify_runtime(run_root=str(root / "runs"), run_id=run_id,
                            pid=PID, bridge=port,
                            runtime_run_id=runtime_id)
    assert result["verdict"] == "pass", result
    assert port.reloaded == [PID]
    return envelope, report, cand, result


def test_repair_fixture_seals_completed(tmp_path: Path) -> None:
    """Control: the fixture seals a completed repair run to bind against."""
    envelope, _report, _cand = _sealed_repair(tmp_path, "proj", "rep1")
    assert envelope["verdict"] == "pass"
    assert verify_seal(tmp_path / "runs" / "rep1") == []


def test_runtime_without_capability_blocks_precisely(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No Bridge binary and no injected port: exact missing piece, no run."""
    import shutil as _shutil

    _sealed_repair(tmp_path, "proj", "rep1")
    monkeypatch.setattr(_shutil, "which", lambda _name: None)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID)
    assert result["verdict"] == "blocked"
    assert "no live Desktop capability" in result["blocked_reasons"][0]
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == ["rep1"]


def test_runtime_pass_seals_and_never_touches_original(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: reload + capture the candidate, seal runtime evidence."""
    _envelope, report, cand, result = _passing_runtime(
        monkeypatch, tmp_path)
    assert result["evidence"][0]["kind"] == "sealed_runtime"
    run_dir = tmp_path / "runs" / "rt1"
    assert verify_seal(run_dir) == []
    runtime_doc = json.loads((run_dir / "runtime.json").read_text(
        encoding="utf-8"))
    assert runtime_doc["candidate_digest"] == tree_digest(str(cand))
    assert runtime_doc["pid"] == PID
    assert "renders" in runtime_doc["capture"]
    assert (run_dir / "capture-manifest.json").is_file()
    assert "promote with vqs.promote" in result["next_actions"][0]


def test_runtime_refuses_instance_holding_original(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Desktop holds the original: binding fails, original never driven."""
    _envelope, report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    port = _FakePort(report)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtrefuse")
    assert result["verdict"] == "blocked"
    assert "candidate binding failed" in result["blocked_reasons"][0]
    assert port.reloaded == []
    assert verify_seal(tmp_path / "runs" / "rtrefuse") == []


def test_runtime_refuses_original_masquerading_as_candidate(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """reportDir matches but the open file is the original: explicit refusal."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    port = _FakePort(cand, current_file=_report)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtmasq")
    assert result["verdict"] == "blocked"
    assert "holds the original" in result["blocked_reasons"][0]
    assert port.reloaded == []


def test_runtime_reload_refusal_blocks_and_seals(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Bridge that rejects reload blocks; the sealed run says blocked."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    port = _FakePort(cand, fail_reload=True)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtreload")
    assert result["verdict"] == "blocked"
    assert "reload refused" in result["blocked_reasons"][0]
    manifest = json.loads((tmp_path / "runs" / "rtreload" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["status"] == "blocked"
    assert verify_seal(tmp_path / "runs" / "rtreload") == []


def test_runtime_capture_failure_blocks_without_fail(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unverifiable capture (wrong-size PNG) blocks, never fails."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand, png=_png(500, 500), viewport=None)
    port = _FakePort(cand)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtcap")
    assert result["verdict"] == "blocked"
    assert "no verified candidate capture" in result["blocked_reasons"][0]


def test_runtime_candidate_drift_fails(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Post-seal candidate edits fail runtime; promotion must refuse these."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    (cand / VISUAL_REL).write_text(
        (cand / VISUAL_REL).read_text(encoding="utf-8") + " ",
        encoding="utf-8")
    port = _FakePort(cand)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtdrift")
    assert result["verdict"] == "fail"
    assert result["findings"][0]["check"] == "runtime:runtime_candidate_drift"
    assert verify_seal(tmp_path / "runs" / "rtdrift") == []


def test_runtime_and_promote_need_completed_repair(
        tmp_path: Path) -> None:
    """A blocked (never applied) repair verifies and promotes nowhere."""
    proj, _report = _project(tmp_path, "proj")
    (proj / "plan.json").write_text("not a plan", encoding="utf-8")
    envelope = repair_candidate(str(proj / "plan.json"), str(_report),
                                str(proj / "cand-bad"),
                                run_root=str(tmp_path / "runs"),
                                run_id="rep-bad")
    assert envelope["verdict"] == "blocked"
    assert verify_runtime(run_root=str(tmp_path / "runs"),
                          run_id="rep-bad", pid=PID,
                          bridge=_FakePort(_report))["verdict"] == "blocked"
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep-bad",
                                owner_approval="owner: test")
    assert refused["verdict"] == "blocked"
    assert "not a completed repair run" in refused["blocked_reasons"][0]


def test_promote_needs_explicit_approval(tmp_path: Path) -> None:
    """Empty or blank approval never promotes silently."""
    _sealed_repair(tmp_path, "proj", "rep1")
    for approval in ("", "   "):
        refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                    run_id="rep1", owner_approval=approval)
        assert refused["verdict"] == "blocked"
        assert "owner approval required" in refused["blocked_reasons"][0]
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["rep1"]


def test_promote_refuses_original_drift(tmp_path: Path) -> None:
    """A save landing after repair refuses; nothing is created or moved."""
    _envelope, report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    before = tree_digest(str(report))
    (report / VISUAL_REL).write_text(
        (report / VISUAL_REL).read_text(encoding="utf-8") + " ",
        encoding="utf-8")
    assert tree_digest(str(report)) != before
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep1",
                                owner_approval="owner: drift case")
    assert refused["verdict"] == "blocked"
    assert "original drifted" in refused["blocked_reasons"][0]
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["rep1"]
    assert tree_digest(str(cand)) != tree_digest(str(report))


def test_promote_refuses_candidate_drift(tmp_path: Path) -> None:
    """A touched candidate refuses even with approval in hand."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    (cand / VISUAL_REL).write_text(
        (cand / VISUAL_REL).read_text(encoding="utf-8") + " ",
        encoding="utf-8")
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep1",
                                owner_approval="owner: drift case")
    assert refused["verdict"] == "blocked"
    assert "candidate drifted" in refused["blocked_reasons"][0]


def test_promote_happy_path_static_only(tmp_path: Path) -> None:
    """Approval + digests + fresh verify: swap, backup, separate seal."""
    _envelope, report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    precondition = tree_digest(str(report))
    candidate_digest = tree_digest(str(cand))
    result = promote_candidate(run_root=str(tmp_path / "runs"), run_id="rep1",
                               owner_approval="owner: accept static repair",
                               desktop_recheck=False,
                               promote_run_id="prom1")
    assert result["verdict"] == "pass", result
    assert result["evidence"][0]["kind"] == "sealed_promotion"
    assert verify_seal(tmp_path / "runs" / "prom1") == []
    backup = tmp_path / "proj" / "original.Report.vqs-backup"
    assert tree_digest(str(backup)) == precondition
    assert tree_digest(str(report)) == candidate_digest
    assert tree_digest(str(cand)) == candidate_digest
    promotion_doc = json.loads(
        (tmp_path / "runs" / "prom1" / "promotion.json").read_text(
            encoding="utf-8"))
    assert promotion_doc["owner_approval"] == "owner: accept static repair"
    assert promotion_doc["runtime"] == {
        "status": "not-performed",
        "reason": "no runtime verification bound; static verification only"}
    assert promotion_doc["desktop_recheck"] == {
        "status": "skipped", "reason": "owner opted out"}
    assert promotion_doc["backup"] == str(backup)
    assert promotion_doc["rollback"]["precondition_digest"] == precondition
    assert promotion_doc["final_source_sha256"]
    assert (tmp_path / "runs" / "rep1" / "repairs.json").is_file()


def test_promote_binds_passing_runtime(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A sealed passing runtime run binds; the record names it."""
    _envelope, _report, _cand = _passing_runtime(monkeypatch, tmp_path)
    result = promote_candidate(run_root=str(tmp_path / "runs"), run_id="rep1",
                               owner_approval="owner: accept with runtime",
                               runtime_run_id="rt1", desktop_recheck=False,
                               promote_run_id="prom2")
    assert result["verdict"] == "pass", result
    promotion_doc = json.loads(
        (tmp_path / "runs" / "prom2" / "promotion.json").read_text(
            encoding="utf-8"))
    assert promotion_doc["runtime"]["status"] == "pass"
    assert promotion_doc["runtime"]["run_id"] == "rt1"


def test_promote_refuses_failed_runtime(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unresolved live regressions refuse even with owner approval."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    (cand / VISUAL_REL).write_text(
        (cand / VISUAL_REL).read_text(encoding="utf-8") + " ",
        encoding="utf-8")
    drifted = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                             pid=PID, bridge=_FakePort(cand),
                             runtime_run_id="rtfail")
    assert drifted["verdict"] == "fail"
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep1",
                                owner_approval="owner: override attempt",
                                runtime_run_id="rtfail")
    assert refused["verdict"] == "blocked"
    assert "unresolved" in refused["blocked_reasons"][0]


def test_promote_refuses_runtime_for_other_candidate(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A runtime record never transfers across different candidates."""
    proj, _report = _project(tmp_path, "proj")
    cand_a = proj / "cand-a"
    first = repair_candidate(str(proj / "plan.json"), str(_report),
                             str(cand_a), run_root=str(tmp_path / "runs"),
                             run_id="rep-a")
    assert first["verdict"] == "pass"
    (proj / "plan.json").write_text(json.dumps({
        "operations": [{
            "type": "axis.tick_format",
            "selector": {"page": "P1", "visual": "v1"},
            "target": "visual", "path": list(LEAF), "value": "4",
            "writes": [VISUAL_REL]}],
        "rollback": "re-materialize from original",
        "write_targets": [VISUAL_REL]}), encoding="utf-8")
    cand_b = proj / "cand-b"
    second = repair_candidate(str(proj / "plan.json"), str(_report),
                              str(cand_b), run_root=str(tmp_path / "runs"),
                              run_id="rep-b")
    assert second["verdict"] == "pass"
    assert tree_digest(str(cand_a)) != tree_digest(str(cand_b))
    _fake_capture(monkeypatch, cand_a)
    sealed = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep-a",
                            pid=PID, bridge=_FakePort(cand_a),
                            runtime_run_id="rt-other")
    assert sealed["verdict"] == "pass"
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep-b",
                                owner_approval="owner: cross-bind attempt",
                                runtime_run_id="rt-other")
    assert refused["verdict"] == "blocked"
    assert "different candidate" in refused["blocked_reasons"][0]


def test_promote_refuses_existing_backup(tmp_path: Path) -> None:
    """A pre-existing backup path is never overwritten silently."""
    _sealed_repair(tmp_path, "proj", "rep1")
    (tmp_path / "proj" / "original.Report.vqs-backup").mkdir()
    refused = promote_candidate(run_root=str(tmp_path / "runs"),
                                run_id="rep1",
                                owner_approval="owner: backup clash")
    assert refused["verdict"] == "blocked"
    assert "backup path exists" in refused["blocked_reasons"][0]


class _RecheckPort:
    """Bridge double holding the promoted original; optional reload failure."""

    def __init__(self, original: Path, fail_reload: bool = False) -> None:
        self.original = os.path.realpath(original)
        self.fail_reload = fail_reload

    def status(self) -> dict:
        return {"instances": [{
            "pid": PID, "currentFilePath": str(self.original),
            "reportDir": str(self.original), "hasUnsavedChanges": False,
            "desktopVersion": "2.0-test"}]}

    def reload(self, pid: int) -> None:
        if self.fail_reload:
            raise OSError("Bridge reload rejected for PID 4242: gone")


def test_promote_desktop_recheck_pass_records_pid(tmp_path: Path) -> None:
    """A live Desktop holding the promoted report reloads and rebinds."""
    _envelope, report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    candidate_digest = tree_digest(str(cand))
    result = promote_candidate(run_root=str(tmp_path / "runs"), run_id="rep1",
                               owner_approval="owner: live recheck",
                               bridge=_RecheckPort(report),
                               promote_run_id="promlive")
    assert result["verdict"] == "pass", result
    assert tree_digest(str(report)) == candidate_digest
    promotion_doc = json.loads(
        (tmp_path / "runs" / "promlive" / "promotion.json").read_text(
            encoding="utf-8"))
    assert promotion_doc["desktop_recheck"] == {"status": "pass",
                                                "pid": PID}


def test_promote_recheck_failure_fails_with_rollback(
        tmp_path: Path) -> None:
    """Failed recheck seals failed; rollback restores the precondition."""
    _envelope, report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    precondition = tree_digest(str(report))
    candidate_digest = tree_digest(str(cand))
    result = promote_candidate(run_root=str(tmp_path / "runs"), run_id="rep1",
                               owner_approval="owner: recheck fails",
                               bridge=_RecheckPort(report, fail_reload=True),
                               promote_run_id="promfail")
    assert result["verdict"] == "fail", result
    assert tree_digest(str(report)) == candidate_digest
    manifest = json.loads((tmp_path / "runs" / "promfail" / "manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert verify_seal(tmp_path / "runs" / "promfail") == []
    promotion_doc = json.loads(
        (tmp_path / "runs" / "promfail" / "promotion.json").read_text(
            encoding="utf-8"))
    assert promotion_doc["desktop_recheck"]["status"] == "failed"
    backup = promotion_doc["backup"]
    rolled = rollback_promotion(
        original=str(report), backup_dir=backup,
        precondition_digest=precondition)
    assert rolled["digest"] == precondition
    assert tree_digest(str(report)) == precondition
    assert tree_digest(Path(rolled["retired"])) == candidate_digest


def test_rollback_refuses_tampered_backup(tmp_path: Path) -> None:
    """Rolling back to unknown bytes refuses instead of restoring them."""
    _sealed_repair(tmp_path, "proj", "rep1")
    result = promote_candidate(run_root=str(tmp_path / "runs"), run_id="rep1",
                               owner_approval="owner: rollback case",
                               desktop_recheck=False,
                               promote_run_id="promrb")
    assert result["verdict"] == "pass"
    promotion_doc = json.loads(
        (tmp_path / "runs" / "promrb" / "promotion.json").read_text(
            encoding="utf-8"))
    backup = Path(promotion_doc["backup"])
    (backup / VISUAL_REL).write_text(
        (backup / VISUAL_REL).read_text(encoding="utf-8") + " ",
        encoding="utf-8")
    with pytest.raises(PromoteError, match="differs from the sealed"):
        rollback_promotion(original=str(tmp_path / "proj" / "original.Report"),
                           backup_dir=str(backup),
                           precondition_digest=promotion_doc["rollback"][
                               "precondition_digest"])


def _mcp_session(lines: list[str]) -> list[dict]:
    import io as _io

    from vqs.mcp.server import PROTOCOL_VERSION, serve

    opened = [
        json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                    "params": {"protocolVersion": PROTOCOL_VERSION,
                               "capabilities": {},
                               "clientInfo": {"name": "u4", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0",
                    "method": "notifications/initialized"})]
    reader = _io.StringIO("".join(line + "\n" for line in opened + lines))
    writer = _io.StringIO()
    assert serve(reader, writer) == 0
    return [json.loads(line) for line in writer.getvalue().splitlines()
            if line.strip()]


def test_mcp_promote_and_runtime_tools(tmp_path: Path) -> None:
    """MCP tools run the same engine; unknown runs block, never crash."""
    from vqs.mcp.schemas import validate_call

    spec, error = validate_call(
        "vqs_promote", {"run_root": "r", "run_id": "x",
                        "owner_approval": "owner: mcp"})
    assert error is None and spec["tool"] == "vqs.promote"
    assert validate_call("vqs_promote", {"run_root": "r"})[1] is not None
    spec_rt, error_rt = validate_call(
        "vqs_verify_runtime", {"run_root": "r", "run_id": "x"})
    assert error_rt is None and spec_rt["tool"] == "vqs.verify-runtime"
    assert validate_call(
        "vqs_verify_runtime",
        {"run_root": "r", "run_id": "x", "bogus": 1})[1] is not None
    responses = _mcp_session([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "vqs_promote",
                               "arguments": {
                                   "run_root": str(tmp_path),
                                   "run_id": "nope",
                                   "owner_approval": "owner: mcp"}}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "vqs_verify_runtime",
                               "arguments": {
                                   "run_root": str(tmp_path),
                                   "run_id": "nope"}}})])
    for response in responses[1:]:
        assert "error" not in response
    first = json.loads(responses[1]["result"]["content"][0]["text"])
    assert first["verdict"] == "blocked" and first["tool"] == "vqs.promote"
    second = json.loads(responses[2]["result"]["content"][0]["text"])
    assert second["verdict"] == "blocked"
    assert second["tool"] == "vqs.verify-runtime"


def test_runtime_status_failure_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead Bridge during binding blocks with the exact failure."""
    _envelope, _report, cand = _sealed_repair(tmp_path, "proj", "rep1")
    _fake_capture(monkeypatch, cand)
    port = _FakePort(cand, fail_status=True)
    result = verify_runtime(run_root=str(tmp_path / "runs"), run_id="rep1",
                            pid=PID, bridge=port,
                            runtime_run_id="rtdead")
    assert result["verdict"] == "blocked"
    assert "candidate binding failed" in result["blocked_reasons"][0]
    assert port.reloaded == []


def test_argument_validation_tables(tmp_path: Path) -> None:
    """Malformed engine inputs block before touching seals or trees."""
    _sealed_repair(tmp_path, "proj", "rep1")
    runs = str(tmp_path / "runs")
    bad_runtime = [
        {"run_root": "", "run_id": "rep1"},
        {"run_root": runs, "run_id": "", "pid": PID},
        {"run_root": runs, "run_id": "rep1", "pid": True},
        {"run_root": runs, "run_id": "rep1", "pid": PID, "scale": 3},
        {"run_root": runs, "run_id": "rep1", "pid": PID,
         "wait_seconds": 0},
        {"run_root": runs, "run_id": "rep1", "pid": PID,
         "reload_first": "yes"},
        {"run_root": runs, "run_id": "rep1", "pid": PID,
         "runtime_run_id": "rep1"},
        {"run_root": runs, "run_id": "nope", "pid": PID,
         "bridge": _FakePort(tmp_path)}]
    for kwargs in bad_runtime:
        assert verify_runtime(**kwargs)["verdict"] == "blocked", kwargs
    bad_promote = [
        {"run_root": "", "run_id": "rep1", "owner_approval": "o: r"},
        {"run_root": runs, "run_id": "rep1", "owner_approval": ""},
        {"run_root": runs, "run_id": "rep1", "owner_approval": "o: r",
         "runtime_run_id": ""},
        {"run_root": runs, "run_id": "rep1", "owner_approval": "o: r",
         "backup_dir": ""},
        {"run_root": runs, "run_id": "rep1", "owner_approval": "o: r",
         "desktop_recheck": "yes"},
        {"run_root": runs, "run_id": "nope", "owner_approval": "o: r"}]
    for kwargs in bad_promote:
        assert promote_candidate(**kwargs)["verdict"] == "blocked", kwargs


def test_cli_promote_and_runtime_exit_codes(tmp_path: Path) -> None:
    """CLI surfaces the engine verdicts as 0/1/2 without new logic."""
    from vqs.cli import main as vqs_main

    assert vqs_main(["promote", "--run-root", str(tmp_path),
                     "--run-id", "nope",
                     "--owner-approval", "owner: cli"]) == 2
    assert vqs_main(["verify-runtime", "--run-root", str(tmp_path),
                     "--run-id", "nope", "--pid", "4242"]) == 2
    _sealed_repair(tmp_path, "proj", "rep1")
    assert vqs_main(["promote", "--run-root", str(tmp_path / "runs"),
                     "--run-id", "rep1",
                     "--owner-approval", "owner: cli happy",
                     "--no-desktop-recheck",
                     "--promote-run-id", "promcli"]) == 0
    assert verify_seal(tmp_path / "runs" / "promcli") == []
