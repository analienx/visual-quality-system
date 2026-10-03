"""Bridge version gate tests: proven minimum only, fail closed."""
from vqs.powerbi.desktop import (
    MIN_BRIDGE_VERSION,
    gate_bridge_version,
    parse_bridge_version,
)


def test_parse_extracts_triplet() -> None:
    assert parse_bridge_version("powerbi-desktop 1.0.0") == (1, 0, 0)
    assert parse_bridge_version("v2.3.4 (spike)") == (2, 3, 4)
    assert parse_bridge_version("") is None
    assert parse_bridge_version("no version here") is None
    assert parse_bridge_version("1.0") is None


def test_gate_passes_proven_minimum_and_above() -> None:
    assert MIN_BRIDGE_VERSION == (1, 0, 0)
    passed = gate_bridge_version("powerbi-desktop 1.0.0")
    assert passed == {"verdict": "pass", "version": [1, 0, 0]}
    assert gate_bridge_version("2.1.0")["verdict"] == "pass"


def test_gate_blocks_below_minimum_and_unparseable() -> None:
    low = gate_bridge_version("powerbi-desktop 0.9.9")
    assert low["verdict"] == "blocked"
    assert "below" in low["reason"]
    assert low["observed"] == [0, 9, 9]
    unknown = gate_bridge_version("Bridge version one")
    assert unknown["verdict"] == "blocked"
    assert "unparseable" in unknown["reason"]
    assert unknown["observed"] == "Bridge version one"
    assert gate_bridge_version("", minimum=(2, 0, 0))["verdict"] == "blocked"
    assert gate_bridge_version("1.9.9", minimum=(2, 0, 0))["verdict"] == "blocked"
