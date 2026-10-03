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


def _contrast_pair(foreground: str, background: str, threshold: float) -> dict | None:
    """Evaluate one pair; None when the pair proves no luminance."""
    try:
        lighter, darker = sorted((_srgb_luminance(foreground), _srgb_luminance(background)), reverse=True)
    except ValueError:
        return None
    ratio = (lighter + 0.05) / (darker + 0.05)
    return {"ratio": round(ratio, 3), "passed": ratio >= threshold}


def text_contrast(foreground: str | None = None, background: str | None = None, *,
                  large_text: bool = False, readings: list[dict] | None = None) -> dict:
    """Compare resolved opaque colors to WCAG 2.2 SC 1.4.3 thresholds.

    With ``readings`` (every honestly-paired foreground/background run),
    majority and minority colors alike are evaluated: one failing pair
    fails the rule. Without readings, the legacy single pair applies.
    Passing this local calculation does not establish broader WCAG compliance.
    """
    rule = "typography.text_contrast"
    threshold = 3.0 if large_text else 4.5
    if readings is not None:
        if not isinstance(readings, list) or not readings:
            return _finding(rule, "unknown", reason="Measured contrast readings required")
        failures = []
        evaluated = 0
        for item in readings:
            if not isinstance(item, dict):
                return _finding(rule, "unknown", reason="Invalid contrast observation")
            pair = _contrast_pair(str(item.get("foreground", "")),
                                  str(item.get("background", "")), threshold)
            if pair is None:
                continue
            evaluated += 1
            if not pair["passed"]:
                failures.append({"foreground": item.get("foreground"),
                                 "background": item.get("background"),
                                 "page": item.get("page"), "role": item.get("role"),
                                 "count": item.get("count"), "ratio": pair["ratio"]})
        if not evaluated:
            return _finding(rule, "unknown", reason="No resolvable contrast pairs")
        return _finding(rule, "fail" if failures else "pass",
                        pairs=evaluated, failures=failures,
                        required_ratio=threshold)
    if foreground is None or background is None:
        return _finding(rule, "unknown", reason="Resolved colors are not both available")
    pair = _contrast_pair(foreground, background, threshold)
    if pair is None:
        return _finding(rule, "unknown", reason="Unresolved, invalid or translucent color")
    return _finding(rule, "pass" if pair["passed"] else "fail",
                    ratio=pair["ratio"], required_ratio=threshold,
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


def _grain_rows(visuals: Sequence[dict]) -> tuple[list[dict], str | None]:
    """Validate grain readings; return (rows, None) or ([], reason)."""
    rows = []
    for item in visuals:
        if not isinstance(item, dict):
            return [], "Invalid grain observation"
        page, visual, vtype = (item.get("page"), item.get("visual"),
                               item.get("type"))
        measures, dimensions = item.get("measures"), item.get("dimensions")
        filtered = item.get("valued_filters", 0)
        if not all(isinstance(v, str) and v for v in (page, visual, vtype)):
            return [], "page, visual, and type must be nonempty strings"
        if (not isinstance(measures, list) or not isinstance(dimensions, list)
                or not all(isinstance(m, str) for m in measures)
                or not all(isinstance(d, str) for d in dimensions)):
            return [], "measures and dimensions must be string lists"
        if not isinstance(filtered, int) or filtered < 0:
            return [], "valued_filters must be a non-negative int"
        rows.append({"page": page, "visual": visual, "type": vtype,
                     "measures": set(measures), "dimensions": set(dimensions),
                     "filtered": filtered})
    return rows, None


def _pair_kind(first: dict, second: dict, *, cross_page: bool) -> str | None:
    """Classify a measure-sharing pair, or None when clearly distinct.

    Cross-page pairs additionally require non-empty dimensions: a bare
    card repeated on another page is the summary pattern, not a
    duplicated breakdown.
    """
    if first["measures"] != second["measures"] or not first["measures"]:
        return None
    dims_a, dims_b = first["dimensions"], second["dimensions"]
    if dims_a == dims_b:
        if cross_page and not dims_a:
            return None
        return "same_grain"
    if dims_a < dims_b or dims_b < dims_a:
        if not (dims_a and dims_b):
            return None
        return "contained_grain"
    return None


def insight_no_duplicate_grain(visuals: Sequence[dict] | None) -> dict:
    """Two visuals on one page must not tell the same insight (INS-01).

    Each visual needs ``page``, ``visual``, ``type``, ``measures`` and
    ``dimensions`` (bound ``Entity.Property`` refs), and
    ``valued_filters`` (visual-level filters that may restrict rows).
    A pair fails when it carries an equal non-empty measure set and either the
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
    rows, error = _grain_rows(visuals)
    if error is not None:
        return _finding(rule, "unknown", reason=error)
    conflicts = []
    skipped_filtered = 0
    compared = 0
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            if first["page"] != second["page"]:
                continue
            compared += 1
            kind = _pair_kind(first, second, cross_page=False)
            if kind is None:
                continue
            if first["filtered"] or second["filtered"]:
                skipped_filtered += 1
                continue
            conflicts.append({"kind": kind, "page": first["page"],
                              "visuals": sorted([first["visual"],
                                                 second["visual"]]),
                              "types": sorted([first["type"], second["type"]]),
                              "measures": sorted(first["measures"]),
                              "dimensions": sorted(first["dimensions"]
                                                   | second["dimensions"])})
    return _finding(rule, "fail" if conflicts else "pass",
                    visuals=len(rows), pairs_compared=compared,
                    conflicts=conflicts,
                    skipped_filtered_pairs=skipped_filtered)


def decomposition_tree_dimensions(trees: Sequence[dict] | None) -> dict:
    """A decomposition tree must earn its depth (CHT-01).

    Each tree needs ``page``, ``visual``, ``analyze`` (measure refs),
    ``explain_by`` (dimension refs), and ``unrecognized_roles``. Fails
    when Analyze is empty (including trees with no bindings at all),
    when ExplainBy holds fewer than two distinct dimensions (a single
    breakdown is a bar chart's job, and one dimension cannot decompose),
    or when ExplainBy repeats a field. A tree whose non-empty query
    roles match neither Analyze nor ExplainBy is unknown -- its
    bindings cannot be proven. Proven fails win over unknowns.
    """
    rule = "chart.decomposition_tree_dimensions"
    if not trees:
        return _finding(rule, "unknown",
                         reason="Measured decomposition-tree bindings required")
    conflicts = []
    unverified = []
    for item in trees:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid tree observation")
        page, visual = item.get("page"), item.get("visual")
        analyze, explain = item.get("analyze"), item.get("explain_by")
        if not all(isinstance(v, str) and v for v in (page, visual)):
            return _finding(rule, "unknown",
                             reason="page and visual must be nonempty strings")
        if (not isinstance(analyze, list) or not isinstance(explain, list)
                or not all(isinstance(a, str) for a in analyze)
                or not all(isinstance(e, str) for e in explain)):
            return _finding(rule, "unknown",
                             reason="analyze and explain_by must be string lists")
        if item.get("unrecognized_roles"):
            unverified.append(f"{page}/{visual}")
            continue
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
    if conflicts:
        return _finding(rule, "fail", trees=len(trees), conflicts=conflicts,
                         unverified=sorted(unverified))
    if unverified:
        return _finding(rule, "unknown",
                         reason="Unrecognized tree query roles; bindings unproven",
                         trees=sorted(unverified))
    return _finding(rule, "pass", trees=len(trees))


_GEO_CATEGORIES = frozenset({
    "address", "city", "continent", "country", "county", "latitude",
    "longitude", "place", "postalcode", "stateorprovince",
})


def map_location_binding(maps: Sequence[dict] | None) -> dict:
    """A map must bind a location field, ideally a geographic one (CHT-02).

    Each map needs ``page``, ``visual``, ``type``, ``locations``
    (bound column refs), and ``categories`` (ref to TMDL dataCategory
    or null). Locations span every role's dimensions: role names vary
    across map types, so scoping to one role could miss the location.
    Fails when a map binds no column at all, or when every bound
    column carries a provably non-geographic data category. Maps with
    any geographic or uncategorized column -- or measured without a
    model -- are unknown or pass: geocoding by name may still resolve
    them.
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
        if (not isinstance(locations, list) or not isinstance(categories, dict)
                or not all(isinstance(ref, str) for ref in locations)):
            return _finding(rule, "unknown",
                             reason="locations must be a string list and "
                                    "categories an object")
        if not locations:
            conflicts.append({"kind": "no_location_field", "page": page,
                              "visual": visual, "type": vtype})
            continue
        known = [categories.get(ref) for ref in locations]
        if any(isinstance(cat, str) and cat.casefold() in _GEO_CATEGORIES
               for cat in known):
            continue
        if all(isinstance(cat, str) and cat
               and cat.casefold() not in _GEO_CATEGORIES for cat in known):
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


def insight_no_cross_page_duplicate_grain(
        visuals: Sequence[dict] | None) -> dict:
    """One breakdown must not repeat on another page (INS-02).

    Same readings as INS-01. A pair fails when two visuals on different
    pages carry an equal non-empty measure set and their dimension sets
    are equal (non-empty) or one strictly contains the other. Bare
    cards are exempt: a KPI repeated on an overview page is the summary
    pattern, not a duplicated breakdown. Value-filtered pairs are
    skipped, as in INS-01.
    """
    rule = "insight.no_cross_page_duplicate_grain"
    if not visuals:
        return _finding(rule, "unknown",
                         reason="Measured page-visual grain readings required")
    rows, error = _grain_rows(visuals)
    if error is not None:
        return _finding(rule, "unknown", reason=error)
    conflicts = []
    skipped_filtered = 0
    compared = 0
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            if first["page"] == second["page"]:
                continue
            compared += 1
            kind = _pair_kind(first, second, cross_page=True)
            if kind is None:
                continue
            if first["filtered"] or second["filtered"]:
                skipped_filtered += 1
                continue
            conflicts.append({"kind": kind,
                              "pages": sorted([first["page"],
                                               second["page"]]),
                              "visuals": sorted(
                                  [f"{first['page']}/{first['visual']}",
                                   f"{second['page']}/{second['visual']}"]),
                              "types": sorted([first["type"], second["type"]]),
                              "measures": sorted(first["measures"]),
                              "dimensions": sorted(first["dimensions"]
                                                   | second["dimensions"])})
    return _finding(rule, "fail" if conflicts else "pass",
                    visuals=len(rows), pairs_compared=compared,
                    conflicts=conflicts,
                    skipped_filtered_pairs=skipped_filtered)


def _geometry(item: dict) -> tuple[str, str, float, float, float, float, float, bool]:
    """Validate a positioned visual; raise ValueError(reason) if unusable.

    Returns (page, visual, x, y, width, height, z, bound). NaN/Infinity
    prove no geometry. ``z`` defaults to 0 and ``bound`` to True so
    readings without layer/binding facts keep the strict behavior.
    """
    page, visual = item.get("page"), item.get("visual")
    rect = [item.get(key) for key in ("x", "y", "width", "height")]
    if not all(isinstance(v, str) and v for v in (page, visual)):
        raise ValueError("page and visual must be nonempty strings")
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) for v in rect) or rect[2] < 0 or rect[3] < 0):
        raise ValueError("x, y, width, height must be finite numbers with "
                         "non-negative size")
    x, y, width, height = (float(v) for v in rect)
    raw_z = item.get("z", 0)
    z = float(raw_z) if isinstance(raw_z, (int, float)) and not isinstance(raw_z, bool) else 0.0
    bound = item.get("bound", True)
    return page, visual, x, y, width, height, z, bound is not False


def layout_no_visual_overlap(visuals: Sequence[dict] | None) -> dict:
    """Two visuals on one page must not overlap (LAY-01).

    Each visual needs ``page``, ``visual``, and numeric ``x``/``y``/
    ``width``/``height`` from PBIR positions. A pair fails when their
    rectangles intersect with positive area; edge-touching (zero area)
    passes. Intentional background layering is exempt: when the behind
    visual sits at a lower ``z``, fully contains the front visual, and
    binds no data (``bound`` false), the pair is skipped as background,
    never failed.
    """
    rule = "layout.no_visual_overlap"
    if not visuals:
        return _finding(rule, "unknown",
                         reason="Measured visual geometry required")
    rows = []
    for item in visuals:
        if not isinstance(item, dict):
            return _finding(rule, "unknown",
                             reason="Invalid geometry observation")
        try:
            rows.append(_geometry(item))
        except ValueError as exc:
            return _finding(rule, "unknown", reason=str(exc))
    conflicts = []
    compared = 0
    skipped_background = 0
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            if first[0] != second[0]:
                continue
            compared += 1
            left = max(first[2], second[2])
            top = max(first[3], second[3])
            right = min(first[2] + first[4], second[2] + second[4])
            bottom = min(first[3] + first[5], second[3] + second[5])
            if right > left and bottom > top:
                behind, front = (first, second) if first[6] < second[6] else (second, first)
                if (behind[6] != front[6] and not behind[7]
                        and behind[2] <= front[2] and behind[3] <= front[3]
                        and behind[2] + behind[4] >= front[2] + front[4]
                        and behind[3] + behind[5] >= front[3] + front[5]):
                    skipped_background += 1
                    continue
                conflicts.append({"page": first[0],
                                  "visuals": sorted([first[1], second[1]]),
                                  "overlap": {"x": left, "y": top,
                                              "width": right - left,
                                              "height": bottom - top}})
    return _finding(rule, "fail" if conflicts else "pass",
                    visuals=len(rows), pairs_compared=compared,
                    conflicts=conflicts,
                    skipped_background_pairs=skipped_background)


def layout_visuals_within_page(pages: Sequence[dict] | None) -> dict:
    """Every visual must fit inside its page (LAY-02).

    Each page needs ``page``, numeric ``width``/``height``, and
    ``visuals`` with ``visual``/``x``/``y``/``width``/``height``. A
    visual fails when any edge crosses the page bounds. Pages with
    missing size prove nothing and render the rule unknown unless a
    proven violation already fails it.
    """
    rule = "layout.visuals_within_page"
    if not pages:
        return _finding(rule, "unknown",
                         reason="Measured page bounds required")
    conflicts = []
    unverified = []
    for item in pages:
        if not isinstance(item, dict):
            return _finding(rule, "unknown",
                             reason="Invalid page-bounds observation")
        name, width, height = (item.get("page"), item.get("width"),
                               item.get("height"))
        members = item.get("visuals")
        if (not isinstance(name, str) or not name
                or not isinstance(members, list)):
            return _finding(rule, "unknown",
                             reason="page must be a string and visuals a list")
        if (not isinstance(width, (int, float))
                or not isinstance(height, (int, float))
                or isinstance(width, bool) or isinstance(height, bool)
                or not math.isfinite(width) or not math.isfinite(height)
                or width <= 0 or height <= 0):
            unverified.append(name)
            continue
        for member in members:
            if not isinstance(member, dict):
                return _finding(rule, "unknown",
                                 reason="Invalid geometry observation")
            try:
                _, visual, x, y, w, h, _, _ = _geometry(
                    {"page": name, **member})
            except ValueError as exc:
                return _finding(rule, "unknown", reason=str(exc))
            if x < 0 or y < 0 or x + w > width or y + h > height:
                conflicts.append({"kind": "outside_page", "page": name,
                                  "visual": visual,
                                  "rect": {"x": x, "y": y, "width": w,
                                           "height": h},
                                  "page_size": {"width": width,
                                                "height": height}})
    if conflicts:
        return _finding(rule, "fail", pages=len(pages), conflicts=conflicts,
                         unverified=sorted(unverified))
    if unverified:
        return _finding(rule, "unknown",
                         reason="Some pages lack a measurable size",
                         pages=sorted(unverified))
    return _finding(rule, "pass", pages=len(pages))


def chart_map_location_labels(maps: Sequence[dict] | None) -> dict:
    """A bubble map must label what its bubbles are (CHT-03).

    Each map needs ``page``, ``visual``, ``labels_shown`` (whether
    ``categoryLabels.show`` is true), and ``heatmap`` (whether a heatMap
    layer is configured, which encodes values without labels). A plain
    bubble map with no labels fails: unidentified bubbles are decoration.
    """
    rule = "chart.map_location_labels"
    if not maps:
        return _finding(rule, "unknown",
                         reason="Measured map label bindings required")
    conflicts = []
    for item in maps:
        if not isinstance(item, dict):
            return _finding(rule, "unknown", reason="Invalid map observation")
        page, visual = item.get("page"), item.get("visual")
        shown, heat = item.get("labels_shown"), item.get("heatmap")
        if not all(isinstance(v, str) and v for v in (page, visual)):
            return _finding(rule, "unknown",
                             reason="page and visual must be nonempty strings")
        if not isinstance(shown, bool) or not isinstance(heat, bool):
            return _finding(rule, "unknown",
                             reason="labels_shown and heatmap must be booleans")
        if not shown and not heat:
            conflicts.append({"kind": "unlabeled_map", "page": page,
                              "visual": visual})
    return _finding(rule, "fail" if conflicts else "pass",
                    maps=len(maps), conflicts=conflicts)
