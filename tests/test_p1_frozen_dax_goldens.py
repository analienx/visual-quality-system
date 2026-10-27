"""P1: a wrong query must not validate by regenerating its own oracle SHA."""
from __future__ import annotations

import hashlib

import pytest

from tests.test_contoso_p14_interaction_audit import PID, SOURCE, _evidence
from vqs.powerbi import contoso_runtime, interaction_audit
from vqs.powerbi.contoso_goldens import PINNED_DAX_SHA256


@pytest.mark.parametrize("year", [None, 2023, 2024, 2025])
def test_current_approved_queries_match_independently_frozen_text(year):
    assert {
        name: hashlib.sha256(dax.encode("utf8")).hexdigest()
        for name, dax in contoso_runtime.build_queries(year).items()
    } == PINNED_DAX_SHA256[year]


def test_live_oracle_refuses_mirrored_wrong_measure_before_model_connection(monkeypatch):
    original = contoso_runtime.build_queries

    def incorrect(year):
        return {
            name: dax.replace("Reporting Year Sales", "Wrong Sales Metric")
            for name, dax in original(year).items()
        }

    class MustNotConnect:
        def connect(self):
            raise AssertionError("wrong query must not touch an authenticated model")

    monkeypatch.setattr(contoso_runtime, "build_queries", incorrect)
    outcome = contoso_runtime.collect(MustNotConnect(), SOURCE, 2024)
    assert outcome["semantic"] == "blocked"
    assert "independently pinned" in outcome["reason"]


def test_trace_validator_refuses_receipt_with_mirrored_wrong_query_hashes(tmp_path):
    oracle, _trace = _evidence(tmp_path)
    original = contoso_runtime.build_queries
    for state in oracle["states"]:
        state["queries"] = {
            name: hashlib.sha256(dax.replace(
                "Reporting Year Sales", "Wrong Sales Metric").encode("utf8")).hexdigest()
            for name, dax in original(state["year"]).items()
        }
    with pytest.raises(interaction_audit.InteractionEvidenceError, match="fingerprint"):
        interaction_audit._year_states(oracle, SOURCE, PID)
