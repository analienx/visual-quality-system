"""Adaptive Light/Dark PBIP theme engine (issue #80).

Stdlib-only, candidate-only, path/property-aware re-theming. Preview and
apply share one planner (:func:`build_plan`), so a previewed plan is
exactly what apply writes. Role is derived from the JSON path and visual
type, never from the old hex alone: the same ``#FFFFFF`` in a surface
role and in a text-on-accent role maps to different targets.
"""
from __future__ import annotations

import hashlib
import importlib.resources
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .series_readability import categorical_series_findings

SCHEMA_VERSION = "vqs.theme/1"
THEME_SCHEMA = (
    "https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/"
    "main/Report%20Theme%20JSON%20Schema/reportThemeSchema-2.159.json"
)
HEX_RE = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8}|[0-9A-Fa-f]{3})\b")
HEX_FULL = re.compile(r"#(?:[0-9A-Fa-f]{6})")

REQUIRED_ROLES: tuple[str, ...] = (
    "canvas", "surface", "surfaceElevated", "foreground",
    "mutedForeground", "subtleText", "outline", "gridline", "accent",
    "accentForeground", "selection", "selectionForeground",
    "slicerBackground", "tableHeader", "rowAlternate", "tooltip",
    "good", "neutral", "bad", "gradientMin", "gradientCenter",
    "gradientMax",
)

_LIGHT: dict[str, Any] = {
    "canvas": "#E9EEF4", "surface": "#FFFFFF",
    "surfaceElevated": "#F8FAFC", "foreground": "#0F1626",
    "mutedForeground": "#475569", "subtleText": "#5B6B82",
    "outline": "#64748B", "gridline": "#CBD5E1", "accent": "#1D4ED8",
    "accentForeground": "#FFFFFF", "selection": "#1D4ED8",
    "selectionForeground": "#FFFFFF", "slicerBackground": "#FFFFFF",
    "slicerForeground": "#0F1626", "tableHeader": "#1E3A5F",
    "tableHeaderForeground": "#FFFFFF", "rowAlternate": "#F1F5F9",
    "tooltip": "#0F1626", "tooltipForeground": "#FFFFFF",
    "dataColors": ["#2563EB", "#0E7490", "#047857", "#B45309",
                   "#BE123C", "#6D28D9", "#0F766E", "#9D174D"],
    "good": "#047857", "neutral": "#B45309", "bad": "#BE123C",
    "gradientMin": "#DBEAFE", "gradientCenter": "#2563EB",
    "gradientMax": "#1E3A5F",
}
_DARK: dict[str, Any] = {
    "canvas": "#0B1220", "surface": "#111C2E",
    "surfaceElevated": "#1A2A44", "foreground": "#F1F5F9",
    "mutedForeground": "#CBD5E1", "subtleText": "#A8B8CC",
    "outline": "#64748B", "gridline": "#334155", "accent": "#60A5FA",
    "accentForeground": "#0B1220", "selection": "#1D4ED8",
    "selectionForeground": "#FFFFFF", "slicerBackground": "#111C2E",
    "slicerForeground": "#F1F5F9", "tableHeader": "#1E3A5F",
    "tableHeaderForeground": "#F1F5F9", "rowAlternate": "#16233A",
    "tooltip": "#F1F5F9", "tooltipForeground": "#0B1220",
    # IBM Carbon-inspired dark categorical ordering; use differentiated
    # hues while preserving soft, legible chrome. Values are an adaptation,
    # not a claim that IBM published this exact color combination.
    "dataColors": ["#78A9FF", "#3DDBD9", "#BE95FF", "#FFB784",
                   "#FF7EB6", "#A7F0BA", "#F1C21B", "#82CFFF"],
    "good": "#34D399", "neutral": "#FBBF24", "bad": "#FB7185",
    # Increasing luminance for numeric gradients; never map categories to
    # a sequential ramp, and never change conditional red/green rules.
    "gradientMin": "#46688D", "gradientCenter": "#76A9D8",
    "gradientMax": "#C5E0F7",
}
BUILTIN_PALETTES: dict[str, dict[str, dict[str, Any]]] = {
    "executive-blue": {"light": _LIGHT, "dark": _DARK},
}
PALETTE_PRESETS = ("executive-blue", "graphite-mint",
                   "warm-basalt", "slate-lavender",
                   "okabe-ito-night",
                   "petrol-gold",
                   "indigo-ember",
                   "arctic-aurora",
                   "mediterranean-terra",
                   "saffron-spruce",
                   "autumn-editorial",
                   "violet-ice",
                   "electric-atelier",
                   "riviera-pop",
                   "bold-eclectic",
                   "graphite-red",
                   "organic-palette",
                   "sunny-palette",
)


def palette_presets() -> tuple[str, ...]:
    return PALETTE_PRESETS


def _preset_override(preset: str, mode: str) -> dict[str, Any]:
    if preset == "executive-blue":
        return {}
    # Existing dark-only colorways remain backwards compatible. Newly
    # approved dual-mode families are packaged as self-contained resources.
    filename = (f"dark-{preset}.json" if preset in (
        "graphite-mint", "warm-basalt", "slate-lavender")
        else f"preset-{preset}.json")
    resource = importlib.resources.files("vqs").joinpath(
        "palettes", filename)
    try:
        doc = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, ValueError, ModuleNotFoundError) as exc:
        raise ThemeError(f"packaged palette preset {preset!r} unavailable") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get(mode, {}), dict):
        raise ThemeError("invalid bundled palette preset")
    return doc.get(mode, {})


SUPPORTED_TYPES = frozenset({
    "slicer", "filterSlicer", "card",
    "multiRowCard", "kpi", "textbox", "shape",
    "basicShape", "tableEx", "pivotTable", "barChart", "columnChart",
    "lineChart", "areaChart", "comboChart", "donutChart", "pieChart",
    "scatterChart", "clusteredBarChart", "clusteredColumnChart",
    "stackedBarChart", "stackedColumnChart", "waterfallChart",
    "funnel", "gauge", "treemap", "map", "filledMap", "shapeMap",
    "azureMap", "ribbonChart", "lineStackedColumnComboChart",
    "lineClusteredColumnComboChart", "multiRowCardVisual", "image",
    "button", "actionButton",
})
SLICER_TYPES = frozenset({"slicer", "filterSlicer", "advancedSlicerVisual"})
CARD_TYPES = frozenset({"card", "cardVisual", "multiRowCard", "kpi"})
TABLE_TYPES = frozenset({"tableEx", "pivotTable"})
CHART_TYPES = SUPPORTED_TYPES - SLICER_TYPES - CARD_TYPES - TABLE_TYPES - {
    "textbox", "shape", "basicShape", "image", "button", "actionButton",
    "azureMap", "map", "filledMap", "shapeMap",
}
MAP_TYPES = frozenset({"azureMap", "map", "filledMap", "shapeMap"})


class ThemeError(ValueError):
    """Blocked theme operation; callers map it to exit 2."""


# ---------------------------------------------------------------- palette
def _valid_hex(value: object) -> bool:
    return isinstance(value, str) and HEX_FULL.fullmatch(value.strip()) is not None


def _norm_hex(value: str) -> str:
    return "#" + value.strip().lstrip("#").upper()


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a ``#RRGGBB`` color."""
    text = hex_color.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ThemeError(f"not a #RRGGBB color: {hex_color!r}")

    def channel(raw: int) -> float:
        srgb = raw / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    red = channel(int(text[0:2], 16))
    green = channel(int(text[2:4], 16))
    blue = channel(int(text[4:6], 16))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two ``#RRGGBB`` colors."""
    lum_a = relative_luminance(first)
    lum_b = relative_luminance(second)
    high, low = max(lum_a, lum_b), min(lum_a, lum_b)
    return (high + 0.05) / (low + 0.05)


_CONTRAST_PAIRS: tuple[tuple[str, str, float, str], ...] = (
    ("foreground", "canvas", 4.5, "normal"),
    ("foreground", "surface", 4.5, "normal"),
    ("foreground", "surfaceElevated", 4.5, "normal"),
    ("mutedForeground", "surface", 4.5, "normal"),
    ("mutedForeground", "canvas", 4.5, "normal"),
    ("subtleText", "surface", 4.5, "normal"),
    ("accentForeground", "accent", 4.5, "normal"),
    ("selectionForeground", "selection", 4.5, "normal"),
    ("slicerForeground", "slicerBackground", 4.5, "normal"),
    ("tableHeaderForeground", "tableHeader", 4.5, "normal"),
    ("tooltipForeground", "tooltip", 4.5, "normal"),
    ("outline", "surface", 3.0, "control"),
    ("outline", "canvas", 3.0, "control"),
)


def palette_contrast_check(palette: dict[str, Any]) -> list[dict[str, Any]]:
    """Fail-closed WCAG self-check; unknown colors are violations."""
    violations: list[dict[str, Any]] = []
    for fg_role, bg_role, minimum, kind in _CONTRAST_PAIRS:
        fg = palette.get(fg_role)
        bg = palette.get(bg_role)
        if not _valid_hex(fg) or not _valid_hex(bg):
            violations.append({"foreground": fg_role, "background": bg_role,
                               "ratio": None, "required": minimum,
                               "kind": kind, "status": "unknown"})
            continue
        ratio = contrast_ratio(str(fg), str(bg))
        if ratio + 1e-9 < minimum:
            violations.append({"foreground": fg_role, "background": bg_role,
                               "ratio": round(ratio, 3), "required": minimum,
                               "kind": kind, "status": "fail"})
    return violations


def load_palette(mode: str, palette_path: Path | None,
                 preset: str = "executive-blue") -> dict[str, Any]:
    """Resolve the effective palette for ``mode`` (builtin + custom merge)."""
    if mode not in ("light", "dark"):
        raise ThemeError(f"mode must be light or dark, not {mode!r}")
    if preset not in PALETTE_PRESETS:
        raise ThemeError("unknown preset: " + preset)
    if palette_path is not None and preset != "executive-blue":
        raise ThemeError("cannot combine --palette and --palette-preset")
    base = BUILTIN_PALETTES["executive-blue"][mode]
    palette: dict[str, Any] = json.loads(json.dumps(base))
    palette.update(_preset_override(preset, mode))
    if palette_path is not None:
        try:
            raw = json.loads(Path(palette_path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ThemeError(f"palette unreadable: {exc}") from exc
        if not isinstance(raw, dict):
            raise ThemeError("palette must be a JSON object")
        section: Any = raw
        if isinstance(raw.get("modes"), dict):
            section = raw["modes"].get(mode, {})
        elif "light" in raw or "dark" in raw:
            section = raw.get(mode, {})
        if not isinstance(section, dict):
            raise ThemeError(f"palette section for mode {mode!r} must be an object")
        allowed_roles = set(base)
        unexpected = set(section) - allowed_roles
        if unexpected:
            raise ThemeError("unknown palette roles: " + ", ".join(sorted(unexpected)))
        for key, value in section.items():
            if key == "dataColors":
                if (not isinstance(value, list) or len(value) < 8
                        or not all(_valid_hex(item) for item in value)):
                    raise ThemeError(
                        "palette dataColors must be >=8 #RRGGBB hex strings")
                palette[key] = [_norm_hex(str(item)) for item in value]
            elif isinstance(value, str):
                if not _valid_hex(value):
                    raise ThemeError(f"palette role {key!r} is not #RRGGBB: {value!r}")
                palette[key] = _norm_hex(value)
            else:
                raise ThemeError(f"palette role {key!r} must be a hex string")
    for role in REQUIRED_ROLES:
        if role == "dataColors":
            continue
        if not _valid_hex(palette.get(role)):
            raise ThemeError(f"palette missing/invalid required role {role!r}")
    colors = palette.get("dataColors")
    if (not isinstance(colors, list) or len(colors) < 8
            or not all(_valid_hex(item) for item in colors)):
        raise ThemeError("palette dataColors must be >=8 #RRGGBB hex strings")
    palette["dataColors"] = [_norm_hex(str(item)) for item in colors]
    # New approved presets must pass the categorical perceptual screen when
    # loaded, not only in test fixtures. Legacy palettes retain compatibility;
    # arbitrary imported customer palettes are analyzed via vqs premium.
    if preset in PALETTE_PRESETS[4:] and palette_path is None:
        weaknesses = categorical_series_findings(palette["dataColors"][:8])
        if weaknesses:
            raise ThemeError(
                "approved preset categorical series are insufficiently "
                "distinguishable: " + json.dumps(weaknesses[:3]))
    for role in REQUIRED_ROLES:
        if role != "dataColors":
            palette[role] = _norm_hex(str(palette[role]))
    for extra in ("slicerForeground", "tableHeaderForeground",
                  "tooltipForeground"):
        if not _valid_hex(palette.get(extra)):
            palette[extra] = palette["foreground"]
        else:
            palette[extra] = _norm_hex(str(palette[extra]))
    return palette


def palette_hash(palette: dict[str, Any]) -> str:
    canonical = json.dumps(palette, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def palette_canonical(palette: dict[str, Any]) -> str:
    return json.dumps(palette, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------- resolution
def resolve_report_dir(report: str | Path) -> Path:
    """Resolve a ``.Report`` dir or ``.pbip`` file to the ``.Report`` dir."""
    path = Path(report)
    if path.is_file() and path.suffix.lower() == ".pbip":
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict):
            for artifact in doc.get("artifacts", []) or []:
                if isinstance(artifact, dict):
                    rel = (artifact.get("report") or {}).get("path")
                    if isinstance(rel, str) and rel:
                        candidate = (path.parent / rel).resolve()
                        if not candidate.is_relative_to(path.parent.resolve()):
                            raise ThemeError("PBIP report path escapes its project")
                        if candidate.is_dir() and candidate.name.endswith(".Report"):
                            return candidate
                        raise ThemeError("PBIP references a missing Report directory")
        siblings = sorted(p for p in path.parent.iterdir()
                          if p.is_dir() and p.name.endswith(".Report"))
        if len(siblings) == 1:
            return siblings[0]
        raise ThemeError(f"cannot resolve a unique .Report beside {path}")
    if path.is_dir() and (path / "definition" / "report.json").is_file():
        return path
    if path.is_dir():
        siblings = sorted(p for p in path.iterdir()
                          if p.is_dir() and p.name.endswith(".Report"))
        if len(siblings) == 1:
            return siblings[0]
    raise ThemeError(f"report not found (need .Report dir or .pbip): {path}")


def candidate_report_dir(candidate_root: Path) -> Path:
    """Resolve an audit target (project dir, .pbip, or .Report) to .Report."""
    path = Path(candidate_root)
    if path.is_file():
        return resolve_report_dir(path)
    if (path / "definition" / "report.json").is_file():
        return path
    return resolve_report_dir(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def tree_digest(root: str | Path) -> str:
    """Content digest of a tree (relative path + bytes), links refused."""
    base = Path(root)
    digest = hashlib.sha256()
    entries = sorted(
        (p for p in base.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(base).as_posix())
    for item in entries:
        if item.is_symlink():
            raise ThemeError(f"link inside tree: {item}")
        try:
            if item.stat().st_nlink > 1:
                raise ThemeError(f"hardlink inside tree: {item}")
        except OSError as exc:
            raise ThemeError(f"cannot stat {item}: {exc}") from exc
        digest.update(item.relative_to(base).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_digest(report_dir: Path) -> str:
    """Source-bound digest; reuses pbir identity when available."""
    try:
        from .pbir import source_digest as _pbir_digest

        return str(_pbir_digest(Path(report_dir)))
    except Exception:  # noqa: BLE001 - fall back to content digest
        return tree_digest(report_dir)


def _check_no_links(root: Path) -> None:
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise ThemeError(f"source contains a symlink: {item}")
        if item.is_file():
            try:
                if item.stat().st_nlink > 1:
                    raise ThemeError(f"source contains a hardlink: {item}")
            except OSError as exc:
                raise ThemeError(f"cannot stat {item}: {exc}") from exc


def _registered_theme(report_dir: Path) -> tuple[dict[str, Any] | None, Path | None]:
    """(theme doc, theme file) for the registered custom theme, if any."""
    report_path = report_dir / "definition" / "report.json"
    if not report_path.is_file():
        return None, None
    try:
        report = _read_json(report_path)
    except (OSError, ValueError):
        return None, None
    if not isinstance(report, dict):
        return None, None
    custom = (report.get("themeCollection") or {}).get("customTheme") or {}
    name = custom.get("name") if isinstance(custom, dict) else None
    if not isinstance(name, str) or not name:
        # No registration: orphan files in RegisteredResources are not
        # a registered theme and must never satisfy registration checks.
        return None, None
    theme_file = report_dir / "StaticResources" / "RegisteredResources" / name
    if not theme_file.is_file():
        return None, None
    try:
        doc = _read_json(theme_file)
    except (OSError, ValueError):
        return None, theme_file
    return (doc if isinstance(doc, dict) else None), theme_file


def _any_theme_doc(report_dir: Path) -> dict[str, Any] | None:
    """Registered theme doc, else first orphan theme (data colors only)."""
    doc, _file = _registered_theme(report_dir)
    if isinstance(doc, dict):
        return doc
    resources = report_dir / "StaticResources" / "RegisteredResources"
    if resources.is_dir():
        for candidate in sorted(resources.glob("*.json")):
            try:
                loaded = _read_json(candidate)
            except (OSError, ValueError):
                continue
            if isinstance(loaded, dict):
                return loaded
    return None


def _source_data_colors(report_dir: Path) -> list[str]:
    doc = _any_theme_doc(report_dir)
    if isinstance(doc, dict):
        colors = doc.get("dataColors")
        if isinstance(colors, list):
            return [_norm_hex(str(c)) for c in colors if _valid_hex(c)]
    return []


def _validate_report(report_dir: Path) -> None:
    """Fail closed on a malformed report (reuses pbir's contract)."""
    from .pbir import read_report_files

    found = read_report_files(report_dir)
    fatal_rules = {
        "report_unreadable", "report_doc_unreadable", "report_doc_missing",
        "report_doc_invalid", "version_missing", "version_unreadable",
        "version_invalid", "unsupported_report_version",
        "page_doc_unreadable", "page_doc_missing", "visual_doc_unreadable",
        "visual_doc_missing", "unsupported_schema",
    }
    fatal = [i for i in found["issues"] if i.get("rule") in fatal_rules]
    if fatal:
        detail = "; ".join(sorted(
            f"{i['rule']}:{i.get('page', '')}/{i.get('visual', '')}"
            for i in fatal))
        raise ThemeError(f"malformed report: {detail}")
    if not (report_dir / "definition" / "report.json").is_file():
        raise ThemeError("malformed report: definition/report.json missing")
    if not (report_dir / "definition" / "pages").is_dir():
        raise ThemeError("malformed report: definition/pages missing")


# ---------------------------------------------------------------- registry
def _pointer(path: list[Any]) -> str:
    parts = [str(step).replace("~", "~0").replace("/", "~1") for step in path]
    return "/" + "/".join(parts)


def _is_colorish(path: list[Any]) -> bool:
    text = "/".join(str(step) for step in path).lower()
    tokens = ("color", "fill", "background", "backcolor", "fontcolor",
              "labelcolor", "linecolor", "border", "gridline",
              "textstyle", "solid", "accent")
    return any(token in text for token in tokens)


def _group_of(path: list[Any]) -> tuple[str, str]:
    """(container, group): e.g. (objects, labels) from a PBIR path."""
    for anchor in ("visualContainerObjects", "objects"):
        if anchor in path:
            idx = path.index(anchor)
            group = path[idx + 1] if idx + 1 < len(path) else ""
            return anchor, str(group)
    return "", ""


def _property_of(path: list[Any]) -> str:
    if "properties" in path:
        idx = path.index("properties")
        if idx + 1 < len(path):
            return str(path[idx + 1])
    return str(path[-1]) if path else ""


def role_for(path: list[Any], visual_type: str, file_kind: str) -> str | None:
    """Semantic role for a color leaf, from path + type (never hex)."""
    if file_kind == "page":
        container, group = _group_of(path)
        if group in ("background", "outspace", "wallpaper"):
            return "canvas"
        if group == "outspacePane":
            return {"backgroundColor": "surfaceElevated",
                    "foregroundColor": "foreground",
                    "borderColor": "outline",
                    "checkboxAndApplyColor": "accent",
                    "inputBoxColor": "slicerBackground"}.get(_property_of(path))
        if group == "filterCard":
            return {"backgroundColor": "surface",
                    "foregroundColor": "foreground",
                    "borderColor": "outline",
                    "inputBoxColor": "slicerBackground"}.get(_property_of(path))
        return None
    prop = _property_of(path).lower()
    container, group = _group_of(path)
    group_l = group.lower()
    vtype = visual_type or ""
    if container == "visualContainerObjects":
        if group_l == "background":
            return "surface"
        if group_l == "border":
            return "outline"
        if group_l in ("title", "subtitle"):
            if "back" in prop:
                return "surfaceElevated"
            if group_l == "subtitle":
                return "mutedForeground"
            return "foreground"
        if "back" in prop:
            return "surface"
        if "font" in prop or "color" in prop:
            return "foreground"
        return "surface"
    # visual.objects groups
    if group_l == "datapoint":
        return "dataColors"
    if (vtype in CHART_TYPES and group_l in ("linestyles", "markers")
            and prop in ("strokecolor", "markercolor", "areacolor")):
        return "dataColors"
    if vtype in SLICER_TYPES:
        if group_l == "selectionicon" and prop == "color":
            # Native dropdown checkbox must contrast with its item surface,
            # not inherit the selected-label or accent shade.
            return "slicerForeground"
        if group_l == "searchbox":
            return "outline" if "border" in prop else "slicerBackground"
        if group_l == "header":
            return "slicerBackground" if "back" in prop else "slicerForeground"
        if group_l == "items":
            if "back" in prop:
                return "slicerBackground"
            if "selection" in prop:
                return "selectionForeground" if "font" in prop else "selection"
            return "slicerForeground"
        if group_l == "selection":
            return "selection" if "back" in prop else "selectionForeground"
    if vtype in TABLE_TYPES:
        if group_l == "grid" and prop in (
                "gridhorizontalcolor", "gridverticalcolor"):
            return "gridline"
        if group_l == "columnheaders":
            return "tableHeader" if "back" in prop else "tableHeaderForeground"
        if group_l == "values":
            if "back" in prop:
                return "rowAlternate" if "second" in prop else "surface"
            return "foreground"
        if group_l in ("rowheaders", "rowheader"):
            return "surfaceElevated" if "back" in prop else "foreground"
        if "total" in group_l:
            return "surfaceElevated" if "back" in prop else "foreground"
        if "back" in prop:
            return "surface"
        return "foreground"
    if vtype in CARD_TYPES:
        if group_l in ("labels", "value", "values", "calloutvalue"):
            return "foreground"
        if group_l in ("categorylabels", "label", "categorylabel"):
            return "mutedForeground"
    if vtype == "textbox":
        return "foreground"
    if vtype in ("shape", "basicShape"):
        if group_l in ("fill",):
            return "accent"
        if group_l in ("line", "outline"):
            return "outline"
        if group_l in ("text",):
            # Shape text sits on the accent fill, not the canvas/surface.
            return "surfaceElevated" if "back" in prop else "accentForeground"
        if "fill" in prop:
            return "accent"
        if "line" in prop or "border" in prop:
            return "outline"
        return "foreground"
    # charts and generic visuals
    if group_l == "grid" and "color" in prop:
        return "gridline"
    if group_l in ("categoryaxis", "valueaxis"):
        if "gridline" in prop:
            return "gridline"
        return "mutedForeground"
    if group_l == "legend":
        return "mutedForeground"
    if group_l in ("labels", "datalabels"):
        return "foreground"
    if "gridline" in prop:
        return "gridline"
    if "back" in prop or group_l == "background":
        return "surface"
    if "border" in prop or "line" in prop:
        return "outline"
    if "font" in prop or "label" in prop or "text" in prop or "color" in prop:
        return "foreground"
    if "fill" in prop:
        return "accent"
    return None


def _expand_short_hex(text: str) -> str:
    digits = text.strip().lstrip("#")
    return "#" + "".join(ch * 2 for ch in digits).upper()


def _extract_hex(value: str) -> str | None:
    """Hex from a PBIR literal; ``#RGB`` expands to ``#RRGGBB``."""
    text = value.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        text = text[1:-1].strip()
    if _valid_hex(text):
        return _norm_hex(text)
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", text):
        return _expand_short_hex(text)
    # Do not convert arbitrary text containing embedded hex (including
    # query text and rich-text strings): replacing the entire value is unsafe.
    return None


def _is_full_hex(text: str) -> bool:
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", text.strip()))


def _repr_value(old: str, new_hex: str) -> str:
    """Re-encode ``new_hex`` in the old literal's quoting style."""
    text = old.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return f"'{new_hex}'"
    return new_hex


def _subtree_has(node: Any, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_subtree_has(v, key) for v in node.values())
    if isinstance(node, list):
        return any(_subtree_has(item, key) for item in node)
    return False


def _entry_scoped(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    selector = entry.get("selector")
    if selector is None:
        return False
    text = json.dumps(selector)
    return "scopeId" in text or "ScopeId" in text


def _gradient_stop_role(path: list[Any], visual_type: str,
                        kind: str) -> str | None:
    """Recognize only PBIR numeric FillRule *ramp-stop* color literals.

    The Input measure, FillRule condition/predicate, transparency and
    selector identities are untouched. A conditional Cases.Value is *not*
    an ordinary color ramp. Map supported chart / shape-map visual scales
    to the paired semantic gradient palette, not arbitrary blue values.
    """
    if kind != "visual" or (visual_type not in CHART_TYPES
                             and visual_type != "shapeMap"):
        return None
    if (len(path) != 16
            or path[:3] != ["visual", "objects", "dataPoint"]
            or not isinstance(path[3], int)
            or path[4:9] != ["properties", "fill", "solid",
                            "color", "expr"]
            or path[9:11] != ["FillRule", "FillRule"]
            or path[11] not in ("linearGradient2", "linearGradient3")
            or path[13:] != ["color", "Literal", "Value"]):
        return None
    stop = path[12]
    allowed = ("min", "max") if path[11] == "linearGradient2" else (
        "min", "mid", "max")
    if stop not in allowed:
        return None
    return {"min": "gradientMin", "mid": "gradientCenter",
            "max": "gradientMax"}[stop]


_CLASSIFICATIONS = ("supported", "supported-add", "preserved", "blocked",
                    "unknown", "not_applicable")

_COLOR_KEYS = frozenset({
    "color", "fill", "fillColor", "background", "backgroundColor",
    "backColor", "backColorPrimary", "backColorSecondary", "backColorTotal",
    "fontColor", "fontColorPrimary", "fontColorSecondary", "labelColor",
    "lineColor", "borderColor", "gridlineColor", "markerColor", "strokeColor",
    "foregroundColor", "inputBoxColor", "checkboxAndApplyColor",
    "negativeColor", "positiveColor", "neutralColor",
    "dataLabelColor", "gridHorizontalColor", "gridVerticalColor",
    "defaultColor", "areaColor",
})


def _format_color_leaf(path: list[Any], kind: str) -> bool:
    """Admit only a full PBIR appearance literal, never query/filter metadata."""
    if kind == "page":
        start = ["objects"]
        groups = {"background", "outspace", "wallpaper",
                  "outspacePane", "filterCard"}
    elif kind == "visual":
        start = ["visual"]
        groups = None
    else:
        return False
    if path[:len(start)] != start:
        return False
    if kind == "visual":
        if len(path) < 6 or path[1] not in ("objects", "visualContainerObjects"):
            return False
        group_offset = 2
    else:
        if len(path) < 5 or path[1] not in groups:
            return False
        group_offset = 1
    if (len(path) <= group_offset + 3
            or not isinstance(path[group_offset+1], int)
            or path[group_offset+2] != "properties"):
        return False
    prop = str(path[group_offset+3])
    # Only PBIR visual formatting keys, never a parameter/query with "color"
    # somewhere in a parent name.
    if prop in _COLOR_KEYS:
        return path[-5:] == ["solid", "color", "expr", "Literal", "Value"]
    # textbox rich text: general[].properties.paragraphs[].textRuns[].textStyle.color
    return (kind == "visual" and prop == "paragraphs"
            and "textRuns" in path and "textStyle" in path
            and path[-2:] == ["textStyle", "color"])


def _walk_doc(node: Any, path: list[Any], ctx: dict[str, Any],
              out: list[dict[str, Any]], palette: dict[str, Any] | None,
              source_colors: list[str], *, dynamic: bool = False,
              scoped: bool = False) -> None:
    if isinstance(node, dict):
        if "ThemeDataColor" in node:
            out.append({**ctx, "pointer": _pointer(path), "_path": list(path),
                        "old": "ThemeDataColor", "new": None, "role": None,
                        "classification": "preserved",
                        "detail": "ThemeDataColor reference preserved"})
            return
        dyn = dynamic or ("FillRule" in node) or ("Conditional" in node)
        for key, child in node.items():
            _walk_doc(child, [*path, key], ctx, out, palette, source_colors,
                      dynamic=dyn, scoped=scoped)
        return
    if isinstance(node, list):
        for index, child in enumerate(node):
            child_scoped = scoped or _entry_scoped(child)
            child_dyn = dynamic or _subtree_has(child, "FillRule")
            child_ctx = ctx
            # A dataViewWildcard selector applies one chart fill to all
            # categories. It is not a bound scopeId or business color rule.
            # See the actual Contoso "How sales are delivered" bar chart.
            if (path == ["visual", "objects", "dataPoint"]
                    and isinstance(child, dict)):
                selector = child.get("selector")
                if (isinstance(selector, dict)
                        and selector.get("data") == [
                            {"dataViewWildcard": {"matchingOption": 1}}]):
                    child_ctx = {**ctx, "_globalDataPointWildcard": True}
            if path == ["objects", "filterCard"] and isinstance(child, dict):
                selector = child.get("selector")
                if isinstance(selector, dict) and selector.get("id") in (
                        "Applied", "Available"):
                    child_ctx = {**ctx, "_filterState": selector["id"]}
            _walk_doc(child, [*path, index], child_ctx, out, palette, source_colors,
                      dynamic=child_dyn, scoped=child_scoped)
        return
    if not isinstance(node, str):
        return
    file_kind = str(ctx.get("kind", ""))
    visual_type = str(ctx.get("visualType", ""))
    if file_kind in ("bookmark", "shared"):
        # Never re-themed: every color/enum leaf is explicitly counted.
        if (re.search(r"#[0-9A-Fa-f]+\b", node)
                or node.strip().strip("'").lower() == "transparent"
                or _property_of(path).lower() == "defaultstyle"):
            detail = ("bookmark snapshot preserved; not re-themed"
                      if file_kind == "bookmark" else
                      "shared base theme not re-themed; candidate compiles "
                      "its own registered theme")
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": node, "new": None, "role": None,
                        "classification": "not_applicable", "detail": detail})
        return
    # Azure Maps basemap enum (not a hex; visual files only).
    if (file_kind == "visual" and path[:2] == ["visual", "objects"]
            and len(path) >= 9 and path[2] == "mapControls"
            and "properties" in path and "defaultStyle" in path
            and path[-3:] == ["expr", "Literal", "Value"]):
        enum = node.strip().strip("'").lower()
        if enum in ("road", "night", "grayscale_light", "grayscale_dark",
                    "high_contrast_dark"):
            mode = str(ctx.get("_mode", ""))
            target = None
            if mode == "dark" and enum != "night":
                target = "night"
            elif mode == "light" and enum != "road":
                target = "road"
            new_raw = None
            if target is not None:
                new_raw = f"'{target}'" if node.strip().startswith("'") else target
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": node, "new": new_raw, "role": "basemap",
                        "classification": "supported-enum",
                        "detail": "Azure Maps defaultStyle enum"})
        return
    odd_hex = re.search(r"#[0-9A-Fa-f]+\b", node)
    if (odd_hex and len(odd_hex.group(0)) not in (4, 7, 9)
            and _is_colorish(path)):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": node, "new": None, "role": None,
                    "classification": "unknown",
                    "detail": "non-standard hex length cannot be resolved safely"})
        return
    if re.search(r"#[0-9A-Fa-f]{8}\b", node) and _is_colorish(path):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": node, "new": None, "role": None,
                    "classification": "unknown",
                    "detail": "alpha-channel color cannot be resolved safely"})
        return
    stripped = node.strip()
    unquoted = stripped[1:-1] if len(stripped) >= 2 and stripped[0] == "'" \
        and stripped[-1] == "'" else stripped
    if unquoted.lower() == "transparent" and _is_colorish(path):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": node, "new": None, "role": None,
                    "classification": "unknown",
                    "detail": "transparent color cannot be resolved"})
        return
    hex_value = _extract_hex(node)
    if hex_value is None:
        if (re.search(r"#[0-9A-Fa-f]{3,8}\b", node)
                and _is_colorish(path) and file_kind in ("page", "visual")):
            out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": node, "new": None, "role": None,
                        "classification": "unknown",
                        "detail": "ambiguous embedded hex; not a complete color literal"})
        return
    if file_kind == "theme":
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "not_applicable",
                    "detail": "registered theme superseded by compiled theme"})
        return
    if file_kind in ("bookmark", "shared"):
        detail = ("bookmark snapshot preserved; not re-themed"
                  if file_kind == "bookmark" else
                  "shared base theme not re-themed; candidate compiles "
                  "its own registered theme")
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "not_applicable", "detail": detail})
        return
    if not _is_colorish(path):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "not_applicable",
                    "detail": "hex outside a color property"})
        return
    # A numeric gradient's literal stop colors are appearance only.
    # Theme them without changing the measure, bound or selector. Other
    # dynamic expressions (Conditional, custom rules) stay untouched.
    gradient_role = _gradient_stop_role(path, visual_type, file_kind)
    if gradient_role is not None:
        out.append({**{k: v for k, v in ctx.items()
                       if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value,
                    "new": (str(palette[gradient_role])
                            if palette is not None else None),
                    "role": gradient_role, "classification": "supported",
                    "detail": "numeric chart FillRule gradient stop only; "
                              "measure and thresholds preserved"})
        return
    # The curated Contoso Graphite Red showcase explicitly uses blue for
    # positive business outcomes instead of green. Predicate, comparison,
    # measure, threshold and negative red are NOT changed. Never apply this
    # exception to arbitrary customer reports or other palette families.
    graphite_showcase = (
        palette is not None
        and str(palette.get("accent")) in ("#BC4D54", "#DB5961")
        and str(palette.get("good")) in ("#2B5F82", "#94B0DB"))
    if (graphite_showcase and file_kind == "visual"
            and ctx.get("visual") == "cd368855f0cc75592aed"
            and hex_value == "#047857" and "Conditional" in path
            and path[-3:] == ["Value", "Literal", "Value"]):
        out.append({**{k: v for k, v in ctx.items()
                       if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": str(palette["good"]),
                    "role": "good", "classification": "supported",
                    "detail": "explicit Graphite Red positive outcome blue; "
                              "GM threshold predicate unchanged"})
        return
    if (graphite_showcase and file_kind == "visual"
            and ctx.get("visual") == "product-opportunity"
            and hex_value == "#35C9B4" and "Conditional" in path
            and path[-3:] == ["Value", "Literal", "Value"]):
        out.append({**{k: v for k, v in ctx.items()
                       if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": str(palette["good"]),
                    "role": "good", "classification": "supported",
                    "detail": "Graphite Red positive margin table text blue; "
                              "GM target measure and threshold unchanged"})
        return
    if dynamic:
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "preserved",
                    "detail": "inside FillRule/conditional/dynamic expression; "
                              "preserved with warning"})
        return
    if len(hex_value) == 9:  # #RRGGBBAA alpha channel
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "unknown",
                    "detail": "alpha-channel color cannot be resolved safely"})
        return
    _container, group = _group_of(path)
    if group.lower() == "datapoint":
        if scoped:
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": None, "role": "dataColors",
                        "classification": "preserved",
                        "detail": "dataPoint with selector scopeId preserved"})
            return
        if (_property_of(path) == "defaultColor"
                and _format_color_leaf(path, file_kind)):
            first_color = (str(palette["dataColors"][0])
                           if palette is not None else None)
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": first_color,
                        "role": "dataColors[0]",
                        "classification": "supported",
                        "detail": "unscoped chart default data color"})
            return
        if (ctx.get("_globalDataPointWildcard")
                and file_kind == "visual"
                and visual_type in CHART_TYPES
                and _property_of(path) == "fill"
                and _format_color_leaf(path, file_kind)):
            first_color = (str(palette["dataColors"][0])
                           if palette is not None else None)
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": first_color,
                        "role": "dataColors[0]", "classification": "supported",
                        "detail": "unscoped wildcard chart fill recolored"})
            return
        if hex_value in source_colors:
            index = source_colors.index(hex_value)
            target_hex = (str(palette["dataColors"][index % len(
                palette["dataColors"])]) if palette is not None else None)
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": target_hex,
                        "role": f"dataColors[{index}]",
                        "classification": "supported",
                        "detail": "dataPoint mapped by source dataColors index"})
        else:
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": None, "role": "dataColors",
                        "classification": "preserved",
                        "detail": "dataPoint hex not in source dataColors; "
                                  "preserved with warning"})
        return
    if (file_kind == "visual" and visual_type in CHART_TYPES
            and group.lower() in ("linestyles", "markers")
            and _property_of(path) in (
                "strokeColor", "markerColor", "areaColor")
            and _format_color_leaf(path, file_kind)):
        if scoped:
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": None, "role": "dataColors",
                        "classification": "preserved",
                        "detail": "scoped chart series identity preserved"})
        else:
            # Use the registered source-palette index when it exists;
            # otherwise use the deterministic series slot for that
            # explicit chart line/marker. No hash/color-similarity logic.
            index = (source_colors.index(hex_value)
                     if hex_value in source_colors else
                     (path[3] if len(path) > 3 and
                      isinstance(path[3], int) else 0))
            new_color = (str(palette["dataColors"][
                index % len(palette["dataColors"])])
                if palette is not None else None)
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": new_color,
                        "role": f"dataColors[{index}]",
                        "classification": "supported",
                        "detail": "chart line/marker series slot recolored"})
        return
    # Waterfall increase/decrease/total encode business polarity: preserve
    # exact source colors instead of silently reassigning category semantics.
    _unused_container, source_group = _group_of(path)
    source_prop = _property_of(path)
    if (file_kind == "visual" and visual_type == "waterfallChart"
            and source_group.lower() == "sentimentcolors"
            and source_prop in ("increaseFill", "decreaseFill", "totalFill")):
        if (graphite_showcase and ctx.get("visual") == "b1c2d3e4f5061728394a"
                and source_prop == "increaseFill" and hex_value == "#22C55E"):
            out.append({**{k: v for k, v in ctx.items()
                           if not k.startswith("_")},
                        "pointer": _pointer(path), "_path": list(path),
                        "old": hex_value, "new": str(palette["good"]),
                        "role": "good", "classification": "supported",
                        "detail": "explicit Graphite Red waterfall increase "
                                  "blue, with increase/decrease semantics intact"})
            return
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": source_prop,
                    "classification": "preserved",
                    "detail": "waterfall business-polarity fill intentionally preserved"})
        return
    if not _format_color_leaf(path, file_kind):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "unknown",
                    "detail": "unrecognized PBIR appearance path; preserved"})
        return
    if (file_kind == "visual" and visual_type
            and visual_type not in SUPPORTED_TYPES
            and path[:2] != ["visual", "visualContainerObjects"]):
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": None,
                    "classification": "blocked",
                    "detail": f"unsupported visual type {visual_type!r}"})
        return
    role = role_for(path, visual_type, file_kind)
    if (file_kind == "page" and _group_of(path)[1] == "filterCard"
            and ctx.get("_filterState") == "Applied"):
        role = {"backgroundColor": "selection",
                "foregroundColor": "selectionForeground",
                "borderColor": "accent",
                "inputBoxColor": "slicerBackground"}.get(_property_of(path))
    if role is None:
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": role,
                    "classification": "unknown",
                    "detail": "no registry role for this path"})
        return
    if palette is None:
        out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                    "pointer": _pointer(path), "_path": list(path),
                    "old": hex_value, "new": None, "role": role,
                    "classification": "supported",
                    "detail": f"role {role} from property path "
                              "(no palette in inspect)"})
        return
    if role == "dataColors":
        target_hex = str(palette["dataColors"][0])
    else:
        target_hex = str(palette.get(role, palette["foreground"]))
    out.append({**{k: v for k, v in ctx.items() if not k.startswith("_")},
                "pointer": _pointer(path), "_path": list(path),
                "old": hex_value, "new": target_hex, "role": role,
                "classification": "supported",
                "detail": f"role {role} from property path"})


def inventory(report_dir: Path, palette: dict[str, Any] | None = None,
              mode: str = "") -> list[dict[str, Any]]:
    """Every hex/enum occurrence in the report, path-classified."""
    report_dir = Path(report_dir)
    source_colors = _source_data_colors(report_dir)
    out: list[dict[str, Any]] = []
    pages_root = report_dir / "definition" / "pages"
    docs: list[tuple[str, Path, dict[str, Any]]] = []
    _theme_doc, theme_file = _registered_theme(report_dir)
    resources_root = report_dir / "StaticResources" / "RegisteredResources"
    theme_files = (sorted(resources_root.glob("*.json"))
                   if resources_root.is_dir() else [])
    if theme_file is not None and theme_file not in theme_files:
        theme_files.insert(0, theme_file)
    for each_theme in theme_files:
        if each_theme.is_file():
            docs.append(("theme", each_theme,
                         {"file": each_theme.relative_to(report_dir).as_posix(),
                          "page": "", "visual": "", "visualType": "",
                          "kind": "theme", "_mode": mode}))
    bookmarks_root = report_dir / "definition" / "bookmarks"
    if bookmarks_root.is_dir():
        for bookmark_file in sorted(bookmarks_root.glob("*.bookmark.json")):
            docs.append(("bookmark", bookmark_file,
                         {"file": bookmark_file.relative_to(report_dir).as_posix(),
                          "page": "", "visual": "", "visualType": "",
                          "kind": "bookmark", "_mode": mode}))
    shared_root = report_dir / "StaticResources" / "SharedResources"
    if shared_root.is_dir():
        for shared_file in sorted(shared_root.rglob("*.json")):
            docs.append(("shared", shared_file,
                         {"file": shared_file.relative_to(report_dir).as_posix(),
                          "page": "", "visual": "", "visualType": "",
                          "kind": "shared", "_mode": mode}))
    if pages_root.is_dir():
        for page_dir in sorted(p for p in pages_root.iterdir() if p.is_dir()):
            page_file = page_dir / "page.json"
            if page_file.is_file():
                docs.append(("page", page_file,
                             {"file": page_file.relative_to(report_dir).as_posix(),
                              "page": page_dir.name, "visual": "",
                              "visualType": "", "kind": "page", "_mode": mode}))
            visuals_root = page_dir / "visuals"
            if visuals_root.is_dir():
                for visual_dir in sorted(p for p in visuals_root.iterdir()
                                         if p.is_dir()):
                    visual_file = visual_dir / "visual.json"
                    if visual_file.is_file():
                        docs.append(("visual", visual_file,
                                     {"file": visual_file.relative_to(
                                         report_dir).as_posix(),
                                      "page": page_dir.name,
                                      "visual": visual_dir.name,
                                      "visualType": "", "kind": "visual",
                                      "_mode": mode}))
    for _kind, file_path, ctx in docs:
        try:
            doc = _read_json(file_path)
        except (OSError, ValueError):
            continue
        local_ctx = dict(ctx)
        if local_ctx["kind"] == "visual" and isinstance(doc, dict):
            visual = doc.get("visual") or {}
            if isinstance(visual, dict):
                local_ctx["visualType"] = str(visual.get("visualType", ""))
        _walk_doc(doc, [], local_ctx, out, palette, source_colors)
    return out


def _counts(occurrences: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in _CLASSIFICATIONS}
    counts["supported-enum"] = 0
    counts["total"] = len(occurrences)
    for item in occurrences:
        key = str(item.get("classification"))
        counts[key] = counts.get(key, 0) + 1
    counts["preserved_theme_data_color"] = sum(
        1 for item in occurrences if item.get("old") == "ThemeDataColor")
    return counts


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items()
            if not key.startswith("_")}


def inspect_report(report: str | Path) -> dict[str, Any]:
    """Read-only inventory document (``vqs theme inspect``)."""
    report_dir = resolve_report_dir(report)
    _validate_report(report_dir)
    _check_no_links(report_dir)
    occurrences = inventory(report_dir)
    return {"schema": SCHEMA_VERSION, "command": "inspect",
            "status": "pass", "report": str(report_dir),
            "sourceDigest": source_digest(report_dir),
            "counts": _counts(occurrences),
            "occurrences": [_public(item) for item in occurrences]}


def _inline_color(hex_color: str) -> dict[str, Any]:
    """PBIR color expression (different from native theme visualStyles)."""
    return {"solid": {"color": {"expr": {
        "Literal": {"Value": f"'{hex_color}'"}}}}}


def _synthesized_changes(report_dir: Path, palette: dict[str, Any]) -> list[dict[str, Any]]:
    """Add absent formatting leaves by proven type/property semantics."""
    additions: list[dict[str, Any]] = []

    def add(file: Path, ctx: dict[str, str], path: list[Any],
            role: str, value: Any, reason: str) -> None:
        additions.append({**ctx, "file": file.relative_to(report_dir).as_posix(),
                          "pointer": _pointer(path), "_path": path,
                          "old": None, "new": value, "role": role,
                          "classification": "supported-add", "detail": reason})

    pages = report_dir / "definition" / "pages"
    if not pages.is_dir():
        return additions
    for page_dir in sorted(p for p in pages.iterdir() if p.is_dir()):
        page_file = page_dir / "page.json"
        if not page_file.is_file():
            continue
        page = _read_json(page_file)
        if not isinstance(page, dict):
            raise ThemeError("invalid page object for color synthesis")
        objects = page.get("objects") or {}
        if not isinstance(objects, dict):
            raise ThemeError("invalid page objects group")
        ctx = {"page": page_dir.name, "visual": "", "visualType": "", "kind": "page"}
        background = objects.get("background")
        if background is None:
            add(page_file, ctx, ["objects", "background"], "canvas",
                [{"properties": {"color": _inline_color(str(palette["canvas"]))}}],
                "explicit canvas required: page theme does not color canvas")
        elif isinstance(background, list) and background:
            first = background[0]
            if isinstance(first, dict) and not first.get("selector"):
                props = first.get("properties")
                if isinstance(props, dict) and "color" not in props:
                    add(page_file, ctx, ["objects", "background", 0, "properties", "color"],
                        "canvas", _inline_color(str(palette["canvas"])),
                        "explicit page background missing color")
        # Filters are distinct from report filter *definitions*. Only page
        # appearance objects are inserted/updated; never filterConfig.
        pane_roles = {"backgroundColor": "surfaceElevated",
                      "foregroundColor": "foreground",
                      "borderColor": "outline",
                      "checkboxAndApplyColor": "accent",
                      "inputBoxColor": "slicerBackground"}
        pane_entries = objects.get("outspacePane")
        if pane_entries is None:
            add(page_file, ctx, ["objects", "outspacePane"], "surfaceElevated",
                [{"properties": {k: _inline_color(str(palette[r]))
                                 for k, r in pane_roles.items()}}],
                "filter pane background, text, border, input and apply controls")
        elif isinstance(pane_entries, list):
            for i, entry in enumerate(pane_entries):
                if not isinstance(entry, dict) or entry.get("selector"):
                    continue
                props = entry.get("properties")
                if not isinstance(props, dict):
                    continue
                for k, r in pane_roles.items():
                    if k not in props:
                        add(page_file, ctx, ["objects", "outspacePane",
                                            i, "properties", k], r,
                            _inline_color(str(palette[r])),
                            "fill missing pane appearance property")
        card_states = {
            "Available": {"backgroundColor": "surface",
                          "foregroundColor": "foreground",
                          "borderColor": "outline",
                          "inputBoxColor": "slicerBackground"},
            "Applied": {"backgroundColor": "selection",
                        "foregroundColor": "selectionForeground",
                        "borderColor": "accent",
                        "inputBoxColor": "slicerBackground"},
        }
        card_entries = objects.get("filterCard")
        if card_entries is None:
            cards = [{"selector": {"id": state},
                      "properties": {k: _inline_color(str(palette[role]))
                                     for k, role in properties.items()}}
                     for state, properties in card_states.items()]
            add(page_file, ctx, ["objects", "filterCard"], "surface", cards,
                "distinct Available and Applied filter-card appearance")
        elif isinstance(card_entries, list):
            existing_states = {
                entry.get("selector", {}).get("id")
                for entry in card_entries
                if isinstance(entry, dict)
                and isinstance(entry.get("selector"), dict)}
            for state, properties in card_states.items():
                if state not in existing_states:
                    add(page_file, ctx, ["objects", "filterCard", len(card_entries)],
                        "selection" if state == "Applied" else "surface",
                        {"selector": {"id": state},
                         "properties": {k: _inline_color(str(palette[role]))
                                        for k, role in properties.items()}},
                        "missing filter card state")
                    # Only one missing state is supported in a single pass.
                    break
            for i, entry in enumerate(card_entries):
                selector = entry.get("selector") if isinstance(entry, dict) else None
                state = selector.get("id") if isinstance(selector, dict) else None
                if state not in card_states:
                    continue
                props = entry.get("properties")
                if not isinstance(props, dict):
                    continue
                for k, role in card_states[state].items():
                    if k not in props:
                        add(page_file, ctx, ["objects", "filterCard",
                                            i, "properties", k], role,
                            _inline_color(str(palette[role])),
                            "fill missing filter-card state appearance")
        visuals = page_dir / "visuals"
        if not visuals.is_dir():
            continue
        for visual_file in sorted(visuals.glob("*/visual.json")):
            doc = _read_json(visual_file)
            visual = doc.get("visual") if isinstance(doc, dict) else None
            if not isinstance(visual, dict):
                continue
            vtype = visual.get("visualType")
            if not isinstance(vtype, str) or vtype not in SUPPORTED_TYPES:
                continue
            objects = visual.get("objects") or {}
            if not isinstance(objects, dict):
                continue
            ctx = {"page": page_dir.name, "visual": visual_file.parent.name,
                   "visualType": vtype, "kind": "visual"}
            targets: dict[str, dict[str, str]] = {}
            if vtype in SLICER_TYPES:
                targets = {
                    "items": {"fontColor": "slicerForeground",
                              "background": "slicerBackground"},
                    "header": {"fontColor": "slicerForeground",
                               "background": "slicerBackground"},
                    "searchBox": {"background": "slicerBackground",
                                  "borderColor": "outline"}}
                if vtype == "slicer":
                    # Microsoft native SelectionIcon catalog is for slicer.
                    # Avoid guessing support for other filter visual families.
                    targets["selectionIcon"] = {"color": "slicerForeground"}
            elif vtype in TABLE_TYPES:
                targets = {
                    "columnHeaders": {"fontColor": "tableHeaderForeground",
                                      "backColor": "tableHeader"},
                    "values": {"fontColorPrimary": "foreground",
                               "fontColorSecondary": "foreground",
                               "backColorPrimary": "surface",
                               "backColorSecondary": "rowAlternate"},
                    "rowHeaders": {"fontColor": "foreground",
                                   "backColor": "surfaceElevated"},
                    "rowTotal": {"fontColor": "foreground",
                                 "backColor": "surfaceElevated"},
                    "columnTotal": {"fontColor": "foreground",
                                    "backColor": "surfaceElevated"}}
            elif vtype in ("shape", "basicShape"):
                targets = {"text": {"fontColor": "accentForeground"}}
            elif vtype in ("card", "cardVisual", "multiRowCard", "kpi"):
                targets = {"labels": {"color": "foreground"},
                           "categoryLabels": {"color": "mutedForeground"}}
            elif vtype in CHART_TYPES:
                targets = {"categoryAxis": {"labelColor": "mutedForeground"},
                           "valueAxis": {"labelColor": "mutedForeground"},
                           "legend": {"labelColor": "mutedForeground"}}
            if vtype == "tableEx":
                targets.pop("rowHeaders", None)
            # Power BI's implicit native legend text can render almost black
            # on dark surfaces even with high-contrast active theme tokens.
            # Include line charts with native series legends, not only
            # donuts and waterfall/numeric legends. The default show/series
            # selection remains unchanged; only label color is supplied.
            chrome = visual.get("visualContainerObjects") or {}
            has_numeric_legend = (
                vtype in ("clusteredBarChart", "clusteredColumnChart")
                and _subtree_has(objects.get("dataPoint", []), "FillRule"))
            if ((vtype in ("donutChart", "waterfallChart", "lineChart")
                 or has_numeric_legend)
                    and chrome.get("title") and not objects.get("legend")):
                add(visual_file, ctx, ["visual", "objects", "legend"],
                    "mutedForeground",
                    [{"properties": {"labelColor": _inline_color(
                        str(palette["mutedForeground"]))}}],
                    "explicit built-in chart legend text for dark/light")
            # A shown native VCO subtitle may lack an explicit fontColor,
            # even while the title is correctly themed. Add color alone,
            # never modify subtitle wording/visibility or geometry.
            subtitle_entries = chrome.get("subTitle")
            if isinstance(subtitle_entries, list):
                for index, entry in enumerate(subtitle_entries):
                    if not isinstance(entry, dict) or entry.get("selector"):
                        continue
                    properties = entry.get("properties")
                    if not isinstance(properties, dict) or "fontColor" in properties:
                        continue
                    show = properties.get("show", {}).get("expr", {}).get(
                        "Literal", {}).get("Value")
                    if show not in ("true", "'true'"):
                        continue
                    add(visual_file, ctx, [
                        "visual", "visualContainerObjects", "subTitle", index,
                        "properties", "fontColor"], "mutedForeground",
                        _inline_color(str(palette["mutedForeground"])),
                        "shown subtitle needs a surface-contrasting explicit color")
            for group, props_to_add in targets.items():
                entries = objects.get(group)
                if entries is None:
                    if vtype in SLICER_TYPES and group in (
                            "items", "searchBox", "selectionIcon"):
                        new_entry = {"properties": {k: _inline_color(str(palette[v]))
                                                     for k, v in props_to_add.items()}}
                        add(visual_file, ctx, ["visual", "objects", group],
                            ("slicerForeground" if group == "selectionIcon" else
                             "slicerBackground"), [new_entry],
                            ("explicit checkbox indicator contrasts with item surface"
                             if group == "selectionIcon" else
                             "slicer item group synthesized to avoid white dropdown"))
                    continue
                if not isinstance(entries, list):
                    continue
                for index, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    selector = entry.get("selector")
                    if selector and selector != {"id": "default"}:
                        continue
                    props = entry.get("properties")
                    if not isinstance(props, dict):
                        continue
                    if group == "text" and vtype in ("shape", "basicShape"):
                        show = props.get("show", {}).get("expr", {}).get("Literal", {}).get("Value")
                        if show not in ("true", "'true'"):
                            continue
                    if group == "header" and vtype in SLICER_TYPES:
                        show = props.get("show", {}).get("expr", {}).get("Literal", {}).get("Value")
                        if show in ("false", "'false'"):
                            continue
                    for prop, role in props_to_add.items():
                        if prop not in props:
                            add(visual_file, ctx, ["visual", "objects", group,
                                                   index, "properties", prop],
                                role, _inline_color(str(palette[role])),
                                "explicit group override suppresses theme inheritance")
    return additions


def build_plan(report: str | Path, mode: str,
               palette: dict[str, Any]) -> dict[str, Any]:
    """Shared planner for preview and apply (identical changes)."""
    report_dir = resolve_report_dir(report)
    _validate_report(report_dir)
    _check_no_links(report_dir)
    violations = palette_contrast_check(palette)
    if violations:
        raise ThemeError(
            "palette contrast check failed: " + json.dumps(violations))
    occurrences = inventory(report_dir, palette=palette, mode=mode)
    synthesized = _synthesized_changes(report_dir, palette)
    changes: list[dict[str, Any]] = list(synthesized)
    occurrences.extend(synthesized)
    for item in occurrences:
        if item.get("classification") not in ("supported", "supported-enum"):
            continue
        if item.get("new") is None:
            continue
        # Compare hex-level identity for no-op detection.
        if item.get("classification") == "supported" and \
                str(item.get("old", "")).upper() == str(item["new"]).upper():
            continue
        if item.get("classification") == "supported-enum" and \
                item.get("old") == item.get("new"):
            continue
        changes.append(item)
    digest = source_digest(report_dir)
    suffix = hashlib.sha256(
        (digest + palette_canonical(palette) + mode).encode("utf-8")
    ).hexdigest()[:12]
    theme_name = f"VQSAdaptive-{mode}-{suffix}.json"
    # Idempotence only when the existing compiled theme already equals
    # this palette's compilation; a palette-only change recompiles.
    existing_doc, existing_file = _registered_theme(report_dir)
    existing_name = existing_file.name if existing_file is not None else ""
    if (existing_name.startswith(f"VQSAdaptive-{mode}-")
            and existing_doc == compile_theme(palette, mode, existing_name)):
        theme_name = existing_name
    return {"schema": SCHEMA_VERSION, "mode": mode,
            "sourceDigest": digest,
            "paletteHash": palette_hash(palette),
            "themeFileName": theme_name,
            "counts": _counts(occurrences),
            "occurrences": occurrences, "changes": changes,
            "reportDir": report_dir}


def preview_plan(report: str | Path, mode: str,
                 palette: dict[str, Any]) -> dict[str, Any]:
    """Read-only plan document (``vqs theme preview``); writes nothing."""
    plan = build_plan(report, mode, palette)
    return {"schema": SCHEMA_VERSION, "command": "preview",
            "status": "pass", "mode": mode,
            "sourceDigest": plan["sourceDigest"],
            "paletteHash": plan["paletteHash"],
            "themeFileName": plan["themeFileName"],
            "counts": plan["counts"],
            "changes": [_public(item) for item in plan["changes"]],
            "occurrences": [_public(item) for item in plan["occurrences"]],
            "rollback": "preview only; no candidate was written"}


def _solid(hex_color: str) -> dict[str, Any]:
    return {"solid": {"color": hex_color}}


def compile_theme(palette: dict[str, Any], mode: str,
                  theme_name: str) -> dict[str, Any]:
    """Compile the native registered theme for ``mode``."""
    p = palette
    slicer_style = {
        "items": [{"background": _solid(str(p["slicerBackground"])),
                   "fontColor": _solid(str(p["slicerForeground"]))}],
        "header": [{"background": _solid(str(p["slicerBackground"])),
                    "fontColor": _solid(str(p["slicerForeground"]))}],
    }
    table_style = {
        "columnHeaders": [{"backColor": _solid(str(p["tableHeader"])),
                           "fontColor": _solid(
                               str(p["tableHeaderForeground"]))}],
        "values": [{"backColorPrimary": _solid(str(p["surface"])),
                    "backColorSecondary": _solid(str(p["rowAlternate"])),
                    "fontColorPrimary": _solid(str(p["foreground"])),
                    "fontColorSecondary": _solid(str(p["foreground"]))}],
        "rowHeaders": [{"backColor": _solid(str(p["surfaceElevated"])),
                        "fontColor": _solid(str(p["foreground"]))}],
        "total": [{"backColor": _solid(str(p["surfaceElevated"])),
                   "fontColor": _solid(str(p["foreground"]))}],
    }
    card_style = {
        "labels": [{"color": _solid(str(p["foreground"]))}],
        "categoryLabels": [{"color": _solid(str(p["mutedForeground"]))}],
    }
    return {
        "$schema": THEME_SCHEMA,
        "name": theme_name,
        "dataColors": list(p["dataColors"]),
        "background": str(p["canvas"]),
        "foreground": str(p["foreground"]),
        "tableAccent": str(p["accent"]),
        "good": str(p["good"]), "neutral": str(p["neutral"]),
        "bad": str(p["bad"]),
        "maximum": str(p["gradientMax"]), "center": str(p["gradientCenter"]),
        "minimum": str(p["gradientMin"]),
        "textClasses": {
            "title": {"fontFace": "Segoe UI", "fontSize": 16,
                      "color": str(p["foreground"]), "fontWeight": "bold"},
            "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12,
                       "color": str(p["foreground"]), "fontWeight": "bold"},
            "label": {"fontFace": "Segoe UI", "fontSize": 10,
                      "color": str(p["mutedForeground"])},
            "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 28,
                        "color": str(p["foreground"]), "fontWeight": "bold"},
        },
        "visualStyles": {
            "*": {"*": {
                "background": [{"color": _solid(str(p["surface"])),
                                "transparency": 0}],
                # Note: the official Oct-2026 theme schema admits outspace,
                # outspacePane and filterCard, but Microsoft authoring CLI
                # 0.5.0 rejects these report-level groups. Canvas/outspace
                # are explicitly rewritten in page objects. The filter pane
                # remains a documented Desktop-only coverage limitation.
            }},
            "slicer": {"*": slicer_style},
            "filterSlicer": {"*": slicer_style},
            # New card and advanced slicer objects differ from legacy
            # styling; pinned Microsoft authoring rejects these defaults.
            "tableEx": {"*": {k: v for k, v in table_style.items()
                               if k != "rowHeaders"}},
            "pivotTable": {"*": table_style},
            "card": {"*": card_style},
        },
    }


def _get_path(doc: Any, path: list[Any]) -> Any:
    node = doc
    for step in path:
        node = node[step]
    return node


def _set_path(doc: Any, path: list[Any], value: Any) -> None:
    node = doc
    for step in path[:-1]:
        node = node[step]
    last = path[-1]
    if isinstance(node, list) and isinstance(last, int) and last == len(node):
        # Only synthesize a missing trailing filter-card state, never splice.
        if path[:2] != ["objects", "filterCard"]:
            raise ThemeError("list-append forbidden outside filter cards")
        node.append(value)
    else:
        node[last] = value


def _overlaps(first: Path, second: Path) -> bool:
    a = os.path.normcase(os.path.realpath(first))
    b = os.path.normcase(os.path.realpath(second))
    return a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep)


def _model_source(report_dir: Path) -> Path | None:
    """Sibling SemanticModel dir when byPath resolves inside the project."""
    pbir = report_dir / "definition.pbir"
    if not pbir.is_file():
        return None
    try:
        doc = _read_json(pbir)
    except (OSError, ValueError) as exc:
        raise ThemeError("malformed definition.pbir dataset reference") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("datasetReference"), dict):
        raise ThemeError("definition.pbir missing datasetReference")
    dataset = doc["datasetReference"]
    if "byPath" not in dataset:
        if "byConnection" in dataset:
            return None
        raise ThemeError("unknown definition.pbir dataset reference type")
    ref = dataset["byPath"]
    target = ref.get("path") if isinstance(ref, dict) else None
    if not isinstance(target, str) or not target:
        raise ThemeError("definition.pbir byPath has no valid model path")
    resolved = (report_dir / target).resolve()
    project = report_dir.resolve().parent
    if not resolved.is_relative_to(project) or resolved == report_dir.resolve():
        raise ThemeError("definition.pbir byPath model escapes project")
    if not resolved.is_dir() or resolved.is_symlink():
        raise ThemeError(f"definition.pbir byPath model is missing: {target}")
    _check_no_links(resolved)
    return resolved


def _copy_model(source: Path, dest: Path) -> None:
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            raise ThemeError(f"model contains a symlink: {item}")
        if item.is_dir():
            continue
        target = dest / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item, target)


def _write_wrapper(source_report: Path, cand_report: Path) -> Path | None:
    """Candidate .pbip beside the report, mirroring repair's wrapper."""
    project = cand_report.parent
    source_project = source_report.parent
    sources = sorted(source_project.glob("*.pbip"))
    if not sources:
        return None
    stem = cand_report.name
    for suffix in (".Report", ".report"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    wrapper = project / f"{stem}.pbip"
    schema = ("https://developer.microsoft.com/json-schemas/fabric/"
              "pbip/pbipProperties/1.0.0/schema.json")
    try:
        original = _read_json(sources[0])
        if isinstance(original, dict) and isinstance(
                original.get("$schema"), str):
            schema = str(original["$schema"])
    except (OSError, ValueError):
        pass
    doc = {"$schema": schema, "version": "1.0",
           "artifacts": [{"report": {"path": cand_report.name}}],
           "settings": {"enableAutoRecovery": True}}
    wrapper.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return wrapper


def _update_report_json(cand_report: Path, theme_name: str,
                        old_theme_name: str | None) -> None:
    path = cand_report / "definition" / "report.json"
    doc = _read_json(path)
    if not isinstance(doc, dict):
        raise ThemeError("candidate definition/report.json is not an object")
    collection = doc.get("themeCollection")
    if not isinstance(collection, dict):
        collection = {}
        doc["themeCollection"] = collection
    previous = collection.get("customTheme") or {}
    custom: dict[str, Any] = {"name": theme_name,
                              "type": "RegisteredResources"}
    if isinstance(previous, dict) and isinstance(
            previous.get("reportVersionAtImport"), dict):
        custom["reportVersionAtImport"] = previous["reportVersionAtImport"]
    collection["customTheme"] = custom
    packages = doc.get("resourcePackages")
    if not isinstance(packages, list):
        packages = []
        doc["resourcePackages"] = packages
    package = next((p for p in packages if isinstance(p, dict)
                    and p.get("type") == "RegisteredResources"), None)
    if package is None:
        package = {"name": "RegisteredResources",
                   "type": "RegisteredResources", "items": []}
        packages.append(package)
    items = package.get("items")
    if not isinstance(items, list):
        items = []
        package["items"] = items
    items[:] = [i for i in items if not (isinstance(i, dict)
                                         and i.get("type") == "CustomTheme")]
    items.append({"name": theme_name, "path": theme_name,
                  "type": "CustomTheme"})
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if old_theme_name and old_theme_name != theme_name:
        old_file = (cand_report / "StaticResources" / "RegisteredResources"
                    / old_theme_name)
        if old_file.is_file():
            old_file.unlink()


def apply_theme(report: str | Path, mode: str, palette: dict[str, Any],
                candidate_root: str | Path) -> dict[str, Any]:
    """Atomically write a themed candidate project; original untouched."""
    report_dir = resolve_report_dir(report)
    cand_root = Path(candidate_root)
    # Candidate project must not sit inside, nor contain, the original
    # report tree or its containing project.
    if _overlaps(report_dir, cand_root) or _overlaps(
            report_dir.parent, cand_root):
        raise ThemeError("candidate root overlaps the original report")
    if cand_root.exists():
        if cand_root.is_symlink():
            raise ThemeError("candidate root is a symlink")
        if any(cand_root.iterdir()):
            raise ThemeError("candidate root exists and is not empty")
    plan = build_plan(report_dir, mode, palette)
    before_digest = source_digest(report_dir)
    if before_digest != plan["sourceDigest"]:
        raise ThemeError("source changed while planning; retry")
    parent = cand_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_root = parent / f".{cand_root.name}.vqs-theme-tmp-{uuid.uuid4().hex[:12]}"
    if tmp_root.exists():
        raise ThemeError(f"temporary candidate root already exists: {tmp_root}")
    tmp_root.mkdir(parents=True)
    try:
        cand_report = tmp_root / report_dir.name
        shutil.copytree(report_dir, cand_report)
        _check_no_links(cand_report)
        # Inline changes, grouped by file; literal-old precondition checked.
        by_file: dict[str, list[dict[str, Any]]] = {}
        for change in plan["changes"]:
            by_file.setdefault(str(change["file"]), []).append(change)
        for rel, changes in by_file.items():
            target = cand_report / rel
            doc = _read_json(target)
            for change in changes:
                if change["classification"] == "supported-add":
                    path_steps = change["_path"]
                    if path_steps[0] == "objects" and not isinstance(doc.get("objects"), dict):
                        doc["objects"] = {}
                    if (path_steps[:2] == ["visual", "objects"]
                            and not isinstance(doc["visual"].get("objects"), dict)):
                        doc["visual"]["objects"] = {}
                    try:
                        _get_path(doc, path_steps)
                    except (KeyError, IndexError):
                        pass
                    else:
                        raise ThemeError(f"synthesis path occupied: {rel}{change['pointer']}")
                    new_raw = change["new"]
                else:
                    raw_old = _get_path(doc, change["_path"])
                    if not isinstance(raw_old, str):
                        raise ThemeError(
                            f"precondition failed at {rel}{change['pointer']}")
                    if change["classification"] == "supported-enum":
                        if raw_old != change["old"]:
                            raise ThemeError("enum precondition changed")
                        new_raw = str(change["new"])
                    else:
                        new_raw = _repr_value(raw_old, str(change["new"]))
                        if _extract_hex(raw_old) != change["old"]:
                            raise ThemeError(
                                f"precondition failed at {rel}"
                                f"{change['pointer']}: {raw_old!r}")
                _set_path(doc, change["_path"], new_raw)
                change["_applied_new"] = new_raw
            target.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        # Compiled theme + registration (skipped when already applied).
        old_doc, old_file = _registered_theme(report_dir)
        old_name = old_file.name if old_file is not None else None
        already = bool(
            old_name and old_name == plan["themeFileName"]
            and old_doc == compile_theme(palette, mode, str(old_name)))
        theme_name = str(plan["themeFileName"])
        if not already:
            resources = (cand_report / "StaticResources"
                         / "RegisteredResources")
            resources.mkdir(parents=True, exist_ok=True)
            theme_doc = compile_theme(palette, mode, theme_name)
            (resources / theme_name).write_text(
                json.dumps(theme_doc, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
            _update_report_json(cand_report, theme_name, old_name)
        # Sibling semantic model, byte-identical, when byPath is in-project.
        model_source = _model_source(report_dir)
        model_digest_before = (tree_digest(model_source)
                               if model_source is not None else None)
        if model_source is not None:
            rel_model = model_source.relative_to(report_dir.parent.resolve())
            model_dest = tmp_root / rel_model
            _copy_model(model_source, model_dest)
            if tree_digest(model_dest) != model_digest_before:
                raise ThemeError("candidate model copy differs from source")
        wrapper = _write_wrapper(report_dir, cand_report)
        cand_digest = source_digest(cand_report)
        manifest: dict[str, Any] = {
            "schema": SCHEMA_VERSION, "command": "apply", "status": "pass",
            "mode": mode, "paletteHash": plan["paletteHash"],
            "palette": palette, "themeFileName": theme_name,
            "sourceReport": str(report_dir),
            "sourceDigest": plan["sourceDigest"],
            "candidateDigest": cand_digest,
            "candidateReport": cand_report.name,
            "modelDigest": model_digest_before,
            "counts": plan["counts"],
            "changes": [_public(item) for item in plan["changes"]],
            "occurrences": [_public(item) for item in plan["occurrences"]],
            "wrapper": wrapper.name if wrapper is not None else None,
            "rollback": ("delete the candidate project root and this "
                         "theme-manifest.json; the original was never "
                         "written"),
        }
        manifest["candidateRoot"] = str(cand_root)
        # Sealed manifest and byte/invariant proofs BEFORE public rename.
        if _invariant_snapshot(report_dir) != _invariant_snapshot(cand_report):
            raise ThemeError("nonappearance PBIR invariants changed during apply")
        (tmp_root / "theme-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        if source_digest(report_dir) != before_digest:
            raise ThemeError("original changed during apply; candidate "
                             "discarded")
        if cand_root.exists():
            cand_root.rmdir()
        os.replace(tmp_root, cand_root)
    except BaseException:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise
    # The rename is the sole publish step: no writes after it succeeds.
    return manifest


def _invariant_snapshot(report_dir: Path) -> dict[str, str]:
    """Hashes of query/filter/sort/selector/interaction subtrees."""
    snapshot: dict[str, str] = {}

    def record(key: str, node: Any) -> None:
        canonical = json.dumps(node, sort_keys=True, default=str)
        snapshot[key] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    pages_root = report_dir / "definition" / "pages"
    if pages_root.is_dir():
        for page_dir in sorted(p for p in pages_root.iterdir() if p.is_dir()):
            page_file = page_dir / "page.json"
            if page_file.is_file():
                try:
                    page = _read_json(page_file)
                except (OSError, ValueError):
                    continue
                if isinstance(page, dict):
                    for field in ("filterConfig", "filters"):
                        if field in page:
                            record(f"{page_dir.name}/page/{field}",
                                   page[field])
            visuals_root = page_dir / "visuals"
            if not visuals_root.is_dir():
                continue
            for visual_dir in sorted(p for p in visuals_root.iterdir()
                                     if p.is_dir()):
                visual_file = visual_dir / "visual.json"
                if not visual_file.is_file():
                    continue
                try:
                    doc = _read_json(visual_file)
                except (OSError, ValueError):
                    continue
                if not isinstance(doc, dict):
                    continue
                visual = doc.get("visual") or {}
                key = f"{page_dir.name}/{visual_dir.name}"
                if isinstance(visual, dict):
                    query = visual.get("query") or {}
                    if isinstance(query, dict):
                        for field in ("queryState", "sortDefinition"):
                            if field in query:
                                record(f"{key}/query/{field}", query[field])
                    for field in ("filterConfig", "filters"):
                        if field in visual:
                            record(f"{key}/{field}", visual[field])
                    if "objects" in visual:
                        record(f"{key}/selectors",
                               _selector_fingerprint(visual["objects"]))
                for field in ("interactions", "filterConfig"):
                    if field in doc:
                        record(f"{key}/doc/{field}", doc[field])
    return snapshot


def _selector_fingerprint(node: Any) -> Any:
    """Only selector subtrees, so color edits never move this hash."""
    found: list[Any] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "selector" in value:
                found.append(value["selector"])
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


_AUDIT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("foreground", "canvas", "foreground/canvas"),
    ("foreground", "surface", "foreground/surface"),
    ("mutedForeground", "surface", "muted/surface"),
    ("tableHeaderForeground", "tableHeader", "tableHeader fg/bg"),
    ("slicerForeground", "slicerBackground", "slicer fg/bg"),
)


def audit_candidate(candidate: str | Path) -> dict[str, Any]:
    """Re-inventory a candidate and verify manifest-bound invariants."""
    cand_report = candidate_report_dir(Path(candidate))
    project = cand_report.parent
    manifest_path = project / "theme-manifest.json"
    manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        try:
            loaded = _read_json(manifest_path)
            manifest = loaded if isinstance(loaded, dict) else None
        except (OSError, ValueError):
            manifest = None
    occurrences = inventory(cand_report)
    counts = _counts(occurrences)
    checks: list[dict[str, Any]] = []
    palette = (manifest or {}).get("palette")
    if isinstance(palette, dict):
        for fg_role, bg_role, label in _AUDIT_PAIRS:
            fg, bg = palette.get(fg_role), palette.get(bg_role)
            if _valid_hex(fg) and _valid_hex(bg):
                ratio = contrast_ratio(str(fg), str(bg))
                checks.append({"pair": label, "ratio": round(ratio, 3),
                               "required": 4.5,
                               "status": "pass" if ratio >= 4.5 else "fail"})
            else:
                checks.append({"pair": label, "ratio": None,
                               "required": 4.5, "status": "unknown"})
    else:
        for _fg, _bg, label in _AUDIT_PAIRS:
            checks.append({"pair": label, "ratio": None, "required": 4.5,
                           "status": "unknown"})
    invariants: dict[str, Any] = {"status": "unknown",
                                  "detail": "no manifest source bound"}
    manifest_ok: bool | None = None
    if manifest is not None:
        expected = manifest.get("candidateDigest")
        actual = source_digest(cand_report)
        manifest_ok = bool(expected) and expected == actual
        checks.append({"pair": "manifest candidateDigest",
                       "status": "pass" if manifest_ok else "fail"})
        source_raw = manifest.get("sourceReport")
        if isinstance(source_raw, str) and Path(source_raw).is_dir():
            source_dir = Path(source_raw)
            before = _invariant_snapshot(source_dir)
            after = _invariant_snapshot(cand_report)
            keys = sorted(set(before) | set(after))
            diffs = [k for k in keys if before.get(k) != after.get(k)]
            invariants = {"status": "pass" if not diffs else "fail",
                          "compared": len(keys), "differences": diffs}
            model_source = _model_source(source_dir)
            cand_model = _model_source(cand_report)
            if manifest.get("modelDigest") is not None:
                if cand_model is None:
                    invariants["modelDigestEqual"] = False
                    invariants["status"] = "fail"
                    invariants["detail"] = "candidate model missing"
                else:
                    same = tree_digest(cand_model) == manifest["modelDigest"]
                    invariants["modelDigestEqual"] = same
                    if not same:
                        invariants["status"] = "fail"
            elif model_source is not None and cand_model is not None:
                same = tree_digest(model_source) == tree_digest(cand_model)
                invariants["modelDigestEqual"] = same
                if not same:
                    invariants["status"] = "fail"
        else:
            invariants = {"status": "unknown",
                          "detail": "manifest source no longer present"}
    if isinstance(palette, dict):
        theme_doc, _tf = _registered_theme(cand_report)
        actual_colors = (theme_doc or {}).get("dataColors")
        expected_colors = palette.get("dataColors")
        theme_match = actual_colors == expected_colors
        checks.append({"pair": "registered theme dataColors vs manifest",
                       "status": "pass" if theme_match else "fail"})
    failed = [c for c in checks if c.get("status") == "fail"]
    unknown = [c for c in checks if c.get("status") == "unknown"]
    integrity = ("fail" if failed or invariants.get("status") == "fail"
                 else "unknown" if unknown or invariants.get("status") == "unknown"
                 or manifest is None else "pass")
    unresolved = [o for o in occurrences
                  if o.get("classification") in ("blocked", "unknown")]
    appearance = ("partial" if unresolved else "complete")
    # Report passes only when appearance is also fully classified.
    status = (integrity if integrity != "pass"
              else "unknown" if unresolved else "pass")
    return {"schema": SCHEMA_VERSION, "command": "audit",
            "status": status,
            "integrityStatus": integrity,
            "appearanceCoverageStatus": appearance,
            "unresolved": [_public(o) for o in unresolved],
            "candidate": str(cand_report),
            "candidateDigest": source_digest(cand_report),
            "manifestPresent": manifest is not None,
            "manifestDigestMatch": manifest_ok,
            "counts": counts, "contrastChecks": checks,
            "invariants": invariants,
            "occurrences": [_public(item) for item in occurrences]}





