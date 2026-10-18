# P14 — Real-value interaction trace comparison, Desktop clicks still blocked

P11 established live DAX map / region / KPI values for `All`, 2023, 2024 and 2025, but its receipts correctly stated `interactive: not_run`. Matching a DAX query is **not** evidence that the visible slicer changed, a map click filtered the KPI cards or any drill action ran.

P14 adds a source-bound, screenshot-byte-bound **recorded trace consistency validator** for the Deep-dive insights page. It measures possible parity violations without conflating written metadata with authenticated Desktop input. Both P13 and P14 are engineering checkpoints; they do not independently certify a customer report.

## Mandatory source and interaction checks

The CLI compares the currently loaded source project fingerprint with a fresh, source-bound, same-PID model oracle, then reads actual PBIR visual fields and default/overridden interactions:

| Control | Exact PBIR evidence | Expected runtime check |
|---|---|---|
| Year slicer | `slicer-year` projects `Dim Date.Year` | Select All, 2023, 2024, 2025; match the four cards and visible geography values against executed DAX, using the text's rounding interval |
| Country map | `sales-by-country` is a `shapeMap` with `Dim Store.Country` | After returning to 2024, click United States and verify the filtered sales card equals the model's 2024 United States sales |
| Region bar | `what-drives-sales` uses `Dim Store.Region` | Explicitly clear the country selection, check the full-year total returned, click Europe and compare with its year-filtered regional sales |
| Drill | The P10/P12 region bar has **one** Category axis projection, not a declared hierarchy | `not_declared_for_single_region_axis` for this particular visual; this says nothing about unrelated pages or future drill features |

`visualInteractions` overrides of type `NoFilter` between these source visuals and their guarded cards cause a structural failure. Missing runtime observations are not silently inferred from default Power BI behavior.

Eight separate UI states must be provided in **that order**: `year:all`, `year:2023`, `year:2024`, `year:2025`, `year:2024-reset`, `country:United States`, `clear:country`, `region:Europe`. A return to 2024 and clearing the country are mandatory controls against residual context. Every state has a different real PNG capture, exact SHA-256, dimensions, page ID, source fingerprint and Desktop PID, plus independently transcribed *visible strings*. Display strings such as `$12.3M` or `7.2%` are compared as rounding intervals against the actual, unrounded DAX numbers; a 2023 blank YoY is legitimate.

## Run only against current source and private evidence

```text
python -m scripts.contoso_p14_interaction_assess <live-Report-dir> \
  --oracle <private-current-all-years-dax.json> \
  --trace <private-ui-observations.json> \
  --captures <private-PNG-dir> \
  --output <new-private-interaction-audit.json>
```

The existing `scripts.contoso_p11_semantic_probe` is historically pinned to the **P10** archived source. To use a **P12** source, obtain a genuinely fresh same-source model receipt (using the P11 `collect` API in the relevant live Desktop model); never copy the old P10 hash or alter the JSON label to make it fit. In the Windows runner, source hashing must be performed in the same environment as the report/receipt because the prior P10 archive inventory reported cross-platform `source_digest` ordering drift.

The trace JSON uses `schema: vqs.contoso-desktop-interaction-trace/1`, the same `source_sha256` and `desktop_pid` as the oracle, `model`, `page_id: d9bc3b8f90439bcc`, and an eight-item `events` array. Example of one event (repeat with all required scenarios):

```json
{
  "id": "year:2024",
  "action": "select_year",
  "capture": {
    "file": "2024-visible.png",
    "sha256": "<sha256 of exact on-disk PNG>",
    "pixels": [2560, 1440],
    "page_id": "d9bc3b8f90439bcc",
    "desktop_pid": 12345,
    "source_sha256": "<current source digest>"
  },
  "observed": {
    "selected_year": 2024,
    "kpis": {"Sales": "$100.0M", "Units": "1.0M", "YoY": "2.0%", "GM": "30.0%"},
    "country": {"United States": "$30.0M", "Canada": "$25.0M", "United Kingdom": "$20.0M", "Germany": "$15.0M", "Australia": "$10.0M"},
    "region": {"North America": "$55.0M", "Europe": "$35.0M", "Asia Pacific": "$10.0M"}
  }
}
```

Those example values and screenshot dimensions are **illustrative, not actual Contoso model measurements**. A complete trace must have every observed year, selected geography, and after-filter sales amount; map and region values may require visiting each tooltip separately.

## Truth boundary and review

- A mismatch returns `evidence_consistency: fail` and exit 1. Missing state, unreadable capture or missing model proof returns `blocked` and exit 2.
- A numerically consistent transcript sets `evidence_consistency: pass`, but **`interactive: blocked` and exit 2 remain**. A script receiving a caller-authored JSON file cannot prove a user actually clicked Power BI Desktop or read those strings from the pixels.
- Genuine interactive acceptance requires an authorized Desktop/UI collector or an independently executed and signed-off observation with verified source, action sequence and fresh captures. The present pinned report CLI supports warm screenshots but has not supplied a trusted click/hover witness. Until that capability is established, report UI acceptance cannot be green.
- The source is never changed by this checker. Screenshot paths are confined to one supplied private directory, SHA-verified and temporarily frozen for decode. Do not commit business-value screenshots, DAX numbers or raw user observations to Git.
