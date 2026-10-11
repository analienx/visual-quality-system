"""Data-preserving private preview: complete PBIP clone and strict cosmetic overlay."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tests.test_s16_candidate_model import _project
from vqs.repair.preview import (
    PreviewMaterializationError,
    materialize_populated_preview,
)

VISUAL = "definition/pages/P1/visuals/v1/visual.json"


def _project_pair(tmp_path: Path, with_cache=True):
    original, model = _project(tmp_path / "source", "table T\n")
    wrapper = original.parent / "original.pbip"
    wrapper.write_text(json.dumps({"version": "1.0", "artifacts": [
        {"report": {"path": "original.Report"}}]}), encoding="utf-8")
    if with_cache:
        (model / ".pbi" / "cache.abf").write_bytes(b"private populated test model")
    typed = tmp_path / "typed.Report"
    shutil.copytree(original, typed)
    value = json.loads((typed / VISUAL).read_text())
    value["visual"]["objects"]["categoryLabels"] = [{
        "properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}]
    (typed / VISUAL).write_text(json.dumps(value), encoding="utf-8")
    return wrapper, original, model, typed


def test_local_preview_preserves_cache_and_only_typed_delta(tmp_path):
    wrapper, original, model, typed = _project_pair(tmp_path)
    source_before = hashlib.sha256((original / VISUAL).read_bytes()).hexdigest()
    output = tmp_path / "preview"
    proof = materialize_populated_preview(wrapper, typed, output, [VISUAL])
    assert proof["status"] == "materialized"
    assert proof["preview_cache_present"] is True
    assert proof["semantic_runtime_readiness"] == "NOT_RUN"
    assert (output / "Model.SemanticModel/.pbi/cache.abf").read_bytes() == (
        model / ".pbi/cache.abf").read_bytes()
    assert (output / "original.Report" / VISUAL).read_bytes() == (
        typed / VISUAL).read_bytes()
    assert hashlib.sha256((original / VISUAL).read_bytes()).hexdigest() == source_before
    assert proof["source_unchanged"]


def test_preview_without_cache_does_not_claim_live_data(tmp_path):
    wrapper, _original, _model, typed = _project_pair(tmp_path, with_cache=False)
    proof = materialize_populated_preview(
        wrapper, typed, tmp_path / "preview", [VISUAL])
    assert proof["preview_cache_present"] is False
    assert proof["semantic_runtime_readiness"] == "NOT_RUN"


@pytest.mark.parametrize("change,fragment", [
    ("query", "semantic/interaction change"),
    ("undeclared-file", "do not match"),
    ("wrong-write", "do not match"),
])
def test_wrong_semantic_scope_refused(tmp_path, change, fragment):
    wrapper, original, _model, typed = _project_pair(tmp_path)
    expected = [VISUAL]
    if change == "query":
        visual = json.loads((typed / VISUAL).read_text())
        visual["visual"]["query"] = {"replaced": "measure"}
        (typed / VISUAL).write_text(json.dumps(visual), encoding="utf-8")
    elif change == "undeclared-file":
        (typed / "definition.pbir").write_text(
            (typed / "definition.pbir").read_text() + " ", encoding="utf-8")
    else:
        expected = ["definition/pages/P1/visuals/wrong/visual.json"]
    out = tmp_path / "preview"
    with pytest.raises(PreviewMaterializationError, match=fragment):
        materialize_populated_preview(wrapper, typed, out, expected)
    assert not out.exists()
    assert original.exists()


def test_source_overlap_refused_without_copying(tmp_path):
    wrapper, original, _model, typed = _project_pair(tmp_path)
    with pytest.raises(PreviewMaterializationError, match="overlap"):
        materialize_populated_preview(
            wrapper, typed, original.parent / "nested-preview", [VISUAL])
    assert not (original.parent / "nested-preview").exists()


def test_private_cache_preview_refuses_git_checkout(tmp_path):
    wrapper, _original, _model, typed = _project_pair(tmp_path)
    checkout = tmp_path / "working"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(PreviewMaterializationError, match="Git checkout"):
        materialize_populated_preview(wrapper, typed, checkout / "preview", [VISUAL])
    assert not (checkout / "preview").exists()
