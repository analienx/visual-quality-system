"""Runnable VQS demo on the shipped synthetic fixtures.

Measures the mini PBIR report, gates the looping and clean TMDL
models, and prints one JSON summary. Offline, deterministic, no
Desktop needed::

    python examples/quickstart.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vqs.powerbi.cycles import check_model
from vqs.powerbi.measure import measure_report


def main() -> int:
    fixtures = ROOT / "tests" / "powerbi" / "fixtures"
    facts = measure_report(str(fixtures / "mini_report"),
                           str(fixtures / "mini_model" / "definition"))
    loopy = check_model(str(fixtures / "cycle_model"))
    clean = check_model(str(fixtures / "clean_model"))
    summary = {
        "measure": {"sections": sorted(facts["rules"]),
                    "bindings": len(facts["models"][0]["bindings"])},
        "cycles_loopy": {"acyclic": loopy["acyclic"],
                         "dax_cycles": len(loopy["dax_cycles"]),
                         "m_cycles": len(loopy["m_cycles"]),
                         "let_cycles": len(loopy["let_cycles"])},
        "cycles_clean": {"acyclic": clean["acyclic"]},
    }
    print(json.dumps(summary, indent=2))
    ok = (summary["measure"]["sections"] and not loopy["acyclic"]
          and clean["acyclic"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
