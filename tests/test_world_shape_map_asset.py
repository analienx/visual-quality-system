"""Protect account-free world geography and country keys."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "assets" / "maps"

def test_topology_and_country_keys():
    data = json.loads((ROOT / "world-countries-110m-vqs.topojson").read_text(encoding="utf-8"))
    assert data["type"] == "Topology"
    assert len(data["objects"]["countries"]["geometries"]) >= 170
    assert len(data["arcs"]) >= 500
    keys = [x["properties"]["name"] for x in data["objects"]["countries"]["geometries"]]
    assert len(keys) == len(set(keys))
    assert {"United States","Canada","United Kingdom","Germany","Australia"} <= set(keys)
    assert "United States of America" not in keys
    assert "Copyright 2013-2019 Michael Bostock" in (ROOT / "WORLD_ATLAS_LICENSE.txt").read_text()
