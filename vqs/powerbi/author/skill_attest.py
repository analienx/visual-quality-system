"""Installed-wheel-safe integrity verifier for the reviewed Microsoft skill.

Never execute checker code from a user-selected or cloned checkout. The approved
tree digest and revision are compiled into this VQS release; updating the
official skill requires review and repinning these values. Source checkouts
work without setup; installed wheels may use VQS_APPROVED_SKILL_ROOT to point
to the approved VQS checkout holding the official vendored skill.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from . import mscli

APPROVED_UPSTREAM = "https://github.com/microsoft/skills-for-fabric"
APPROVED_COMMIT = "bc42aaf734771bf752c1d7082dd91e5a6ca72b9f"
APPROVED_TREE_SHA256 = "82a19935d88def4600522430fa61cbdcee689f9d3e76db2a57b1eea0983b1eda"
APPROVED_SKILL_VERSION = "1.0.5"
APPROVED_CLI_VERSION = "0.5.0"
APPROVED_FILE_COUNT = 88
APPROVED_ALGORITHM = "sha256-lf-v1"


def _tree_digest(folder: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    count = 0
    if not folder.is_dir() or not (folder / "SKILL.md").is_file():
        raise ValueError("reviewed Microsoft skill subtree is missing")
    for path in sorted(folder.rglob("*"), key=lambda p: p.relative_to(folder).as_posix()):
        if path.is_symlink():
            raise ValueError(f"skill symlink disallowed: {path}")
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix not in (".md", ".json", ".yml", ".yaml"):
            raise ValueError("unexpected vendor file type")
        rel = path.relative_to(folder).as_posix()
        data = path.read_bytes().replace(b"\r\n", b"\n")
        if b"\r" in data:
            raise ValueError("noncanonical vendor carriage return")
        file_hash = hashlib.sha256(data).hexdigest()
        h.update(f"{rel}\0{file_hash}\n".encode())
        count += 1
    return h.hexdigest(), count


def check() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read-only offline hash attestation and real executable identity."""
    specified = os.environ.get("VQS_APPROVED_SKILL_ROOT")
    root = Path(specified).resolve() if specified else Path(__file__).resolve().parents[3]
    folder = root / ".agents" / "skills" / "powerbi-report-cli"
    lockfile = root / ".agents" / "skills" / "powerbi-report-cli-upstream.json"
    skill: dict[str, Any] = {"status": "blocked", "checkout": str(root)}
    try:
        tree, count = _tree_digest(folder)
        lock = json.loads(lockfile.read_text(encoding="utf-8"))
        if not isinstance(lock, dict):
            raise TypeError("skill provenance lock is not an object")
        expected = {
            "sha256": APPROVED_TREE_SHA256, "file_count": APPROVED_FILE_COUNT,
            "version": APPROVED_SKILL_VERSION, "commit": APPROVED_COMMIT,
            "upstream": APPROVED_UPSTREAM, "hash_algorithm": APPROVED_ALGORITHM,
            "cli_package": mscli.PACKAGE_NAME, "cli_version": APPROVED_CLI_VERSION,
        }
        if any(lock.get(k) != v for k, v in expected.items()):
            raise ValueError("skill provenance lock differs from approved VQS release")
        if tree != APPROVED_TREE_SHA256 or count != APPROVED_FILE_COUNT:
            raise ValueError("reviewed skill bytes differ from approved release digest")
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s*version:\s*1\.0\.5\s*$", text):
            raise ValueError("skill semantic version mismatch")
        skill = {"status": "pass", "commit": APPROVED_COMMIT,
                 "snapshot": {"sha256": tree, "version": APPROVED_SKILL_VERSION,
                              "file_count": count}, "checkout": str(root)}
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        skill["reason"] = str(exc)
    cli_probe = mscli.probe()
    cli: dict[str, Any] = {
        "status": "pass" if (cli_probe.get("available")
                            and cli_probe.get("version") == APPROVED_CLI_VERSION)
                  else "blocked",
        "version": cli_probe.get("version"), "path": cli_probe.get("path"),
        "package": mscli.PACKAGE_NAME,
    }
    if cli["status"] != "pass":
        cli["reason"] = "pinned Microsoft authoring CLI unavailable or incompatible"
    return skill, cli
