"""Measured, pure design rules. Never fabricate unavailable rendered/data values.

Input facts must come from a separately verified data/render/format adapter.
These are narrow building blocks, not an overall dashboard-design verdict.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def _finding(rule: str, status: str, **evidence: object) -> dict:
    if status not in {"pass", "fail", "unknown"}:
        raise ValueError("Invalid rule status")
    return {"rule_id": rule, "status": status, "evidence": evidence}


def axis_display_distinctness(
    numeric_ticks: Sequence[float] | None, displayed_labels: Sequence[str] | None,
) -> dict:
    """Detect distinct numeric tick positions with identical *actually rendered* labels."""
    rule = "axis.display_values_not_distinct"
    if numeric_ticks is None or displayed_labels is None:
        return _finding(rule, "unknown", reason="Numerical tick values and rendered labels must both be measured")
    if len(numeric_ticks) != len(displayed_labels) or len(numeric_ticks) < 2:
        return _finding(rule, "unknown", reason="Insufficient paired tick observations")
    if (any(not isinstance(n, (int, float)) or not math.isfinite(n) for n in numeric_ticks) or
            any(not isinstance(s, str) or not s.strip() for s in displayed_labels)):
        return _finding(rule, "unknown", reason="Invalid or missing tick observations")
    collisions = []
    for i, (number, label) in enumerate(zip(numeric_ticks, displayed_labels, strict=True)):
        for j in range(i):
            if numeric_ticks[j] != number and displayed_labels[j].strip() == label.strip():
                collisions.append({"indices": [j, i], "numeric_ticks": [numeric_ticks[j], number],
                                   "displayed_label": label})
    return _finding(rule, "fail" if collisions else "pass",
                    tick_count=len(numeric_ticks), collisions=collisions)


def _srgb_luminance(hex_color: str) -> float:
    if not isinstance(hex_color, str) or len(hex_color) != 7 or hex_color[0] != "#":
        raise ValueError("Expected opaque #RRGGBB color")
    try:
        rgb = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    except ValueError as exc:
        raise ValueError("Expected opaque #RRGGBB color") from exc
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
              for value in rgb]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def text_contrast(foreground: str | None, background: str | None, *, large_text: bool = False) -> dict:
    """Compare two fully resolved opaque colors to WCAG 2.2 SC 1.4.3 thresholds.

    Passing this local calculation does not establish broader WCAG compliance.
    """
    rule = "typography.text_contrast"
    if foreground is None or background is None:
        return _finding(rule, "unknown", reason="Resolved colors are not both available")
    try:
        lighter, darker = sorted((_srgb_luminance(foreground), _srgb_luminance(background)), reverse=True)
    except ValueError:
        return _finding(rule, "unknown", reason="Unresolved, invalid or translucent color")
    ratio = (lighter + 0.05) / (darker + 0.05)
    threshold = 3.0 if large_text else 4.5
    return _finding(rule, "pass" if ratio >= threshold else "fail",
                    ratio=round(ratio, 3), required_ratio=threshold,
                    foreground=foreground, background=background, large_text=large_text)


def category_axis_space(label_widths_px: Sequence[float] | None,
                        available_width_px: float | None, *, gap_px: float = 8) -> dict:
    """A conservative label-space budget for a *specified* horizontal category axis.

    The caller must measure label widths at actual effective font and report zoom.
    Rotation, responsive layout or skipped ticks require a separate adapter.
    """
    rule = "axis.category_label_space"
    if label_widths_px is None or available_width_px is None or not label_widths_px:
        return _finding(rule, "unknown", reason="Measured label widths and plot width required")
    widths = list(label_widths_px)
    values = [*widths, available_width_px, gap_px]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return _finding(rule, "unknown", reason="Invalid layout measurements")
    if any(width <= 0 for width in widths) or available_width_px <= 0 or gap_px < 0:
        return _finding(rule, "unknown", reason="Invalid plot or label geometry")
    required = sum(widths) + gap_px * (len(widths) - 1)
    return _finding(rule, "pass" if required <= available_width_px else "fail",
                    labels=len(widths), required_px=round(required, 2), available_px=available_width_px,
                    assumptions="All labels visible, horizontal, nonoverlapping, measured at target zoom")


def palette_semantic_consistency(
    assignments: Sequence[dict] | None, declared_overrides: Sequence[str] | None = None,
) -> dict:
    """One state must keep one color across pages unless an override is declared.

    Each assignment needs ``state``, ``color`` (resolved opaque literal), and
    ``page``. DES-04: unexplained cross-page recoloring of the same state fails.
    """
    rule = "palette.semantic_consistency"
    overrides = set(declared_overrides or [])
    if not assignments:
        return _finding(rule, "unknown", reason="Measured state-color-page assignments required")
    by_state: dict[str, dict[str, str]] = {}
    for item in assignments:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid assignment observation")
        state, color, page = item.get("state"), item.get("color"), item.get("page")
        if not all(isinstance(v, str) and v for v in (state, color, page)):
            return _finding(rule, "unknown", reason="state, color, and page must be nonempty strings")
        by_state.setdefault(state, {})[color] = page
    conflicts = [
        {"state": state, "colors": sorted(pages), "pages": [pages[c] for c in sorted(pages)]}
        for state, pages in by_state.items()
        if len(pages) > 1 and state not in overrides
    ]
    return _finding(rule, "fail" if conflicts else "pass",
                    states=len(by_state), conflicts=conflicts,
                    overrides=sorted(overrides))


def format_declaration_consistency(readings: Sequence[dict] | None) -> dict:
    """One cohort of visuals must declare one formatting value (DES-06).

    Each reading needs ``cohort`` (visual type + property, e.g.
    ``"slicer/header.textSize"``), ``visual``, ``page``, and ``value`` —
    the declared literal, or null when the visual leaves the property
    to the theme default. A cohort fails when declarations are mixed
    (some visuals override while others inherit) or disagree; an
    all-default cohort passes. Effective rendered values are NOT
    inferred here — resolving the default needs a render adapter.
    """
    rule = "typography.format_declaration_consistency"
    if not readings:
        return _finding(rule, "unknown",
                         reason="Measured cohort format readings required")
    by_cohort: dict[str, dict[str, list[str]]] = {}
    for item in readings:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid format observation")
        cohort = item.get("cohort")
        visual, page = item.get("visual"), item.get("page")
        if not all(isinstance(v, str) and v for v in (cohort, visual, page)):
            return _finding(rule, "unknown",
                             reason="cohort, visual, and page must be nonempty strings")
        if "value" not in item:
            return _finding(rule, "unknown", reason="reading needs a value key")
        value = item["value"]
        if value is not None and not isinstance(value, (str, int, float, bool)):
            return _finding(rule, "unknown", reason="value must be a literal or null")
        slot = by_cohort.setdefault(cohort, {"declared": [], "visuals": []})
        slot["visuals"].append(f"{page}/{visual}")
        if value is not None:
            slot["declared"].append(str(value))
    conflicts = []
    for cohort, slot in by_cohort.items():
        distinct = sorted(set(slot["declared"]))
        if 0 < len(slot["declared"]) < len(slot["visuals"]):
            conflicts.append({"cohort": cohort, "kind": "mixed_declaration",
                              "declared": distinct, "visuals": slot["visuals"]})
        elif len(distinct) > 1:
            conflicts.append({"cohort": cohort, "kind": "divergent_values",
                              "declared": distinct, "visuals": slot["visuals"]})
    return _finding(rule, "fail" if conflicts else "pass",
                    cohorts=len(by_cohort), conflicts=conflicts)


def cross_page_metric_units(readings: Sequence[dict] | None) -> dict:
    """One measure must keep one unit across pages (DES-05 encoding truth).

    Each reading needs ``measure``, ``unit``, and ``page``. A plausible chart
    with a changed denominator or unit is a semantic finding, never cosmetic.
    """
    rule = "encoding.metric_unit_consistency"
    if not readings:
        return _finding(rule, "unknown", reason="Measured measure-unit-page readings required")
    by_measure: dict[str, set[str]] = {}
    for item in readings:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid unit observation")
        measure, unit = item.get("measure"), item.get("unit")
        if not all(isinstance(v, str) and v for v in (measure, unit)):
            return _finding(rule, "unknown", reason="measure and unit must be nonempty strings")
        by_measure.setdefault(measure, set()).add(unit)
    conflicts = [
        {"measure": measure, "units": sorted(units)}
        for measure, units in by_measure.items() if len(units) > 1
    ]
    return _finding(rule, "fail" if conflicts else "pass",
                    measures=len(by_measure), conflicts=conflicts)


def insight_no_duplicate_grain(visuals: Sequence[dict] | None) -> dict:
    """Two visuals on one page must not tell the same insight (INS-01).

    Each visual needs ``page``, ``visual``, ``type``, ``measures`` and
    ``dimensions`` (bound ``Entity.Property`` refs), and
    ``valued_filters`` (visual-level filters that may restrict rows).
    A pair fails when it shares a non-empty measure set and either the
    dimension sets are equal (same grain -- including twin cards) or one
    strictly contains the other with a non-empty smaller side (a map of
    sales by region inside a tree rooted at sales by region). Pairs
    where either side carries value-bearing filters are skipped: the
    filters may differentiate the numbers, so sameness is unproven.
    """
    rule = "insight.no_duplicate_grain"
    if not visuals:
        return _finding(rule, "unknown",
                         reason="Measured page-visual grain readings required")
    rows = []
    for item in visuals:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid grain observation")
        page, visual, vtype = (item.get("page"), item.get("visual"),
                               item.get("type"))
        measures, dimensions = item.get("measures"), item.get("dimensions")
        filtered = item.get("valued_filters", 0)
        if not all(isinstance(v, str) and v for v in (page, visual, vtype)):
            return _finding(rule, "unknown",
                             reason="page, visual, and type must be nonempty strings")
        if (not isinstance(measures, list) or not isinstance(dimensions, list)
                or not all(isinstance(m, str) for m in measures)
                or not all(isinstance(d, str) for d in dimensions)):
            return _finding(rule, "unknown",
                             reason="measures and dimensions must be string lists")
        if not isinstance(filtered, int) or filtered < 0:
            return _finding(rule, "unknown",
                             reason="valued_filters must be a non-negative int")
        rows.append({"page": page, "visual": visual, "type": vtype,
                     "measures": set(measures), "dimensions": set(dimensions),
                     "filtered": filtered})
    conflicts = []
    skipped_filtered = 0
    compared = 0
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            if first["page"] != second["page"]:
                continue
            compared += 1
            if first["measures"] != second["measures"] or not first["measures"]:
                continue
            if first["filtered"] or second["filtered"]:
                skipped_filtered += 1
                continue
            dims_a, dims_b = first["dimensions"], second["dimensions"]
            if dims_a == dims_b:
                kind = "same_grain"
            elif dims_a < dims_b or dims_b < dims_a:
                if not (dims_a and dims_b):
                    continue
                kind = "contained_grain"
            else:
                continue
            conflicts.append({"kind": kind, "page": first["page"],
                              "visuals": sorted([first["visual"],
                                                 second["visual"]]),
                              "types": sorted([first["type"], second["type"]]),
                              "measures": sorted(first["measures"]),
                              "dimensions": sorted(dims_a | dims_b)})
    return _finding(rule, "fail" if conflicts else "pass",
                    visuals=len(rows), pairs_compared=compared,
                    conflicts=conflicts,
                    skipped_filtered_pairs=skipped_filtered)


def decomposition_tree_dimensions(trees: Sequence[dict] | None) -> dict:
    """A decomposition tree must earn its depth (CHT-01).

    Each tree needs ``page``, ``visual``, ``analyze`` (measure refs),
    ``explain_by`` (dimension refs), and ``unrecognized_roles``. Fails
    when Analyze is empty, when ExplainBy holds fewer than two distinct
    dimensions (a single breakdown is a bar chart's job, and one
    dimension cannot decompose), or when ExplainBy repeats a field. A
    tree whose query roles match neither Analyze nor ExplainBy is
    unknown -- its bindings cannot be proven.
    """
    rule = "chart.decomposition_tree_dimensions"
    if not trees:
        return _finding(rule, "unknown",
                         reason="Measured decomposition-tree bindings required")
    conflicts = []
    for item in trees:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid tree observation")
        page, visual = item.get("page"), item.get("visual")
        analyze, explain = item.get("analyze"), item.get("explain_by")
        if not all(isinstance(v, str) and v for v in (page, visual)):
            return _finding(rule, "unknown",
                             reason="page and visual must be nonempty strings")
        if not isinstance(analyze, list) or not isinstance(explain, list):
            return _finding(rule, "unknown",
                             reason="analyze and explain_by must be lists")
        if item.get("unrecognized_roles"):
            return _finding(rule, "unknown",
                             reason="Unrecognized tree query roles; bindings unproven")
        if not analyze:
            conflicts.append({"kind": "missing_analyze", "page": page,
                              "visual": visual})
            continue
        distinct = []
        for ref in explain:
            if ref not in distinct:
                distinct.append(ref)
        if len(distinct) < len(explain):
            conflicts.append({"kind": "duplicate_dimension", "page": page,
                              "visual": visual, "explain_by": list(explain)})
        if len(distinct) < 2:
            conflicts.append({"kind": "too_few_dimensions", "page": page,
                              "visual": visual,
                              "distinct_dimensions": len(distinct)})
    return _finding(rule, "fail" if conflicts else "pass",
                    trees=len(trees), conflicts=conflicts)


_GEO_CATEGORIES = frozenset({
    "address", "city", "continent", "country", "county", "latitude",
    "longitude", "place", "postalcode", "stateorprovince",
})


def map_location_binding(maps: Sequence[dict] | None) -> dict:
    """A map must bind a location field, ideally a geographic one (CHT-02).

    Each map needs ``page``, ``visual``, ``type``, ``locations``
    (bound column refs), and ``categories`` (ref to TMDL dataCategory
    or null). Fails when a map binds no column at all, or when every
    bound column carries a provably non-geographic data category. Maps
    on uncategorized columns -- or measured without a model -- are
    unknown: geocoding by name may still resolve them.
    """
    rule = "chart.map_location_binding"
    if not maps:
        return _finding(rule, "unknown",
                         reason="Measured map location bindings required")
    conflicts = []
    unverified = []
    for item in maps:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid map observation")
        page, visual, vtype = (item.get("page"), item.get("visual"),
                               item.get("type"))
        locations, categories = item.get("locations"), item.get("categories")
        if not all(isinstance(v, str) and v for v in (page, visual, vtype)):
            return _finding(rule, "unknown",
                             reason="page, visual, and type must be nonempty strings")
        if not isinstance(locations, list) or not isinstance(categories, dict):
            return _finding(rule, "unknown",
                             reason="locations must be a list and categories an object")
        if not locations:
            conflicts.append({"kind": "no_location_field", "page": page,
                              "visual": visual, "type": vtype})
            continue
        known = [categories.get(ref) for ref in locations]
        if any(isinstance(cat, str) and cat.casefold() in _GEO_CATEGORIES
               for cat in known):
            continue
        if any(isinstance(cat, str) and cat for cat in known):
            conflicts.append({"kind": "non_geographic_binding", "page": page,
                              "visual": visual, "type": vtype,
                              "locations": list(locations),
                              "categories": {ref: categories.get(ref)
                                             for ref in locations}})
        else:
            unverified.append(f"{page}/{visual}")
    if conflicts:
        return _finding(rule, "fail", maps=len(maps), conflicts=conflicts,
                         unverified=sorted(unverified))
    if unverified:
        return _finding(rule, "unknown",
                         reason="Some maps bind uncategorized columns; "
                                "geographic fit unproven",
                         maps=sorted(unverified))
    return _finding(rule, "pass", maps=len(maps))
