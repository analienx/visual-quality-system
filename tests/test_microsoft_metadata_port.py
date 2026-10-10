"""Microsoft schema/formatting metadata port: typed, nonmutating, fail closed."""
from __future__ import annotations

import hashlib
import json

import pytest

from vqs.powerbi.author import metadata


def _attested():
    return {
        "status": "pass", "validation_provider": "microsoft",
        "assurance": "microsoft_structural_only",
        "cli": {"status": "pass", "path": "/approved/author", "version": "0.5.0"},
        "probe": {"path": "/approved/author", "version": "0.5.0"},
    }


def _property(argv, timeout):
    assert timeout == 22
    assert argv == ["/approved/author", "formatting", "describe-property",
                    "barChart", "categoryAxis", "labelPrecision"]
    return {"returncode": 0, "stdout": json.dumps({
        "data": {"visualType": "barChart", "objectName": "categoryAxis",
                 "propertyName": "labelPrecision",
                 "property": {"type": "integer", "displayName": "Decimal places"}}})}


def test_property_metadata_is_pinned_schema_bound_and_hash_stable():
    first = metadata.query(_attested(), "formatting.describe_property",
                           "barChart", "categoryAxis", "labelPrecision",
                           runner=_property, timeout=22)
    assert first["status"] == "pass"
    assert first["data"]["property"]["type"] == "integer"
    assert first["mutates_report"] is False
    assert len(bytes.fromhex(first["sha256"])) == hashlib.sha256().digest_size
    assert first["sha256"] == metadata.query(
        _attested(), "formatting.describe_property",
        "barChart", "categoryAxis", "labelPrecision",
        runner=_property, timeout=22)["sha256"]


def test_catalog_required_roles_are_source_metadata():
    record = metadata.query(
        _attested(), "catalog.describe", "barChart",
        runner=lambda argv, timeout: {"returncode": 0,
          "stdout": json.dumps({"data": {
            "visualType": "barChart", "roles": {
                "Category": {"kind": "Grouping"}, "Y": {"kind": "Measure"}},
            "requiredRoles": ["Category", "Y"], "deprecated": False}})})
    assert record["status"] == "pass"
    assert record["data"]["requiredRoles"] == ["Category", "Y"]


@pytest.mark.parametrize("capability,names", [
    ("shell.exec", ("barChart",)),
    ("catalog.describe", ("../evil",)),
    ("formatting.describe_property", ("barChart", "categoryAxis")),
    ("formatting.describe_property", ("barChart", "categoryAxis", "x&rm")),
    ("catalog.describe", ("",)),
    ("catalog.describe", ("x" * 100,)),
])
def test_unsafe_or_unknown_metadata_lookup_never_executes(capability, names):
    executed = []
    result = metadata.query(
        _attested(), capability, *names,
        runner=lambda *a: executed.append(a))
    assert result["status"] == "blocked"
    assert executed == []


def test_wrong_tool_identity_blocks_before_metadata_command():
    bad = _attested()
    bad["probe"]["path"] = "/shadowing/cli"
    observed = []
    result = metadata.query(bad, "catalog.describe", "barChart",
                            runner=lambda *a: observed.append(a))
    assert result["status"] == "blocked"
    assert observed == []


@pytest.mark.parametrize("output", [
    {"returncode": 1, "stdout": '{"error":{"message":"unsupported"}}'},
    {"returncode": 0, "stdout": '{"error":{"message":"unsupported"}}'},
    {"returncode": 0, "stdout": '{"data":{"visualType":"barChart"}}'},
    {"returncode": 0, "stdout": '{"data":{"visualType":"other","property":{"type":"integer"}}}'},
    {"returncode": 0, "stdout": '{"data":{"visualType":"barChart","objectName":"categoryAxis","propertyName":"labelPrecision","property":{}}}'},
    {"returncode": 0, "stdout": "not json"},
    {"returncode": 0, "stdout": "x" * 512_001},
])
def test_untrusted_metadata_responses_cannot_be_accepted(output):
    result = metadata.query(
        _attested(), "formatting.describe_property",
        "barChart", "categoryAxis", "labelPrecision",
        runner=lambda *a: output)
    assert result["status"] == "blocked"
    assert "data" not in result


def test_crashed_metadata_runner_is_blocked():
    def crashed(*_args):
        raise OSError("tool unavailable")

    result = metadata.query(_attested(), "catalog.describe", "barChart",
                            runner=crashed)
    assert result["status"] == "blocked"


def test_metadata_timeout_is_bounded():
    result = metadata.query(_attested(), "catalog.describe", "barChart",
                            timeout=601)
    assert result["status"] == "blocked"


def test_object_metadata_is_a_raw_property_map_not_a_named_envelope():
    result = metadata.query(
        _attested(), "formatting.describe_object",
        "barChart", "categoryAxis",
        runner=lambda *a: {"returncode": 0, "stdout": json.dumps({
            "data": {"labelPrecision": {"type": "integer"},
                     "fontSize": {"type": "formatting"}}})})
    assert result["status"] == "pass"
    assert result["data"]["labelPrecision"]["type"] == "integer"


def test_effective_properties_require_both_visual_and_container_objects():
    result = metadata.query(
        _attested(), "formatting.effective_properties", "barChart",
        runner=lambda *a: {"returncode": 0, "stdout": json.dumps({
            "data": {"visualType": "barChart",
                     "visualObjects": {"categoryAxis": {}},
                     "visualContainerObjects": {"title": {}}}})})
    assert result["status"] == "pass"
    refused = metadata.query(
        _attested(), "formatting.effective_properties", "barChart",
        runner=lambda *a: {"returncode": 0, "stdout": json.dumps({
            "data": {"visualType": "barChart", "visualObjects": {}}})})
    assert refused["status"] == "blocked"
