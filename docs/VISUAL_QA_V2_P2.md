# VQS 2.0 P2 — card/matrix specialist review (draft pilot)

Stack: draft PR #42 -> draft PR #43 -> draft PR #44. No merges or original
PBIP edits. P1's verified v1 review bundles and separate pixel-exact
`regions.json` sidecar remain the only valid source of model imagery.

## Operator invocation

Only run from an authorized local machine with a verified full Contoso
bundle and derived regions. Each explicit target is the **actual PBIR**
page ID and visual directory ID, not a model-generated name:

```console
python -m vqs.review.adaptive_port C:\private\review-bundle C:\private\visual-regions --model muse-spark-1.3-contributor --allow-remote-images --allow-contributor --target Markets_drivers/market-sales --target Stores_customers/customer-health --max-tasks 2 --out C:\private\p2-specialist.json
```

Contributor Mode is **not** an enterprise-safe default. For corporate
report screenshots use an independently approved non-Contributor model
and omit `--allow-contributor`; remote-image consent is still required.
No model choice silently falls back. The adapter sends **the verified
full page and the hash-matched native target crop**, from immutable
local frozen copies, into separate tool-disabled high-effort invocations.
If the installed Muse CLI cannot expose a recognized and trustworthy
model completion event, the run must be recorded **BLOCKED**, not PASS.

## New code contracts

- `vqs.review.contracts`: VQS-owned source, page, visual, image and task
  identity. Checks are required fixed keys; extra/missing keys, fabricated
  identity, empty evidence, inconsistent PASS/FAIL and invalid uncertainty
  types block. `observed_symptom` is independent of verdict, so a BLOCKED
  response describing clipping remains an explicit confirmation candidate.
- `vqs.review.specialists`: versioned KPI and table/matrix rubrics.
  A scrollbar alone is not an error. Prompts never supply source
  authority, property paths, DAX facts or release permission.
- `vqs.review.providers.muse`: explicit model + high effort,
  zero shell/write/web, bounded execution and image hashing, independent
  provider-event actual-model receipt required.
- `vqs.review.adaptive_port`: strict P1 sidecar verification,
  source-linked observations, budget tracking, optional exact targets and
  compatibility with `ReviewPort.review(bundle_dir)`. Every page remains
  **BLOCKED for full-page completeness** until P3 page sweeps are added;
  specialists do not certify a whole report.

## Acceptance still pending

Hosted synthetic checks/CI must pass on the exact PR #44 head.
A genuinely live two-image Muse run is **NOT VERIFIED** until Zephyrus is
responsive and the actual installed Muse stream/event format can be
checked and pinned. Even with runtime success, two independent card and
matrix reviews, clean controls, true location and false-positive scoring
are required before P2 is accepted.

P3 remains adaptive dispatch, page sweeps, maps, cross-page review and
precision-led reconciliation. P5 is the candidate-only Microsoft
authoring and fresh before/after visual repair; P6 adds real matched
semantic/filter/period data scopes and honest RLS NOT_RUN. The second
unrelated PBIP is still missing. No publication/release approval.
