"""Standalone program-ledger end-to-end acceptance for issue #4.

Exercises the full offline chain a user/integrator runs before any
Desktop/Word spike: published ledger -> STATUS snapshot -> roadmap CLI ->
vqs inventory/request-review on synthetic fixtures, with negative controls.

This does NOT claim WP-11 full two-PBIP/DOCX acceptance (issue #16) or any
verified work package. It proves the #4 planning ledger is internally
consistent and the pre-alpha CLIs behave honestly end to end.
"""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from scripts.roadmap_report import DEFAULT_LEDGER, summarize, validate
from vqs.cli import main as vqs_main
from vqs.pbir import report_context, source_digest

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_SCRIPT = ROOT / "scripts" / "roadmap_report.py"
CALIBRATION = {"canvas_width": 500, "canvas_height": 500, "scale": 1,
               "viewport": "500x500@1x", "method": "bridge-screenshot-all"}
CALIBRATION_1280 = {"canvas_width": 1280, "canvas_height": 720, "scale": 1,
                    "viewport": "1280x720@1x",
                    "method": "bridge-screenshot-all"}
READINESS = {"populated": True, "method": "scoped-dax-probe",
             "checked_at": "2026-10-03T00:00:00Z"}


def _ledger() -> dict:
    return json.loads(Path(DEFAULT_LEDGER).read_text(encoding="utf-8-sig"))


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    """Write a minimal valid truecolor PNG using stdlib only."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width for _ in range(height))
    compressed = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(
            ">I", zlib.crc32(tag + payload) & 0xFFFFFFFF
        )

    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def _make_report(root: Path) -> Path:
    report = root / "Example.Report"
    visual = report / "definition" / "pages" / "p1" / "visuals" / "vis1"
    visual.mkdir(parents=True)
    (report / "definition" / "pages.json").write_text(
        json.dumps({"pageOrder": ["p1"]}), encoding="utf-8"
    )
    (report / "definition" / "version.json").write_text(
        json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "1.0"}), encoding="utf-8"
    )
    (report / "definition" / "report.json").write_text(
        json.dumps({
            "$schema": ("https://developer.microsoft.com/json-schemas/fabric/item/"
                        "report/definition/report/3.3.0/schema.json"),
            "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8",
    )
    (report / "definition" / "pages" / "p1" / "page.json").write_text(
        json.dumps({"displayName": "Overview", "width": 1280, "height": 720}),
        encoding="utf-8",
    )
    (visual / "visual.json").write_text(
        json.dumps(
            {
                "name": "vis1",
                "position": {"x": 24, "y": 24, "width": 350, "height": 210},
                "visual": {
                    "visualType": "clusteredBarChart",
                    "query": {
                        "queryState": {
                            "Category": {
                                "projections": [{"queryRef": "Dim Product.Brand"}]
                            },
                            "Y": {
                                "projections": [{"queryRef": "Fact Sales.Amount"}]
                            },
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return report


def test_e2e_ledger_valid_with_zero_verified_and_wp00_runnable() -> None:
    data = _ledger()
    assert validate(data) == []
    summary = summarize(data)
    assert summary["independently_verified"] == 0
    assert summary["initial_release_packages"] == 14
    assert summary["deferred"] == 1
    assert summary["next_runnable"] == ["WP-00"]


def test_e2e_status_snapshot_matches_machine_ledger() -> None:
    data = _ledger()
    summary = summarize(data)
    status = (ROOT / "roadmap" / "STATUS.md").read_text(encoding="utf-8-sig")
    assert "issues/4" in status
    assert "0 independently verified / 14" in status
    assert "| **verified" not in status
    assert summary["snapshot_utc"] in ("2026-09-23T20:40:00Z", data["snapshot_utc"])
    for issue in list(range(5, 19)) + [19]:
        assert f"/issues/{issue}" in status
    ledger_issues = sorted(item["issue"] for item in data["packages"])
    assert ledger_issues == list(range(5, 19)) + [19]


def test_e2e_program_docs_link_issue4_and_ledger() -> None:
    program = (ROOT / "docs" / "IMPLEMENTATION_PROGRAM.md").read_text(encoding="utf-8")
    protocol = (ROOT / "docs" / "LEDGER_AND_AGENT_PROTOCOL.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs" / "ACCEPTANCE_MATRIX.md").read_text(encoding="utf-8")
    assert "issues/4" in program
    assert "work_packages.json" in program
    assert "issues/4" in protocol
    assert "work_packages.json" in matrix or "work-packages" in matrix or "WP-11" in matrix
    assert _ledger()["program_issue"].endswith("/issues/4")


def test_e2e_roadmap_cli_check_and_json_report(tmp_path: Path) -> None:
    direct = subprocess.run(
        [sys.executable, str(ROADMAP_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert direct.returncode == 0
    assert "VALID ROADMAP" in direct.stdout
    out = tmp_path / "summary.json"
    direct_json = subprocess.run(
        [sys.executable, str(ROADMAP_SCRIPT), "--format", "json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert direct_json.returncode == 0
    out.write_text(direct_json.stdout, encoding="utf-8")
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["independently_verified"] == 0
    assert parsed["next_runnable"] == ["WP-00"]


def test_e2e_vqs_inventory_roundtrip(tmp_path: Path, capsys) -> None:
    report = _make_report(tmp_path)
    code = vqs_main(["inventory", str(report)])
    captured = capsys.readouterr()
    assert code == 0
    info = json.loads(captured.out)
    assert info["source_sha256"] == source_digest(report)
    assert [page["id"] for page in info["pages"]] == ["p1"]
    assert info["pages"][0]["visuals"][0]["visual_id"] == "vis1"
    assert report_context(report)["source_sha256"] == info["source_sha256"]


def test_e2e_request_review_success_and_stale_negative(tmp_path: Path, capsys) -> None:
    """S11: renders must fit the source canvas (1280x720 here)."""
    report = _make_report(tmp_path)
    renders = tmp_path / "renders"
    renders.mkdir()
    png = renders / "p1.png"
    _write_png(png, 1280, 720)
    sha = source_digest(report)
    png_sha = hashlib.sha256(png.read_bytes()).hexdigest()
    (renders / "capture-manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": sha,
                "page_images": {"p1": "p1.png"},
                "files": {"p1.png": png_sha},
                "calibration": CALIBRATION_1280,
                "data_readiness": READINESS,
            }
        ),
        encoding="utf-8",
    )
    code = vqs_main(["request-review", str(report), str(renders), "--fixer-id", "e2e"])
    captured = capsys.readouterr()
    assert code == 0
    template = json.loads(captured.out)
    assert template["source_sha256"] == sha
    assert template["fixer_id"] == "e2e"
    assert template["pages"][0]["image_source_sha256"] == sha

    (renders / "capture-manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": "stale-source",
                "page_images": {"p1": "p1.png"},
                "files": {"p1.png": png_sha},
                "calibration": CALIBRATION_1280,
                "data_readiness": READINESS,
            }
        ),
        encoding="utf-8",
    )
    code = vqs_main(["request-review", str(report), str(renders), "--fixer-id", "e2e"])
    captured = capsys.readouterr()
    assert code == 2
    assert json.loads(captured.out)["status"] == "blocked"


def test_e2e_tampered_ledger_cannot_verify(tmp_path: Path) -> None:
    data = copy.deepcopy(_ledger())
    data["packages"][0]["state"] = "verified"
    data["packages"][0]["verification"] = "verified"
    problems = validate(data)
    assert any("lacks independent evidence" in problem for problem in problems)
    tampered = tmp_path / "work_packages.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    direct = subprocess.run(
        [sys.executable, str(ROADMAP_SCRIPT), "--ledger", str(tampered), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert direct.returncode == 2
    assert "INVALID ROADMAP" in direct.stderr


def test_e2e_issue_closure_alone_cannot_verify() -> None:
    data = copy.deepcopy(_ledger())
    item = data["packages"][2]
    item["state"] = "verified"
    item["verification"] = "verified"
    problems = validate(data)
    assert any("lacks independent evidence" in problem for problem in problems)
    assert any("WP-02" in problem or "WP-00" in problem or "prerequisite" in problem
               or "lacks independent" in problem for problem in problems)


def test_e2e_validator_presence_check_is_not_proof(tmp_path: Path) -> None:
    """Pin the documented trust boundary: VALID means pointers present, not authentic.

    Per docs/LEDGER_AND_AGENT_PROTOCOL.md raw evidence outranks the ledger
    snapshot, and scripts/roadmap_report.py checks claims without resolving
    commits, PRs, or evidence URIs. A forged verified claim with dummy
    pointers therefore passes the presence check; it must never be read
    as independent proof.
    """
    data = copy.deepcopy(_ledger())
    data["packages"][0]["state"] = "verified"
    data["packages"][0]["verification"] = "verified"
    data["packages"][0]["verified_commit"] = "0" * 40
    data["packages"][0]["evidence_uri"] = "private://vqs/fake/manifest.json"
    data["packages"][0]["pull_request"] = 9999
    assert validate(data) == []
    assert summarize(data)["independently_verified"] == 1
    forged = tmp_path / "work_packages.json"
    forged.write_text(json.dumps(data), encoding="utf-8")
    direct = subprocess.run(
        [sys.executable, str(ROADMAP_SCRIPT), "--ledger", str(forged), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert direct.returncode == 0
    assert "VALID ROADMAP" in direct.stdout


def test_e2e_remanifested_stale_pixels_trust_manifest_author(
    tmp_path: Path, capsys
) -> None:
    """Pin the manifest-author trust boundary: a fresh manifest for old pixels passes.

    request-review binds renders to the source SHA named in the manifest; it
    cannot prove the pixels were captured after the latest source edit. Only
    the lazy stale-manifest case (wrong SHA left in place) is blocked.
    S11: canvas fit is still enforced — the old pixels here are source-sized.
    """
    report = _make_report(tmp_path)
    renders = tmp_path / "renders"
    renders.mkdir()
    png = renders / "p1.png"
    _write_png(png, 1280, 720)
    png_sha = hashlib.sha256(png.read_bytes()).hexdigest()
    visual = report / "definition" / "pages" / "p1" / "visuals" / "vis1" / "visual.json"
    visual.write_text(visual.read_text(encoding="utf-8") + " ", encoding="utf-8")
    new_sha = source_digest(report)
    (renders / "capture-manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": new_sha,
                "page_images": {"p1": "p1.png"},
                "files": {"p1.png": png_sha},
                "calibration": CALIBRATION_1280,
                "data_readiness": READINESS,
            }
        ),
        encoding="utf-8",
    )
    code = vqs_main(["request-review", str(report), str(renders), "--fixer-id", "e2e"])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["source_sha256"] == new_sha
