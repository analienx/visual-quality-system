"""A genuine model-powered review adapter: provenance, isolation and refusal."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_review_canvas_bundle import _ready_bundle
from vqs import cli
from vqs.review.bundle import pack, verify
from vqs.review.muse import (
    CHECKS,
    MuseVisionReviewer,
    _structured_result,
    _validate_result,
)
from vqs.review.port import ReviewError, review_bundle


def _payload(page, digest, failed=False):
    return {
        "checks": [
            {"check": name, "verdict": (
                "fail" if failed and name == "text_clipping" else "pass"),
             "detail": ("The upper-left Sales KPI subtitle is clipped at "
                        "the bottom of its card." if failed and
                        name == "text_clipping" else
                        "The entire visible report page looks coherent here.")}
            for name in CHECKS
        ],
    }


def _bundle(tmp_path):
    report, renders, bundle = _ready_bundle(tmp_path)
    pack(str(report), str(renders), str(bundle), "distinct-fixer")
    return report, bundle, verify(str(bundle))


def test_muse_tool_disabled_provenance_bound_review(tmp_path, monkeypatch):
    _, bundle, authority = _bundle(tmp_path)
    sha = authority["review_images"]["p1"]["sha256"]
    invoked = []

    def runner(command, **kwargs):
        invoked.append((command, kwargs))
        assert "--disable-write" in command
        assert "--disable-shell" in command
        assert "--disable-web-tools" in command
        assert "--no-session-log" in command
        assert "--no-foreign-personal-context" in command
        assert "--output-schema" in command
        frozen = Path(command[command.index("--image") + 1])
        assert frozen.name == "verified-image.png"
        assert frozen.is_file()
        import hashlib
        assert hashlib.sha256(frozen.read_bytes()).hexdigest() == sha
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 30
        schema = json.loads(Path(command[command.index(
            "--output-schema") + 1]).read_text(encoding="utf-8"))
        assert "checks" in schema["properties"]
        output = json.dumps(_payload("p1", sha, failed=True))
        return SimpleNamespace(returncode=0, stdout="muse: startup\n" + output,
                               stderr="")

    monkeypatch.setenv("VQS_ALLOW_VISION_UPLOAD", "1")
    reviewer = MuseVisionReviewer(
        timeout_seconds=30, executable="test-muse", runner=runner)
    reviewed = review_bundle(
        bundle_dir=str(bundle), reviewer=reviewer,
        reviewer_id=reviewer.reviewer_id, fixer_id="distinct-fixer")
    assert reviewed["visual"] == "fail"
    assert reviewed["tally"]["fail"] == 1
    # The synthetic source contains no matrix: N/A is NOT an image pass.
    assert reviewed["tally"]["pass"] == len(CHECKS) - 2
    assert reviewed["tally"]["not_applicable"] == 1
    matrix = next(x for x in reviewed["observations"]
                  if x["check"] == "table_matrix_overflow")
    assert matrix["verdict"] == "not_applicable"
    assert matrix["detail"]["matrix_visual_count"] == 0
    assert reviewed["observations"][0]["detail"]["image_sha256"] == sha
    assert len(invoked) == 1


def test_privacy_consent_missing_refuses_even_verified_images(tmp_path, monkeypatch):
    _, bundle, _ = _bundle(tmp_path)
    monkeypatch.delenv("VQS_ALLOW_VISION_UPLOAD", raising=False)
    def runner(*args, **kwargs):
        raise AssertionError("no image may leave the host")
    reviewer = MuseVisionReviewer(executable="fake", runner=runner)
    with pytest.raises(ReviewError, match="upload not authorized"):
        reviewer.review(str(bundle))


@pytest.mark.parametrize("modification", [
    "wrong_page", "wrong_sha", "missing", "duplicate", "malformed",
    "empty_detail",
])
def test_model_cannot_fabricate_source_or_partial_review(modification):
    value = _payload("p1", "a" * 64)
    if modification == "wrong_page":
        value["page_id"] = "wrong"
    elif modification == "wrong_sha":
        value["image_sha256"] = "b" * 64
    elif modification == "missing":
        value["checks"].pop()
    elif modification == "duplicate":
        value["checks"][1]["check"] = value["checks"][0]["check"]
    elif modification == "malformed":
        value["checks"][0]["verdict"] = "perfect"
    else:
        value["checks"][0]["detail"] = "ok"
    with pytest.raises(ReviewError):
        _validate_result(value, "p1", "a" * 64)


def test_stdout_requires_real_final_json():
    result = _structured_result(
        'muse: settings\n{"checks":[]}\n')
    assert result["checks"] == []
    with pytest.raises(ReviewError, match="structured"):
        _structured_result("muse: warnings and nothing else")


@pytest.mark.parametrize("case", ["timeout", "failed", "invalid"])
def test_muse_model_failure_never_pretends_pass(tmp_path, case):
    image = tmp_path / "canvas.png"
    image.write_bytes(b"x")
    def runner(*args, **kwargs):
        if case == "timeout":
            raise subprocess.TimeoutExpired("muse", 10)
        if case == "failed":
            return SimpleNamespace(returncode=41, stdout="", stderr="private")
        return SimpleNamespace(returncode=0, stdout="Not JSON", stderr="")
    reviewer = MuseVisionReviewer(executable="fake", runner=runner)
    with pytest.raises(ReviewError):
        reviewer._review_page("p1", image, "a" * 64)


def test_advisory_cli_refuses_upload_without_consent(tmp_path, capsys):
    _, bundle, _ = _bundle(tmp_path)
    assert cli.main(["review-images", str(bundle)]) == 2
    assert "consent" in capsys.readouterr().out


def test_advisory_cli_can_use_independent_provider_without_release_claim(
        tmp_path, monkeypatch, capsys):
    _, bundle, authority = _bundle(tmp_path)
    sha = authority["review_images"]["p1"]["sha256"]
    from vqs.review import muse
    def runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            _payload("p1", sha, failed=True)), stderr="")
    reviewer = MuseVisionReviewer(executable="test-muse", runner=runner)
    monkeypatch.setattr(muse, "muse_reviewer", reviewer)
    output = tmp_path / "private-review.json"
    assert cli.main([
        "review-images", str(bundle), "--allow-remote-images",
        "--out", str(output)]) == 1
    captured = json.loads(capsys.readouterr().out)
    assert captured["advisory"] is True
    assert captured["release_authority"] is False
    assert captured["visual"] == "fail"
    assert len(captured["observations"]) == len(CHECKS)
    assert json.loads(output.read_text())["visual"] == "fail"
    assert os.getenv("VQS_ALLOW_VISION_UPLOAD") != "1"
    assert cli.main(["review-images", str(bundle), "--allow-remote-images",
                     "--out", str(output)]) == 2


def test_matrix_overflow_is_a_distinct_blocking_visible_defect():
    """A concrete unreadable matrix cannot be buried in generic legibility."""
    response = _payload("stores", "a" * 64)
    for check in response["checks"]:
        if check["check"] == "table_matrix_overflow":
            check["verdict"] = "fail"
            check["detail"] = (
                "The Small Business matrix row is clipped above Total; "
                "horizontal and vertical scrollbars obscure the last values."
            )
    obs = _validate_result(response, "stores", "a" * 64)
    assert len(obs) == len(CHECKS)
    assert next(row for row in obs
                if row["check"] == "table_matrix_overflow")["verdict"] == "fail"


def test_matrix_overflow_prompt_is_required_and_context_aware():
    from vqs.review import muse
    assert "table_matrix_overflow" in muse.CHECKS
    assert "scrollbars" in muse._PROMPT
    assert "A scrollbar is not automatically a defect" in muse._PROMPT
    assert "no table or matrix on page" in muse._PROMPT
