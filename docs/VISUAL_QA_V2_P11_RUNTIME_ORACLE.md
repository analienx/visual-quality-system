# P11 — Country / Region / Year *executed* DAX oracle

**Status:** draft implementation; semantic runtime and visual interactions not
accepted until source-bound live evidence and independent review exist.
**Base:** P10 `908c538582a9510b8932d94aa5dd6860eb22a1a2`, PR #51, issue #50.

## Concrete coverage

- Query the **real Microsoft Modeling MCP** model associated with an exact
  run-owned Power BI Desktop PID. Refuse ambiguous or absent local engines.
  Reuse a single connection across all year states and reject model/PID drift
  even if the individual DAX results are internally consistent.
- Verify the opened candidate's on-disk report+model **files byte-for-byte**
  against the committed screenshot-bound P10 fixture, whose historical
  report+model fingerprint is
  `0aabd401d0fb2973263a77faa8349b552e7a74325b3154499c0aeef40d29bdc3`
  *before* launching an MCP connection. A portability review found that
  `vqs.pbir.source_digest` can vary between Linux and Windows for identical
  archived files; it may also equal the historical fingerprint on Windows.
  The **byte comparison**, not digest inequality, authorizes use of the
  stable manifest identity for live queries. Record the local digest as a
  diagnostic only (`vqs_runtime_source_digest`).
- DAX `SUMMARIZECOLUMNS` uses `Fact Sales[Reporting Year Sales]` by `Dim
  Store[Country]` (five expected values), `Dim Store[Region]` (three expected
  values), and a KPI `ROW` (Sales, Units, YoY growth, GM%).
- The **year filter is executed in DAX** using `TREATAS ( { YEAR }, 'Dim
  Date'[Year] )`, not a misleading `scope.period` tag. The latter is
  explicitly unsupported by the current Modeling MCP adapter.
- Both group sums must match the scalar Sales measure to within $0.05.
  Duplicate/mismatched geography, missing rows, bad types, wrong model/query
  context, inconsistent totals, absent live model and source drift block.
- Distinguish first-year blank YoY (legitimate) and negative YoY growth
  from invalid negative Sales or nonfinite numeric values.
- Compare explicitly transcribed **full-precision UI tooltips and bars** to
  DAX; rounded `$2.7M` screenshot labels cannot establish numerical parity.
  Absence of screenshot/tooltip observation means `BLOCKED`.

## Running on the owned Windows Desktop host

1. Use a **freshly opened, disposable P10 candidate** matching the manifest.
   Record the actual process PID that owns the model; do not attach to an
   unrelated Desktop instance. The probe itself never opens/reloads/saves it.
2. From the VQS checkout, where Microsoft Modeling MCP is available:

   ```text
   python -m scripts.contoso_p11_semantic_probe C:\Workspace\scratch\P10-candidate --desktop-pid 12345 --year all --year 2024 --year 2025 --output C:\Workspace\scratch\vqs-p11-runtime\semantic-receipt.json
   ```

3. Review each state: `semantic: pass` means executed DAX matches itself
   across country, region and KPI aggregates. It does **not** certify the
   report visuals, hover tooltip values or interactivity. Store runtime
   receipts in private scratch/run storage, **not public Git history**.
4. Capture genuine before/after selected-year Desktop screenshots and hover
   values on the same exact source and compare through `compare_ui`. Run click
   interaction experiments separately and record which visuals respond and
   how; do not turn `interactive` green based on numerical equality alone.

## Phase-review boundary

| Gate | This phase |
|---|---|
| P10 visual design & structural authoring | Previously evidenced in #51 |
| Model-source fingerprint | Enforced before live connection |
| Country/Region/KPI semantic queries | Implemented; live runtime execution required |
| Year-specific DAX query (not metadata-only) | Implemented; live runtime execution required |
| Model sums, exact country aliases, negative controls | Automated tests |
| Actual map tooltips, slicer screenshots | **BLOCKED** until run-owned UI evidence |
| Country/map and region/bar click behavior | **BLOCKED** until interactive capture |
| Decomposition-tree feature parity | **Not equivalent**; product decision pending |

The original Contoso and P10 assets are unchanged; there are **no report or
semantic-model edits** in this phase. Hosted Linux/Windows CI tests the
deterministic oracle contract, not Power BI Desktop's real query results.
