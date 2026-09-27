---
name: vqs
description: Review Power BI reports with the Visual Quality System: source-measured facts, sealed verdicts, source-bound screenshots, and independent adjudication. Use for any report-quality, model-acyclicity, or review-handoff task.
---

# VQS agent skill

VQS-first routing. Measure from sources, never invent theme literals,
measures, or data values. Unknown provenance blocks; it never passes.

## Capability map

| Need | Command | Needs |
| --- | --- | --- |
| Report facts (contrast, cohorts, units, bindings, page insights, duplication + chart practice) | `vqs measure REPORT --model MODELDIR` | sources only |
| DAX/M acyclicity gate | `vqs cycles MODELDIR` (0 acyclic, 1 cycle, 2 blocked) | sources only |
| Facts → sealed verdict | `vqs check facts.json --run-id ID` | sources only |
| Screenshot evidence + manifest | `vqs capture REPORT RENDERS [--pid P]` | Windows + Desktop + Bridge |
| Review template from renders | `vqs request-review REPORT RENDERS --fixer-id YOU` | renders + manifest |
| Portable evidence handoff | `vqs bundle pack/verify/unpack` | - |
| Static adjudication | `vqs adjudicate-bundle BUNDLE` | completed template |
| Environment report | `vqs doctor` (always exit 0, installs nothing) | - |

Full reference: `docs/CLI.md`. Workflows: `docs/USER_GUIDE.md`.

## External tools (arm's length, VQS owns the decision)

- **Modeling MCP** (Microsoft): live Desktop models — tables, measures,
  DAX Execute/Validate, edits, transactions. Cannot touch report pages.
  Connect via `connection_operations` (`ListLocalInstances`/`Connect`).
- **Desktop Bridge** (`powerbi-desktop`): instance control and captures.
  `vqs capture` wraps it; call it directly only for `open`/`reload`.
- **pbir-cli** (optional, Custom Non-Commercial): report-side
  `validate`/`fields`/`bpa`/`add`/`set` only. Only `model -d/-q` and
  `validate --fields` need AdomdClient — prefer the MCP instead.
  VQS must work with pbir absent.

## Rules

- Name exact commands and require validator output in every result; a
  claim without validator output is not done.
- Static facts before pixels: run `measure`/`cycles`/`check` before
  any screenshot loop. Repeated open-observe-edit cycles are banned
  when a validator answers the question.
- No-cycles handover gate for semantic models: (1) `vqs cycles`
  over TMDL (DAX graph + M graph + `let` bindings), zero cycles;
  (2) live engine via MCP batched `measure_operations Get` — every
  measure `Ready` with empty `errorMessage`. `Validate` checks
  syntax only and does not prove acyclicity.
- Screenshots: `vqs capture` (exact PID + report path); unsaved
  changes, wrong report, or missing pages block. Never capture a
  report the user has open with unsaved work without asking.
- Multi-agent review: fixer packs with `vqs bundle pack`, the
  reviewer verifies with `vqs bundle verify --report` on their own
  machine. Reviewer ≠ fixer (CORE-06); a bare template can never
  pass adjudication — fill observations with ≥32-char reasons,
  located failures, `image_capability`, and `calibration`.
- Privacy: renders, bundles, `.abf`, credentials, `.vqs-runs/` stay
  out of git and public issues. Quote hashes and finding IDs, never
  pixels or business data.
- One Desktop instance at a time for captures; confirm before
  killing Desktop processes. If the user must interact, the window
  must be visible (restore + foreground + title check).
