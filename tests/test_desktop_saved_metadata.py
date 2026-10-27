"""Native Desktop 2.159 Save metadata repair: narrow, fail-closed negatives."""
from __future__ import annotations

import json

import pytest

from scripts.normalize_saved_pbip_metadata import main
from vqs.powerbi.desktop_saved_metadata import (
    REFERENCE_SCHEMA,
    WRAPPER_SCHEMA,
    normalize_saved_metadata,
)


@pytest.fixture
def saved_project(tmp_path):
    root = tmp_path / "private-scratch"
    project = root / "isolated-candidate"
    report = project / "Test.Report"
    model = project / "Test.SemanticModel"
    report.mkdir(parents=True)
    model.mkdir()
    (model / "definition.tmdl").write_text("model", encoding="utf8")
    (report / "definition.pbir").write_text(json.dumps({
        "version": "4.0", "datasetReference": {
            "byPath": {"path": "../Test.SemanticModel"}
        }
    }), encoding="utf8")
    (report / "definition" / "pages").mkdir(parents=True)
    (report / "definition" / "pages" / "page.json").write_text(
        '{"preserve":true}', encoding="utf8"
    )
    wrapper = project / "Test.pbip"
    wrapper.write_text('{"version":"1.0"}', encoding="utf8")
    return root, project, report, model, wrapper


def test_schema_only_auto_fix_preserves_semantics_and_report_data(saved_project):
    root, project, report, _model, wrapper = saved_project
    original = [(wrapper, json.loads(wrapper.read_text())),
                (report / "definition.pbir",
                 json.loads((report / "definition.pbir").read_text()))]
    untouched = {
        f.relative_to(project): f.read_bytes()
        for f in project.rglob("*") if f.is_file() and f not in [x[0] for x in original]
    }
    dry = normalize_saved_metadata(project, disposable_root=root)
    assert dry["status"] == "dry_run"
    assert dry["changed_file_count"] == 2
    assert "$schema" not in json.loads(wrapper.read_text())
    fixed = normalize_saved_metadata(project, disposable_root=root, apply=True)
    assert fixed["status"] == "applied"
    assert not fixed["desktop_loaded_file_attested"]
    assert fixed["independent_g2_g4_g6"] == "blocked"
    for file, expected in original:
        got = json.loads(file.read_text())
        assert got.pop("$schema") in (WRAPPER_SCHEMA, REFERENCE_SCHEMA)
        assert got == expected
    for path, content in untouched.items():
        assert (project / path).read_bytes() == content
    assert normalize_saved_metadata(
        project, disposable_root=root, apply=True
    )["changed_file_count"] == 0


def test_refuses_original_or_unrelated_project(saved_project, tmp_path):
    _root, project, *_ = saved_project
    with pytest.raises(ValueError, match="scratch"):
        normalize_saved_metadata(project, disposable_root=project)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ValueError, match="scratch"):
        normalize_saved_metadata(project, disposable_root=outside)


def test_rejects_existing_wrong_schema_without_overwrite(saved_project):
    root, project, _, _, wrapper = saved_project
    wrapper.write_text('{"$schema":"https://unexpected.invalid","version":"1.0"}')
    old = wrapper.read_bytes()
    with pytest.raises(ValueError, match="unexpected existing schema"):
        normalize_saved_metadata(project, disposable_root=root, apply=True)
    assert wrapper.read_bytes() == old


def test_wrong_declared_model_blocks(saved_project):
    root, project, report, *_ = saved_project
    source = report / "definition.pbir"
    source.write_text(json.dumps({"datasetReference": {
        "byPath": {"path": "../../private-other.SemanticModel"}
    }}), encoding="utf8")
    with pytest.raises(ValueError, match="local byPath semantic model missing"):
        normalize_saved_metadata(project, disposable_root=root, apply=True)


def test_remote_model_cannot_claim_local(saved_project):
    root, project, report, *_ = saved_project
    (report / "definition.pbir").write_text(json.dumps({
        "datasetReference": {"byConnection": {"connectionString": "opaque"}}
    }))
    with pytest.raises(ValueError, match="local byPath"):
        normalize_saved_metadata(project, disposable_root=root, apply=True)


def test_cli_writes_receipt_no_false_release_and_never_overwrites(saved_project, tmp_path):
    root, project, *_ = saved_project
    output = tmp_path / "private-receipt.json"
    args = [str(project), "--disposable-root", str(root), "--output", str(output),
            "--apply"]
    assert main(args) == 0
    receipt = json.loads(output.read_text())
    assert receipt["changed_file_count"] == 2
    assert receipt["independent_g2_g4_g6"] == "blocked"
    with pytest.raises(SystemExit):
        main(args)


def test_cli_blocks_outside_scratch_without_touching_source(saved_project, tmp_path):
    _root, project, _, _, wrapper = saved_project
    initial = wrapper.read_bytes()
    output = tmp_path / "blocked.json"
    assert main([str(project), "--disposable-root", str(project),
                 "--output", str(output), "--apply"]) == 2
    assert json.loads(output.read_text())["status"] == "blocked"
    assert wrapper.read_bytes() == initial
