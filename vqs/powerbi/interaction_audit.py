"""P14: verify recorded Desktop UI states against source-bound live DAX.

Recorded screenshots and visible strings are checked, never silently treated
as authenticated clicks. Without a trusted interactive collector this can
establish numeric/capture consistency but must NOT proclaim UI acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from vqs.evidence import _PNG_FILE_CAP, _decode_png
from vqs.powerbi.contoso_runtime import (
    COUNTRIES,
    CURRENT_SOURCE_CONTRACT,
    REGIONS,
    SOURCE_CONTRACT,
    YEARS,
    build_queries,
)

SCHEMA = "vqs.contoso-desktop-interaction-trace/1"
RESULT_SCHEMA = "vqs.contoso-desktop-interaction-audit/1"
DEEP_DIVE_PAGE = "d9bc3b8f90439bcc"

_DISPLAY = re.compile(
    r"^\s*(?P<neg>\()?\s*(?P<minus>-)?\s*(?P<dollar>\$)?\s*"
    r"(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<suffix>[KMBT])?\s*(?P<percent>%)?\s*(?P<close>\))?\s*$",
    re.IGNORECASE,
)
_UNIT_SCALE = {"": Decimal(1), "K": Decimal(1000),
               "M": Decimal(1000000), "B": Decimal(1000000000),
               "T": Decimal(1000000000000)}


class InteractionEvidenceError(ValueError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _require(condition: bool, status: str, message: str) -> None:
    if not condition:
        raise InteractionEvidenceError(status, message)


def _hex(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(letter in "0123456789abcdef" for letter in value))


def displayed_interval(label: str, *, percentage: bool = False
                       ) -> tuple[float, float] | None:
    """Interval of real values that round to the captured formatted text.

    Values like '$12.3M', '1,220', '4.5%', and em dash for a DAX BLANK are
    supported. The interval is conservative around half a last shown digit.
    Percentages are divided by 100 for DAX's fractional measure convention.
    """
    if not isinstance(label, str):
        raise TypeError("visible value must be a string, never typed oracle data")
    if label.strip() in ("—", "–", "(Blank)", "BLANK"):
        return None
    found = _DISPLAY.fullmatch(label)
    if found is None or bool(found["percent"]) != percentage:
        raise ValueError(f"unrecognized or incorrectly formatted UI number: {label!r}")
    if percentage and found["suffix"]:
        raise ValueError("percent display must not include a magnitude suffix")
    if bool(found["neg"]) != bool(found["close"]):
        raise ValueError("unbalanced negative-number parentheses")
    try:
        amount = Decimal(found["amount"].replace(",", ""))
        scale = _UNIT_SCALE[(found["suffix"] or "").upper()]
        precision = Decimal(1).scaleb(-len(found["amount"].partition(".")[2]))
        center = amount * scale
        tolerance = precision * scale / 2
        if found["neg"] or found["minus"]:
            center = -center
    except (InvalidOperation, KeyError) as exc:
        raise ValueError("invalid visible number") from exc
    if percentage:
        center /= 100
        tolerance /= 100
    return float(center - tolerance), float(center + tolerance)


def _matches(label: object, expected: object, *, percentage: bool = False) -> bool:
    if not isinstance(label, str):
        raise InteractionEvidenceError("blocked", "UI value missing/nontextual")
    try:
        bounds = displayed_interval(label, percentage=percentage)
    except (TypeError, ValueError) as exc:
        raise InteractionEvidenceError("blocked", str(exc)) from exc
    if bounds is None:
        return expected is None
    return (isinstance(expected, (int, float)) and not isinstance(expected, bool)
            and math.isfinite(expected)
            and bounds[0] - 1e-8 <= expected <= bounds[1] + 1e-8)


def inspect_deep_dive_contract(report: str | Path) -> dict[str, Any]:
    """Read real PBIR axes/interaction declarations, not guessed UI behavior.

    This does NOT prove default Power BI cross-filtering works when clicked.
    Drill is examined only for the named region bar chart, not globally.
    """
    root = Path(report).resolve() / "definition" / "pages" / DEEP_DIVE_PAGE
    result = {"structural": "blocked", "region_bar_drill": "unknown",
              "runtime_interaction": "not_run"}
    try:
        page = json.loads((root / "page.json").read_text(encoding="utf-8"))
        _require(page.get("name") == DEEP_DIVE_PAGE,
                 "fail", "Deep Dive page identity mismatch")
        refs = (
            ("slicer-year", "slicer", "Values", "Dim Date.Year"),
            ("sales-by-country", "shapeMap", "Category", "Dim Store.Country"),
            ("what-drives-sales", "clusteredBarChart", "Category", "Dim Store.Region"),
        )
        for name, visual_type, role, projected in refs:
            file = root / "visuals" / name / "visual.json"
            visual = json.loads(file.read_text(encoding="utf-8"))["visual"]
            _require(visual.get("visualType") == visual_type,
                     "fail", f"{name} visual type changed")
            projections = visual["query"]["queryState"][role]["projections"]
            _require(isinstance(projections, list) and projections
                     and projections[0].get("queryRef") == projected,
                     "fail", f"{name} field binding changed")
            if name in ("sales-by-country", "what-drives-sales"):
                sales_role = "Value" if name == "sales-by-country" else "Y"
                measure = visual["query"]["queryState"][sales_role]["projections"]
                _require(isinstance(measure, list) and measure
                         and measure[0].get("queryRef") ==
                         "Fact Sales.Reporting Year Sales",
                         "fail", f"{name} sales measure binding changed")
            if name == "what-drives-sales":
                result["region_bar_drill"] = (
                    "not_declared_for_single_region_axis" if len(projections) == 1
                    else "hierarchy_requires_live_drill_test")
        forbidden_sources = {name for name, *_rest in refs}
        guarded_targets = {"card-sales", "card-units", "card-yoy", "card-gm",
                           "sales-by-country", "what-drives-sales"}
        interactions = page.get("visualInteractions", [])
        _require(isinstance(interactions, list), "blocked",
                 "invalid PBIR visual-interaction inventory")
        if any(isinstance(item, dict) and item.get("type") == "NoFilter"
               and item.get("source") in forbidden_sources
               and item.get("target") in guarded_targets
               for item in interactions):
            raise InteractionEvidenceError(
                "fail", "year/map/region source disables required KPI cross-filter")
        result["structural"] = "pass"
    except InteractionEvidenceError as exc:
        result["structural"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["reason"] = f"PBIR interaction contract unreadable: {exc}"
    return result


def _photo(event: dict[str, Any], images_dir: Path, *,
           source: str, desktop_pid: int, page: str) -> str:
    capture = event.get("capture")
    _require(isinstance(capture, dict), "blocked", "event has no screenshot binding")
    _require(capture.get("source_sha256") == source
             and capture.get("desktop_pid") == desktop_pid
             and capture.get("page_id") == page,
             "fail", "screenshot is attributed to wrong source, window or page")
    name = capture.get("file")
    _require(isinstance(name, str) and name.endswith(".png")
             and name not in (".", "..") and "/" not in name
             and "\\" not in name and ":" not in name,
             "blocked", "screenshot path must be a confined PNG basename")
    path = images_dir / name
    _require(not path.is_symlink() and path.is_file()
             and path.resolve().parent == images_dir.resolve(),
             "blocked", "screenshot missing or escaped private capture directory")
    expected = capture.get("sha256")
    _require(_hex(expected), "blocked", "screenshot SHA missing/invalid")
    # Bound read, then decode only frozen bytes; never allow a swap between
    # the recorded SHA check and decoder's second open.
    try:
        with path.open("rb") as handle:
            raw = handle.read(_PNG_FILE_CAP + 1)
    except OSError as exc:
        raise InteractionEvidenceError("blocked", f"screenshot unreadable: {exc}") from exc
    _require(len(raw) <= _PNG_FILE_CAP, "blocked", "screenshot exceeds PNG size cap")
    _require(hashlib.sha256(raw).hexdigest() == expected,
             "fail", "screenshot bytes differ from capture SHA")
    try:
        with tempfile.TemporaryDirectory(prefix="vqs-ui-image-frozen-") as scratch:
            frozen = Path(scratch) / "captured.png"
            frozen.write_bytes(raw)
            width, height, _channels, _png = _decode_png(frozen)
    except (OSError, ValueError) as exc:
        raise InteractionEvidenceError("blocked", f"unreadable screenshot: {exc}") from exc
    _require(capture.get("pixels") == [width, height],
             "fail", "screenshot dimensions differ from claimed capture")
    try:
        _require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                 "fail", "screenshot changed while decoded")
    except OSError as exc:
        raise InteractionEvidenceError("blocked", f"screenshot disappeared: {exc}") from exc
    return expected


def _year_states(oracle: object, source: str, desktop_pid: int
                 ) -> tuple[dict[int | None, dict[str, Any]], str]:
    # The schema and exact DAX query fingerprints provide basic provenance
    # checks, not cryptographic proof that a caller really executed them.
    _require(isinstance(oracle, dict) and oracle.get("semantic") == "pass"
             and oracle.get("contract") == CURRENT_SOURCE_CONTRACT
             and oracle.get("local_project_source_fingerprinted") is True,
             "blocked", "current-source, four-year live DAX oracle receipt is required")
    _require(oracle.get("source_sha256") == source
             and oracle.get("desktop_pid") == desktop_pid,
             "fail", "DAX source/PID differs from UI session")
    states = oracle.get("states")
    _require(isinstance(states, list) and len(states) == 4,
             "blocked", "All/2023/2024/2025 DAX states required")
    model_set: set[str] = set()
    indexed: dict[int | None, dict[str, Any]] = {}
    for state in states:
        _require(isinstance(state, dict) and state.get("semantic") == "pass"
                 and state.get("source_sha256") == source
                 and state.get("desktop_pid") == desktop_pid,
                 "fail", "a live year oracle is unbound or did not execute")
        year = state.get("year")
        _require(year is None or (type(year) is int and year in YEARS),
                 "blocked", "unexpected DAX year")
        _require(year not in indexed, "blocked", "duplicate DAX year")
        _require(state.get("contract") == SOURCE_CONTRACT
                 and state.get("queries") == {
                     key: hashlib.sha256(dax.encode("utf-8")).hexdigest()
                     for key, dax in build_queries(year).items()},
                 "blocked", "DAX query fingerprint is absent or altered")
        model = state.get("model")
        _require(isinstance(model, str) and bool(model),
                 "blocked", "live DAX model identity absent")
        indexed[year] = state
        model_set.add(model)
        for group, allowed in (("country", COUNTRIES), ("region", REGIONS)):
            _require(isinstance(state.get(group), dict)
                     and set(state[group]) == allowed,
                     "blocked", f"DAX {group} inventory incomplete")
        _require(isinstance(state.get("kpis"), dict)
                 and set(state["kpis"]) == {"Sales", "Units", "YoY", "GM"},
                 "blocked", "DAX KPI inventory incomplete")
    _require(set(indexed) == {None, *YEARS} and len(model_set) == 1,
             "blocked", "DAX years or model identity incomplete")
    return indexed, next(iter(model_set))


def assess_recorded_trace(oracle: object, trace: object, images_dir: str | Path
                          ) -> dict[str, Any]:
    """Fail closed on missing years, wrong filters/PID, stale images & numbers.

    This is an *evidence consistency* checker, not an input-event authenticator:
    even a numerically matching JSON transcript has ``interactive: blocked``.
    An independent Desktop operator/capability must establish real clicks,
    selected-state screenshots, cross-filter behavior, and drill affordances.
    """
    result: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "evidence_consistency": "blocked",
        "interactive": "blocked", "drill": "not_run",
        "reason": "independent executable Desktop click/selection witness absent",
    }
    try:
        _require(isinstance(trace, dict) and trace.get("schema") == SCHEMA,
                 "blocked", "typed UI trace is absent")
        source = trace.get("source_sha256")
        pid = trace.get("desktop_pid")
        page = trace.get("page_id")
        _require(_hex(source) and type(pid) is int and pid > 0
                 and page == DEEP_DIVE_PAGE,
                 "blocked", "exact Deep Dive source/PID/page is required")
        states, model = _year_states(oracle, source, pid)
        _require(trace.get("model") == model, "fail", "UI/DAX model mismatch")
        events = trace.get("events")
        _require(isinstance(events, list) and len(events) == 8,
                 "blocked", "year/return/reset and two cross-filters required")
        names = [event.get("id") if isinstance(event, dict) else None
                 for event in events]
        sequence = ("year:all", "year:2023", "year:2024", "year:2025",
                    "year:2024-reset", "country:United States",
                    "clear:country", "region:Europe")
        _require(tuple(names) == sequence,
                 "blocked", "UI selection/clear sequence missing, reordered or substituted")
        seen_shas: set[str] = set()
        for event in events:
            ident = event["id"]
            recorded_hash = _photo(event, Path(images_dir),
                                   source=source, desktop_pid=pid, page=page)
            _require(recorded_hash not in seen_shas,
                     "fail", "reused/frozen screenshot across different UI states")
            seen_shas.add(recorded_hash)
            observed = event.get("observed")
            _require(isinstance(observed, dict), "blocked", f"{ident}: UI readout absent")
            if ident.startswith("year:"):
                selected = (None if ident == "year:all"
                            else int(ident.split(":")[1].split("-")[0]))
                _require(event.get("action") == "select_year"
                         and "selected_year" in observed
                         and observed["selected_year"] == selected,
                         "fail", f"{ident}: selected year contradicted recorded action")
                expected = states[selected]
                values = observed.get("kpis")
                _require(isinstance(values, dict)
                         and set(values) == {"Sales", "Units", "YoY", "GM"},
                         "blocked", f"{ident}: visible KPI inventory missing")
                for key, reference in expected["kpis"].items():
                    _require(_matches(values[key], reference,
                                      percentage=key in ("YoY", "GM")),
                             "fail", f"{ident}: visible {key} contradicts DAX")
                for group, allowed in (("country", COUNTRIES), ("region", REGIONS)):
                    labels = observed.get(group)
                    _require(isinstance(labels, dict) and set(labels) == allowed,
                             "blocked", f"{ident}: UI {group} tooltip inventory missing")
                    for item in allowed:
                        _require(_matches(labels[item], expected[group][item]),
                                 "fail", f"{ident}: visible {group}/{item} contradicts DAX")
            elif ident == "clear:country":
                _require(event.get("action") == "clear_country"
                         and observed.get("selected_category") is None
                         and event.get("year") == 2024,
                         "fail", "country selection was not cleared before region click")
                _require(_matches(observed.get("filtered_sales"),
                                  states[2024]["kpis"]["Sales"]),
                         "fail", "cleared-country sales did not return to 2024 total")
            else:
                category, selected = ident.split(":", 1)
                group = "country" if category == "country" else "region"
                _require(event.get("action") == f"select_{category}"
                         and event.get("year") == 2024
                         and observed.get("selected_category") == selected,
                         "fail", f"{ident}: cross-filter selection mismatch")
                _require(_matches(observed.get("filtered_sales"),
                                  states[2024][group][selected]),
                         "fail", f"{ident}: filtered sales differ from live DAX")
        result.update({
            "evidence_consistency": "pass", "source_sha256": source,
            "desktop_pid": pid, "page_id": page, "model": model,
            "checked_scenarios": list(sequence),
        })
    except InteractionEvidenceError as exc:
        result["evidence_consistency"] = exc.status
        result["reason"] = str(exc)
    return result
