"""P0-U6: structured reviewer adapter, never a manual form as primary UX.

The ReviewPort consumes verified source-bound bundles and returns typed
observations. Tests use explicit fakes with synthetic labels that see no
pixels; PNG bytes, hashes, packs, and seals are all genuine. Hosted CI
only (no live Desktop, no live reviewer).
"""
import hashlib
import json
import shutil
import struct
import sys
import types
import zlib
from pathlib import Path

import pytest

from vqs import coordinator as coordinator_module
from vqs.config import default_config
from vqs.coordinator import run_workflow
from vqs.pbir import report_context, source_digest
from vqs.review.bundle import pack
from vqs.review.port import (
    ReviewError,
    resolve_reviewer,
    review_bundle,
)

FIXTURES = Path(__file__).parent / "powerbi" / "fixtures"
FIXER = "fixer-u6"


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


def _renders(report: Path, outdir: Path) -> dict[str, tuple[int, int]]:
    """Genuine renders + manifest: real bytes, hashes, measured pixels."""
    outdir.mkdir(parents=True, exist_ok=True)
    info = report_context(report)
    mapping: dict[str, str] = {}
    files: dict[str, str] = {}
    pixels: dict[str, tuple[int, int]] = {}
    for page in info["pages"]:
        canvas = page.get("canvas") or [1280, 720]
        width, height = int(canvas[0]) * 2, int(canvas[1]) * 2
        png = _png(width, height)
        name = f"{page['id']}.png"
        (outdir / name).write_bytes(png)
        mapping[page["id"]] = name
        files[name] = hashlib.sha256(png).hexdigest()
        pixels[page["id"]] = (width, height)
    first = pixels[info["pages"][0]["id"]]
    canvas0 = info["pages"][0].get("canvas") or [1280, 720]
    (outdir / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report),
         "page_images": mapping, "files": files,
         "calibration": {
             "canvas_width": int(canvas0[0]),
             "canvas_height": int(canvas0[1]), "scale": 2,
             "png_pixels": f"{first[0]}x{first[1]}",
             "viewport": f"{first[0]}x{first[1]}@2x",
             "method": "u6-test-double"},
         "data_readiness": {"populated": True,
                             "method": "u6-test-double"}}),
        encoding="utf-8")
    return pixels


def _bundle(tmp_path: Path, name: str = "rep") -> tuple[Path, Path, Path]:
    report = tmp_path / f"{name}.Report"
    shutil.copytree(FIXTURES / "mini_report", report)
    renders = tmp_path / f"{name}-renders"
    _renders(report, renders)
    out = tmp_path / f"{name}-bundle"
    pack(str(report), str(renders), str(out), FIXER)
    return report, renders, out


class _SyntheticReviewer:
    """Explicit test fake: canned typed observations; sees no pixels."""

    def __init__(self, reviewer_id: str = "synth-reviewer",
                 observations: list | None = None,
                 error: Exception | None = None) -> None:
        self.reviewer_id = reviewer_id
        self.observations = observations if observations is not None else []
        self.error = error
        self.seen: list[str] = []

    def review(self, bundle_dir: str) -> dict:
        self.seen.append(bundle_dir)
        if self.error is not None:
            raise self.error
        return {"observations": [dict(item) for item in self.observations]}


def test_reviewer_pass_record_binds_verified_renders(
        tmp_path: Path) -> None:
    """Clean observations seal with the exact verified render hashes."""
    _report, _renders, out = _bundle(tmp_path)
    observations = [{"page_id": "P1", "check": "synthetic-layout",
                     "verdict": "pass"}]
    record = review_bundle(bundle_dir=str(out),
                           reviewer=_SyntheticReviewer(
                               observations=observations),
                           reviewer_id="synth-reviewer", fixer_id=FIXER)
    assert record["visual"] == "pass"
    assert record["tally"] == {"pass": 1, "fail": 0, "blocked": 0}
    assert record["reviewer"] == "synth-reviewer"
    assert record["observations"] == [
        {"page_id": "P1", "check": "synthetic-layout", "verdict": "pass",
         "detail": None}]
    for name, sha in record["renders"].items():
        assert (out / name).is_file()
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == sha
    assert record["source_sha256"] == source_digest(_report)


def test_reviewer_fixer_separation_refuses(tmp_path: Path) -> None:
    """The reviewer may never be the fixer, even with clean observations."""
    _report, _renders, out = _bundle(tmp_path)
    with pytest.raises(ReviewError, match="separation violated"):
        review_bundle(bundle_dir=str(out),
                      reviewer=_SyntheticReviewer(reviewer_id=FIXER),
                      reviewer_id=FIXER, fixer_id=FIXER)


@pytest.mark.parametrize("observations", [
    [{"page_id": "P1", "check": "x", "verdict": "maybe"}],
    [{"page_id": "P9", "check": "x", "verdict": "pass"}],
    [{"page_id": "P1", "check": "x", "verdict": "pass"},
     {"page_id": "P1", "check": "x", "verdict": "fail"}],
    [{"page_id": "P1", "check": "", "verdict": "pass"}],
    [{"page_id": "P1", "check": "x"}],
    "not-a-list",
])
def test_malformed_observations_refuse(tmp_path: Path,
                                       observations: object) -> None:
    """Untyped verdicts, unknown pages, dups, and shapes never coerce."""
    _report, _renders, out = _bundle(tmp_path)
    with pytest.raises(ReviewError):
        review_bundle(bundle_dir=str(out),
                      reviewer=_SyntheticReviewer(
                          observations=observations),  # type: ignore[arg-type]
                      reviewer_id="synth-reviewer", fixer_id=FIXER)


def test_unsealable_observations_refuse(tmp_path: Path) -> None:
    """Observations must survive JSON sealing; exotic values refuse."""
    _report, _renders, out = _bundle(tmp_path)
    with pytest.raises(ReviewError, match="sealable"):
        review_bundle(bundle_dir=str(out),
                      reviewer=_SyntheticReviewer(observations=[
                          {"page_id": "P1", "check": "x", "verdict": "pass",
                           "detail": object()}]),
                      reviewer_id="synth-reviewer", fixer_id=FIXER)


def test_reviewer_crash_and_tampered_bundle_refuse(tmp_path: Path) -> None:
    """Port crashes and post-pack tampering refuse with precise reasons."""
    _report, _renders, out = _bundle(tmp_path)
    with pytest.raises(ReviewError, match="reviewer failed"):
        review_bundle(bundle_dir=str(out),
                      reviewer=_SyntheticReviewer(
                          error=RuntimeError("down")),
                      reviewer_id="synth-reviewer", fixer_id=FIXER)
    (out / "P1.png").write_bytes(_png(1280, 720))
    with pytest.raises(ReviewError, match="bundle invalid"):
        review_bundle(bundle_dir=str(out),
                      reviewer=_SyntheticReviewer(),
                      reviewer_id="synth-reviewer", fixer_id=FIXER)


def test_resolve_reviewer_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """None stays unconfigured; objects duck-check; paths import."""
    assert resolve_reviewer(None) == (None, None)
    port = _SyntheticReviewer()
    assert resolve_reviewer(port) == (port, "synth-reviewer")
    with pytest.raises(ReviewError):
        resolve_reviewer(object())
    with pytest.raises(ReviewError):
        resolve_reviewer("no.such.module:Missing")
    with pytest.raises(ReviewError):
        resolve_reviewer(42)
    module = types.ModuleType("u6_fake_mod")
    instance = _SyntheticReviewer()
    module.Fake = instance  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "u6_fake_mod", module)
    found, identity = resolve_reviewer("u6_fake_mod:Fake")
    assert found is instance and identity == "synth-reviewer"


def _desktop_config() -> dict:
    config = default_config()
    config["data_permissions"]["allow_desktop"] = True
    return config


def _stub_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Bridge capture with genuine local bytes + manifest."""

    def _fake(name: str, report: str, renders: str, pid: int | None,
              record, adopted: dict, ctx: dict) -> dict:
        from vqs.coordinator import _stage

        _renders(Path(report), Path(renders))
        manifest = json.loads((Path(renders) / "capture-manifest.json")
                              .read_text(encoding="utf-8"))
        return record(_stage(name, "pass", evidence={
            "renders": renders,
            "source_sha256": manifest["source_sha256"],
            "pages": sorted(manifest["page_images"])}))

    monkeypatch.setattr(coordinator_module, "_capture_stage", _fake)


def _ready(monkeypatch: pytest.MonkeyPatch) -> None:
    from vqs.powerbi import desktop

    monkeypatch.setattr(desktop, "desktop_spike_readiness",
                        lambda: {"verdict": "ready", "missing": []})


def _run_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                reviewer: object, run_id: str,
                fixer_id: str = FIXER) -> dict:
    report = tmp_path / "Live.Report"
    shutil.copytree(FIXTURES / "mini_report", report)
    _ready(monkeypatch)
    _stub_capture(monkeypatch)
    return run_workflow(report_dir=str(report), mode="review",
                        scope="desktop", config=_desktop_config(),
                        run_root=str(tmp_path / "runs"), run_id=run_id,
                        pid=4242, fixer_id=fixer_id, reviewer=reviewer)


def _stages(envelope: dict) -> dict:
    return {entry["stage"]: entry for entry in envelope["stages"]}


def test_coordinator_handoff_calls_configured_reviewer(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime handoff packs, calls the port, and seals reviewer evidence."""
    reviewer = _SyntheticReviewer()
    envelope = _run_review(tmp_path, monkeypatch, reviewer, "u6-ok")
    stages = _stages(envelope)
    assert stages["readiness"]["status"] == "pass"
    assert stages["baseline_capture"]["status"] == "pass"
    assert stages["handoff"]["status"] == "pass"
    evidence = stages["handoff"]["evidence"]
    assert evidence["reviewer"] == "synth-reviewer"
    assert evidence["visual_acceptance"] == "pass"
    assert reviewer.seen == [evidence["bundle"]]
    run_dir = tmp_path / "runs" / "u6-ok"
    persisted = json.loads((run_dir / "reviewer.json").read_text(
        encoding="utf-8"))
    assert persisted["reviewer"] == "synth-reviewer"
    assert (hashlib.sha256((run_dir / "reviewer.json").read_bytes())
            .hexdigest() == evidence["reviewer_sha256"])
    assert envelope["summary"]["visual_acceptance"]["status"] == "pass"


def test_coordinator_handoff_without_reviewer_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing reviewer capability blocks visual acceptance precisely."""
    envelope = _run_review(tmp_path, monkeypatch, None, "u6-norev")
    stages = _stages(envelope)
    assert stages["handoff"]["status"] == "blocked"
    assert "no reviewer capability" in stages["handoff"]["reason"]
    assert envelope["verdict"] == "blocked"
    assert envelope["summary"]["outcome"] == "blocked"
    assert (envelope["summary"]["visual_acceptance"]["status"]
            == "blocked")


def test_coordinator_reviewer_fail_fails_acceptance_not_execution(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reviewer-found defects extend remaining findings; stages stay green."""
    reviewer = _SyntheticReviewer(observations=[
        {"page_id": "P1", "check": "synthetic-visual-overlap",
         "verdict": "fail"}])
    envelope = _run_review(tmp_path, monkeypatch, reviewer, "u6-fail")
    stages = _stages(envelope)
    assert stages["handoff"]["status"] == "pass"
    assert "reviewer:P1:synthetic-visual-overlap" in (
        envelope["summary"]["remaining_findings"])
    assert envelope["summary"]["visual_acceptance"]["status"] == "fail"
    assert envelope["verdict"] == "fail"
    assert envelope["summary"]["outcome"] == "not_accepted"


def test_coordinator_blocked_observation_blocks_handoff(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unevaluated observation blocks; unknown quality never passes."""
    reviewer = _SyntheticReviewer(observations=[
        {"page_id": "P1", "check": "synthetic-unseen",
         "verdict": "blocked"}])
    envelope = _run_review(tmp_path, monkeypatch, reviewer, "u6-blocked")
    stages = _stages(envelope)
    assert stages["handoff"]["status"] == "blocked"
    assert "could not evaluate" in stages["handoff"]["reason"]
    assert envelope["summary"]["visual_acceptance"]["status"] == "blocked"


def test_coordinator_reviewer_separation_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reviewer identical to the fixer blocks the handoff."""
    reviewer = _SyntheticReviewer(reviewer_id=FIXER)
    envelope = _run_review(tmp_path, monkeypatch, reviewer, "u6-sep")
    stages = _stages(envelope)
    assert stages["handoff"]["status"] == "blocked"
    assert "separation violated" in stages["handoff"]["reason"]
