"""P16: native Desktop actions must agree with actual DAX and rendered boxes."""
from __future__ import annotations

import hashlib

import pytest

from vqs.powerbi.contoso_runtime import (
    CURRENT_SOURCE_CONTRACT,
    SOURCE_CONTRACT,
    build_queries,
)
from vqs.powerbi.desktop_uia import (
    OBSERVATION_SCHEMA,
    SCENARIOS,
    _invoke_native,
    _snapshot,
    assess_native_sequence,
)
from vqs.powerbi.interaction_audit import InteractionEvidenceError

SOURCE = "b" * 64
PID = 48552
MODEL = "test-run-owned-model"
COUNTRY = {"United States": 35., "Canada": 25., "United Kingdom": 20.,
           "Germany": 15., "Australia": 5.}
REGION = {"North America": 60., "Europe": 30., "Asia Pacific": 10.}


def _oracle() -> dict:
    states = []
    for year, factor in ((None, 2.), (2023, .8), (2024, 1.), (2025, 1.1)):
        states.append({
            "contract": SOURCE_CONTRACT,
            "year": year, "desktop_pid": PID, "source_sha256": SOURCE,
            "model": MODEL, "semantic": "pass",
            "queries": {key: hashlib.sha256(dax.encode()).hexdigest()
                        for key, dax in build_queries(year).items()},
            "kpis": {"Sales": 100 * factor, "Units": 200 * factor,
                     "YoY": None if year == 2023 else .1, "GM": .333},
            "region": {key: val * factor for key, val in REGION.items()},
            "country": {key: val * factor for key, val in COUNTRY.items()},
        })
    return {"contract": CURRENT_SOURCE_CONTRACT, "semantic": "pass",
            "source_sha256": SOURCE, "desktop_pid": PID,
            "local_project_source_fingerprinted": True, "states": states}


def _observation(index: int) -> dict:
    scenario, action, value, year = SCENARIOS[index]
    factor = {None: 2., 2023: .8, 2024: 1., 2025: 1.1}[year]
    region_active = scenario == "region:Europe"
    sales = REGION["Europe"] * factor if region_active else 100 * factor
    coords = {
        "Sales": [100, 550, 300, 80],
        "Units": [430, 550, 300, 80],
        "YoY": [760, 550, 300, 80],
        "GM": [1090, 550, 300, 80],
    }
    rows = []
    for ri, (name, val) in enumerate(REGION.items()):
        yy = 1000 + ri * 55
        rows.append({"name": name, "sales": val * factor,
                     "selected": region_active and name == "Europe",
                     "label_rect": [800, yy + 10, 90, 20],
                     "bar_rect": [900, yy, 300, 40]})
    return {
        "schema": OBSERVATION_SCHEMA,
        "desktop_pid": PID, "window_title": "Contoso Retail",
        "action": action, "requested_value": value,
        "method": ("read_only" if action == "probe" else
                   "SelectionItemPattern.RemoveFromSelection"
                   if action == "clear-region" else
                   "SelectionItemPattern" if value == "All" else
                   "SelectionItemPattern.Select"),
        "utc": "2026-10-19T09:00:00Z",
        "action_rect": None if action == "probe" else [100, 400, 320, 35],
        "observed": {
            "year": "All" if year is None else str(year),
            "kpis": {"Sales": f"${sales:g}",
                     "Units": f"{200*factor:g}",
                     "YoY": "—" if year == 2023 else "10.0%",
                     "GM": "33.3%"},
            "kpi_rects": coords,
            "kpi_title_rects": {
                name: [rect[0], 520, 300, 25] for name, rect in coords.items()
            },
            "year_label_rect": [105, 360, 200, 35],
            "year_rect": [100, 400, 320, 35],
            "layout_rects": {
                "Sales": [90, 510, 320, 120],
                "Units": [420, 510, 320, 120],
                "YoY": [750, 510, 320, 120],
                "GM": [1080, 510, 320, 120],
                "Map": [90, 645, 650, 500],
                "Channel": [750, 645, 650, 240],
                "Regional": [750, 900, 650, 240],
            },
            "regions": rows,
        },
    }


def _run_fake(change=None) -> dict:
    events = [_observation(ix) for ix in range(len(SCENARIOS))]
    if change:
        change(events)
    iterator = iter(events)

    def invoke(_pid: int, action: str, value: str) -> dict:
        item = next(iterator)
        assert (item["action"], item["requested_value"]) == (action, value)
        return item

    return assess_native_sequence(_oracle(), SOURCE, PID, invoke=invoke)


@pytest.mark.parametrize("year_method,clear_method", [
    ("SelectionItemPattern.Select", "SelectionItemPattern.RemoveFromSelection"),
    ("TogglePattern.ToggleOn", "TogglePattern.ToggleOff"),
])
def test_native_year_selection_patterns_preserve_exact_readbacks(
    year_method: str, clear_method: str,
) -> None:
    def use_supported_patterns(events: list[dict]) -> None:
        for event in events:
            if event["action"] != "year":
                continue
            event["method"] = (
                clear_method if event["requested_value"] == "All"
                else year_method
            )
    result = _run_fake(use_supported_patterns)
    assert result["native_uia"] == "pass"
    assert len(result["events"]) == len(SCENARIOS)


@pytest.mark.parametrize("bad_method", [
    "TogglePattern.ToggleOff",
    "InvokePattern.Invoke",
    "TogglePattern",
])
def test_wrong_year_toggle_direction_fails_closed(bad_method: str) -> None:
    def corrupt(events: list[dict]) -> None:
        event = next(x for x in events if x["action"] == "year"
                     and x["requested_value"] == "2024")
        event["method"] = bad_method
    result = _run_fake(corrupt)
    assert result["native_uia"] in ("fail", "blocked")


def test_all_native_years_region_and_clear_have_concrete_numeric_witness():
    result = _run_fake()
    assert result["native_uia"] == "pass"
    assert len(result["events"]) == len(SCENARIOS)
    assert result["events"][-2]["observed"]["regions"][1]["name"] == "Europe"
    assert result["interactive"] == "blocked"
    assert result["independent_acceptance"] == "blocked"
    assert result["country_map"] == "blocked"


@pytest.mark.parametrize("change,expected", [
    (lambda es: es[2].__setitem__("desktop_pid", 99), "blocked"),
    (lambda es: es[2]["observed"].__setitem__("year", "2024"), "fail"),
    (lambda es: es[2]["observed"]["kpis"].__setitem__("Sales", "$999"), "fail"),
    (lambda es: es[3]["observed"]["kpis"].__setitem__("YoY", "—"), "fail"),
    (lambda es: es[4]["observed"]["kpi_rects"]["GM"].__setitem__(1, 600), "fail"),
    (lambda es: es[4]["observed"]["kpi_rects"]["GM"].__setitem__(0, 950), "fail"),
    (lambda es: es[3]["observed"]["kpi_title_rects"]["Units"].__setitem__(1, 600), "fail"),
    (lambda es: es[4]["observed"]["kpi_title_rects"]["Sales"].__setitem__(3, 90), "fail"),
    (lambda es: es[5]["observed"]["year_label_rect"].__setitem__(1, 390), "fail"),
    (lambda es: es[2]["observed"]["layout_rects"]["Map"].__setitem__(0, 150), "fail"),
    (lambda es: es[3]["observed"]["layout_rects"]["Units"].__setitem__(3, 240), "fail"),
    (lambda es: es[4]["observed"]["layout_rects"]["Channel"].__setitem__(1, 675), "fail"),
    (lambda es: es[5]["observed"]["layout_rects"]["Regional"].__setitem__(0, 790), "fail"),
    (lambda es: es[4]["observed"]["regions"][0].__setitem__("sales", 999), "fail"),
    (lambda es: es[5]["observed"]["regions"][0].__setitem__(
        "label_rect", [800, 200, 90, 20]), "fail"),
    (lambda es: es[6]["observed"]["regions"][1].__setitem__("selected", False), "fail"),
    (lambda es: es[7]["observed"]["regions"][0].__setitem__("selected", True), "fail"),
    (lambda es: es[5]["observed"]["regions"].pop(), "blocked"),
    (lambda es: es[5]["observed"]["kpis"].pop("Sales"), "blocked"),
    (lambda es: es[2].__setitem__("method", "SendInput"), "blocked"),
])
def test_forged_misaligned_or_stale_native_states_rejected(change, expected):
    result = _run_fake(change)
    assert result["native_uia"] == expected
    assert len(result["events"]) < len(SCENARIOS)


def test_real_action_with_unsupported_primitive_fails_closed():
    item = _observation(6)
    item["method"] = "Click"
    with pytest.raises(InteractionEvidenceError, match="UIA method"):
        _snapshot(item, PID, action="region", value="Europe", year=2024,
                  oracle=_oracle()["states"][2], scenario="region:Europe")


def test_invalid_live_dax_receipt_cannot_promote_native_uia():
    fake = _oracle()
    fake["states"][2]["queries"]["region"] = "0" * 64
    result = assess_native_sequence(fake, SOURCE, PID,
                                    invoke=lambda *_: pytest.fail("must not interact"))
    assert result["native_uia"] == "blocked"


def test_windows_ui_adapter_not_called_on_other_os(monkeypatch):
    from vqs.powerbi import desktop_uia

    monkeypatch.setattr(desktop_uia.os, "name", "posix")
    with pytest.raises(InteractionEvidenceError, match="needs Windows"):
        _invoke_native(PID, "probe", "")


def test_minimized_desktop_diagnosis_never_silently_restores_window():
    """Bridge connectivity is not proof the Win32/UIA canvas is rendered."""
    from pathlib import Path

    adapter = (Path(__file__).resolve().parents[1] /
               "scripts/windows/contoso_native_uia.ps1").read_text(
                   encoding="utf-8")
    assert "WindowVisualState]::Minimized" in adapter
    assert "BoundingRectangle.IsEmpty" in adapter
    assert "target Desktop window is minimized/unrendered" in adapter
    assert "SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Normal)" not in adapter


def test_native_year_action_restores_collapsed_slicer_after_value_change():
    """Visible dropdown state is part of a clean before/after screenshot."""
    from pathlib import Path

    native = (Path(__file__).resolve().parents[1] /
              "scripts/windows/contoso_native_uia.ps1").read_text(
                  encoding="utf-8")
    begin = native.index("# A completed Year action must leave the slicer")
    end = native.index("# Power BI redraws its accessibility subtree", begin)
    cleanup = native[begin:end]
    assert "if ($Action -eq 'year')" in cleanup
    assert "Find-Exact $currentReport 'Year'" in cleanup
    assert "$currentExpand.Collapse()" in cleanup
    assert "$collapsed = $true" in cleanup
    assert "if (-not $collapsed)" in cleanup
    assert "did not restore collapsed UI state" in cleanup
    assert begin < native.index("$observed = $null", end)
