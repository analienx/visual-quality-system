"""Positive and deliberate negative controls for P11 executed DAX evidence."""
from __future__ import annotations

import hashlib
import zipfile
from copy import deepcopy

import pytest

from scripts import contoso_p11_semantic_probe as cli
from vqs.powerbi.contoso_runtime import (
    COUNTRIES,
    REGIONS,
    build_queries,
    collect,
    compare_ui,
)

SHA = "a" * 64
COUNTRY = {"United States": 100.0, "Canada": 20.0,
           "United Kingdom": 50.0, "Germany": 30.0, "Australia": 10.0}
REGION = {"North America": 120.0, "Europe": 80.0, "Asia Pacific": 10.0}
KPI = {"Sales": 210.0, "Units": 99.0, "YoY": 0.10, "GM": 0.34}


class FakePort:
    def __init__(self) -> None:
        self.tables = {
            "country": [{"[Key]": k, "[Sales]": v} for k, v in COUNTRY.items()],
            "region": [{"[Key]": k, "[Sales]": v} for k, v in REGION.items()],
            "kpis": [{f"[{k}]": v for k, v in KPI.items()}],
        }
        self.calls = []
        self.available = True
        self.bad_context = False

    def connect(self):
        if not self.available:
            raise OSError("no local owned model")
        return {"model": "localhost:123/P10", "desktopPid": 4242}

    def readiness(self, scope):
        return {"populated": self.available}

    def close(self):
        pass

    def query_scoped(self, dax, scope, max_rows=100):
        self.calls.append((dax, scope, max_rows))
        key = ("country" if "[Country]" in dax else
               "region" if "[Region]" in dax else "kpis")
        return {"rows": deepcopy(self.tables[key]), "context": {
            "model": scope.model,
            "source_sha256": scope.source_sha256,
            "query_sha256": ("0" * 64 if self.bad_context else
                             hashlib.sha256(dax.encode("utf-8")).hexdigest()),
        }}


def test_year_filter_is_real_dax_not_fake_metadata():
    all_queries = build_queries(None)
    yearly = build_queries(2024)
    assert all("TREATAS" not in q for q in all_queries.values())
    assert all("TREATAS ( { 2024 }, 'Dim Date'[Year] )" in q for q in yearly.values())
    assert all("'Fact Sales'[Reporting Year Sales]" in q for q in yearly.values())
    assert "CALCULATETABLE" in yearly["kpis"]
    for invalid in (0, 2026, True, "2024", 2024.0):
        with pytest.raises(ValueError):
            build_queries(invalid)


def test_live_oracle_covers_all_values_and_blocks_ui_claims():
    port = FakePort()
    result = collect(port, SHA, 2024)
    assert result["semantic"] == "pass"
    assert result["interactive"] == "not_run"
    assert set(result["country"]) == COUNTRIES
    assert set(result["region"]) == REGIONS
    assert result["kpis"] == KPI
    assert all(call[1].filters is None and call[1].period is None for call in port.calls)
    assert all("TREATAS" in call[0] for call in port.calls)
    assert all(call[2] == 25 for call in port.calls)


@pytest.mark.parametrize("mutation", [
    "no_model", "bad_context", "missing_country", "wrong_country",
    "duplicate_country", "bad_region", "regional_total", "nonfinite",
    "negative", "blank_kpi", "wrong_schema",
])
def test_fail_closed_on_live_data_errors(mutation):
    port = FakePort()
    if mutation == "no_model":
        port.available = False
    if mutation == "bad_context":
        port.bad_context = True
    if mutation == "missing_country":
        port.tables["country"].pop()
    if mutation == "wrong_country":
        port.tables["country"][0]["[Key]"] = "United States of America"
    if mutation == "duplicate_country":
        port.tables["country"][0]["[Key]"] = "Canada"
    if mutation == "bad_region":
        port.tables["region"][0]["[Key]"] = "Northern America"
    if mutation == "regional_total":
        port.tables["region"][0]["[Sales]"] = 500.0
    if mutation == "nonfinite":
        port.tables["country"][0]["[Sales]"] = float("nan")
    if mutation == "negative":
        port.tables["country"][0]["[Sales]"] = -1.0
    if mutation == "blank_kpi":
        port.tables["kpis"][0]["[Sales]"] = None
    if mutation == "wrong_schema":
        port.tables["kpis"][0]["[Extra]"] = 7
    result = collect(port, SHA, 2024)
    assert result["semantic"] == "blocked"
    assert result["interactive"] == "not_run"
    assert "reason" in result


def test_missing_source_blocks_before_model_connection():
    port = FakePort()
    for sha in ("", "A" * 64, "a" * 63, None):
        assert collect(port, sha, None)["semantic"] == "blocked"
    assert port.calls == []


def test_negative_yoy_and_blank_initial_year_are_legitimate():
    port = FakePort()
    port.tables["kpis"][0]["[YoY]"] = -0.17
    assert collect(port, SHA, 2024)["semantic"] == "pass"
    port.tables["kpis"][0]["[YoY]"] = None
    result = collect(port, SHA, 2023)
    assert result["semantic"] == "pass"
    assert result["kpis"]["YoY"] is None


def test_ui_comparison_exact_year_source_and_numbers():
    receipt = collect(FakePort(), SHA, None)
    observation = {"source_sha256": SHA, "year": None,
                   "country": dict(COUNTRY), "region": dict(REGION)}
    assert compare_ui(receipt, None)["verdict"] == "blocked"
    assert compare_ui(receipt, observation) == {
        "verdict": "pass", "scope": "numeric map tooltip/region values only",
        "interactive": "not_run",
    }
    wrong = deepcopy(observation)
    wrong["year"] = 2024
    assert compare_ui(receipt, wrong)["verdict"] == "fail"
    wrong = deepcopy(observation)
    wrong["source_sha256"] = "b" * 64
    assert compare_ui(receipt, wrong)["verdict"] == "fail"
    wrong = deepcopy(observation)
    wrong["country"]["Germany"] = 31
    assert compare_ui(receipt, wrong)["verdict"] == "fail"
    wrong = deepcopy(observation)
    del wrong["region"]["Europe"]
    assert compare_ui(receipt, wrong)["verdict"] == "blocked"
    wrong = deepcopy(observation)
    wrong["region"]["Europe"] = "not a number"
    assert compare_ui(receipt, wrong)["verdict"] == "blocked"


def test_cli_refuses_wrong_project_before_mcp(tmp_path, monkeypatch):
    class NoClient:
        def __init__(self, **_kw):
            raise AssertionError("must never connect for mismatched source")

    monkeypatch.setattr(cli, "StdioModelingClient", NoClient)
    result = cli.run(tmp_path, 12, [None, 2024])
    assert result["semantic"] == "blocked"
    report = tmp_path / "Contoso Retail.Report"
    report.mkdir()
    result = cli.run(tmp_path, 12, [None])
    assert result["semantic"] == "blocked"
    assert "drift" in result["reason"] or "missing" in result["reason"]


def test_exact_archived_project_accepts_valid_fingerprint(tmp_path, monkeypatch):
    with zipfile.ZipFile(cli.FIXTURE) as archive:
        archive.extractall(tmp_path)
    monkeypatch.setattr(cli, "StdioModelingClient", lambda **kw: FakePort())
    # The fake uses a deliberately different PID, illustrating why the
    # semantic-only receipt cannot claim Desktop runtime binding verified.
    result = cli.run(tmp_path, 42, [None, 2024])
    assert result["semantic"] == "pass"
    assert result["interactive"] == "not_run"
    assert result["source_verified_against_p10_fixture"] is True
    assert result["source_sha256"] == result["p10_historical_fingerprint"]
    assert len(result["vqs_runtime_source_digest"]) == 64
    assert all(s["source_sha256"] == result["source_sha256"] for s in result["states"])
    assert len(result["states"]) == 2
    visual = tmp_path / (
        "Contoso Retail.Report/definition/pages/d9bc3b8f90439bcc/"
        "visuals/sales-by-country/visual.json")
    visual.write_bytes(visual.read_bytes() + b" ")
    blocked = cli.run(tmp_path, 42, [None])
    assert blocked["semantic"] == "blocked"
    assert "drift" in blocked["reason"]
