"""60-second repo smoke test: CLI entry points on shipped fixtures.

Exercises `measure`, `cycles`, and `doctor` in-process and asserts
their exit codes. Fast, offline, no Desktop::

    python scripts/smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vqs.cli import main as vqs_main


def main() -> int:
    fixtures = ROOT / "tests" / "powerbi" / "fixtures"
    failures = []

    def check(name: str, argv: list[str], want: int) -> None:
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            got = vqs_main(argv)
        status = "ok" if got == want else f"WANT {want} GOT {got}"
        print(f"{name}: {status}")
        if got != want:
            failures.append(name)

    check("measure", ["measure", str(fixtures / "mini_report"), "--model",
                      str(fixtures / "mini_model" / "definition")], 0)
    check("cycles-clean", ["cycles", str(fixtures / "clean_model")], 0)
    check("cycles-loopy", ["cycles", str(fixtures / "cycle_model")], 1)
    check("cycles-missing", ["cycles", str(fixtures / "absent")], 2)
    check("doctor", ["doctor"], 0)
    check("measure-missing", ["measure", str(fixtures / "absent")], 2)
    if failures:
        print("SMOKE FAILED:", ", ".join(failures))
        return 1
    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
