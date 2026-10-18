"""Microsoft-metadata-bound cosmetic repair gate, BEFORE candidate creation.

The existing VQS typed recipe binder remains authoritative for selectors,
PBIR paths and old literals. Official Microsoft catalog/property information
provides *additional* capability evidence; it never invents PBIR operations.
Only a deliberately narrow set of provable literal types is authorized.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ...repair.execute import RepairError, tree_digest
from ...repair.recipes import FORMAT_OPS, LEAF_OPS, RecipeError, bind_operation
from . import metadata

CONTRACT = "vqs.metadata-repair-gate/1"
DECIMAL = re.compile(r"(0|[1-9][0-9]{0,14})\Z")
SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,119}\Z")


def _refusal(reason: str, index: int | None = None) -> dict[str, Any]:
    return {"contract": CONTRACT, "status": "blocked",
            "reason": reason, "operation_index": index,
            "mutates_report": False}


def evaluate(
    plan: dict[str, Any], original: str, attestation: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed for Microsoft-selected formatting edits; no filesystem writes.

    Source tree identity is bound to each receipt and handed to the executor,
    which must pin the same bytes again before creating candidate artifacts.
    Only canonical integer precision PBIR literals have complete type proof
    in this first compiler tranche. All other formats require further work.
    """
    if attestation.get("validation_provider") != "microsoft":
        return {"contract": CONTRACT, "status": "not_applicable",
                "reason": "native-only validation; no Microsoft capability proof",
                "mutates_report": False}
    try:
        source_sha = tree_digest(original)
    except (RepairError, OSError) as exc:
        return _refusal(f"source report is not safely readable: {exc}")
    root = Path(original)
    records: list[dict[str, Any]] = []
    cache: dict[tuple[str, ...], dict[str, Any]] = {}
    operations = plan.get("operations", [])
    if not isinstance(operations, list):
        return _refusal("plan operations unavailable")

    def lookup(capability: str, *names: str) -> dict[str, Any]:
        key = (capability, *names)
        if key not in cache:
            cache[key] = metadata.query(attestation, capability, *names)
        return cache[key]

    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            return _refusal("operation not an object", index)
        kind = op.get("type")
        if kind not in LEAF_OPS | FORMAT_OPS:
            records.append({"index": index, "status": "not_applicable",
                            "reason": "non-formatting operation governed by typed VQS gate"})
            continue
        selector = op.get("selector")
        if not isinstance(selector, dict):
            return _refusal("source selector missing", index)
        page, visual = selector.get("page"), selector.get("visual")
        if (not isinstance(page, str) or not SEGMENT.fullmatch(page)
                or not isinstance(visual, str) or not SEGMENT.fullmatch(visual)):
            return _refusal("source page/visual selector unsafe", index)
        rel = f"definition/pages/{page}/visuals/{visual}/visual.json"
        try:
            source_bytes = (root / rel).read_bytes()
            source_doc = json.loads(source_bytes.decode("utf-8-sig"))
            if not isinstance(source_doc, dict):
                raise TypeError("visual source is not a JSON object")
            if source_doc.get("name") != visual:
                raise ValueError("visual ID disagrees with selected path")
            bound = bind_operation(op, source_doc)
            visual_info = source_doc.get("visual")
            if not isinstance(visual_info, dict):
                raise TypeError("selected source is not a PBIR visual")
            visual_type = visual_info.get("visualType")
            if not isinstance(visual_type, str):
                raise TypeError("selected source lacks visualType")
            path = op.get("path")
            if not isinstance(path, list) or "properties" not in path:
                raise ValueError("formatting property path not proven")
            anchor = path.index("properties")
            if (len(path) < 4 or path[0:2] != ["visual", "objects"]
                    or path[2] is None or not isinstance(path[2], str)
                    or anchor not in (4, 5) or anchor + 1 >= len(path)):
                raise ValueError("formatting object path outside metadata pilot")
            object_name, property_name = path[2], path[anchor + 1]
            if not isinstance(property_name, str):
                raise TypeError("formatting property name invalid")
        except (OSError, ValueError, KeyError, IndexError, RecipeError,
                UnicodeError, TypeError) as exc:
            return _refusal(f"source/recipe binding rejected: {exc}", index)
        try:
            catalog = lookup("catalog.describe", visual_type)
            if (not isinstance(catalog, dict)
                    or catalog.get("status") != "pass"
                    or not isinstance(catalog.get("data"), dict)
                    or catalog["data"].get("deprecated") is not False
                    or not isinstance(catalog.get("sha256"), str)
                    or len(catalog["sha256"]) != 64):
                return _refusal("visual catalog unknown or deprecated", index)
            prop = lookup("formatting.describe_property", visual_type,
                          object_name, property_name)
            if (not isinstance(prop, dict)
                    or prop.get("status") != "pass"
                    or not isinstance(prop.get("data"), dict)
                    or not isinstance(prop["data"].get("property"), dict)
                    or not isinstance(prop["data"]["property"].get("type"), str)
                    or not isinstance(prop.get("sha256"), str)
                    or len(prop["sha256"]) != 64):
                return _refusal("property unsupported in Microsoft capability catalog",
                                index)
            field_type = prop["data"]["property"]["type"]
        except Exception as exc:  # noqa: BLE001 - untrusted metadata port
            return _refusal(f"Microsoft metadata lookup crashed: {type(exc).__name__}",
                            index)
        # PBIR QueryLiteralExpression.Value is a string even for an integer.
        # The recipe binder separately verifies canonical decimal 0-15 for
        # precision terminals; do not infer other formatting/enum encodings.
        new_value = bound.get("new")
        if kind == "format.unset_override":
            new_value = bound.get("old")
        supported = (
            field_type == "integer"
            and property_name in {"labelPrecision", "precision"}
            and isinstance(new_value, str)
            and DECIMAL.fullmatch(new_value) is not None
            and int(new_value) <= 15
        )
        if not supported:
            return _refusal(f"Microsoft {field_type!r} property encoding not proven", index)
        records.append({
            "index": index, "status": "supported", "type": kind,
            "page": page, "visual": visual, "visual_type": visual_type,
            "property": f"{object_name}.{property_name}",
            "source_visual_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "catalog_sha256": catalog["sha256"],
            "property_sha256": prop["sha256"],
            "old": bound.get("old"), "new": new_value,
        })
    receipt = {"contract": CONTRACT, "status": "pass",
               "source_tree_sha256": source_sha,
               "skill_sha256": attestation.get("skill", {}).get("snapshot", {}).get("sha256"),
               "cli_version": attestation.get("cli", {}).get("version"),
               "operations": records, "mutates_report": False}
    receipt["sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, ensure_ascii=False,
                   allow_nan=False).encode("utf-8")).hexdigest()
    return receipt
