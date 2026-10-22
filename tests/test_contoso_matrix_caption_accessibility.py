"""Readable matrix captions without changing semantic bindings."""
from __future__ import annotations

import json
from pathlib import Path


def test_contoso_customer_matrix_has_compact_nonambiguous_headers():
    repo = Path(__file__).resolve().parents[1]
    path = (repo / "examples" / "contoso-retail" / "Contoso Retail.Report"
            / "definition" / "pages" / "Stores_customers"
            / "visuals" / "customer-health" / "visual.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["visual"]["visualType"] == "pivotTable"
    assert data["position"]["width"] >= 608
    query = data["visual"]["query"]["queryState"]
    rows = query["Rows"]["projections"]
    values = query["Values"]["projections"]
    assert [(v["queryRef"], v["nativeQueryRef"], v["displayName"])
            for v in rows] == [("Dim Customer.Segment", "Segment", "Segment")]
    assert [(v["queryRef"], v["nativeQueryRef"], v["displayName"])
            for v in values] == [
        ("Fact Sales.Reporting Year Sales", "Reporting Year Sales", "Sales"),
        ("Fact Sales.Reporting Year GM %", "Reporting Year GM %", "GM %"),
    ]
    assert len(values) == 2
    assert "rowPadding" in data["visual"]["objects"]["grid"][0]["properties"]
