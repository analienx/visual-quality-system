"""Unambiguous PBIP/Report input resolution for human and MCP entrypoints.

Never guess among multiple report/model projects, and never edit source here.
"""
from __future__ import annotations

import json
from pathlib import Path


def resolve_project_input(report: str, model: str | None = None) -> tuple[str, str | None]:
    """Resolve a .pbip, project root, or enhanced *.Report folder.

    A missing/ambiguous model is not invented. Resolve explicit .pbip
    report paths only when safely contained within the same project.
    """
    raw = Path(report).expanduser()
    if raw.is_file() and raw.suffix.lower() == ".pbip":
        root = raw.parent
        try:
            metadata = json.loads(raw.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read PBIP project metadata: {exc}") from exc
        candidates = [p for p in root.glob("*.Report") if p.is_dir()]
        if not isinstance(metadata, dict):
            raise ValueError("PBIP metadata must be an object")
        # .pbip's artifacts are not a portable report-location guarantee.
        # Exact filename wins only if the report folder is unambiguous.
        matches = [p for p in candidates if p.stem.lower() == raw.stem.lower()]
        if len(matches) == 1:
            selected = matches[0]
        elif len(candidates) == 1:
            selected = candidates[0]
        else:
            raise ValueError(f"ambiguous PBIP report folder ({len(candidates)} candidates); provide a *.Report path")
    elif raw.is_dir() and (raw.name.lower().endswith(".report")
                           or (raw / "definition" / "pages").is_dir()):
        selected = raw
        root = raw.parent
    elif raw.is_dir():
        root = raw
        candidates = [p for p in root.glob("*.Report") if p.is_dir()]
        if len(candidates) != 1:
            raise ValueError(f"project root has {len(candidates)} report folders; provide a *.Report path")
        selected = candidates[0]
    else:
        raise ValueError(f"report must be an existing .pbip, *.Report or project root: {raw}")
    if model:
        return str(selected.resolve()), str(Path(model).expanduser().resolve())
    models = [p / "definition" for p in root.glob("*.SemanticModel")
              if p.is_dir() and (p / "definition").is_dir()]
    if len(models) == 1:
        return str(selected.resolve()), str(models[0].resolve())
    # Multi-model sources require explicit selection; do not silently
    # validate a report against a randomly selected semantic model.
    if len(models) > 1:
        raise ValueError("multiple semantic models present; supply --model/model_dir")
    return str(selected.resolve()), None
