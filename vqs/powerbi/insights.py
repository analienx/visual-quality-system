"""Page-insight inventory emitter: what each page delivers, per visual.

Walks a ``*.Report`` folder and records, for every page and visual, the
bound measures, dimensions, and query roles straight from PBIR
``queryState`` projections — the machine-readable "what insight lives
where" record. An optional ``*.SemanticModel`` definition dir adds
TMDL ``dataCategory`` values so map rules can prove (or fail to prove)
geographic bindings. Read-only; anything unproven stays ``None`` or is
omitted, never inferred.

Shapes here are grounded in real PBIR: decomposition trees expose
``Analyze``/``ExplainBy`` roles, maps expose ``Category``/``Size``,
titles live under ``visualContainerObjects.title``. Unknown roles and
field kinds are carried through as unclassified facts, not guessed.
Geometry (PBIR ``position`` blocks) and map label configuration are
measured the same way: present numbers and literals only.
"""
from __future__ import annotations

import glob
import json
import os
import re

TREE_TYPE = "decompositiontreevisual"
MAP_TYPES = frozenset({"map", "filledmap", "shapemap", "azuremap", "arcgismap"})

# PBIR filter entries carrying only these keys prove no restriction, so
# they cannot differentiate two visuals' numbers. Any extra key (values,
# conditions, operators, ...) means the filter may restrict rows.
_FILTER_STRUCTURAL_KEYS = frozenset({"name", "field", "type"})


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _pages(report_dir: str) -> list[dict]:
    found = []
    for path in sorted(glob.glob(os.path.join(
            report_dir, "definition", "pages", "*", "page.json"))):
        page = _read_json(path)
        if page is not None:
            page["_dir"] = os.path.basename(os.path.dirname(path))
            found.append(page)
    return found


def _visuals(report_dir: str, page_dir: str) -> list[dict]:
    found = []
    pattern = os.path.join(report_dir, "definition", "pages", page_dir,
                           "visuals", "*", "visual.json")
    for path in sorted(glob.glob(pattern)):
        visual = _read_json(path)
        if visual is not None:
            visual["_id"] = os.path.basename(os.path.dirname(path))
            found.append(visual)
    return found


def _title(node: dict) -> str | None:
    """Declared container title text, or None when the visual has none."""
    try:
        containers = node.get("visualContainerObjects", {})
        first = containers.get("title", [])[0]
        raw = first["properties"]["text"]["expr"]["Literal"]["Value"]
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if len(text) >= 2 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text or None


def _slot_text(slot: object, *keys: str) -> str:
    """Walk nested dicts defensively; non-dict links yield ""."""
    node = slot
    for key in keys:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    return node if isinstance(node, str) else ""


def _dotted(field: dict) -> tuple[str | None, str | None]:
    """Split a projection field into (kind, Entity.Property ref)."""
    if not isinstance(field, dict):
        return None, None
    for kind in ("Measure", "Column"):
        slot = field.get(kind)
        if not isinstance(slot, dict):
            continue
        entity = _slot_text(slot, "Expression", "SourceRef", "Entity")
        prop = _slot_text(slot, "Property")
        if entity and prop:
            return kind, f"{entity}.{prop}"
        return kind, None
    return None, None


def _query_fields(node: dict) -> dict[str, dict[str, list[str]]]:
    """Map each query role to its measure/dimension/field refs.

    Refs whose field shape is unknown keep their ``queryRef`` label under
    ``fields`` so grain rules can see something is bound without guessing
    its kind.
    """
    roles: dict[str, dict[str, list[str]]] = {}
    state = node.get("query", {})
    state = state.get("queryState", {}) if isinstance(state, dict) else {}
    if not isinstance(state, dict):
        return roles
    for role, content in state.items():
        slot = roles.setdefault(role, {"measures": [], "dimensions": [],
                                       "fields": []})
        if not isinstance(content, dict):
            continue
        projections = content.get("projections", [])
        if not isinstance(projections, list):
            continue
        for projection in projections:
            if not isinstance(projection, dict):
                continue
            kind, dotted = _dotted(projection.get("field", {}))
            label = (projection.get("queryRef")
                     or projection.get("query_ref")
                     or projection.get("nativeQueryRef"))
            if kind == "Measure" and dotted:
                slot["measures"].append(dotted)
            elif kind == "Column" and dotted:
                slot["dimensions"].append(dotted)
            elif isinstance(label, str) and label:
                slot["fields"].append(label)
    return roles


def _valued_filters(visual: dict) -> int:
    """Count visual-level filters that may restrict rows.

    Entries with only structural keys (name/field/type) prove no
    restriction — typically field bookkeeping or cleared filters — and
    do not count. Anything richer may change the numbers.
    """
    config = visual.get("filterConfig", {})
    filters = config.get("filters", []) if isinstance(config, dict) else []
    if not isinstance(filters, list):
        return 0
    count = 0
    for entry in filters:
        if not isinstance(entry, dict):
            continue
        if set(entry) - _FILTER_STRUCTURAL_KEYS:
            count += 1
    return count


def _column_categories(model_dir: str) -> dict[tuple[str, str], str]:
    """Map (table, column) to TMDL dataCategory, exact and folded keys."""
    categories: dict[tuple[str, str], str] = {}
    pattern = os.path.join(model_dir, "**", "*.tmdl")
    for path in sorted(glob.glob(pattern, recursive=True)):
        try:
            with open(path, encoding="utf-8-sig") as handle:
                text = handle.read()
        except OSError:
            continue
        table = re.search(r"^table '(.+)'$", text, re.MULTILINE)
        if table is None:
            table = re.search(r"^table (\S+)$", text, re.MULTILINE)
        if table is None:
            continue
        name = table.group(1)
        blocks = re.finditer(
            r"^\tcolumn ('([^']+)'|([^\s=]+))(.*?)(?=^\t\S|\Z)",
            text, re.MULTILINE | re.DOTALL)
        for match in blocks:
            column = match.group(2) or match.group(3)
            found = re.search(r"dataCategory: (\S+)\s*$", match.group(4),
                              re.MULTILINE)
            if found:
                value = found.group(1).strip().strip("'\"")
                categories[(name, column)] = value
                categories[(name.casefold(), column.casefold())] = value
    return categories


def _number(value: object) -> float | None:
    """PBIR position/size numbers; bools and strings never qualify."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _geometry(visual: dict) -> dict | None:
    """Position rect, or None when the visual proves no geometry."""
    pos = visual.get("position", {})
    if not isinstance(pos, dict):
        return None
    rect = {key: _number(pos.get(key))
            for key in ("x", "y", "width", "height")}
    if any(v is None for v in rect.values()):
        return None
    if rect["width"] < 0 or rect["height"] < 0:
        return None
    return rect


def _page_size(page: dict) -> dict | None:
    width, height = _number(page.get("width")), _number(page.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        return None
    return {"width": width, "height": height}


def _label_facts(node: dict) -> dict:
    """Map label configuration: shown labels or a heatMap layer."""
    objects = node.get("objects", {})
    if not isinstance(objects, dict):
        return {"labels_shown": False, "heatmap": False}
    shown = False
    try:
        first = objects.get("categoryLabels", [])[0]
        raw = first["properties"]["show"]["expr"]["Literal"]["Value"]
        shown = raw == "true"
    except (KeyError, IndexError, TypeError, AttributeError):
        shown = False
    return {"labels_shown": shown, "heatmap": "heatMap" in objects}


def page_insights(report_dir: str, model_dir: str | None = None) -> dict:
    """Inventory what insight each page delivers, plus rule-ready params.

    Returns ``pages`` (full per-visual inventory with titles, roles,
    measures, dimensions, and a ``customized`` flag for visuals that
    declare any format objects), ``visuals`` (flat grain list for the
    duplication rules), ``trees`` (decomposition-tree bindings),
    ``maps`` (map-family location bindings with model categories and
    label facts), ``layout`` (flat geometry list for the overlap rule),
    and ``page_bounds`` (per-page sizes with member geometry).
    Raises OSError when the report folder is unreadable.
    """
    if not os.path.isdir(report_dir):
        raise OSError(f"report folder not found: {report_dir}")
    categories = _column_categories(model_dir) if model_dir else {}
    pages = []
    visuals = []
    trees = []
    maps = []
    layout = []
    page_bounds = []
    for page in _pages(report_dir):
        display = page.get("displayName")
        entries = []
        for visual in _visuals(report_dir, page["_dir"]):
            node = visual.get("visual", {})
            if not isinstance(node, dict):
                continue
            visual_type = node.get("visualType", "?")
            roles = _query_fields(node)
            measures = sorted({ref for role in roles.values()
                               for ref in role["measures"]})
            dimensions = sorted({ref for role in roles.values()
                                 for ref in role["dimensions"]})
            objects = node.get("objects", {})
            entry = {"visual": visual["_id"], "type": visual_type,
                     "title": _title(node), "measures": measures,
                     "dimensions": dimensions, "roles": roles,
                     "customized": isinstance(objects, dict)
                     and len(objects) > 0}
            entries.append(entry)
            rect = _geometry(visual)
            if rect is not None:
                layout.append({"page": page["_dir"], "visual": visual["_id"],
                               **rect})
            if measures or dimensions:
                visuals.append({"page": page["_dir"], "visual": visual["_id"],
                                "type": visual_type, "measures": measures,
                                "dimensions": dimensions,
                                "valued_filters": _valued_filters(visual)})
            # Tree/map classification is independent of parseable refs: a
            # tree or map with no bindings is a broken visual the rules
            # must see (missing_analyze / no_location_field), not a skip.
            folded = str(visual_type).casefold()
            if folded == TREE_TYPE:
                lowered = {role.casefold(): refs
                           for role, refs in roles.items()}
                trees.append({"page": page["_dir"], "visual": visual["_id"],
                              "analyze": sorted(
                                  lowered.get("analyze", {}).get(
                                      "measures", [])),
                              "explain_by": sorted(
                                  lowered.get("explainby", {}).get(
                                      "dimensions", [])),
                              "unrecognized_roles": bool(
                                  roles) and "analyze" not in lowered
                              and "explainby" not in lowered})
            elif folded in MAP_TYPES:
                locations = dimensions
                resolved = {}
                for ref in locations:
                    table, _, column = ref.partition(".")
                    hit = categories.get((table, column))
                    if hit is None:
                        hit = categories.get(
                            (table.casefold(), column.casefold()))
                    resolved[ref] = hit
                maps.append({"page": page["_dir"], "visual": visual["_id"],
                             "type": visual_type, "locations": locations,
                             "categories": resolved,
                             **_label_facts(node)})
        pages.append({"page": page["_dir"],
                      "display_name": display if isinstance(display, str)
                      else None,
                      "visuals": entries})
        size = _page_size(page)
        members = [{"visual": v["visual"], "x": v["x"], "y": v["y"],
                    "width": v["width"], "height": v["height"]}
                   for v in layout if v["page"] == page["_dir"]]
        if members:
            # Pages without a measurable size stay in the list with null
            # bounds so the rule reports unknown instead of passing blind.
            size = size if size is not None else {"width": None,
                                                 "height": None}
            page_bounds.append({"page": page["_dir"], **size,
                                "visuals": members})
    return {"pages": pages, "visuals": visuals, "trees": trees,
            "maps": maps, "layout": layout, "page_bounds": page_bounds}
