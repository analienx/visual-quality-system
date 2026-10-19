"""Shared local Contoso PBIP source verification for live DAX and native UIA.

A report-only digest is insufficient: verify the wrapper, referenced TMDL,
missing assets, and symlinks before/after touching a Desktop model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from vqs.pbir import source_inventory


def inventory(project: Path) -> tuple[dict[str, Any], str]:
    """Return source inventory and PBIP wrapper hash; reject unsafe sources."""
    wrapper = project / "Contoso Retail.pbip"
    report = project / "Contoso Retail.Report"
    model = project / "Contoso Retail.SemanticModel"
    if (any(path.is_symlink() for path in (project, wrapper, report, model))
            or not wrapper.is_file() or not report.is_dir() or not model.is_dir()):
        raise ValueError("Contoso PBIP, Report and SemanticModel must be local files")
    try:
        doc = json.loads(wrapper.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"PBIP wrapper unreadable: {exc}") from exc
    if (not isinstance(doc, dict) or doc.get("artifacts") != [
            {"report": {"path": "Contoso Retail.Report"}}]):
        raise ValueError("PBIP wrapper does not identify the exact Contoso report")
    for root in (report, model):
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if ".pbi" in relative.parts:
                continue
            if path.is_symlink():
                raise ValueError("symlinked PBIP source cannot be fingerprinted")
    found = source_inventory(report)
    if (found["issues"] or not found["report_files"]
            or not found["model_files"]
            or Path(found["model_dir"] or "").resolve() not in (
                model.resolve(), (model / "definition").resolve())):
        raise ValueError("referenced TMDL model/report source is missing or unresolved")
    return found, hashlib.sha256(wrapper.read_bytes()).hexdigest()
