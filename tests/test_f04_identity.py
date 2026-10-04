"""F04 RED: one source/model identity across apply/capture/verify.

apply_plan exposes only tree_digest content hashes (report-root
relative), while capture manifests bind pbir.source_digest (report +
referenced-model source). The two domains cannot compose: no field of
an applied result verifies a capture manifest through real consumers.

M2 fix shape: apply_plan additionally exposes the capture-domain
source_sha256 of the candidate, keeping before/after as the byte-exact
rollback digests; verify routes through the production verifier.
"""
import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

from vqs.pbir import source_digest
from vqs.repair.execute import apply_plan, tree_digest
from vqs.repair.regress import verify_renders

FIXTURES = (Path(__file__).resolve().parent / "fixtures"
            / "vqs_agent_first" / "repair")


def _load(scenario):
    root = FIXTURES / scenario
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    return root / "original.Report", plan


def _applied(tmp_path):
    fixture_report, plan = _load("scenario_tick")
    original = tmp_path / "original.Report"
    shutil.copytree(fixture_report, original)
    applied = apply_plan(plan, str(original), str(tmp_path / "cand"))
    assert applied["verdict"] == "applied"
    return applied


def test_f04_apply_exposes_capture_domain_source(tmp_path) -> None:
    """RED: applied result must carry the capture-domain source identity."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    assert applied["source_sha256"] == source_digest(candidate)


def test_f04_rollback_digests_stay_byte_exact(tmp_path) -> None:
    """Byte-exact rollback digests keep their own names (passes now)."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    assert applied["after"] == tree_digest(candidate)


def test_f04_apply_to_verify_composes(tmp_path) -> None:
    """Producer-to-consumer wiring apply -> manifest -> verify."""
    applied = _applied(tmp_path)
    candidate = Path(applied["candidate"])
    digest = source_digest(candidate)
    assert applied["source_sha256"] == digest
    renders = tmp_path / "renders"
    renders.mkdir()
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * 500 for _ in range(500))
    ihdr = struct.pack(">IIBBBBB", 500, 500, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    png = (b"\x89PNG\r\n\x1a\n"
           + struct.pack(">I", 13) + b"IHDR" + ihdr
           + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
           + struct.pack(">I", len(idat)) + b"IDAT" + idat
           + struct.pack(">I", zlib.crc32(b"IDAT" + idat) & 0xFFFFFFFF)
           + struct.pack(">I", 0) + b"IEND"
           + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF))
    (renders / "P1.png").write_bytes(png)
    sha = hashlib.sha256(png).hexdigest()
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": digest, "page_images": {"P1": "P1.png"},
         "files": {"P1.png": sha},
         "calibration": {"canvas_width": 500, "canvas_height": 500, "scale": 1,
                         "viewport": "500x500@1x", "method": "bridge"},
         "data_readiness": {"populated": True,
                           "method": "modeling-mcp:repeat-query"}}),
        encoding="utf-8")
    verdict = verify_renders(["P1"], [renders], applied["source_sha256"])
    assert verdict["verdict"] == "pass"
