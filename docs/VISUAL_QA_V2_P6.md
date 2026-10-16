# VQS 2.0 — P6: paired Microsoft authoring diagnostics

**Date:** 2026-10-16
**Branch:** `work/vqs-authoring-baseline-delta-r1`, stacked above draft P2 PR #44.
**Status:** Implemented and validated as a *diagnostic* capability, not as repair/release authority.

## Problem observed on actual Contoso

A one-operation candidate repair removed the clipped Sales-card category label
without affecting any other pixels on the captured page. Both the complete
unchanged source and its one-property candidate nevertheless failed the
Microsoft structural validator: two missing $schema declarations and an
unrelated registered-theme filename mismatch. Three further warnings were
present on both reports.

The older VQS CLI reported Microsoft `invalid` honestly, but it did not
answer the user's practical question: **did the candidate introduce the
problem, or did the inherited baseline already contain it?**

## Implemented functional surface

```console
vqs compare-authoring BASELINE/Contoso.Report CANDIDATE/Contoso.Report \
  --visual definition/pages/Markets_drivers/visuals/market-sales/visual.json \
  --out PRIVATE_NEW_RECEIPT.json
```

The new *read-only* command:

1. Requires separate, same-named, non-overlapping PBIR report trees.
2. Hashes every report file. Rejects missing/extra files, symlink or hardlink
   escape, unexpected mutations, and any difference outside the explicitly
   declared PBIR `visual.json` targets.
3. Also binds the sibling PBIP project shortcut, which Microsoft validates
   outside the `.Report` tree, refusing unequal or missing counterpart
   shortcuts. The referenced local semantic-model definition inventory and
   all its included TMDL/JSON file bytes must also match across both projects.
4. Probes the Microsoft authoring CLI once and runs **the same executable**
   against both reports. No direct-writer fallback.
5. Reconciles structured diagnostic codes, severities and complete messages,
   normalizing only the distinct project-root paths (never stripping visual
   identities or message bodies). Uses multiset deltas to retain duplicates.
6. Reports newly introduced versus inherited errors and warnings, as well as
   cleared findings. The result is `no_new_diagnostics` only when the
   evidence genuinely supports that limited claim.
7. **Always** sets `release_verdict: blocked`; no static comparison
   certifies Desktop rendering, DAX parity, RLS, interactive behavior, or
   approval. Production warning waivers remain forbidden.
8. Optionally saves a JSON receipt to a **new** private path; never overwrites
   an existing receipt.

### Real CLI bug discovered and addressed

The existing Microsoft CLI adapter shortened diagnostic messages to 300
characters. As the A/B clones had different absolute root path lengths,
the same inherited theme diagnostic ended mid-word at different positions.
It therefore initially appeared to be a new candidate defect.

The adapter now provides a separate, bounded complete-diagnostic array
while preserving its legacy 300-character summaries. The paired checker
rejects old/capped evidence rather than fabricating equivalence. Test cases
cover full long path messages, 300-character truncation, oversized diagnostic
payloads, provider errors, new and inherited warnings, source drift, and
unsafe candidate paths.

## Actual private Contoso experiment

1. **Raw, unmodified paired reports:** Microsoft CLI v0.5.0 reports
   `invalid` with **3 errors + 3 warnings** for both baseline and Sales
   candidate. Paired checker: `no_new_diagnostics`, **0 new errors,
   0 new warnings**, `release_verdict=blocked`.
2. **Separately corrected metadata clones:** In private scratch *only*,
   inserted pinned `pbip/pbipProperties/1.0.0` $schema and
   `item/report/definitionProperties/2.0.0` $schema, and corrected the
   registered theme file's inner `name` to match its referenced filename.
   Both unchanged and Sales-candidate clones were identically corrected.
   Microsoft reports `valid` with **0 errors + 3 warnings** for both.
   Paired checker: `no_new_diagnostics`, **0 new errors, 0 new warnings**;
   `release_verdict=blocked`.
3. The only file delta between the *two* corrected `.Report` trees remains
   `definition/pages/Markets_drivers/visuals/market-sales/visual.json`.
   Original Contoso and the already captured P5 candidate are unchanged.
4. Previous P5 live A/B evidence: two independently opened Power BI
   Desktop hosts with populated Modeling MCP readings and native
   3915×2394 screenshots. The deleted clipped caption's pixel differences
   were confined to the Sales card; **zero changed RGB components outside**
   the manually identified Sales ROI. This proves that earlier unnormalized
   diagnostic preview improved, **not** that the newly normalized reports
   are visually certified.

The three remaining Microsoft warnings refer to two undersized Subtitle
textboxes and a legacy map visual; these are broader design/product tasks
and have not been silently waived or mutated as part of P6.

## Acceptance and next valuable step

**What P6 proves:** The single Sales-property mutation introduces no new
Microsoft structural errors or warnings, even against an inherited-invalid
source, and two matched metadata clones can achieve zero structural errors.

**What P6 does not prove:** report release, visual correctness after theme
metadata normalization, DAX answer parity, matrix scroll accessibility, RLS,
filter/period behavior, or general model reliability.

Next: separately remediate the three warnings or document explicit
non-waiving dispositions under an appropriate future policy; fresh candidate
render after any metadata/style corrections; independent focused and page-wide
review; semantic answer regression; then the full promotion gate. Avoid
altering the original Contoso project without explicit approval. Preserve
private screenshots and model caches outside the Git checkout.
