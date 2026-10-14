"""Run-owned populated Desktop previews from complete local PBIP projects.

The sealed repair candidate deliberately excludes local .pbi model cache.
Desktop may show (Blank) everywhere without it. For *preview only*, copy the
complete original PBIP project into a private scratch root, preserve its local
model cache and overlay the cosmetic VQS candidate's proven changed visuals.
Never publish or promote this preview. Populated data remains an independent
runtime check, NOT a conclusion from cache presence.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any


class PreviewMaterializationError(ValueError):
    """A complete and source-bound private preview cannot be produced."""


def _inventory(root: Path) -> dict[str, str]:
    if not root.is_dir() or root.is_symlink():
        raise PreviewMaterializationError(f"unreadable project tree: {root}")
    inventory = {}
    for item in root.rglob("*"):
        if item.is_symlink() or getattr(os.path, "isjunction", lambda _p: False)(item):
            raise PreviewMaterializationError(f"linked project entry: {item}")
        if item.is_file():
            if item.stat().st_nlink > 1:
                raise PreviewMaterializationError(f"hardlinked entry: {item}")
            sha = hashlib.sha256()
            with item.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(chunk)
            inventory[item.relative_to(root).as_posix()] = sha.hexdigest()
    return inventory


def _report_from_pbip(project: Path) -> Path:
    if not project.is_file() or project.suffix.lower() != ".pbip":
        raise PreviewMaterializationError("source must be a complete .pbip")
    try:
        doc = json.loads(project.read_text(encoding="utf-8-sig"))
        paths = [item["report"]["path"] for item in doc["artifacts"]
                 if isinstance(item, dict) and isinstance(item.get("report"), dict)]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PreviewMaterializationError("unreadable PBIP report reference") from exc
    if len(paths) != 1 or not isinstance(paths[0], str):
        raise PreviewMaterializationError("expected exactly one PBIP report reference")
    relative = Path(paths[0])
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".report":
        raise PreviewMaterializationError("invalid PBIP report reference")
    report = (project.parent / relative).resolve()
    if report.parent != project.parent.resolve() or not report.is_dir():
        raise PreviewMaterializationError("referenced PBIP report is not a local sibling")
    return report


def materialize_populated_preview(
        source_pbip: str | Path, typed_candidate_report: str | Path,
        preview_root: str | Path, declared_visual_files: list[str]
        ) -> dict[str, Any]:
    """Build a *private scratch preview* with one exact, confined repair delta.

    Checks every report member; any unexpected change, model/query/filter
    mutation or source drift blocks. The complete source cache is intentionally
    reused locally; it must never be considered tested freshness/RLS or shipped.
    """
    original_project = Path(source_pbip).resolve()
    source_root = original_project.parent
    original_report = _report_from_pbip(original_project)
    typed_root = Path(typed_candidate_report).resolve()
    destination = Path(preview_root).absolute()
    if destination.exists() or destination.is_symlink():
        raise PreviewMaterializationError("preview root must be new and empty")
    # Cache may contain customer data. Never materialize it into a Git
    # checkout where it could be committed accidentally, even on draft PRs.
    if any((parent / ".git").exists() for parent in
           (destination.parent, *destination.parents)):
        raise PreviewMaterializationError(
            "private preview may not be placed inside a Git checkout")
    if (destination == source_root
            or source_root in destination.parents
            or destination in source_root.parents
            or typed_root == original_report or typed_root == destination
            or typed_root in destination.parents
            or destination in typed_root.parents):
        raise PreviewMaterializationError("preview must not overlap source or candidate")
    if not declared_visual_files or len(set(declared_visual_files)) != len(
            declared_visual_files):
        raise PreviewMaterializationError("expected nonempty unique visual paths")
    allowed = set(declared_visual_files)
    for path in allowed:
        rel = Path(path)
        parts = rel.parts
        if (rel.is_absolute() or ".." in parts or len(parts) != 6
                or parts[0:2] != ("definition", "pages")
                or parts[3] != "visuals" or parts[5] != "visual.json"):
            raise PreviewMaterializationError(
                f"only exact PBIR visual.json changes may be previewed: {path}")
    source_files = _inventory(source_root)
    source_report_files = _inventory(original_report)
    typed_files = _inventory(typed_root)
    if set(source_report_files) != set(typed_files):
        raise PreviewMaterializationError("candidate report file inventory differs")
    observed = {name for name in source_report_files
                if source_report_files[name] != typed_files[name]}
    if observed != allowed:
        raise PreviewMaterializationError(
            f"candidate changes do not match declared visuals: {sorted(observed ^ allowed)}")
    for path in sorted(allowed):
        before = json.loads((original_report / path).read_text(encoding="utf-8"))
        after = json.loads((typed_root / path).read_text(encoding="utf-8"))
        old = before.get("visual", {})
        new = after.get("visual", {})
        for key in ("visualType", "query", "filterConfig", "drillFilterOtherVisuals"):
            if old.get(key) != new.get(key):
                raise PreviewMaterializationError(
                    f"semantic/interaction change is not a cosmetic preview: {path}/{key}")
        if before.get("name") != after.get("name"):
            raise PreviewMaterializationError("visual identity changed")
    cache = sorted(p for p in source_root.glob("*.SemanticModel/.pbi/cache.abf")
                   if p.is_file())
    try:
        shutil.copytree(source_root, destination)
        preview_report = destination / original_report.name
        for path in sorted(allowed):
            shutil.copy2(typed_root / path, preview_report / path)
        if _inventory(source_root) != source_files:
            raise PreviewMaterializationError(
                "original project changed during preview materialization")
        preview_files = _inventory(destination)
        source_rel = original_report.relative_to(source_root).as_posix()
        expected = dict(source_files)
        for path in allowed:
            expected[f"{source_rel}/{path}"] = typed_files[path]
        if preview_files != expected:
            raise PreviewMaterializationError("preview has undeclared/missing bytes")
        return {
            "status": "materialized",
            "preview_pbip": str(destination / original_project.name),
            "preview_report": str(preview_report),
            "changed_visuals": sorted(allowed),
            "source_file_count": len(source_files),
            "source_unchanged": True,
            "preview_cache_present": bool(cache),
            "semantic_runtime_readiness": "NOT_RUN",
            "privacy": "local-only; never promote/publish preview model cache",
        }
    except Exception:
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        raise
