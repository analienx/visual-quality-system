"""Explicit high-effort Muse vision transport for source-bound specialist tasks.

No tool access, no implicit model fallback, no external image upload without
explicit opt-in. Provider runtime model events, not the model's answer, supply
the model receipt. If the installed Muse CLI does not expose that receipt,
the task is blocked until the adapter is verified against that CLI version.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..contracts import SpecialistTask, answer_schema, validate_answer
from ..port import ReviewError
from ..specialists import KPI, TABLE


def _provider_output(stdout: str, expected_model: str
                     ) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(stdout, str) or len(stdout) > 400_000:
        raise ReviewError("model output missing or oversized")
    response = None
    actual = None
    for raw_line in stdout.splitlines():
        if not raw_line.lstrip().startswith("{"):
            continue
        try:
            event = json.loads(raw_line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        # Only dedicated provider event envelopes attest a runtime model.
        # Never accept a model ID the LLM embeds in its answer.
        if (event.get("type") in {
                "model_selected", "model-selected", "completion_model",
                "completion-model", "model_resolved"}
                and isinstance(event.get("model_id"), str)):
            actual = event["model_id"]
        if "type" not in event and isinstance(event.get("answer"), dict):
            response = event["answer"]
        elif "type" not in event and set(event) in (set(KPI.checks), set(TABLE.checks)):
            response = event
    if actual is None:
        raise ReviewError("Muse runtime model receipt unavailable; no verified specialist result")
    if actual != expected_model:
        raise ReviewError("Muse runtime used a different model from the explicit pin")
    if response is None:
        raise ReviewError("Muse specialist returned no final fixed-key answer")
    return response, {"provider": "muse", "actual_model": actual,
                      "model_provenance": "provider_runtime_event",
                      "effort": "high"}


class MuseHighSpecialist:
    """Fresh, tool-disabled Muse CLI session per card or matrix region."""

    def __init__(self, *, model: str, executable: str | None = None,
                 timeout_seconds: int = 120, runner: Any = None) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("specialist model must be explicitly pinned")
        if type(timeout_seconds) is not int or not 10 <= timeout_seconds <= 240:
            raise ValueError("invalid bounded specialist timeout")
        self.model = model.strip()
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.runner = runner or subprocess.run

    def review_task(self, task: SpecialistTask, page: Path,
                    crop: Path) -> dict[str, Any]:
        if os.getenv("VQS_ALLOW_VISION_UPLOAD") != "1":
            raise ReviewError("remote image upload not authorized")
        if ("contributor" in self.model.casefold()
                and os.getenv("VQS_ALLOW_MUSE_CONTRIBUTOR") != "1"):
            raise ReviewError("Contributor Mode requires separate explicit consent")
        binary = self.executable or shutil.which("muse.cmd") or shutil.which("muse")
        if not binary:
            raise ReviewError("Muse CLI is not installed")
        specialist = {KPI.code: KPI, TABLE.code: TABLE}.get(task.specialist)
        if specialist is None or specialist.checks != task.checks:
            raise ReviewError("unsupported or mismatched specialist task")
        with tempfile.TemporaryDirectory(prefix="vqs-private-specialist-") as name:
            workspace = Path(name)
            sources = [
                (page, workspace / "verified-page.png", task.page_image_sha256),
                (crop, workspace / "verified-region.png", task.crop_image_sha256),
            ]
            for source, frozen, expected in sources:
                if source.is_symlink() or not source.is_file():
                    raise ReviewError("review image is missing or symlinked")
                # Provider reads only frozen bytes, never a mutable source path.
                with source.open("rb") as stream:
                    data = stream.read(32 * 1024 * 1024 + 1)
                if (len(data) > 32 * 1024 * 1024
                        or hashlib.sha256(data).hexdigest() != expected):
                    raise ReviewError("specialist source image digest mismatch")
                frozen.write_bytes(data)
            schema = workspace / "schema.json"
            schema.write_text(json.dumps(answer_schema(task.checks)), encoding="utf-8")
            prompt = (specialist.prompt + "\nRequired checks: "
                      + ", ".join(task.checks))
            command = [
                binary, "exec", "--provider", "meta", "--model", self.model,
                "--image", str(sources[0][1]), "--image", str(sources[1][1]),
                "--output-schema", str(schema),
                "--disable-shell", "--disable-write", "--disable-web-tools",
                "--no-session-log", "--no-foreign-personal-context",
                "--max-model-steps", "2", "--reasoning-effort", "high", prompt,
            ]
            try:
                result = self.runner(
                    command, cwd=str(workspace), stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, check=False,
                    timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise ReviewError("Muse specialist timed out") from exc
            except OSError as exc:
                raise ReviewError(f"Muse failed to launch: {type(exc).__name__}") from exc
            if result.returncode != 0:
                raise ReviewError(f"Muse specialist returned exit {result.returncode}")
            for _, frozen, expected in sources:
                if hashlib.sha256(frozen.read_bytes()).hexdigest() != expected:
                    raise ReviewError("specialist frozen image changed during inference")
            raw, receipt = _provider_output(result.stdout, self.model)
            return {"answer": validate_answer(task, raw),
                    "receipt": {**receipt, "task_id": task.task_id}}
