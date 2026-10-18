# P15 — Composed report assurance / independent acceptance boundary

P13 now measures the actual content occupancy inside every selected PBIR visual rectangle. P14 compares source- and image-bound UI observations with live DAX and rejects missing, stale, incoherent or reused interaction captures. P15 composes those checks, prevents partial visual coverage from being described as whole-page review, and **does not let either automated measurement or the editing agent authorize an independent release**.

## Run a page/report gate

After real Desktop rendering, prepare a verified review bundle and build **all** visual crops from it (omit `--target` for full-report coverage):

```text
vqs regions build <verified-review-bundle> <new-private-regions> --report <current-Report-dir>

vqs assurance <verified-review-bundle> <private-regions> \
  --report <current-Report-dir> \
  [--page <exact-page-id>] \
  [--policy <source-and-bundle-bound-pixel-policy.json>] \
  [--oracle <current-live-DAX-oracle.json> --trace <recorded-UI-trace.json> --captures <private-screenshots-dir>] \
  [--out <new-private-readiness.json>]
```

Do not save the private screenshots, data-bearing oracle or observed customer numbers in Git. The command runs verification/measurement again against the actual current source rather than trusting a prior user's JSON assertion. The output includes visual inventory coverage, exactly scoped pixel findings, any numeric/PNG mismatches, outstanding independently witnessed steps and statuses:

- `G0_verified_source_and_images: pass` only after the stored pixels and report source have been reverified.
- `G2_independent_visual_design_review: blocked` until an actually independent, image-capable reviewer inspects the fresh full-page image and the assessment is bound to the same source/bundle.
- `G4_live_interaction_parity: blocked` until a genuine selected-year, map click and region click have been witnessed on Desktop with the checked screenshots. Caller-entered labels are not a click witness.
- `G6_independent_multi_artifact_release: blocked` until the canonical acceptance system can authenticate a separate verifier across two unrelated PBIPs, a rendered DOCX and the required negative corpus, with explicit owner promotion. Unit tests and existing owner approval of P12 do not implicitly meet this later product-wide release gate.

`verdict: fail` is reserved for demonstrated pixel/source/semantic contradictions; missing coverage or independent capability leaves `verdict: blocked`. Exit codes are 1 for failure and 2 for blocked. There is deliberately no success (exit 0) route before genuine external acceptance can be trusted. This is a **pre-acceptance assessment**, not a second or weaker release authority; `vqs.acceptance.run_acceptance` remains the source of truth for G6.

## Why the old review missed the sizing issue

Before P13, the VQS crop path demonstrated only that screenshots matched PBIR rectangles and that no crop pixels had changed. It did not calculate plot-content bounding boxes, internal voids, or margin imbalance. Structure and source identity are necessary but cannot prove a chart uses its allotted screen space. P12 added a specific source-level Deep Dive repair, and P13 added conservative generic rendered-content signals; P14/P15 now prevent a source-only or actor-only result from claiming that all visual and interaction behavior was accepted.

This still has limits: native pixels cannot reliably infer every intended padding value, distinguish all map shapes from legends, read text collisions without OCR/vision, or automatically repair arbitrary visual formatting. These cases remain explicitly `review_required` or `unknown`; a candidate-only repair followed by a fresh Desktop capture and independent review is the safe path. Until actual visual screenshots and external reviewer/interaction capabilities are supplied, **do not close G2/G4/G6 as passing**.
