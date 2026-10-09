"""Calibration records: judge operator-supplied canvas/PNG dimensions.

Runtime Q1 asks whether a Bridge PNG is exactly canvas x integer scale
or a viewport slice. The operator runs the capture by hand (VQS never
drives Desktop from here) and pastes the measured numbers; this module
computes the verdict: ``exact-fit`` only when PNG == canvas x N for an
integer N in {1, 2}, else ``viewport-gap`` with the measured ratios.
"""
from __future__ import annotations

from typing import Any


def judge_calibration(canvas_width: int, canvas_height: int,
                      png_width: int, png_height: int) -> dict[str, Any]:
    """Verdict on one measured (canvas, PNG) pair; no capture performed."""
    for name, value in (("canvas_width", canvas_width),
                        ("canvas_height", canvas_height),
                        ("png_width", png_width),
                        ("png_height", png_height)):
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    record = {"canvas": [canvas_width, canvas_height],
              "png": [png_width, png_height],
              "ratio_x": png_width / canvas_width,
              "ratio_y": png_height / canvas_height}
    for scale in (1, 2):
        if (png_width, png_height) == (canvas_width * scale,
                                       canvas_height * scale):
            record["verdict"] = "exact-fit"
            record["scale"] = scale
            return record
    record["verdict"] = "viewport-gap"
    record["note"] = ("PNG is not canvas x integer scale; capture must "
                      "block until the Bridge viewport semantics are proven")
    return record
