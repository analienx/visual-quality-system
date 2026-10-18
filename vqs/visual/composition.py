"""PBIR-declared composition facts for deterministic layout review.

Geometry and explicit caption declarations can prove a *layout-policy*
violation. They cannot prove how the application actually rendered pixels;
every repaired report still requires a fresh full-canvas screenshot review.
"""
from __future__ import annotations

from typing import Any


def _literal(slot: Any) -> Any:
    if not isinstance(slot, dict):
        return None
    try:
        value = slot["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _property(owner: Any, group: str, name: str) -> Any:
    if not isinstance(owner, dict):
        return None
    entries = owner.get(group, [])
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return None
    props = entries[0].get("properties", {})
    return _literal(props.get(name)) if isinstance(props, dict) else None


def composition_facts(found: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract actual page/caption/card geometry using the unified PBIR reader.

    If any source is unreadable the reader's existing coverage issues remain
    authoritative; missing geometry is carried as-is for unknown handling.
    """
    pages = []
    for page_id, page in sorted(found.get("pages", {}).items()):
        members = []
        for (pid, visual_id), doc in sorted(found.get("visuals", {}).items()):
            if pid != page_id:
                continue
            visual = doc.get("visual", {}) if isinstance(doc, dict) else {}
            visual = visual if isinstance(visual, dict) else {}
            vco = visual.get("visualContainerObjects", {})
            objects = visual.get("objects", {})
            members.append({
                "visual": visual_id,
                "type": visual.get("visualType"),
                "position": doc.get("position") if isinstance(doc, dict) else None,
                "slicer_title": _property(vco, "title", "text"),
                "slicer_title_shown": _property(vco, "title", "show"),
                "slicer_header": _property(objects, "header", "text"),
                "slicer_header_shown": _property(objects, "header", "show"),
            })
        pages.append({"page": page_id, "width": page.get("width"),
                      "height": page.get("height"), "visuals": members})
    return pages
