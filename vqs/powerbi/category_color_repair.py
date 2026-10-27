"""Strict source-grounded restoration of categorical color selectors.

Use ONLY on a disposable candidate, with a verified same-visual semantic
reference. It never invents category values or mutates the reference.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


class CategoryColorRepairError(ValueError):
    """Candidate cannot be repaired safely from the supplied reference."""


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CategoryColorRepairError(f"visual unreadable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("visual"), dict):
        raise CategoryColorRepairError("invalid native PBIR visual object")
    return data


def _scope(entry: Any) -> tuple[str, str, str] | None:
    try:
        comparison = entry["selector"]["data"][0]["scopeId"]["Comparison"]
        if comparison["ComparisonKind"] != 0:
            return None
        column = comparison["Left"]["Column"]
        literal = comparison["Right"]["Literal"]["Value"]
        if not isinstance(literal, str) or not (literal.startswith("'") and literal.endswith("'")):
            return None
        return (column["Expression"]["SourceRef"]["Entity"],
                column["Property"], literal)
    except (KeyError, IndexError, TypeError):
        return None


def _color_id(entry: Any) -> int | None:
    try:
        color = entry["properties"]["fill"]["solid"]["color"]["expr"]["ThemeDataColor"]
        index = color["ColorId"]
        if type(index) is int and index >= 0 and color.get("Percent") == 0:
            return index
    except (KeyError, TypeError):
        pass
    return None


def restore_from_reference(reference: Path, candidate: Path) -> dict[str, Any]:
    """Repair a same-query candidate using its trusted reference's selectors.

    The candidate must already be an isolated *distinct* file: original source
    mutation is never authorized. Preserve every query, sort, filter and layout
    byte-equivalent in the parsed JSON; only add an absent dataPoint group.
    """
    source = reference.resolve(strict=True)
    target = candidate.resolve(strict=True)
    if source == target or source in target.parents or target in source.parents:
        raise CategoryColorRepairError("reference and candidate must be disjoint")
    ref = _read(source)
    doc = _read(target)
    a, b = ref["visual"], doc["visual"]
    if a.get("visualType") not in ("clusteredBarChart", "clusteredColumnChart"):
        raise CategoryColorRepairError("reference is not a supported native categorical bar")
    if a.get("visualType") != b.get("visualType") or a.get("query") != b.get("query"):
        raise CategoryColorRepairError("the visual type or exact semantic query changed")
    reference_points = a.get("objects", {}).get("dataPoint", [])
    candidate_objects = b.setdefault("objects", {})
    if "dataPoint" in candidate_objects:
        raise CategoryColorRepairError("candidate already has dataPoint; refuse overwriting")
    if not isinstance(reference_points, list) or len(reference_points) < 3:
        raise CategoryColorRepairError("trusted reference has no complete category selectors")
    selectors: list[tuple[tuple[str, str, str], int]] = []
    for e in reference_points:
        if not isinstance(e, dict):
            raise CategoryColorRepairError("unsupported dataPoint entry")
        s = _scope(e)
        if s is not None:
            c = _color_id(e)
            if c is None:
                raise CategoryColorRepairError("reference scoped fill is not an exact theme color")
            selectors.append((s, c))
        elif e.get("selector"):
            raise CategoryColorRepairError("unknown reference selector")
    if len(selectors) < 2 or len({s for s, _ in selectors}) != len(selectors):
        raise CategoryColorRepairError("fewer than two unique categorical selectors")
    if len({i for _, i in selectors}) != len(selectors):
        raise CategoryColorRepairError("different category values would share a color slot")
    if len({s[:2] for s, _ in selectors}) != 1:
        raise CategoryColorRepairError("selectors refer to unrelated semantic fields")
    projection = b.get("query", {}).get("queryState", {}).get("Category", {}).get("projections", [])
    if len(projection) != 1:
        raise CategoryColorRepairError("unsupported category projection")
    col = projection[0]["field"]["Column"]
    if (col["Expression"]["SourceRef"]["Entity"], col["Property"]) != selectors[0][0][:2]:
        raise CategoryColorRepairError("reference selector field is not the candidate category")
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    candidate_objects["dataPoint"] = copy.deepcopy(reference_points)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    # No write until ALL semantic invariants have been verified.
    target.write_text(text, encoding="utf-8")
    return {"status": "repaired", "reference_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "candidate_before_sha256": before,
            "candidate_after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "category_field": selectors[0][0][:2],
            "color_ids": {s[2].strip("'"): i for s, i in selectors},
            "selector_count": len(selectors)}
