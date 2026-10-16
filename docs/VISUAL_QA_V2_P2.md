# VQS 2.0 — P2 source-isolated specialist pilot (16 October 2026)

**Delivery:** stacked draft PR #44 on draft PR #43 / #42. Advisory only;
no original PBIP or semantic-model writes, no merge, no release authority.

## Why this implementation changed after actual visual evaluation

P1 produced verified source-bound crops (54 Contoso visuals). P2 originally
sent the full-page screenshot **and** target crop to each specialist.
This produced a real **wrong-visual false positive**: while assigned the
visually clean `Markets_drivers/market-margin` card, Spark 1.3 Contributor
returned a clipping FAIL for the **other** Sales card on the full page.
The same call correctly found the real Sales clipping, but attribution
to the selected PBIR visual was wrong.

**Implemented and live exercised:** source-specific specialists now see
**only their pixel-verified native target crop**, even though VQS still
verifies and seals the original page, source revision, visual ID, and the
crop-page correspondence. Generic full-page/context scanning must be a
*distinct* task (P3), not a second unmarked image inside per-visual QA.
Provider receipts state which image view was actually sent.

## Real, independent Contoso observations

All evidence below was captured from previously verified five-page
Contoso report-only canvases with actual PBIR selectors. Actual Muse
model identity is observed from the CLI's `--json`
`task.lifecycle.status` provider facet, and the answer from its
single `run.terminal.completed` event. Both are checked independently
of text emitted by the vision model. High reasoning effort and
tool-disabled sessions, with explicit per-run image-upload and
Contributor Mode opt-in.

| Pilot observation | Real observed outcome | Status |
|---|---|---|
| Sales card `Markets_drivers/market-sales`, generic focused reviewer | Clipped lower label detected on two independent reviews | Detected |
| Customer matrix `Stores_customers/customer-health`, generic focused reviewer | One PASS, one FAIL; FAIL partly mislocated the cutoff | Inconsistent |
| Sales + clean Margin KPI, full-page-plus-crop fixed-key review | Sales detected but clean Margin incorrectly FAIL for Sales defect | **False-positive source attribution** |
| Same two KPIs, target-crop-only fixed-key review | Sales `content_cutoff=FAIL`; clean Margin all three checks PASS | **Working two-item P2 KPI slice** |
| Matrix strict 3-check review, full-page-plus-target | `row_total_visibility=PASS` despite partially exposed row | **False-clear** |
| Matrix lower-row prompt / extra lower-body views | Still missed the partially exposed customer row | **No demonstrated benefit** |
| Clean Products matrix with ordinary scrollbar | Model reported visible headers/rows readable | Useful negative control |
| Wonder high independent matrix attempt | Invalid field-length/schema response; no accepted finding | **BLOCKED**, not a model success |

The native screenshot shows the customer segment body row is partially
exposed just above a fixed Total row. This is a legitimate visual
communication concern; screenshot pixels alone **cannot** prove whether
the remainder is interactively reachable by scrolling. Neither normal
scrollbar chrome nor lack of an interactive test automatically constitutes
a FAIL. The correct acceptance state is uncertainty, not a fabricated PASS.

**Product decision:** KPI source isolation advances as a pilot result.
The **matrix row-visibility detection lane is NOT accepted for automated
PASS or repair**. `row_total_visibility=PASS` is normalized to BLOCKED
pending independently proven calibration; `scroll_access=PASS` is
normalized to BLOCKED/NOT_RUN until actual interaction instrumentation.
Both original model responses remain in a private source-bound sidecar.
More image views were measured and did not improve this case; the
production pilot does not upload the extra derived strip by default.

## Provider/event and output contract

- `vqs.review.providers.muse` uses explicit `--json --model`,
  `--contributor-mode on|off`, `--reasoning-effort high`,
  `--output-schema`, frozen exact crop PNG and tool-disabled invocation.
  Runtime event model ID must match the pin; no quiet fallback.
- `vqs.review.contracts` fixed-key schema checks missing/extra data,
  unsupported model assertions, evidence length and contradiction;
  provider schema maxLength matches validator for repair hypotheses.
- `vqs.review.adaptive_port` retains raw responses, source+crop hashes,
  actual model receipts, skipped-budget state and full-page
  `not_run` coverage. The v1 `ReviewPort` contract remains unchanged.
- Contributors must separately opt into both remote pixel upload and
  Contributor Mode. Never upload private screenshots, PBIP caches or
  customer rows to public GitHub.
- No semantic answer parity, RLS assertion, cross-page design audit,
  Microsoft authoring PASS, or final visual repair is implied.

Example advisory invocation (authorized private fixture only):

```console
python -m vqs.review.adaptive_port PRIVATE_BUNDLE PRIVATE_REGIONS --model muse-spark-1.3-contributor --allow-remote-images --allow-contributor --target Markets_drivers/market-sales --target Markets_drivers/market-margin --out PRIVATE_OUTPUT.json
```

## Validation and remaining acceptance

P1's 54/54 crop proof was already independently verified. P2 focused
adversarial tests cover runtime JSON event identity, target-only image
transport, fixed-key response correctness, source drift, consent,
provider failures and matrix interaction PASS suppression. The Windows
full suite in a private, branch-installed venv passed **1,354 tests
(8 skipped)** at the earlier working-tree revision, preventing 23 false
failures from the stale globally installed `vqs.exe`; fresh exact-head
focused/hosted CI must still be checked after this patch.

Next deliver in order: (1) repeat crop-only KPI positive/negative
evaluation on independent runs and additional pages, (2) P3 whole-page
sweeps and evidence reconciliation, (3) candidate-only Sales label repair
through Microsoft's official pinned authoring CLI with fresh, independently
reviewed after-render and honest answer scope, (4) interactive matrix
scroll and holdout corpus, (5) unrelated second populated PBIP.
Keep PR drafts until true functional proof exists.
