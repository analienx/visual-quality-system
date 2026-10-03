"""Portable review bundles for cross-machine, cross-agent handoff.

A bundle is a directory carrying everything an independent reviewer
needs and nothing else: the capture manifest, page PNGs, the report
inventory, and a ``bundle.json`` header pinning fixer, source hash,
policy version, and the SHA-256 of every other member. ``verify``
re-hashes every member, enforces the allowlisted membership (extras,
subdirectories, and symlinks are rejected), and cross-checks page
inventory, manifest sources, and render bindings; ``--report``
additionally binds the bundle to a live report folder. Bundles may
contain business-data pixels: keep them private, never commit them.
"""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = 1
FIXED_MEMBERS = ("capture-manifest.json", "inventory.json")


def _utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pack(report: str, renders: str, out: str, fixer_id: str) -> dict:
    """Assemble a verified bundle; raise when evidence is incomplete."""
    from ..evidence import digest, image_evidence
    from ..pbir import report_context, source_digest
    from ..policy import POLICY_VERSION

    if not fixer_id or not fixer_id.strip():
        raise ValueError("Bundle needs a non-empty fixer id")
    report_path = Path(report)
    try:
        info = report_context(report_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OSError(f"Cannot read report: {exc}") from exc
    expected = [page["id"] for page in info["pages"]]
    pages, issues = image_evidence(Path(renders), source_digest(report_path),
                                   expected)
    if issues or len(pages) != len(expected):
        detail = "; ".join(sorted({i.get("rule", "?") for i in issues}))
        raise ValueError(f"Renders incomplete or unbound: {detail}")
    out_path = Path(out)
    if out_path.exists():
        raise OSError(f"Refusing to overwrite: {out}")
    header = {"schema": SCHEMA, "kind": "vqs-review-bundle",
              "fixer_id": fixer_id, "source_sha256": info["source_sha256"],
              "policy_version": POLICY_VERSION, "pages": expected,
              "created_utc": _utcnow(), "files": {}}
    try:
        out_path.mkdir(parents=True)
        shutil.copy2(Path(renders) / "capture-manifest.json",
                     out_path / "capture-manifest.json")
        for page in pages:
            shutil.copy2(Path(renders) / page["image"],
                         out_path / page["image"])
        (out_path / "inventory.json").write_text(
            json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
        members = list(FIXED_MEMBERS) + [page["image"] for page in pages]
        header["files"] = {name: digest(out_path / name) for name in members}
        (out_path / "bundle.json").write_text(json.dumps(header, indent=2),
                                              encoding="utf-8")
    except FileExistsError as exc:
        # A foreign dir appeared after the exists-check: never rmtree it.
        raise OSError(f"Refusing to overwrite: {out}") from exc
    except (OSError, shutil.Error) as exc:
        shutil.rmtree(out_path, ignore_errors=True)
        raise OSError(f"Bundle assembly failed, rolled back: {exc}") from exc
    return {"status": "packed", "fixer_id": fixer_id,
            "source_sha256": info["source_sha256"],
            "pages": expected, "bundle": str(out_path),
            "files": {page["image"]: digest(out_path / page["image"])
                      for page in pages}}


def verify(bundle: str, report: str | None = None) -> dict:
    """Re-hash and cross-check a bundle; raise on any mismatch."""
    from ..evidence import digest, safe_render_name
    from ..pbir import source_digest

    root = Path(bundle)
    try:
        header = json.loads((root / "bundle.json").read_text(
            encoding="utf-8-sig"))
        manifest = json.loads((root / "capture-manifest.json").read_text(
            encoding="utf-8-sig"))
        inventory = json.loads((root / "inventory.json").read_text(
            encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Bundle unreadable: {exc}") from exc
    if not all(isinstance(part, dict)
               for part in (header, manifest, inventory)):
        raise ValueError("Bundle unreadable: expected JSON objects")
    problems = []
    if header.get("schema") != SCHEMA:
        problems.append("bundle schema mismatch")
    if header.get("kind") != "vqs-review-bundle":
        problems.append("not a vqs review bundle")
    for key in ("fixer_id", "policy_version", "created_utc", "pages",
              "source_sha256"):
        if not header.get(key):
            problems.append(f"bundle header missing {key}")
    member_hashes = header.get("files")
    if not isinstance(member_hashes, dict) or not member_hashes:
        problems.append("bundle header missing file inventory")
        member_hashes = {}
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise TypeError("Bundle invalid: manifest files is not an object")
    mapping = manifest.get("page_images", {})
    if not isinstance(mapping, dict):
        raise TypeError("Bundle invalid: manifest page_images is not an object")
    allowed = {"bundle.json", *FIXED_MEMBERS}
    for name in mapping.values():
        if safe_render_name(name) is not None:
            allowed.add(name)
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise ValueError(f"Bundle unreadable: {exc}") from exc
    on_disk = set()
    for entry in entries:
        if entry.is_symlink():
            problems.append(f"symlink member: {entry.name}")
            continue
        if not entry.is_file() or entry.name not in allowed:
            problems.append(f"unexpected bundle member: {entry.name}")
            continue
        on_disk.add(entry.name)
    for name, expected in member_hashes.items():
        if name not in allowed:
            problems.append(f"unexpected bundle member: {name}")
            continue
        if name not in on_disk:
            problems.append(f"missing member: {name}")
            continue
        try:
            current = digest(root / name)
        except OSError:
            problems.append(f"unreadable member: {name}")
            continue
        if current != expected:
            problems.append(f"tampered member: {name}")
    inv_pages = inventory.get("pages", [])
    hdr_pages = header.get("pages") or []
    if (not isinstance(inv_pages, list)
            or not isinstance(hdr_pages, list)
            or [page.get("id") if isinstance(page, dict) else None
                for page in inv_pages] != list(hdr_pages)):
        problems.append("inventory pages differ from bundle header")
    inv_ids = [page.get("id") if isinstance(page, dict) else None
               for page in inv_pages] if isinstance(inv_pages, list) else []
    if len(set(hdr_pages)) != len(hdr_pages) or len(set(inv_ids)) != len(inv_ids):
        problems.append("duplicate page ids in bundle")
    if manifest.get("source_sha256") != header.get("source_sha256"):
        problems.append("manifest source differs from bundle header")
    if inventory.get("source_sha256") != header.get("source_sha256"):
        problems.append("inventory source differs from bundle header")
    for page_id, name in mapping.items():
        if safe_render_name(name) is None:
            problems.append(f"unsafe render filename: {name}")
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            problems.append(f"missing render: {name}")
            continue
        try:
            current = digest(path)
        except OSError:
            problems.append(f"unreadable render: {name}")
            continue
        if files.get(name) != current:
            problems.append(f"tampered render: {name}")
        if page_id not in (header.get("pages") or []):
            problems.append(f"render outside bundle pages: {page_id}")
    for page_id in header.get("pages") or []:
        if page_id not in (manifest.get("page_images") or {}):
            problems.append(f"page without render: {page_id}")
    if report is not None:
        try:
            live = source_digest(Path(report))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise OSError(f"Cannot read report: {exc}") from exc
        if live != header.get("source_sha256"):
            problems.append("bundle source is stale against live report")
    if problems:
        raise ValueError("Bundle invalid: " + "; ".join(sorted(problems)))
    return {"status": "valid", "source_sha256": header["source_sha256"],
            "pages": header["pages"], "fixer_id": header["fixer_id"]}


def unpack(bundle: str, dest: str) -> dict:
    """Copy a bundle to a destination and verify the copy."""
    if Path(dest).exists():
        raise OSError(f"Refusing to overwrite: {dest}")
    try:
        shutil.copytree(bundle, dest, symlinks=True)
    except FileExistsError as exc:
        raise OSError(f"Refusing to overwrite: {dest}") from exc
    except (OSError, shutil.Error) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise OSError(f"Bundle copy failed, rolled back: {exc}") from exc
    try:
        return verify(dest)
    except (OSError, ValueError, TypeError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise OSError(f"Unpacked copy failed verification, rolled back: "
                      f"{exc}") from exc
