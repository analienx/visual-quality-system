"""P14: reject fake UI parity, source drift and still-unobserved clicks."""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts import contoso_p14_interaction_assess as cli
from vqs.powerbi.contoso_runtime import (
    CURRENT_SOURCE_CONTRACT,
    SOURCE_CONTRACT,
    build_queries,
)
from vqs.powerbi.interaction_audit import (
    DEEP_DIVE_PAGE,
    SCHEMA,
    assess_recorded_trace,
    displayed_interval,
    inspect_deep_dive_contract,
)
from vqs.visual.regions import _encode_crop

SOURCE = "3" * 64
PID = 36824
MODEL = "Contoso Model"
COUNTRY = {"United States": 50., "Canada": 40., "United Kingdom": 30.,
           "Germany": 20., "Australia": 10.}
REGION = {"North America": 90., "Europe": 50., "Asia Pacific": 10.}


@pytest.mark.parametrize("label,percent,point", [
    ("$12.3M", False, 12_345_678.), ("1,200", False, 1_200.),
    ("(1.2K)", False, -1_234.), ("15.0%", True, .15),
    ("-2.5%", True, -.025), ("—", True, None),
])
def test_visible_number_rounding_interval_not_faked_exact_numbers(label, percent, point):
    interval = displayed_interval(label, percentage=percent)
    if point is None:
        assert interval is None
    else:
        assert interval[0] <= point <= interval[1]


@pytest.mark.parametrize("text,percent", [
    ("$two million", False), ("10%", False), ("10M%", False),
    ("10M%", True),
    ("(9", False), ("9)", False), ("", False),
])
def test_bad_ui_number_blocks(text, percent):
    with pytest.raises(ValueError):
        displayed_interval(text, percentage=percent)


def _state(year, factor):
    return {
        "contract": SOURCE_CONTRACT,
        "queries": {key: hashlib.sha256(dax.encode("utf-8")).hexdigest()
                    for key, dax in build_queries(year).items()},
        "source_sha256": SOURCE, "desktop_pid": PID, "year": year,
        "semantic": "pass", "model": MODEL,
        "country": {key: value * factor for key, value in COUNTRY.items()},
        "region": {key: value * factor for key, value in REGION.items()},
        "kpis": {"Sales": 150 * factor, "Units": 250 * factor,
                 "YoY": None if year == 2023 else .1,
                 "GM": .5},
    }


def _evidence(tmp_path):
    states = [_state(None, 2.0), _state(2023, 0.9),
              _state(2024, 1.0), _state(2025, 1.1)]
    oracle = {"contract": CURRENT_SOURCE_CONTRACT,
              "local_project_source_fingerprinted": True,
              "semantic": "pass", "source_sha256": SOURCE,
              "desktop_pid": PID, "states": states}
    identifiers = ["year:all", "year:2023", "year:2024", "year:2025",
                   "year:2024-reset", "country:United States",
                   "clear:country", "region:Europe"]
    events = []
    for ix, key in enumerate(identifiers):
        name = f"capture-{ix}.png"
        rgb = bytes([ix + 20, 70, 110]) * (32 * 24)
        image = _encode_crop(rgb, 32, 24, 3)
        (tmp_path / name).write_bytes(image)
        capture = {"file": name, "sha256": hashlib.sha256(image).hexdigest(),
                   "pixels": [32, 24], "source_sha256": SOURCE,
                   "desktop_pid": PID, "page_id": DEEP_DIVE_PAGE}
        if key.startswith("year:"):
            year = (None if key == "year:all"
                    else int(key.split(":")[1].split("-")[0]))
            state = next(st for st in states if st["year"] == year)
            observed = {
                "selected_year": year,
                "kpis": {"Sales": f"${state['kpis']['Sales']:.1f}",
                         "Units": f"{state['kpis']['Units']:.1f}",
                         "YoY": "—" if state["kpis"]["YoY"] is None else "10.0%",
                         "GM": "50.0%"},
                "country": {name: f"${value:.1f}"
                            for name, value in state["country"].items()},
                "region": {name: f"${value:.1f}"
                           for name, value in state["region"].items()},
            }
            event = {"id": key, "action": "select_year", "capture": capture,
                     "observed": observed}
        elif key == "clear:country":
            event = {"id": key, "action": "clear_country", "year": 2024,
                     "capture": capture,
                     "observed": {"selected_category": None,
                                  "filtered_sales": "$150.0"}}
        else:
            group, name_selected = key.split(":")
            expected = states[2][group][name_selected]
            event = {"id": key, "action": f"select_{group}", "year": 2024,
                     "capture": capture,
                     "observed": {"selected_category": name_selected,
                                  "filtered_sales": f"${expected:.1f}"}}
        events.append(event)
    return oracle, {"schema": SCHEMA, "source_sha256": SOURCE,
                    "desktop_pid": PID, "model": MODEL,
                    "page_id": DEEP_DIVE_PAGE, "events": events}


def _audit(tmp_path, change=None):
    oracle, trace = _evidence(tmp_path)
    if change:
        change(oracle, trace)
    return assess_recorded_trace(oracle, trace, tmp_path)


def test_full_matching_transcript_is_consistency_only_not_fake_ui_acceptance(tmp_path):
    result = _audit(tmp_path)
    assert result["evidence_consistency"] == "pass"
    assert result["interactive"] == "blocked"
    assert result["drill"] == "not_run"
    assert len(result["checked_scenarios"]) == 8
    assert "witness absent" in result["reason"]


@pytest.mark.parametrize("change,expected", [
    (lambda a,t: t["events"][0]["observed"]["kpis"].__setitem__("Sales", "$999"), "fail"),
    (lambda a,t: t["events"][1]["observed"].__setitem__("selected_year", 2025), "fail"),
    (lambda a,t: t["events"][2]["observed"]["country"].__setitem__("Canada", "$999"), "fail"),
    (lambda a,t: t["events"][3]["observed"].__delitem__("region"), "blocked"),
    (lambda a,t: t["events"][5]["observed"].__setitem__("filtered_sales", "$1000"), "fail"),
    (lambda a,t: t["events"][6]["observed"].__setitem__("filtered_sales", "$50"), "fail"),
    (lambda a,t: t["events"][7]["observed"].__setitem__("selected_category", "Canada"), "fail"),
    (lambda a,t: t["events"].pop(), "blocked"),
    (lambda a,t: t["events"][0].__setitem__("id", "year:2024"), "blocked"),
    (lambda a,t: t["events"][0]["capture"].__setitem__("source_sha256", "a" * 64), "fail"),
    (lambda a,t: t["events"][0]["capture"].__setitem__("desktop_pid", 17), "fail"),
    (lambda a,t: t["events"][0]["capture"].__setitem__("sha256", "b" * 64), "fail"),
    (lambda a,t: t["events"][0]["capture"].__setitem__("pixels", [33, 24]), "fail"),
    (lambda a,t: t["events"][0]["capture"].__setitem__("file", "../escape.png"), "blocked"),
    (lambda a,t: t["events"][1]["capture"].__setitem__(
        "sha256", t["events"][0]["capture"]["sha256"]), "fail"),
    (lambda a,t: t.__setitem__("model", "wrong model"), "fail"),
    (lambda a,t: t.__setitem__("source_sha256", "b" * 64), "fail"),
    (lambda a,t: a["states"].pop(), "blocked"),
    (lambda a,t: a["states"][1].__setitem__("semantic", "blocked"), "fail"),
    (lambda a,t: a.__setitem__("semantic", "blocked"), "blocked"),
    (lambda a,t: a.__setitem__("contract", "vqs.contoso-p11-semantic-oracle/1"), "blocked"),
    (lambda a,t: a["states"][2]["queries"].__setitem__("country", "0" * 64), "blocked"),
    (lambda a,t: a["states"][3].__delitem__("queries"), "blocked"),
])
def test_forged_or_incomplete_ui_parity_rejected(tmp_path, change, expected):
    result = _audit(tmp_path, change)
    assert result["evidence_consistency"] == expected
    assert result["interactive"] == "blocked"
    assert "reason" in result


def test_frozen_screenshot_and_missing_physical_image_rejected(tmp_path):
    oracle, trace = _evidence(tmp_path)
    first, second = trace["events"][0]["capture"], trace["events"][1]["capture"]
    copy_second = copy.deepcopy(second)
    second["file"], second["sha256"] = first["file"], first["sha256"]
    assert assess_recorded_trace(oracle, trace, tmp_path)["evidence_consistency"] == "fail"
    second.clear()
    second.update(copy_second)
    (tmp_path / copy_second["file"]).unlink()
    assert assess_recorded_trace(oracle, trace, tmp_path)["evidence_consistency"] == "blocked"


def test_cli_checks_live_source_before_interpreting_ui_trace(tmp_path, monkeypatch):
    oracle, trace = _evidence(tmp_path)
    monkeypatch.setattr(cli, "source_digest", lambda _path: "e" * 64)
    result = cli.run(tmp_path, oracle, trace, tmp_path)
    assert result["evidence_consistency"] == "fail"
    assert "report source digest" in result["reason"]
    monkeypatch.setattr(cli, "source_digest", lambda _path: SOURCE)
    monkeypatch.setattr(cli, "inspect_deep_dive_contract", lambda _path: {
        "structural": "pass", "region_bar_drill": "not_declared_for_single_region_axis"})
    assert cli.run(tmp_path, oracle, trace, tmp_path)["evidence_consistency"] == "pass"


def test_cli_never_returns_success_for_unverified_clicks(tmp_path, monkeypatch, capsys):
    oracle, trace = _evidence(tmp_path)
    monkeypatch.setattr(cli, "source_digest", lambda _path: SOURCE)
    monkeypatch.setattr(cli, "inspect_deep_dive_contract", lambda _path: {
        "structural": "pass", "region_bar_drill": "not_declared_for_single_region_axis"})
    oracle_file, trace_file, output = (tmp_path / "oracle.json", tmp_path / "trace.json",
                                       tmp_path / "private-audit.json")
    oracle_file.write_text(json.dumps(oracle), encoding="utf-8")
    trace_file.write_text(json.dumps(trace), encoding="utf-8")
    args = [str(tmp_path), "--oracle", str(oracle_file), "--trace", str(trace_file),
            "--captures", str(tmp_path), "--output", str(output)]
    assert cli.main(args) == 2
    assert json.loads(output.read_text())["interactive"] == "blocked"
    assert json.loads(capsys.readouterr().out)["evidence_consistency"] == "pass"
    with pytest.raises(SystemExit, match="2"):
        cli.main(args)


def test_exact_p10_deep_dive_has_slicer_country_region_no_drill_hierarchy(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / (
        "contoso-retail-polished-insights-p10.zip")
    with zipfile.ZipFile(fixture) as archive:
        subset = [name for name in archive.namelist()
                  if name.startswith("Contoso Retail.Report/definition/pages/"
                                          + DEEP_DIVE_PAGE + "/")]
        archive.extractall(tmp_path, members=subset)
    report = tmp_path / "Contoso Retail.Report"
    result = inspect_deep_dive_contract(report)
    assert result == {
        "structural": "pass", "region_bar_drill": "not_declared_for_single_region_axis",
        "runtime_interaction": "not_run",
    }
    page_file = report / "definition/pages" / DEEP_DIVE_PAGE / "page.json"
    page = json.loads(page_file.read_text())
    page["visualInteractions"] = [{"source": "slicer-year", "target": "card-sales",
                                   "type": "NoFilter"}]
    page_file.write_text(json.dumps(page), encoding="utf-8")
    broken = inspect_deep_dive_contract(report)
    assert broken["structural"] == "fail"
    assert "disables required KPI" in broken["reason"]
