"""Page-insight inventory emitter: what each page delivers, per visual.

Walks a ``*.Report`` folder through the unified PBIR reader and records,
for every page and visual, the bound measures, dimensions, and query roles
straight from PBIR ``queryState`` projections — the machine-readable "what
insight lives where" record. An optional ``*.SemanticModel`` definition dir
adds TMDL ``dataCategory`` values so map rules can prove (or fail to prove)
geographic bindings. Read-only; anything unproven stays ``None`` or is
omitted, never inferred.

Shapes here are grounded in real PBIR: decomposition trees expose
``Analyze``/``ExplainBy`` roles, maps expose ``Category``/``Size``,
titles live under ``visualContainerObjects.title``. Unknown roles and
field kinds are carried through as unclassified facts, not guessed.
Geometry (PBIR ``position`` blocks incl. ``z`` layering) and map label
configuration are measured the same way: finite numbers and literals
only — NaN/Infinity prove no geometry. Filters count at visual, page, and report scope. Bookmark snapshots
(name, targets, active section, filter entities, groups) and per-page
visual interactions are exposed as static facts for repair invariants;
only their live *effects* still need Desktop behavior.
"""
from __future__ import annotations

import math

TREE_TYPE = "decompositiontreevisual"
MAP_TYPES = frozenset({"map", "filledmap", "shapemap", "azuremap", "arcgismap"})


def _finite(value: object) -> float | None:
    """Finite PBIR numbers; bools, strings, NaN, and infinities never qualify."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


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


def _ref_parts(field: dict) -> tuple[str | None, str | None, str | None]:
    """Split a projection field into (kind, entity, property)."""
    if not isinstance(field, dict):
        return None, None, None
    for kind in ("Measure", "Column"):
        slot = field.get(kind)
        if not isinstance(slot, dict):
            continue
        entity = _slot_text(slot, "Expression", "SourceRef", "Entity")
        prop = _slot_text(slot, "Property")
        if entity and prop:
            return kind, entity, prop
        return kind, None, None
    return None, None, None


def _query_fields(node: dict) -> dict[str, dict[str, list]]:
    """Map each query role to its measure/dimension/field refs.

    Refs whose field shape is unknown keep their ``queryRef`` label under
    ``fields`` so grain rules can see something is bound without guessing
    its kind. Dotted refs keep the historical ``Entity.Property`` string
    form; structured ``*_structured`` lists preserve entity/property
    separately so dotted table names never mis-split downstream.
    """
    roles: dict[str, dict[str, list]] = {}
    state = node.get("query", {})
    state = state.get("queryState", {}) if isinstance(state, dict) else {}
    if not isinstance(state, dict):
        return roles
    for role, content in state.items():
        slot = roles.setdefault(role, {"measures": [], "dimensions": [],
                                       "fields": [], "measures_structured": [],
                                       "dimensions_structured": []})
        if not isinstance(content, dict):
            continue
        projections = content.get("projections", [])
        if not isinstance(projections, list):
            continue
        for projection in projections:
            if not isinstance(projection, dict):
                continue
            kind, entity, prop = _ref_parts(projection.get("field", {}))
            label = (projection.get("queryRef")
                     or projection.get("query_ref")
                     or projection.get("nativeQueryRef"))
            if kind == "Measure" and entity and prop:
                slot["measures"].append(f"{entity}.{prop}")
                slot["measures_structured"].append({"entity": entity,
                                                   "property": prop})
            elif kind == "Column" and entity and prop:
                slot["dimensions"].append(f"{entity}.{prop}")
                slot["dimensions_structured"].append({"entity": entity,
                                                     "property": prop})
            elif isinstance(label, str) and label:
                slot["fields"].append(label)
    return roles


# PBIR filter entries carrying only these keys prove no restriction, so
# they cannot differentiate two visuals' numbers. Any extra key (values,
# conditions, operators, ...) means the filter may restrict rows.
_FILTER_STRUCTURAL_KEYS = frozenset({"name", "field", "type"})


def _valued_filters_in(doc: dict) -> int:
    """Count valued filters in one filterConfig-bearing document."""
    config = doc.get("filterConfig", {})
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


def _bookmark_filter_entities(doc: dict) -> tuple[list[str], bool]:
    """Entity names a bookmark snapshot filters; (entities, malformed).

    Each filter group list is guarded independently: one malformed key
    never crashes the inventory and never hides the well-formed half.
    """
    state = doc.get("explorationState", {})
    filters = state.get("filters", {}) if isinstance(state, dict) else {}
    if not isinstance(filters, dict):
        return [], True
    entities: set[str] = set()
    malformed = False
    for key in ("byExpr", "byColumn"):
        part = filters.get(key, [])
        if not isinstance(part, list):
            malformed = True
            continue
        for group in part:
            if not isinstance(group, dict):
                continue
            expr = group.get("expression", {})
            if not isinstance(expr, dict):
                continue
            for kind in ("Column", "Measure"):
                slot = expr.get(kind, {})
                name = _slot_text(slot, "Expression", "SourceRef", "Entity")
                if name:
                    entities.add(name)
    return sorted(entities), malformed


def _bookmark_facts(found: dict) -> tuple[list[dict], list[dict]]:
    """Shape bookmark snapshots + groups for repair invariants.

    Identity falls back to the file key when ``name`` is missing (the
    reader records the gap); nothing is inferred beyond the snapshot.
    Malformed filter shapes yield an issue plus the proven entities,
    never a crash.
    """
    groups: dict[str, str] = {}
    for group in found.get("bookmark_groups", []) or []:
        if not isinstance(group, dict):
            continue
        gid = group.get("name", "")
        gname = group.get("displayName", gid)
        label = gname if isinstance(gname, str) else gid
        children = group.get("children", [])
        for child in children if isinstance(children, list) else []:
            if isinstance(child, dict) and child.get("name"):
                groups[child["name"]] = label
    facts = []
    issues = []
    for key in sorted(found.get("bookmarks", {}) or {}):
        doc = found["bookmarks"][key]
        name = doc.get("name") if isinstance(doc.get("name"), str) else key
        display = doc.get("displayName")
        options = doc.get("options", {})
        targets = options.get("targetVisualNames", []) if isinstance(
            options, dict) else []
        state = doc.get("explorationState", {})
        section = state.get("activeSection") if isinstance(state, dict) else None
        entities, malformed = _bookmark_filter_entities(doc)
        if malformed:
            issues.append({"rule": "bookmark_filters_unsupported",
                           "bookmark": name})
        facts.append({
            "id": name,
            "display_name": display if isinstance(display, str) else None,
            "target_visuals": targets if isinstance(targets, list) else [],
            "active_section": section if isinstance(section, str) else None,
            "filter_entities": entities,
            "group": groups.get(name)})
    return facts, issues


def _column_categories(model_dir: str) -> dict[tuple[str, str], str]:
    """Map (table, column) to TMDL dataCategory, exact and folded keys."""
    from vqs.data.tmdl import inventory_model

    categories: dict[tuple[str, str], str] = {}
    inventory = inventory_model(model_dir)
    for table, content in inventory.get("tables", {}).items():
        props = content.get("column_props", {})
        for column, values in props.items():
            found = values.get("dataCategory")
            if isinstance(found, str) and found.strip():
                value = found.strip().strip("'\"")
                categories[(table, column)] = value
                categories[(table.casefold(), column.casefold())] = value
    return categories


def _geometry(visual: dict) -> dict | None:
    """Position rect incl. z layer, or None when the visual proves none."""
    pos = visual.get("position", {})
    if not isinstance(pos, dict):
        return None
    rect = {key: _finite(pos.get(key)) for key in ("x", "y", "width", "height")}
    if any(v is None for v in rect.values()):
        return None
    if rect["width"] < 0 or rect["height"] < 0:
        return None
    z_value = _finite(pos.get("z"))
    rect["z"] = z_value if z_value is not None else 0.0
    return rect


def _page_size(page: dict) -> dict | None:
    width, height = _finite(page.get("width")), _finite(page.get("height"))
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
    label facts), ``layout`` (flat geometry list with z layers for the
    overlap rule), ``page_bounds`` (per-page sizes with member geometry),
    ``bookmarks`` (snapshot id, targets, active section, filter entities,
    group), per-page ``interactions`` (raw visualInteractions), and
    ``coverage`` (parse issues plus parsed counts; malformed files
    are skipped with issues, never silently and never crashing).
    ``filter_scopes`` carries visual/page/report valued-filter counts;
    ``valued_filters`` stays visual+page because a report-level filter
    restricts every visual equally and cannot differentiate a pair.
    Raises OSError when the report folder is unreadable.
    """
    import os

    from vqs.data.tmdl import split_table_field
    from vqs.pbir import read_report_files

    if not os.path.isdir(report_dir):
        raise OSError(f"report folder not found: {report_dir}")
    found = read_report_files(report_dir)
    if any(issue["rule"] == "report_unreadable" for issue in found["issues"]):
        raise OSError(f"report folder not found: {report_dir}")
    report_doc = found.get("report")
    report_filters = (_valued_filters_in(report_doc)
                      if isinstance(report_doc, dict) else 0)
    extra_issues: list[dict] = []
    categories = _column_categories(model_dir) if model_dir else {}
    known_tables = {table for table, _ in categories}
    pages = []
    visuals = []
    trees = []
    maps = []
    layout = []
    page_bounds = []
    for page_id in found["order"]:
        page = found["pages"].get(page_id)
        if page is None:
            continue
        display = page.get("displayName")
        page_filters = _valued_filters_in(page)
        entries = []
        for (pid, visual_id) in sorted(found["visuals"]):
            if pid != page_id:
                continue
            visual = found["visuals"][(pid, visual_id)]
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
            entry = {"visual": visual_id, "type": visual_type,
                     "title": _title(node), "measures": measures,
                     "dimensions": dimensions, "roles": roles,
                     "customized": isinstance(objects, dict)
                     and len(objects) > 0}
            entries.append(entry)
            rect = _geometry(visual)
            if rect is not None:
                layout.append({"page": page_id, "visual": visual_id,
                               "bound": bool(measures or dimensions), **rect})
            visual_filters = _valued_filters_in(visual)
            if measures or dimensions:
                visuals.append({"page": page_id, "visual": visual_id,
                                "type": visual_type, "measures": measures,
                                "dimensions": dimensions,
                                "valued_filters": visual_filters + page_filters,
                                "filter_scopes": {"visual": visual_filters,
                                                  "page": page_filters,
                                                  "report": report_filters}})
            # Tree/map classification is independent of parseable refs: a
            # tree or map with no bindings is a broken visual the rules
            # must see (missing_analyze / no_location_field), not a skip.
            folded = str(visual_type).casefold()
            if folded == TREE_TYPE:
                lowered = {role.casefold(): refs
                           for role, refs in roles.items()}
                trees.append({"page": page_id, "visual": visual_id,
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
                        table_guess, column_guess = split_table_field(
                            ref, {t: True for t in known_tables})
                        if table_guess and column_guess:
                            hit = categories.get((table_guess, column_guess))
                    if hit is None:
                        hit = categories.get(
                            (table.casefold(), column.casefold()))
                    resolved[ref] = hit
                maps.append({"page": page_id, "visual": visual_id,
                             "type": visual_type, "locations": locations,
                             "categories": resolved,
                             **_label_facts(node)})
        raw_interactions = page.get("visualInteractions", [])
        if raw_interactions is None:
            raw_interactions = []
        if not isinstance(raw_interactions, list):
            extra_issues.append({"rule": "interactions_unsupported",
                                 "page": page_id})
            raw_interactions = []
        pages.append({"page": page_id,
                      "display_name": display if isinstance(display, str)
                      else None,
                      "visuals": entries,
                      "interactions": raw_interactions})
        size = _page_size(page)
        members = [{"visual": v["visual"], "x": v["x"], "y": v["y"],
                    "width": v["width"], "height": v["height"]}
                   for v in layout if v["page"] == page_id]
        if members:
            # Pages without a measurable size stay in the list with null
            # bounds so the rule reports unknown instead of passing blind.
            size = size if size is not None else {"width": None,
                                                 "height": None}
            page_bounds.append({"page": page_id, **size,
                                "visuals": members})
    bookmark_facts, bookmark_issues = _bookmark_facts(found)
    coverage = {"issues": [*found["issues"], *extra_issues,
                              *bookmark_issues],
                "parsed_pages": len(pages),
                "parsed_visuals": sum(len(p["visuals"]) for p in pages)}
    return {"pages": pages, "visuals": visuals, "trees": trees,
            "maps": maps, "layout": layout, "page_bounds": page_bounds,
            "bookmarks": bookmark_facts, "coverage": coverage}
