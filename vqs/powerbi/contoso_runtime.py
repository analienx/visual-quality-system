"""P11: source-bound live Contoso country/region/year semantic oracle.

This checks *executed* DAX via the existing Microsoft Modeling MCP port.
The period is inside the DAX (TREATAS), never merely echoed in metadata:
``ModelingScope.period`` and ``filters`` deliberately do not execute filters.

An oracle proves the model's numeric answers, not that Desktop rendered the
numbers, handled hover/click, or applied the report slicer. UI acceptance is a
separate gate, explicitly BLOCKED until independently observed.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any, cast

from vqs.powerbi.contoso_goldens import PINNED_DAX_SHA256, PINNED_REGION_EUROPE_2024_SHA256
from vqs.powerbi.modeling import ModelingScope

COUNTRIES = frozenset({
    "United States", "Canada", "United Kingdom", "Germany", "Australia",
})
REGIONS = frozenset({"North America", "Europe", "Asia Pacific"})
YEARS = frozenset({2023, 2024, 2025})
MEASURE = "'Fact Sales'[Reporting Year Sales]"
SOURCE_CONTRACT = "vqs.contoso-p11-semantic-oracle/1"
CURRENT_SOURCE_CONTRACT = "vqs.contoso-p14-current-live-oracle/1"


def _year_filter(year: int | None) -> str:
    if year is None:
        return ""
    if type(year) is not int or year not in YEARS:
        raise ValueError("year must be All (null), 2023, 2024 or 2025")
    return f"TREATAS ( {{ {year} }}, 'Dim Date'[Year] )"


def _group_query(column: str, year: int | None) -> str:
    if column not in ("Country", "Region"):
        raise ValueError("unsupported Contoso grouping")
    filter_arg = f"{_year_filter(year)},\n        " if year is not None else ""
    return (
        "EVALUATE\n"
        "SELECTCOLUMNS (\n"
        "    SUMMARIZECOLUMNS (\n"
        f"        'Dim Store'[{column}],\n"
        f"        {filter_arg}\"__vqs_sales\", {MEASURE}\n"
        "    ),\n"
        f"    \"Key\", 'Dim Store'[{column}],\n"
        "    \"Sales\", [__vqs_sales]\n"
        ")\n"
        "ORDER BY [Key]"
    )


def build_queries(year: int | None) -> dict[str, str]:
    """Generate exactly the report's measure at All or one validated year."""
    filt = _year_filter(year)
    kpis = (
        'ROW ( "Sales", ' + MEASURE + ', '
        '"Units", \'Fact Sales\'[Reporting Year Units], '
        '"YoY", \'Fact Sales\'[Reporting Year Sales YoY %], '
        '"GM", \'Fact Sales\'[Reporting Year GM %] )'
    )
    if filt:
        kpis = f"CALCULATETABLE ( {kpis}, {filt} )"
    return {
        "country": _group_query("Country", year),
        "region": _group_query("Region", year),
        "kpis": f"EVALUATE\n{kpis}",
    }



# This is a separately reviewed fixed query, not a new synthetic KPI oracle.
# The explicit pair of TREATAS filters reproduces Year=2024 + Region=Europe.
REGION_EUROPE_2024_DAX = (
    'EVALUATE\n'
    'CALCULATETABLE (\n'
    '    ROW ( "Sales", \'Fact Sales\'[Reporting Year Sales], '
    '"Units", \'Fact Sales\'[Reporting Year Units], '
    '"YoY", \'Fact Sales\'[Reporting Year Sales YoY %], '
    '"GM", \'Fact Sales\'[Reporting Year GM %] ),\n'
    '    TREATAS ( { 2024 }, \'Dim Date\'[Year] ),\n'
    '    TREATAS ( { "Europe" }, \'Dim Store\'[Region] )\n'
    ')'
)
REGION_EUROPE_2024_CONTRACT = "vqs.contoso-region-europe-kpis/1"


def _column(row: Mapping[str, Any], name: str) -> Any:
    # Microsoft DAX query results may prefix named columns with [name].
    candidates = [v for k, v in row.items() if k in (name, f"[{name}]")]
    if len(candidates) != 1:
        raise ValueError(f"missing/ambiguous DAX output column: {name}")
    return candidates[0]


def _number(value: Any, *, signed: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("DAX value missing or not numeric")
    if not math.isfinite(value) or (value < 0 and not signed):
        raise ValueError("DAX value negative/non-finite")
    return float(value)


def _groups(rows: Any, allowed: frozenset[str]) -> dict[str, float]:
    if not isinstance(rows, list) or len(rows) != len(allowed):
        raise ValueError("country/region row inventory incomplete")
    out: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) not in (
                {"Key", "Sales"}, {"[Key]", "[Sales]"}):
            raise ValueError("unexpected DAX group row schema")
        key = _column(row, "Key")
        if not isinstance(key, str) or key not in allowed or key in out:
            raise ValueError("unmatched or duplicate Contoso geography")
        out[key] = _number(_column(row, "Sales"))
    if set(out) != allowed:
        raise ValueError("country/region category mismatch")
    return dict(sorted(out.items()))


def _kpis(rows: Any) -> dict[str, float | None]:
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("expected exactly one KPI row")
    row = rows[0]
    if set(row) not in (
            {"Sales", "Units", "YoY", "GM"},
            {"[Sales]", "[Units]", "[YoY]", "[GM]"}):
        raise ValueError("unexpected KPI row schema")
    result: dict[str, float | None] = {
        name: _number(_column(row, name))
        for name in ("Sales", "Units", "GM")
    }
    yoy = _column(row, "YoY")
    # In 2023 the Contoso model has no prior year; DIVIDE legitimately
    # returns BLANK. Falling sales can also produce a negative growth rate.
    result["YoY"] = None if yoy is None else _number(yoy, signed=True)
    if cast(float, result["GM"]) > 1 or (result["YoY"] is not None
                             and not -1 <= result["YoY"] <= 100):
        raise ValueError("unreasonable KPI percentage")
    return result


def collect(port: Any, source_sha256: str, year: int | None,
            *, connection: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Collect one source-bound live snapshot; no UI result is inferred.

    ``port`` is the existing StdioModelingClient or a contract-compatible
    injectable fake. ``connection`` can reuse the *same already-connected*
    model across year states instead of creating new Microsoft session labels.
    Any unavailable engine, query failure, or inconsistent data BLOCKS;
    matched numerical totals PASS the semantic axis only.
    """
    queries = build_queries(year)
    receipt: dict[str, Any] = {
        "contract": SOURCE_CONTRACT, "source_sha256": source_sha256,
        "year": year, "semantic": "blocked", "interactive": "not_run",
        "queries": {k: hashlib.sha256(v.encode("utf-8")).hexdigest()
                    for k, v in queries.items()},
    }
    # A self-generated query SHA is no independent semantic oracle.
    # Refuse changed DAX before even connecting to the local model.
    if receipt["queries"] != PINNED_DAX_SHA256.get(year):
        receipt["reason"] = "DAX generator differs from independently pinned query fingerprints"
        return receipt
    if (not isinstance(source_sha256, str) or len(source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_sha256)):
        receipt["reason"] = "missing exact source fingerprint"
        return receipt
    try:
        connection = port.connect() if connection is None else connection
        model = connection["model"]
        if not isinstance(model, str) or not model:
            raise ValueError("MCP connection identity absent")
        scope = ModelingScope(model=model, source_sha256=source_sha256)
        readiness = port.readiness(scope)
        if readiness.get("populated") is not True:
            raise ValueError("live model not proven populated")
        data: dict[str, Any] = {}
        for name, dax in queries.items():
            result = port.query_scoped(dax, scope, max_rows=25)
            context = result.get("context", {})
            if (context.get("model") != model
                    or context.get("source_sha256") != source_sha256
                    or context.get("query_sha256") != receipt["queries"][name]):
                raise ValueError(f"MCP context mismatch for {name}")
            data[name] = result.get("rows")
        countries = _groups(data["country"], COUNTRIES)
        regions = _groups(data["region"], REGIONS)
        kpis = _kpis(data["kpis"])
        if (not math.isclose(sum(countries.values()), cast(float, kpis["Sales"]), rel_tol=0, abs_tol=0.05)
                or not math.isclose(sum(regions.values()), cast(float, kpis["Sales"]), rel_tol=0,
                                    abs_tol=0.05)):
            raise ValueError("map, region and KPI sales disagree")
        receipt.update({
            "semantic": "pass", "model": model,
            "desktop_pid": connection.get("desktopPid"),
            "country": countries, "region": regions, "kpis": kpis,
        })
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        receipt["reason"] = f"live DAX oracle blocked: {exc}"
    return receipt



def collect_region_europe_2024(port: Any, source_sha256: str,
                               connection: Mapping[str, Any],
                               year_2024: Mapping[str, Any]) -> dict[str, Any]:
    """Execute four KPIs under *both* 2024 and Europe, fail closed.

    The source, model, owned Desktop PID, frozen query and 2024 regional
    Sales subtotal must all agree; all other KPI values remain independently
    executed, not copied from the all-regions source snapshot.
    """
    receipt: dict[str, Any] = {
        "contract": REGION_EUROPE_2024_CONTRACT, "semantic": "blocked",
        "source_sha256": source_sha256, "year": 2024, "region": "Europe",
        "model": connection.get("model"), "desktop_pid": connection.get("desktopPid"),
        "dax_sha256": hashlib.sha256(REGION_EUROPE_2024_DAX.encode("utf-8")).hexdigest(),
    }
    if receipt["dax_sha256"] != PINNED_REGION_EUROPE_2024_SHA256:
        receipt["reason"] = "region KPI DAX no longer matches reviewed frozen query"
        return receipt
    if (year_2024.get("year") != 2024 or year_2024.get("semantic") != "pass"
            or year_2024.get("source_sha256") != source_sha256
            or year_2024.get("desktop_pid") != receipt["desktop_pid"]
            or year_2024.get("model") != receipt["model"]):
        receipt["reason"] = "region KPI source/model/PID differs from 2024 snapshot"
        return receipt
    try:
        model = receipt["model"]
        if not isinstance(model, str) or not model:
            raise ValueError("active model identity missing")
        scope = ModelingScope(model=model, source_sha256=source_sha256)
        query = port.query_scoped(REGION_EUROPE_2024_DAX, scope, max_rows=1)
        context = query.get("context", {})
        if (context.get("model") != model
                or context.get("source_sha256") != source_sha256
                or context.get("query_sha256") != receipt["dax_sha256"]):
            raise ValueError("regional live DAX query context mismatch")
        metrics = _kpis(query.get("rows"))
        expected_sales = year_2024["region"]["Europe"]
        if not math.isclose(cast(float, metrics["Sales"]), expected_sales, abs_tol=.05):
            raise ValueError("regional KPI Sales contradicts independent regional subtotal")
        receipt.update({"kpis": metrics, "semantic": "pass"})
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        receipt["reason"] = f"region KPI live query blocked: {exc}"
    return receipt


def compare_ui(receipt: Mapping[str, Any], observed: Mapping[str, Any] | None) -> dict:
    """Compare typed, independently captured UI numbers with live DAX.

    This does not turn visual/interaction acceptance green: an OCR screenshot
    or manual observation alone cannot prove actual click and filter behavior.
    """
    if receipt.get("semantic") != "pass":
        return {"verdict": "blocked", "reason": "live DAX semantic oracle missing"}
    if not isinstance(observed, Mapping):
        return {"verdict": "blocked", "reason": "independent UI evidence missing"}
    if (observed.get("source_sha256") != receipt.get("source_sha256")
            or observed.get("year") != receipt.get("year")):
        return {"verdict": "fail", "reason": "UI source or year differs from oracle"}
    for area, category in (("country", COUNTRIES), ("region", REGIONS)):
        values = observed.get(area)
        if not isinstance(values, dict) or set(values) != category:
            return {"verdict": "blocked", "reason": f"missing exact {area} UI values"}
        for name in category:
            try:
                actual = _number(values[name])
            except (TypeError, ValueError):
                return {"verdict": "blocked", "reason": f"invalid {area} UI value: {name}"}
            if not math.isclose(actual, receipt[area][name], rel_tol=0, abs_tol=0.05):
                return {"verdict": "fail", "reason": f"{area} mismatch: {name}"}
    return {"verdict": "pass", "scope": "numeric map tooltip/region values only",
            "interactive": "not_run"}
