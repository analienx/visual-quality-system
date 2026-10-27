"""Repair only Microsoft's missing PBIP/PBIR metadata schemas in a disposable copy.

Power BI Desktop 2.159 can omit both schema URLs on native Save. This repair
does not certify the loaded Desktop state or bypass its source freshness gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from vqs.powerbi.desktop_source import local_semantic_model, project_artifacts

WRAPPER_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/pbip/"
    "pbipProperties/1.0.0/schema.json"
)
REFERENCE_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/"
    "definitionProperties/2.0.0/schema.json"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _insert_schema(file: Path, schema: str) -> tuple[bytes, bytes]:
    if file.is_symlink() or not file.is_file():
        raise ValueError("metadata file is missing or symlinked")
    original = file.read_bytes()
    parsed = json.loads(original.decode("utf-8-sig"))
    if not isinstance(parsed, dict):
        raise TypeError("metadata must be a JSON object")
    if "$schema" in parsed:
        if parsed["$schema"] != schema:
            raise ValueError("unexpected existing schema; refusing replacement")
        return original, original
    encoded = (json.dumps({"$schema": schema, **parsed}, indent=2,
                          ensure_ascii=False) + "\n").encode("utf-8")
    if {k: v for k, v in json.loads(encoded).items() if k != "$schema"} != parsed:
        raise ValueError("schema-only transformation was not equivalent")
    return original, encoded


def _replace(file: Path, data: bytes) -> None:
    staged: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=file.parent, prefix=".vqs-schema-", delete=False
        ) as temp:
            staged = temp.name
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(staged, file)
    finally:
        if staged is not None and os.path.exists(staged):
            os.unlink(staged)


def normalize_saved_metadata(
    project: Path, *, disposable_root: Path, apply: bool = False
) -> dict[str, Any]:
    """Validate first, then change at most the two allowlisted JSON files.

    An explicit separate scratch parent is mandatory. This does not attest
    Power BI Desktop's in-memory state or make an external post-open edit safe.
    """
    project = project.resolve(strict=True)
    scratch = disposable_root.resolve(strict=True)
    if project == scratch or not project.is_relative_to(scratch):
        raise ValueError("project must be inside the explicitly selected scratch root")
    wrapper, report = project_artifacts(project)
    reference = report / "definition.pbir"
    model, kind = local_semantic_model(project, report, wrapper)
    if kind != "byPath_source_checked" or model is None:
        raise ValueError("only a declared local byPath model can be normalized")
    files = [(wrapper, WRAPPER_SCHEMA), (reference, REFERENCE_SCHEMA)]
    updates = [(path, *_insert_schema(path, schema)) for path, schema in files]
    changes = [
        {"path": str(path.relative_to(project)),
         "before_sha256": _sha(before), "after_sha256": _sha(after)}
        for path, before, after in updates if before != after
    ]
    if apply:
        completed: list[tuple[Path, bytes]] = []
        try:
            for path, before, after in updates:
                if before == after:
                    continue
                if path.read_bytes() != before:
                    raise ValueError("metadata changed during normalization")
                _replace(path, after)
                completed.append((path, before))
            for path, before, after in updates:
                if path.read_bytes() != after:
                    raise ValueError("post-write schema contents changed")
        except Exception:
            for path, original in reversed(completed):
                _replace(path, original)
            raise
    return {
        "schema": "vqs.saved-pbip-metadata-normalization/1",
        "status": "applied" if apply else "dry_run",
        "metadata_only": True,
        "declared_model": kind,
        "changed_file_count": len(changes),
        "changes": changes,
        "desktop_loaded_file_attested": False,
        "independent_g2_g4_g6": "blocked",
    }
