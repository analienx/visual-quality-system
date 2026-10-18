"""Version-pinned visual-template registry (WP-09).

chart.replace applies only a registered template whose required bindings
are all present on the target visual and whose story oracle is recorded.
No templates ship preloaded: bodies must be real captured visual JSON,
and registering a fabricated body would be evidence fabrication, so
registration stays an explicit, reviewed, test-scoped act.
"""
from __future__ import annotations

import copy
import math
from typing import Any


class TemplateError(ValueError):
    """No vetted template for this replacement."""


_registered: dict[tuple[str, str], dict[str, Any]] = {}


def _check_body_finite(value: Any, depth: int = 0) -> None:
    """Anti-abuse walk: template bodies stay finite and bounded."""
    if depth > 12:
        raise TemplateError("template body nests too deep")
    if isinstance(value, float) and not math.isfinite(value):
        raise TemplateError("template body holds a non-finite number")
    if isinstance(value, dict):
        if len(value) > 200:
            raise TemplateError("template body object too large")
        for entry in value.values():
            _check_body_finite(entry, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise TemplateError("template body array too large")
        for entry in value:
            _check_body_finite(entry, depth + 1)


def register_template(name: str, version: str, visual_type: str,
                      body: dict[str, Any],
                      required_bindings: list[str],
                      oracle_id: str) -> None:
    """Register one vetted template version; shape errors raise."""
    if not name or not version or not visual_type or not oracle_id:
        raise TemplateError("template needs name, version, visual_type, "
                            "and oracle_id")
    if not isinstance(body, dict) or not isinstance(
            body.get("visual"), dict):
        raise TemplateError("template body must be a visual.json object")
    if (not isinstance(required_bindings, list) or not required_bindings
            or not all(isinstance(ref, str) and ref
                       for ref in required_bindings)):
        raise TemplateError("template needs a non-empty required_bindings "
                            "list of query refs")
    if not isinstance(body["visual"].get("objects"), dict):
        raise TemplateError("template body objects must be an object")
    _check_body_finite(body)
    _registered[(name, version)] = {
        "name": name, "version": version, "visual_type": visual_type,
        "body": body, "required_bindings": list(required_bindings),
        "oracle_id": oracle_id}


def get_template(name: str, version: str) -> dict[str, Any]:
    """Fetch a registered template; missing versions block, never default.

    Returns a deep copy: callers cannot mutate registered state.
    """
    try:
        return copy.deepcopy(_registered[(name, version)])
    except KeyError as exc:
        raise TemplateError(
            f"no vetted template registered for {name} {version}; "
            "chart.replace is blocked") from exc


def verify_bindings(template: dict[str, Any],
                    field_bindings: dict[str, Any]) -> list[str]:
    """Required query refs missing from the target visual (empty = all met)."""
    present: set[str] = set()
    for spec in (field_bindings or {}).values():
        if not isinstance(spec, list):
            continue
        for projection in spec:
            if isinstance(projection, dict):
                ref = projection.get("queryRef", "")
                if ref:
                    present.add(str(ref))
    return [ref for ref in template.get("required_bindings", [])
            if ref not in present]


def list_templates() -> list[dict[str, str]]:
    """Name/version/oracle inventory of registered templates."""
    return [{"name": name, "version": version,
             "oracle_id": template["oracle_id"]}
            for (name, version), template in sorted(_registered.items())]


def clear_templates() -> None:
    """Forget all registrations (tests only; production never calls this)."""
    _registered.clear()
