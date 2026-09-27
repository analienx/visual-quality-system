"""PBIR/TMDL facts emitter (WP-19): read-only measurement, no renders.

`measure_report` walks a ``*.Report`` folder (plus an optional
``*.SemanticModel`` definition dir) and returns a facts document shaped
for `vqs check`: text contrast, metric units, TMDL bindings, and
format-declaration cohorts. Anything the sources cannot prove is
omitted — never inferred, never defaulted.

Known adapter gaps (omitted, not guessed): per-page series-color
assignments (a theme declares slot colors but never proves a page uses
a slot, so ``palette.semantic_consistency`` stays absent until explicit
per-visual series colors are measured); per-visual display-unit
overrides (units come from the model's ``formatString`` only).
"""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter
from typing import Any


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _walk(node: Any, path: str = "") -> Any:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def _theme(report_dir: str) -> dict | None:
    candidates = sorted(glob.glob(os.path.join(
        report_dir, "StaticResources", "RegisteredResources", "*.json")))
    for path in candidates:
        theme = _read_json(path)
        if theme and isinstance(theme.get("background"), str):
            return theme
    return None


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


def _page_background(page: dict, theme: dict | None) -> str | None:
    try:
        color = (page["objects"]["outspace"][0]["properties"]["color"]
                 ["solid"]["color"]["expr"]["Literal"]["Value"])
    except (KeyError, IndexError, TypeError):
        color = None
    if isinstance(color, str) and re.fullmatch(r"'#[0-9A-Fa-f]{6}'", color):
        return color.strip("'").upper()
    if theme is not None:
        fallback = str(theme.get("background", "")).upper()
        if re.fullmatch(r"#[0-9A-F]{6}", fallback):
            return fallback
    return None


def _page_text_colors(report_dir: str) -> dict[str, Counter]:
    """Map each page dir to its own (paragraph-index, color) counts.

    Colors stay scoped to the page that declares them: pairing page
    A's text with page B's background would invent evidence.
    """
    by_page: dict[str, Counter] = {}

    def visit(node: Any, colors: Counter) -> None:
        if isinstance(node, dict):
            paragraphs = node.get("paragraphs")
            if isinstance(paragraphs, list):
                for index, para in enumerate(paragraphs):
                    runs = para.get("textRuns") if isinstance(para, dict) else None
                    for run in runs or []:
                        if not isinstance(run, dict):
                            continue
                        style = run.get("textStyle") or {}
                        color = style.get("color") if isinstance(style, dict) else None
                        if isinstance(color, str):
                            colors[(index, color.upper())] += 1
            for value in node.values():
                visit(value, colors)
        elif isinstance(node, list):
            for value in node:
                visit(value, colors)

    for page in _pages(report_dir):
        colors: Counter = Counter()
        for visual in _visuals(report_dir, page["_dir"]):
            visit(visual.get("visual", {}).get("objects", {}), colors)
        by_page[page["_dir"]] = colors
    return by_page


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
              for v in rgb]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


def _ratio(foreground: str, background: str) -> float:
    first, second = sorted((_luminance(foreground), _luminance(background)),
                           reverse=True)
    return (first + 0.05) / (second + 0.05)


def _is_hex(color: str) -> bool:
    return re.fullmatch(r"#[0-9A-F]{6}", color) is not None


def _contrast(report_dir: str, theme: dict | None) -> dict | None:
    """Weakest honestly-paired (foreground, background) across pages.

    Non-hex text colors prove no luminance, so pairs using them are
    skipped instead of crashing the ratio math.
    """
    candidates = []
    all_colors = _page_text_colors(report_dir)
    for page in _pages(report_dir):
        colors = all_colors.get(page["_dir"]) or Counter()
        titles = Counter({c: n for (i, c), n in colors.items() if i == 0})
        subtitles = Counter({c: n for (i, c), n in colors.items() if i == 1})
        if not titles and not subtitles:
            continue
        background = _page_background(page, theme)
        if background is None:
            continue
        if titles:
            foreground = titles.most_common(1)[0][0]
            if _is_hex(foreground):
                candidates.append((foreground, background))
        if subtitles:
            foreground = subtitles.most_common(1)[0][0]
            if _is_hex(foreground):
                candidates.append((foreground, background))
    if not candidates:
        return None
    foreground, background = min(candidates, key=lambda pair: _ratio(*pair))
    return {"foreground": foreground, "background": background}


def _measure_formats(model_dir: str) -> dict[tuple[str, str], str]:
    formats: dict[tuple[str, str], str] = {}
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
        blocks = re.finditer(r"^\tmeasure ('([^']+)'|([^\s=]+)) =(.*?)(?=^\t\S|\Z)",
                             text, re.MULTILINE | re.DOTALL)
        for match in blocks:
            measure = match.group(2) or match.group(3)
            found = re.search(r"formatString: (.*)$", match.group(4), re.MULTILINE)
            value = found.group(1).strip() if found else ""
            formats[(name, measure)] = value
            formats[(name.casefold(), measure.casefold())] = value
    return formats


def _format_of(formats: dict[tuple[str, str], str], dotted: str) -> str:
    """Look up a PBIR Entity.Property ref, tolerating case drift."""
    key = tuple(dotted.split(".", 1))
    if len(key) != 2:
        return ""
    hit = formats.get(key)
    if hit is None:
        hit = formats.get((key[0].casefold(), key[1].casefold()), "")
    return hit


def _unit_of(format_string: str) -> str:
    """Classify only what the format string proves.

    A ``%`` scales the value (percent); anything else is carried
    through verbatim so regrouping stays exact without inventing
    currency codes, counts, or point semantics.
    """
    if not format_string:
        return "undeclared"
    if "%" in format_string:
        return "percent"
    return "raw:" + format_string


def _literal(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if len(text) >= 2 and text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)D", text)
    if match:
        number = float(match.group(1))
        return int(number) if number.is_integer() else number
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        number = float(text)
        return int(number) if number.is_integer() else number
    if text == "true":
        return True
    if text == "false":
        return False
    return text


def _bindings_and_cohorts(report_dir: str) -> tuple[list[dict], list[dict], list[dict]]:
    bindings: dict[str, dict] = {}
    units: list[dict] = []
    cohorts: dict[str, dict[str, Any]] = {}
    for page in _pages(report_dir):
        for visual in _visuals(report_dir, page["_dir"]):
            node = visual.get("visual", {})
            visual_type = node.get("visualType", "?")
            state = node.get("query", {}).get("queryState", {})
            for role, content in state.items() if isinstance(state, dict) else []:
                for projection in (content or {}).get("projections", []):
                    ref = projection.get("query_ref") or projection.get("queryRef")
                    if isinstance(ref, str) and ref and ref not in bindings:
                        bindings[ref] = {"query_ref": ref, "measure": None}
                    field = projection.get("field", {}).get("Measure", {})
                    entity = (field.get("Expression", {}).get("SourceRef", {})
                              or {}).get("Entity", "")
                    prop = field.get("Property", "")
                    if entity and prop:
                        units.append({"measure": f"{entity}.{prop}",
                                      "page": page["_dir"]})
            objects = node.get("objects", {})
            for path, value in _walk(objects):
                segments = [s.split("[")[0] for s in path.split("/") if s]
                if "Value" not in segments:
                    continue
                size = [s for s in segments if re.fullmatch(r"(fontSize|textSize)", s)]
                if not size:
                    continue
                owner = segments[0]
                cohort = f"{visual_type}/{owner}.{size[0]}"
                slot = cohorts.setdefault(cohort, {})
                slot[f'{page["_dir"]}/{visual["_id"]}'] = _literal(value)
    readings: list[dict] = []
    for cohort in sorted(cohorts):
        for key in sorted(cohorts[cohort]):
            page_id, visual_id = key.split("/", 1)
            readings.append({"cohort": cohort, "visual": visual_id,
                             "page": page_id, "value": cohorts[cohort][key]})
    return list(bindings.values()), units, readings


def _cohort_nulls(report_dir: str, readings: list[dict]) -> list[dict]:
    """Add explicit nulls where a declared owner leaves a property default.

    A null means "this visual declares the owner object (e.g. ``header``)
    but not the property", which the sources prove. Visuals without the
    owner object are not members — inventing nulls for them would fail
    cohorts over properties that never applied.
    """
    names = sorted({reading["cohort"] for reading in readings})
    nulls = []
    owners: dict[tuple[str, str, str], set[str]] = {}
    for page in _pages(report_dir):
        for visual in _visuals(report_dir, page["_dir"]):
            node = visual.get("visual", {})
            visual_type = node.get("visualType", "?")
            objects = node.get("objects", {})
            declared = set(objects) if isinstance(objects, dict) else set()
            owners[(visual_type, page["_dir"], visual["_id"])] = declared
    seen = {(r["cohort"], r["page"], r["visual"]) for r in readings}
    # Cohort ids embed "{visual_type}/{owner}.{prop}"; real PBIR
    # visualType values never contain "/", so partition is exact.
    for cohort in names:
        visual_type, _, rest = cohort.partition("/")
        owner, _, _prop = rest.rpartition(".")
        for (member_type, page_id, visual_id), declared in owners.items():
            if member_type != visual_type or owner not in declared:
                continue
            if (cohort, page_id, visual_id) not in seen:
                nulls.append({"cohort": cohort, "visual": visual_id,
                              "page": page_id, "value": None})
    return sorted(readings + nulls,
                  key=lambda item: (item["cohort"], item["page"], item["visual"]))


def measure_report(report_dir: str, model_dir: str | None = None) -> dict:
    """Measure check-ready facts for a PBIR report (plus optional model).

    Returns a facts document for `vqs check`. Rules the sources cannot
    prove are omitted. Raises OSError when the report folder is unreadable.
    """
    if not os.path.isdir(report_dir):
        raise OSError(f"report folder not found: {report_dir}")
    theme = _theme(report_dir)
    rules: dict[str, dict] = {}
    # Contrast is a theme rule: without a theme the color roles cannot
    # be proven, so it stays omitted. Palette assignments stay omitted
    # unconditionally — see the module docstring.
    contrast = _contrast(report_dir, theme) if theme is not None else None
    if contrast is not None:
        rules["typography.text_contrast"] = contrast
    bindings, unit_refs, cohort_readings = _bindings_and_cohorts(report_dir)
    cohorts = _cohort_nulls(report_dir, cohort_readings)
    if cohorts:
        rules["typography.format_declaration_consistency"] = {"readings": cohorts}
    facts: dict[str, Any] = {"rules": rules}
    from .insights import page_insights
    inventory = page_insights(report_dir, model_dir)
    facts["insights"] = {"pages": inventory["pages"]}
    if inventory["visuals"]:
        rules["insight.no_duplicate_grain"] = {"visuals": inventory["visuals"]}
        rules["insight.no_cross_page_duplicate_grain"] = {
            "visuals": inventory["visuals"]}
    if inventory["layout"]:
        rules["layout.no_visual_overlap"] = {"visuals": inventory["layout"]}
    if inventory["page_bounds"]:
        rules["layout.visuals_within_page"] = {
            "pages": inventory["page_bounds"]}
    if inventory["trees"]:
        rules["chart.decomposition_tree_dimensions"] = {
            "trees": inventory["trees"]}
    if inventory["maps"]:
        rules["chart.map_location_binding"] = {"maps": inventory["maps"]}
        rules["chart.map_location_labels"] = {"maps": [
            {"page": m["page"], "visual": m["visual"],
             "labels_shown": m["labels_shown"], "heatmap": m["heatmap"]}
            for m in inventory["maps"]]}
    if model_dir is not None:
        formats = _measure_formats(model_dir)
        readings = [{"measure": ref["measure"],
                     "unit": _unit_of(_format_of(formats, ref["measure"])),
                     "page": ref["page"]} for ref in unit_refs]
        if readings:
            facts["rules"]["encoding.metric_unit_consistency"] = {"readings": readings}
        ordered = sorted(bindings, key=lambda item: item["query_ref"])
        facts["models"] = [{"model_dir": model_dir,
                            "bindings": [{"query_ref": b["query_ref"]}
                                         for b in ordered]}]
    return facts
