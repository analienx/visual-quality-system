"""Pin and verify the official Microsoft Power BI Report skill (no implicit upgrades).

The checked-in skill is an exact vendor snapshot. Updates require an explicit
reviewed sync from a checkout of microsoft/skills-for-fabric; live VQS runs only
read this snapshot. This script never calls the network or executes skill text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "powerbi-report-cli"
LOCK = ROOT / ".agents" / "skills" / "powerbi-report-cli-upstream.json"
UPSTREAM = "https://github.com/microsoft/skills-for-fabric"
CLI_PACKAGE = "@microsoft/powerbi-report-authoring-cli"
PINNED_CLI_VERSION = "0.5.0"


def snapshot(folder: Path) -> dict[str, str | int]:
    """Canonical LF digest of regular vendor files across Git checkout policies.

    Git stores official markdown as LF, but Windows autocrlf checks it out as
    CRLF unless text eol=lf is explicitly enforced. Hash the canonical Git
    content bytes, never an operating-system-dependent worktree encoding.
    """
    if not folder.is_dir():
        raise ValueError(f"skill directory missing: {folder}")
    files = sorted(folder.rglob("*"), key=lambda p: p.relative_to(folder).as_posix())
    digest = hashlib.sha256()
    count = 0
    for path in files:
        if path.is_symlink():
            raise ValueError(f"symlink disallowed: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"nonregular file: {path}")
        rel = path.relative_to(folder).as_posix()
        if path.suffix not in {".md", ".json", ".yml", ".yaml"}:
            raise ValueError(f"unapproved skill content: {rel}")
        raw = path.read_bytes()
        canonical = raw.replace(b"\r\n", b"\n")
        if b"\r" in canonical:
            raise ValueError(f"noncanonical carriage return in vendor file: {rel}")
        blob = hashlib.sha256(canonical).hexdigest()
        digest.update(f"{rel}\0{blob}\n".encode())
        count += 1
    if not count or not (folder / "SKILL.md").is_file():
        raise ValueError("empty or missing root SKILL.md")
    match = re.search(r"(?m)^\s*version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$",
                      (folder / "SKILL.md").read_text(encoding="utf-8"))
    if not match:
        raise ValueError("upstream skill has no semantic metadata version")
    return {"sha256": digest.hexdigest(), "version": match.group(1),
            "file_count": count}


def check(skill: Path = SKILL, lock_file: Path = LOCK) -> dict:
    if not lock_file.is_file():
        return {"status": "blocked", "reason": "missing skill provenance lock"}
    try:
        lock = json.loads(lock_file.read_text(encoding="utf-8"))
        actual = snapshot(skill)
    except (OSError, ValueError, UnicodeError) as exc:
        return {"status": "blocked", "reason": str(exc)}
    if (lock.get("sha256") != actual["sha256"]
            or lock.get("version") != actual["version"]
            or lock.get("file_count") != actual["file_count"]
            or lock.get("upstream") != UPSTREAM
            or lock.get("hash_algorithm") != "sha256-lf-v1"
            or lock.get("cli_package") != CLI_PACKAGE
            or lock.get("cli_version") != PINNED_CLI_VERSION
            or not re.fullmatch(r"[0-9a-f]{40}", str(lock.get("commit", "")))):
        return {"status": "blocked", "reason": "skill bytes or identity differ from pinned upstream",
                "actual": actual, "lock": lock}
    return {"status": "pass", "snapshot": actual, "commit": lock["commit"],
            "upstream": UPSTREAM, "cli_version_pinned": lock.get("cli_version")}


def cli_check(expected: str = PINNED_CLI_VERSION) -> dict:
    exe = shutil.which("powerbi-report-author")
    if not exe:
        return {"status": "blocked", "reason": "Microsoft CLI not on PATH"}
    try:
        cp = subprocess.run([exe, "--version"], capture_output=True,
                            text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "blocked", "reason": f"CLI version probe failed: {exc}"}
    version = cp.stdout.strip()
    if cp.returncode != 0 or version != expected:
        return {"status": "blocked", "reason": "CLI version incompatible with tested lock",
                "found": version, "expected": expected, "returncode": cp.returncode}
    return {"status": "pass", "version": version, "path": exe}


def _verify_upstream_git_provenance(skill_path: Path, commit: str) -> None:
    """Require a clean, exact Git commit/tree, not an asserted SHA string."""
    command = ["git", "-C", str(skill_path)]
    try:
        cp = subprocess.run([*command, "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, check=True, timeout=20)
        root = Path(cp.stdout.strip()).resolve()
        repo_cmd = ["git", "-C", str(root)]
        rel = skill_path.resolve().relative_to(root).as_posix()
        if rel != "skills/powerbi-report-cli":
            raise ValueError(f"wrong upstream subtree: {rel}")
        got = subprocess.run([*repo_cmd, "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True,
                             timeout=20).stdout.strip()
        if got != commit:
            raise ValueError(f"upstream commit mismatch: expected {commit}, found {got}")
        tracked = subprocess.run(
            [*repo_cmd, "ls-tree", "-r", "--name-only", "HEAD", rel],
            capture_output=True, text=True, check=True, timeout=20
        ).stdout.splitlines()
        actual = sorted(p.relative_to(skill_path).as_posix()
                        for p in skill_path.rglob("*") if p.is_file())
        expected = sorted(name[len(rel) + 1:] for name in tracked)
        if actual != expected:
            raise ValueError("upstream working tree has missing or extra files")
        for relative in expected:
            blob = subprocess.run(
                [*repo_cmd, "show", f"{commit}:{rel}/{relative}"],
                capture_output=True, check=True, timeout=20
            ).stdout
            worktree = (skill_path / relative).read_bytes()
            if blob.replace(b"\r\n", b"\n") != worktree.replace(b"\r\n", b"\n"):
                raise ValueError(f"uncommitted upstream content change: {relative}")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("cannot attest upstream git origin/tree") from exc


def sync_from(upstream_skill: Path, commit: str) -> dict:
    """Explicit vendor refresh only; never run during an active report edit."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("upstream SHA must be a full 40-hex commit")
    _verify_upstream_git_provenance(upstream_skill, commit)
    observed = snapshot(upstream_skill)
    # Refuse self-copy and unrelated artifact paths.
    if upstream_skill.resolve() == SKILL.resolve():
        raise ValueError("source equals installed destination")
    current = check() if SKILL.exists() else {"status": "blocked"}
    if current["status"] == "pass" and current["snapshot"] == observed:
        return current  # no PR churn for unrelated upstream repository commits
    staging = SKILL.parent / "_powerbi-report-cli-next"
    backup = SKILL.parent / "_powerbi-report-cli-previous"
    if staging.exists() or backup.exists():
        raise ValueError("occupied skill staging/backup directory")
    if SKILL.exists() and check()["status"] != "pass":
        raise ValueError("existing installed skill is modified; preserve and review it")
    previous_lock = LOCK.read_bytes() if LOCK.is_file() else None
    swapped = False
    try:
        shutil.copytree(upstream_skill, staging, symlinks=False)
        if snapshot(staging) != observed:
            raise ValueError("source drift during copy")
        if SKILL.exists():
            SKILL.rename(backup)
        try:
            staging.rename(SKILL)
            swapped = True
            lock = {"upstream": UPSTREAM, "path": "skills/powerbi-report-cli",
                    "commit": commit, "version": observed["version"],
                    "sha256": observed["sha256"], "file_count": observed["file_count"],
                    "hash_algorithm": "sha256-lf-v1",
                    "cli_package": CLI_PACKAGE, "cli_version": PINNED_CLI_VERSION}
            LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
            result = check()
            if result["status"] != "pass":
                raise ValueError("new vendor snapshot did not verify")
            if backup.exists():
                shutil.rmtree(backup)
            return result
        except Exception:
            if swapped and SKILL.exists():
                shutil.rmtree(SKILL)
            if backup.exists():
                backup.rename(SKILL)
            if previous_lock is None:
                LOCK.unlink(missing_ok=True)
            else:
                LOCK.write_bytes(previous_lock)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sync-from", type=Path, help="trusted upstream skill directory")
    p.add_argument("--commit", help="full pinned upstream commit for explicit sync")
    p.add_argument("--check-cli", action="store_true")
    p.add_argument("--compare-upstream", type=Path, help="detect newer skill bytes")
    args = p.parse_args()
    if args.sync_from and not args.commit:
        p.error("--sync-from requires --commit")
    if args.commit and not args.sync_from:
        p.error("--commit requires --sync-from")
    try:
        result = sync_from(args.sync_from, args.commit) if args.sync_from else check()
        if args.compare_upstream:
            newer = snapshot(args.compare_upstream)
            current = result.get("snapshot", {})
            result["upstream_status"] = ("current" if newer == current else "update_available")
            result["upstream_snapshot"] = newer
        if args.check_cli:
            result["cli"] = cli_check()
    except (OSError, ValueError) as exc:
        result = {"status": "blocked", "reason": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (result.get("status") == "pass"
                 and result.get("upstream_status", "current") == "current"
                 and result.get("cli", {"status": "pass"})["status"] == "pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
