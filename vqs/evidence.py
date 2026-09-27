"""Source-bound report/Word page evidence, ported from PBIPDocumenter VQS.

A passed JSON checklist is not proof that the reviewer actually inspected pixels.
The separate rule/data/render stages must also pass before release approval.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

from .policy import CRITERIA, OPTIONAL, POLICY_VERSION, REQUIRED, SEVERITIES, STATUSES


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    """Check PNG signature, chunk bounds, CRCs and final IEND, not only the header."""
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG signature: {path}")
        size = None
        data_seen = end_seen = False
        for _ in range(100000):
            header = stream.read(8)
            if len(header) != 8:
                break
            length, tag = struct.unpack(">I4s", header)
            if length > 100_000_000:
                raise ValueError(f"Oversized PNG chunk: {path}")
            payload, check = stream.read(length), stream.read(4)
            if len(payload) != length or len(check) != 4:
                raise ValueError(f"Truncated PNG chunk: {path}")
            if zlib.crc32(tag + payload) != struct.unpack(">I", check)[0]:
                raise ValueError(f"Corrupt PNG chunk: {path}")
            if tag == b"IHDR":
                if size is not None or length != 13:
                    raise ValueError(f"Invalid PNG header: {path}")
                size = struct.unpack(">II", payload[:8])
            elif tag == b"IDAT":
                data_seen = True
            elif tag == b"IEND":
                end_seen = True
                break
        if size is None or not data_seen or not end_seen or not all(1 <= x <= 20000 for x in size):
            raise ValueError(f"Incomplete PNG image: {path}")
        return size


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def safe_render_name(name: object) -> str | None:
    """Accept plain basenames only; reject traversal and absolute paths."""
    if not isinstance(name, str) or not name or name.startswith((".", "/")):
        return None
    if "/" in name or "\\" in name or Path(name).name != name:
        return None
    return name


def image_evidence(images: Path, source_sha: str, page_ids: list[str]) -> tuple[list[dict], list[dict]]:
    """Validate rendered page PNGs against a source-linked capture manifest."""
    manifest_path = images / "capture-manifest.json"
    if not manifest_path.is_file():
        return [], [{"rule": "render_manifest_missing", "path": str(manifest_path)}]
    try:
        manifest = load(manifest_path)
    except (OSError, ValueError, TypeError) as error:
        return [], [{"rule": "render_manifest_invalid", "detail": str(error)}]
    issues: list[dict] = []
    if manifest.get("source_sha256") != source_sha:
        issues.append({"rule": "render_source_stale"})
    files = manifest.get("files")
    mapping = manifest.get("page_images")
    if not isinstance(files, dict) or not isinstance(mapping, dict):
        return [], issues + [{"rule": "render_manifest_invalid"}]
    pages = []
    for page_id in page_ids:
        fallback = page_id if page_id.lower().endswith(".png") else page_id + ".png"
        name = safe_render_name(mapping.get(page_id, fallback))
        if name is None:
            issues.append({"rule": "page_render_invalid", "page": page_id,
                           "detail": "unsafe render filename in manifest"})
            continue
        path = images / name
        if not path.is_file():
            issues.append({"rule": "page_render_missing", "page": page_id})
            continue
        try:
            dimensions = png_size(path)
            if min(dimensions) < 450:
                raise ValueError("Image too small to review")
            sha = digest(path)
        except (ValueError, OSError) as error:
            issues.append({"rule": "page_render_invalid", "page": page_id, "detail": str(error)})
            continue
        if files.get(name) != sha:
            issues.append({"rule": "page_render_unbound", "page": page_id})
        pages.append({"id": page_id, "image": name, "sha256": sha, "pixels": dimensions})
    return pages, issues


def review_template(kind: str, source_sha: str, pages: list[dict], fixer_id: str) -> dict:
    """Create an unapproved review form; pending observations never imply approval."""
    if not source_sha or not fixer_id:
        raise ValueError("Template needs a source hash and a fixer id")
    if kind not in REQUIRED:
        raise ValueError(f"Unsupported review surface: {kind}")
    return {"schema": 1, "policy_version": POLICY_VERSION, "surface": kind,
            "source_sha256": source_sha, "fixer_id": fixer_id,
            "reviewer": {"id": "", "role": "independent_visual_reviewer"},
            "pages": [{"id": page["id"], "image": page["image"], "image_sha256": page["sha256"],
                       "image_source_sha256": source_sha,
                       "visual_inventory": page.get("visual_inventory", []),
                       "observations": [{"id": check, "criterion": CRITERIA[check], "status": "pending", "reason": "",
                                         "severity": None, "region": None, "visual_id": "page", "proposed_fix": ""}
                                        for check in REQUIRED[kind]]} for page in pages]}


def verify_review(kind: str, source_sha: str, pages: list[dict], review: dict, fixer_id: str) -> list[dict]:
    """Reject missing checks, stale images, self-approval and unlocated failures."""
    if kind not in REQUIRED:
        raise ValueError(f"Unsupported review surface: {kind}")
    findings: list[dict] = []
    if (review.get("schema") != 1 or review.get("policy_version") != POLICY_VERSION or
            review.get("surface") != kind or review.get("source_sha256") != source_sha):
        return [{"rule": "review_policy_or_source_mismatch"}]
    reviewer = review.get("reviewer", {})
    if not isinstance(reviewer, dict):
        reviewer = {}
    reviewer_id = reviewer.get("id", "")
    if not reviewer_id or reviewer_id == fixer_id or reviewer.get("role") != "independent_visual_reviewer":
        findings.append({"rule": "independent_reviewer_required"})
    rows = review.get("pages", [])
    if not isinstance(rows, list) or len(rows) != len(pages):
        return findings + [{"rule": "review_page_inventory_mismatch"}]
    observed = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if len(observed) != len(pages):
        return findings + [{"rule": "review_duplicate_page"}]
    for page in pages:
        item = observed.get(page["id"])
        if not item or item.get("image_sha256") != page["sha256"]:
            findings.append({"rule": "review_image_stale", "page": page["id"]})
            continue
        answers = item.get("observations", [])
        if not isinstance(answers, list):
            findings.append({"rule": "review_observations_invalid", "page": page["id"]})
            continue
        by_id = {answer.get("id"): answer for answer in answers if isinstance(answer, dict)}
        expected = set(REQUIRED[kind])
        if len(by_id) != len(answers) or set(by_id) != expected:
            findings.append({"rule": "review_observations_incomplete", "page": page["id"]})
            continue
        for check in expected:
            answer = by_id[check]
            status, reason = answer.get("status"), answer.get("reason")
            if status not in STATUSES or not isinstance(reason, str) or len(reason.strip()) < 32:
                findings.append({"rule": "observation_unsubstantiated", "page": page["id"], "check": check})
            elif status == "not_applicable" and check not in OPTIONAL[kind]:
                findings.append({"rule": "mandatory_observation_skipped", "page": page["id"], "check": check})
            elif status == "fail":
                region = answer.get("region")
                located = (isinstance(region, list) and len(region) == 4 and
                           all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in region) and
                           region[0] < region[2] and region[1] < region[3])
                valid_ids = {"page"} | {v["id"] for v in page.get("visual_inventory", [])}
                if (answer.get("severity") not in SEVERITIES or not located or
                        answer.get("visual_id") not in valid_ids or
                        len(str(answer.get("proposed_fix", "")).strip()) < 12):
                    findings.append({"rule": "issue_lacks_location_or_repair", "page": page["id"], "check": check})
                else:
                    findings.append({"rule": "visual_defect", "page": page["id"], "check": check,
                                     "severity": answer["severity"], "region": region, "visual_id": answer["visual_id"],
                                     "detail": reason, "proposed_fix": answer["proposed_fix"]})
    return findings
