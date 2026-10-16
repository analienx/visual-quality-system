"""P7 candidate wrapper must preserve valid PBIP schema from input."""
import json
from pathlib import Path

import pytest

from vqs.repair.execute import RepairError, write_candidate_wrapper

SCHEMA="https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"


def _setup(tmp_path, schema=None):
    original=tmp_path/"source"/"Sample.Report"
    original.mkdir(parents=True)
    if schema is not None:
        (original.parent/"Sample.pbip").write_text(json.dumps({
            "$schema":schema,
            "version":"1.0",
            "artifacts":[{"report":{"path":"Sample.Report"}}]}))
    candidate=tmp_path/"candidate"/"Sample.Report"
    candidate.mkdir(parents=True)
    return original,candidate


def test_candidate_wrapper_preserves_exact_source_schema(tmp_path):
    original,candidate=_setup(tmp_path,SCHEMA)
    record=write_candidate_wrapper(str(candidate),source_report=str(original))
    doc=json.loads(Path(record["path"]).read_text())
    assert doc["$schema"]==SCHEMA
    assert doc["artifacts"][0]["report"]["path"]=="Sample.Report"
    with pytest.raises(RepairError,match="occupied"):
        write_candidate_wrapper(str(candidate),source_report=str(original))


def test_candidate_wrapper_adds_schema_if_legacy_source_absent(tmp_path):
    original,candidate=_setup(tmp_path)
    record=write_candidate_wrapper(str(candidate),source_report=str(original))
    assert json.loads(Path(record["path"]).read_text())["$schema"]==SCHEMA


def test_invalid_schema_is_not_silently_substituted(tmp_path):
    original,candidate=_setup(tmp_path,"https://example.com/not-a-fabric-schema.json")
    with pytest.raises(RepairError,match="unsupported schema"):
        write_candidate_wrapper(str(candidate),source_report=str(original))
    assert not (candidate.parent/"Sample.pbip").exists()


def test_source_wrapper_link_rejected(tmp_path):
    original,candidate=_setup(tmp_path)
    outsider=tmp_path/"outside.txt"
    outsider.write_text("protected")
    shortcut=original.parent/"Sample.pbip"
    try:
        shortcut.symlink_to(outsider)
    except (OSError,NotImplementedError):
        pytest.skip("symlink creation not available")
    with pytest.raises(RepairError,match="unsafe original PBIP"):
        write_candidate_wrapper(str(candidate),source_report=str(original))
