"""P16: source-bound, native Power BI Desktop UI Automation interaction witness.

This executes real UIA SelectionItemPattern actions against an *already-open,
disposable* Contoso Desktop PID, then reads the actual accessibility tree.
No paid cloud service, driver, pointer injection or unlocked session required.
The Shape Map still lacks country UIA children, so full G4 remains blocked.

Windows:
  python -m scripts.contoso_p16_native_interaction \
      C:\\Workspace\\scratch\\disposable-Contoso-project \
      --desktop-pid 12345 --oracle C:\\private\\live-oracle.json \
      --output C:\\private\\native-uia-witness.json
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

from vqs.powerbi.contoso_project import inventory
from vqs.powerbi.desktop_source import (
    collect as attest_desktop_source,
)
from vqs.powerbi.desktop_source import (
    strict_local_model_attested,
)
from vqs.powerbi.interaction_audit import (
    DEEP_DIVE_PAGE,
    InteractionEvidenceError,
    _matches,
    _require,
    _year_states,
    inspect_deep_dive_contract,
)

SCHEMA = "vqs.contoso-native-desktop-uia/1"
OBSERVATION_SCHEMA = "vqs.native-desktop-uia-observation/1"
SCENARIOS = (
    ("baseline", "probe", "", None),
    ("year:all", "year", "All", None),
    ("year:2023", "year", "2023", 2023),
    ("year:2024", "year", "2024", 2024),
    ("year:2025", "year", "2025", 2025),
    ("year:2024-reset", "year", "2024", 2024),
    ("region:Europe", "region", "Europe", 2024),
    ("clear:region", "clear-region", "", 2024),
    ("year:all-restored", "year", "All", None),
)
REGIONS = frozenset(("Europe", "North America", "Asia Pacific"))


def _rect(value: Any) -> tuple[int, int, int, int]:
    _require(isinstance(value, list) and len(value) == 4
             and all(type(x) is int for x in value)
             and value[2] > 0 and value[3] > 0
             and all(abs(v) < 100_000 for v in value),
             "blocked", "native UIA returned an invalid element rectangle")
    return tuple(value)


def _snapshot(observation: Any, pid: int, *, action: str, value: str,
              year: int | None, oracle: dict, scenario: str) -> dict:
    """Check *rendered* accessibility values against unrounded executed DAX.

    The adapter must have chosen exactly the target PID, action, and control.
    This is not an independently signed execution receipt: the operator and
    live project's identity must still be reviewed before promotion.
    """
    _require(isinstance(observation, dict)
             and observation.get("schema") == OBSERVATION_SCHEMA
             and observation.get("desktop_pid") == pid
             and isinstance(observation.get("window_title"), str)
             and observation["window_title"].startswith("Contoso Retail")
             and observation.get("action") == action
             and observation.get("requested_value") == value
             and isinstance(observation.get("utc"), str),
             "fail", f"{scenario}: native window/PID/action provenance contradicted")
    method = observation.get("method")
    _require(method in ("read_only", "SelectionItemPattern",
                        "SelectionItemPattern.Select",
                        "SelectionItemPattern.RemoveFromSelection",
                        "TogglePattern.ToggleOn", "TogglePattern.ToggleOff"),
             "blocked", f"{scenario}: UIA method not allowlisted")
    if action == "probe":
        _require(method == "read_only", "fail", "a read-only probe reports interaction")
    elif action == "region":
        _require(method == "SelectionItemPattern.Select", "fail",
                 "region action did not use selection pattern")
    elif action == "clear-region":
        _require(method == "SelectionItemPattern.RemoveFromSelection", "fail",
                 "region clear did not use RemoveFromSelection")
    elif action == "year":
        expected_methods = (("SelectionItemPattern",
                             "SelectionItemPattern.RemoveFromSelection",
                             "TogglePattern.ToggleOff")
                            if value == "All" else
                            ("SelectionItemPattern.Select", "TogglePattern.ToggleOn"))
        _require(method in expected_methods, "fail",
                 "Year input did not use the exact allowed selection pattern")
    data = observation.get("observed")
    _require(isinstance(data, dict), "blocked", f"{scenario}: missing native readback")
    label = "All" if year is None else str(year)
    _require(data.get("year") == label, "fail",
             f"{scenario}: displayed Year is {data.get('year')!r}, expected {label}")
    values = data.get("kpis")
    _require(isinstance(values, dict) and set(values) == {"Sales", "Units", "YoY", "GM"},
             "blocked", f"{scenario}: missing or duplicated native KPI")
    expected = oracle["kpis"]
    for key in ("Sales", "Units", "YoY", "GM"):
        if scenario == "region:Europe" and key != "Sales":
            # The four-year oracle has no region-scoped DAX for other measures.
            continue
        expected_value = (oracle["region"]["Europe"]
                          if scenario == "region:Europe" and key == "Sales"
                          else expected[key])
        _require(_matches(values[key], expected_value,
                          percentage=key in ("YoY", "GM")),
                 "fail", f"{scenario}: rendered {key} disagrees with live DAX")
    kpi_rects = data.get("kpi_rects")
    _require(isinstance(kpi_rects, dict)
             and set(kpi_rects) == {"Sales", "Units", "YoY", "GM"},
             "blocked", "native card bounds incomplete")
    rects = [_rect(kpi_rects[key]) for key in ("Sales", "Units", "YoY", "GM")]
    # Native rendered card accessibility boxes have a common baseline and
    # height; catch a tall/misaligned KPI row without trusting PBIR geometry.
    median_height = sorted(rect[3] for rect in rects)[1]
    _require(median_height >= 20
             and max(rect[1] for rect in rects) -
             min(rect[1] for rect in rects) <= max(8, median_height * .1)
             and max(rect[3] for rect in rects) -
             min(rect[3] for rect in rects) <= max(8, median_height * .1),
             "fail", f"{scenario}: KPI readouts are vertically misaligned")
    ordered = sorted(rects)
    _require(all(left[0] + left[2] <= right[0]
                 for left, right in pairwise(ordered)),
             "fail", f"{scenario}: KPI readout boxes overlap horizontally")
    title_rects = data.get("kpi_title_rects")
    _require(isinstance(title_rects, dict)
             and set(title_rects) == {"Sales", "Units", "YoY", "GM"},
             "blocked", "native KPI title rectangles incomplete")
    headings = [_rect(title_rects[key]) for key in ("Sales", "Units", "YoY", "GM")]
    _require(max(heading[1] for heading in headings) -
             min(heading[1] for heading in headings) <= 8,
             "fail", f"{scenario}: KPI headings are not baseline-aligned")
    for key, caption, number in zip(("Sales", "Units", "YoY", "GM"), headings, rects):
        gap = number[1] - (caption[1] + caption[3])
        _require(0 <= gap <= max(20, median_height * .3)
                 and abs(caption[0] - number[0]) <= max(12, number[2] * .05)
                 and caption[3] < number[3] <= caption[3] * 4,
                 "fail", f"{scenario}: {key} title/value padding or card height disagrees")
    year_rect = _rect(data.get("year_rect"))
    year_label = _rect(data.get("year_label_rect"))
    _require(year_label[1] + year_label[3] <= year_rect[1]
             and year_rect[1] + year_rect[3] <= min(h[1] for h in headings)
             and abs(year_rect[0] - year_label[0]) <= max(20, year_rect[2] * .1),
             "fail", f"{scenario}: Reporting year label/dropdown overlaps KPI row")
    layout = data.get("layout_rects")
    _require(isinstance(layout, dict)
             and set(layout) == {"Sales", "Units", "YoY", "GM",
                                 "Map", "Channel", "Regional"},
             "blocked", "native card/panel grid rectangles incomplete")
    cards = [_rect(layout[key]) for key in ("Sales", "Units", "YoY", "GM")]
    panels = {key: _rect(layout[key]) for key in ("Map", "Channel", "Regional")}
    card_top = min(item[1] for item in cards)
    card_height = sorted(item[3] for item in cards)[1]
    _require(max(item[1] for item in cards) - card_top <= 8
             and max(item[3] for item in cards) -
             min(item[3] for item in cards) <= max(8, card_height * .05)
             and all(a[0] + a[2] < b[0] for a, b in pairwise(cards)),
             "fail", f"{scenario}: KPI card containers differ in row height or overlap")
    for name, card, title, value_rect in zip(
            ("Sales", "Units", "YoY", "GM"), cards, headings, rects):
        _require(all(card[0] <= r[0] and r[0] + r[2] <= card[0] + card[2]
                     and card[1] <= r[1] and r[1] + r[3] <= card[1] + card[3]
                     for r in (title, value_rect)),
                 "fail", f"{scenario}: {name} text escapes its KPI card")
    map_panel, channel, regional = (
        panels["Map"], panels["Channel"], panels["Regional"])
    tol = max(8, card_height * .06)
    _require(abs(map_panel[1] - channel[1]) <= tol
             and 0 <= map_panel[1] - (card_top + card_height) <= 40
             and abs(map_panel[0] - cards[0][0]) <= tol
             and abs(map_panel[0] + map_panel[2] -
                     (cards[1][0] + cards[1][2])) <= tol
             and abs(channel[0] - cards[2][0]) <= tol
             and abs(channel[0] + channel[2] -
                     (cards[3][0] + cards[3][2])) <= tol,
             "fail", f"{scenario}: KPI columns misalign with map/channel visuals")
    _require(abs(regional[0] - channel[0]) <= tol
             and abs(regional[2] - channel[2]) <= tol
             and 0 <= regional[1] - (channel[1] + channel[3]) <= 40,
             "fail", f"{scenario}: Regional sales misaligns with channel panel")
    rows = data.get("regions")
    _require(isinstance(rows, list) and len(rows) == 3
             and all(isinstance(row, dict) for row in rows)
             and {row.get("name") for row in rows} == REGIONS,
             "blocked", f"{scenario}: region bars/labels inventory incomplete")
    selected = []
    seen_rects = set()
    for row in rows:
        _require(type(row.get("selected")) is bool, "blocked",
                 f"{scenario}: missing native Region selection state")
        actual = row.get("sales")
        _require(isinstance(actual, (int, float))
                 and not isinstance(actual, bool) and math.isfinite(actual)
                 and math.isclose(actual, oracle["region"][row["name"]],
                                  rel_tol=0, abs_tol=.05),
                 "fail", f"{scenario}: native Region bar contradicts live DAX")
        label_rect, bar_rect = _rect(row.get("label_rect")), _rect(row.get("bar_rect"))
        _require(abs(label_rect[1] + label_rect[3] / 2 -
                     bar_rect[1] - bar_rect[3] / 2) <= 15,
                 "fail", f"{scenario}: Region value is misaligned with its label")
        _require(tuple(bar_rect) not in seen_rects, "blocked",
                 f"{scenario}: duplicated Region bar rectangle")
        seen_rects.add(tuple(bar_rect))
        if row["selected"]:
            selected.append(row["name"])
    expected_region = ["Europe"] if scenario == "region:Europe" else []
    _require(selected == expected_region, "fail",
             f"{scenario}: actual Region selected state is {selected}")
    if action == "region" or action == "year":
        _rect(observation.get("action_rect"))
    return {
        "id": scenario, "action": action, "method": method,
        "utc": observation["utc"], "year": year, "value": value,
        "action_rect": observation.get("action_rect"),
        "observed": data,
    }


def _invoke_native(pid: int, action: str, value: str) -> dict:
    if os.name != "nt":
        raise InteractionEvidenceError("blocked", "native Windows UI Automation needs Windows")
    shell = shutil.which("powershell.exe")
    if not shell:
        raise InteractionEvidenceError("blocked", "built-in Windows PowerShell unavailable")
    adapter = Path(__file__).resolve().parents[2] / "scripts" / "windows" / "contoso_native_uia.ps1"
    if not adapter.is_file():
        raise InteractionEvidenceError("blocked", "native Contoso UIA adapter missing")
    cmd = [shell, "-NoProfile", "-NonInteractive", "-File", str(adapter),
           "-DesktopProcessId", str(pid), "-Action", action]
    if value:
        cmd.extend(["-Value", value])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                check=False, timeout=35, encoding="utf-8-sig")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InteractionEvidenceError("blocked", f"native UIA execution unavailable: {exc}") from exc
    if result.returncode != 0:
        raise InteractionEvidenceError(
            "blocked", f"native UIA action {action!r} failed: {result.stderr[-700:]}")
    try:
        return json.loads(result.stdout.strip())
    except (ValueError, TypeError) as exc:
        raise InteractionEvidenceError("blocked", "native UIA result is not sole JSON") from exc


def _wait_for_state(pid: int, action: str, value: str, year: int | None,
                    oracle: dict, scenario: str, invoke: Callable[[int, str, str], dict]) -> dict:
    """A UIA selection completes before Power BI finishes its DAX redraw."""
    action_receipt = invoke(pid, action, value)
    if (not isinstance(action_receipt, dict)
            or action_receipt.get("schema") != OBSERVATION_SCHEMA
            or action_receipt.get("desktop_pid") != pid
            or action_receipt.get("action") != action
            or action_receipt.get("requested_value") != value
            or action_receipt.get("method") not in (
                "read_only", "SelectionItemPattern",
                "SelectionItemPattern.Select",
                "SelectionItemPattern.RemoveFromSelection",
                "TogglePattern.ToggleOn", "TogglePattern.ToggleOff")):
        raise InteractionEvidenceError("blocked", "native action receipt has invalid provenance")
    method = action_receipt["method"]
    if not ((action == "probe" and method == "read_only")
            or (action == "year" and
                method in (("SelectionItemPattern",
                            "SelectionItemPattern.RemoveFromSelection",
                            "TogglePattern.ToggleOff")
                           if value == "All" else
                           ("SelectionItemPattern.Select", "TogglePattern.ToggleOn")))
            or (action == "region" and method == "SelectionItemPattern.Select")
            or (action == "clear-region" and
                method == "SelectionItemPattern.RemoveFromSelection")):
        raise InteractionEvidenceError("blocked", "native action uses the wrong UIA control pattern")
    candidate = action_receipt
    deadline = time.monotonic() + 10
    while True:
        try:
            event = _snapshot(candidate, pid, action=(
                "probe" if candidate is not action_receipt else action),
                value=("" if candidate is not action_receipt else value),
                year=year, oracle=oracle, scenario=scenario)
            event["action"] = action
            event["method"] = action_receipt["method"]
            event["action_rect"] = action_receipt.get("action_rect")
            event["redraw_confirmed_by_probe"] = candidate is not action_receipt
            return event
        except InteractionEvidenceError as exc:
            if exc.status != "fail" or invoke is not _invoke_native or time.monotonic() >= deadline:
                raise
            time.sleep(.45)
            # A fresh read-only probe cannot fabricate a second input action.
            candidate = invoke(pid, "probe", "")


def assess_native_sequence(
    oracle: Mapping[str, Any], source: str, desktop_pid: int,
    *, invoke: Callable[[int, str, str], dict] = _invoke_native,
) -> dict:
    """Run allowlisted real UIA actions and compare every year/Region readback.

    Partial results are included on error. Country Shape Map, source-loaded-path
    attestation, original document preservation and independent review remain
    outside this local OS accessibility witness.
    """
    result: dict[str, Any] = {
        "schema": SCHEMA, "source_sha256": source, "desktop_pid": desktop_pid,
        "native_uia": "blocked", "interactive": "blocked",
        "country_map": "blocked", "independent_acceptance": "blocked",
        "reason": "native UI Automation sequence did not finish",
        "events": [],
        "read_only_baseline_verified": False,
        "native_actions_verified": 0,
    }
    try:
        _require(type(desktop_pid) is int and desktop_pid > 0,
                 "blocked", "positive run-owned Desktop PID required")
        states, model = _year_states(oracle, source, desktop_pid)
        result["model"] = model
        for scenario, action, value, year in SCENARIOS:
            if scenario == "baseline":
                # A prior aborted run can leave a valid non-All year selected.
                # Observe the true native displayed value; never infer it from
                # the intended starting condition or a typed caller claim.
                baseline = invoke(desktop_pid, "probe", "")
                shown = baseline.get("observed", {}).get("year") if isinstance(baseline, dict) else None
                _require(shown in ("All", "2023", "2024", "2025"), "blocked",
                         "initial native Desktop year could not be identified")
                year = None if shown == "All" else int(shown)
                event = _snapshot(baseline, desktop_pid, action="probe",
                                  value="", year=year, oracle=states[year],
                                  scenario=scenario)
            else:
                reference = states[year]
                event = _wait_for_state(desktop_pid, action, value, year,
                                        reference, scenario, invoke)
            result["events"].append(event)
            if scenario == "baseline":
                result["read_only_baseline_verified"] = True
            else:
                # A read-only baseline is evidence, not a ninth UI action.
                result["native_actions_verified"] += 1
        _require(result["read_only_baseline_verified"]
                 and result["native_actions_verified"] == len(SCENARIOS) - 1,
                 "blocked", "eight native actions and baseline probe not all verified")
        result["native_uia"] = "pass"
        result["reason"] = (
            "Eight UIA Year/Region actions plus one read-only baseline, "
            "native KPI/geometry readbacks and unrounded DAX agree; "
            "country map, loaded-file source identity, "
            "independent render review and owner release acceptance remain blocked"
        )
    except InteractionEvidenceError as exc:
        result["native_uia"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        result["reason"] = f"native UIA readback unavailable: {exc}"
    return result


def run(project: Path, desktop_pid: int, oracle: Mapping[str, Any],
        *, invoke: Callable[[int, str, str], dict] = _invoke_native,
        attest_source: bool = False,
        native_save_witness: dict[str, Any] | None = None) -> dict:
    result = {"schema": SCHEMA, "native_uia": "blocked", "interactive": "blocked",
              "country_map": "blocked", "independent_acceptance": "blocked",
              "desktop_loaded_file_attested": False}
    try:
        _require(isinstance(oracle, Mapping), "blocked",
                 "live DAX receipt is not a JSON object")
        before, wrapper_hash = inventory(project)
        report = project / "Contoso Retail.Report"
        digest = before["digest"]
        _require(oracle.get("source_sha256") == digest, "fail",
                 "current physical PBIP source differs from executed live DAX")
        if attest_source:
            identity = (attest_desktop_source(project, desktop_pid, native_save_witness=native_save_witness)
                        if native_save_witness is not None else attest_desktop_source(project, desktop_pid))
            result["desktop_loaded_file_attestation"] = identity
            _require(identity.get("loaded_file_attested") is True,
                     "blocked", "Desktop loaded-source proof missing: "
                     + str(identity.get("reason")))
            _require(strict_local_model_attested(identity), "blocked",
                     "Desktop declared local byPath semantic model unverified: "
                     + str(identity.get("local_model_reference")))
        structure = inspect_deep_dive_contract(report)
        _require(structure.get("structural") == "pass", "blocked",
                 "current PBIR interaction structure not verified")
        result = assess_native_sequence(oracle, digest, desktop_pid, invoke=invoke)
        after, wrapper_after = inventory(project)
        if before != after or wrapper_hash != wrapper_after:
            result["native_uia"] = "fail"
            result["reason"] = "physical PBIP report/model/wrapper changed during native UIA"
        result["pbir_contract"] = structure
        result["page_id"] = DEEP_DIVE_PAGE
        result["desktop_loaded_file_attested"] = (
            attest_source and before == after and wrapper_hash == wrapper_after
        )
        if attest_source:
            result["desktop_loaded_file_attestation"] = identity
            if result["native_uia"] == "pass":
                result["reason"] = (
                    "Year/Region UIA and native KPI readbacks agree with DAX; "
                    "Desktop OS/Bridge loaded-file attested. Country map and "
                    "independent release approval remain blocked"
                )
    except InteractionEvidenceError as exc:
        result["native_uia"] = exc.status
        result["reason"] = str(exc)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["reason"] = f"current Contoso project verification unavailable: {exc}"
    return result