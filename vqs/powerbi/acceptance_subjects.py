"""Exact source and capture identity for private two-report acceptance subjects.

The manifest is intentionally local/private: source paths and screenshots can
contain personal or financial details. It is not an owner/G6 approval token.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.pbir import source_digest
from vqs.powerbi.desktop_native_provenance import snapshot
from vqs.powerbi.desktop_source import project_artifacts


def _asset(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("acceptance capture must be a regular file")
    if path.suffix.lower() != ".png":
        raise ValueError("accepted native capture must be a PNG")
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("native capture is not a valid PNG signature")
    return {"path": str(path.resolve()), "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def subject(project: Path, captures: list[Path]) -> dict[str, Any]:
    project = project.resolve(strict=True)
    pbip, report = project_artifacts(project)
    if not pbip.is_file() or not report.is_dir():
        raise ValueError("expected complete PBIP/report project root")
    if len(captures) == 0 or len({p.resolve() for p in captures}) != len(captures):
        raise ValueError("at least one unique native capture is required")
    source = snapshot(project)
    return {
        "schema": "vqs.native-acceptance-subject/1",
        "project": str(project),
        "pbip": str(pbip),
        "report": str(report),
        "source_sha256": source_digest(report),
        "source_files": {
            k: {"sha256": v["sha256"], "size": v["size"]}
            for k, v in sorted(source.items())
        },
        "native_captures": [_asset(p) for p in captures],
        "native_capture_source_bound": False,
        "capture_provenance": "hash-only; no PID/Bridge/source witness",
        "human_g2_g4_signed": False,
        "owner_g6_approved": False,
    }


def bound_subject(project: Path, native_receipt: dict[str, Any]) -> dict[str, Any]:
    """Bind native screenshot bytes to source and Desktop PID from Bridge capture."""
    if native_receipt.get("schema") != "vqs.native-capture-identity/1" or (
            native_receipt.get("source_unchanged_during_capture") is not True):
        raise ValueError("native capture identity receipt unavailable")
    project = project.resolve(strict=True)
    pbip, report = project_artifacts(project)
    if (native_receipt.get("project") != str(project)
            or native_receipt.get("pbip") != str(pbip)
            or native_receipt.get("report") != str(report)
            or type(native_receipt.get("desktop_pid")) is not int):
        raise ValueError("native capture subject/PID mismatch")
    files = snapshot(project)
    hashes = {k: {"sha256": v["sha256"], "size": v["size"]}
              for k, v in files.items()}
    if hashes != native_receipt.get("source_files"):
        raise ValueError("native source changed since Desktop capture")
    shots = native_receipt.get("native_pages")
    if not isinstance(shots, list) or not shots:
        raise ValueError("native capture page inventory missing")
    paths = [Path(item["path"]) for item in shots]
    proof = subject(project, paths)
    actual = proof["native_captures"]
    if len(actual) != len(shots) or any(
            x["path"] != y.get("path")
            or x["sha256"] != y.get("sha256")
            or x["size"] != y.get("size")
            or not isinstance(y.get("page_id"), str)
            for x, y in zip(actual, shots)):
        raise ValueError("native screenshot identity drift")
    if len({item["page_id"] for item in shots}) != len(shots):
        raise ValueError("duplicate native page ID")
    proof["native_capture_source_bound"] = True
    proof["capture_provenance"] = "exact-PID Bridge and before/after source snapshot"
    proof["native_capture_receipt"] = native_receipt
    return proof


def verify_subject(saved: dict[str, Any]) -> tuple[bool, str]:
    try:
        if saved.get("schema") != "vqs.native-acceptance-subject/1":
            raise ValueError("invalid subject schema")
        p = Path(saved["project"]).resolve(strict=True)
        pbip, report = project_artifacts(p)
        if saved.get("pbip") != str(pbip) or saved.get("report") != str(report):
            raise ValueError("project/report identity drift")
        if saved["source_sha256"] != source_digest(report):
            raise ValueError("current report differs from pinned source")
        files = snapshot(p)
        current = {k: {"sha256": v["sha256"], "size": v["size"]}
                   for k, v in files.items()}
        if saved.get("source_files") != current:
            raise ValueError("PBIP or semantic-model source changed")
        shots = saved.get("native_captures")
        if not isinstance(shots, list) or not shots:
            raise ValueError("native capture inventory missing")
        if len({x["path"] for x in shots}) != len(shots):
            raise ValueError("duplicate capture identity")
        for proof in shots:
            new = _asset(Path(proof["path"]))
            if new != proof:
                raise ValueError("source-bound native capture changed")
        if saved.get("native_capture_source_bound") is True:
            receipt = saved.get("native_capture_receipt")
            if not isinstance(receipt, dict):
                raise ValueError("native capture source binding is missing")
            recomputed = bound_subject(p, receipt)
            if recomputed != saved:
                raise ValueError("native capture provenance or source changed")
        elif (saved.get("native_capture_source_bound") is not False or
              saved.get("capture_provenance") != "hash-only; no PID/Bridge/source witness"):
            raise ValueError("hash-only subject cannot claim live source-bound capture")
        if saved.get("human_g2_g4_signed") is not False or (
                saved.get("owner_g6_approved") is not False):
            raise ValueError("generated manifest cannot assert owner signatures")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, str(exc)
    return True, "exact PBIP, model source and native PNG captures unchanged"


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--native-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to replace private evidence")
    if bool(args.capture_dir) == bool(args.native_receipt):
        parser.error("provide exactly one of --capture-dir or --native-receipt")
    if args.native_receipt:
        item = bound_subject(
            args.project, json.loads(args.native_receipt.read_text("utf8")))
        shots = item["native_captures"]
    else:
        shots = sorted(args.capture_dir.glob("*.png"))
        item = subject(args.project, shots)
    valid, reason = verify_subject(item)
    if not valid:
        parser.error("new subject not attestable: " + reason)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(item, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"subject": ("exact_native_source_bound" if item["native_capture_source_bound"]
                                     else "hashes_verified_not_live_source_bound"),
                      "file_count": len(item["source_files"]),
                      "native_page_count": len(shots), "owner_g6_approved": False,
                      "manifest": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
