# P13 — Rendered pixel-content / internal-padding gate

**Scope:** source-bound, native PNG pixel measurements inside an exact PBIR visual rectangle. This closes the former gap where VQS could reproduce a crop pixel-for-pixel, yet never ask whether the content occupied a sensible portion of that visual. It is not OCR, a Power BI formatting introspector, or a substitute for independent aesthetic review.

## Private workflow

Generate a verified report-only canvas review bundle from the real Desktop render using the existing VQS review-capture flow. The source must be the report revision under examination; the screenshot must have a verified canvas transform. Keep screenshots and sidecars in a private location outside the Git repository.

```text
vqs regions build <verified-bundle-dir> <new-private-region-dir> --report <Report-dir> --target <page-id>/<visual-id>
vqs regions audit <verified-bundle-dir> <private-region-dir> --report <Report-dir> [--policy <private-policy.json>]
```

`audit` first independently re-verifies the bundle, source identity, crop-to-canvas pixels, and geometries. It measures only the target rectangle, never an external context gutter; crop bytes are SHA-checked and frozen before decode, and source and crop evidence are reverified after measurement. The JSON response includes per-visual normalized occupancy, content extents, edge/background confidence, left/right/top/bottom margins, longest *central horizontal blank band*, findings and bounded verdicts. No customer screenshot pixel data is serialized in the receipt.

An optional design budget deliberately states expected chart occupancy, rather than treating an intentional sparse KPI or map as a false hard failure:

```json
{
  "schema": "vqs.pixel-content-policy/1",
  "source_sha256": "<exact verified source digest>",
  "bundle_sha256": "<exact verified review bundle digest>",
  "targets": [
    {
      "page_id": "<exact page id>",
      "visual_id": "<exact visual id>",
      "requirements": {
        "min_content_width": 0.65,
        "min_content_height": 0.5,
        "min_foreground_fraction": 0.05,
        "min_interior_foreground_fraction": 0.04,
        "max_blank_band": 0.4,
        "max_margin_skew_x": 0.15,
        "max_margin_skew_y": 0.15
      }
    }
  ]
}
```

All seven values are fractions bounded between zero and one. The width, height and margin figures are relative to the visual's target dimensions; foreground fraction is the proportion of pixels differing materially from the inferred background. Interior foreground excludes an 8% perimeter on every edge, reducing the influence of full-frame borders. These numbers are *illustrative*, not universally correct or automatically endorsed design tokens; a reviewer should select and record limits per report/visual/task before judging. A surrounding frame can make bounding-box width and height look healthy despite a tiny actual plot, so low overall **or interior** foreground density also causes review. Explicit `min_foreground_fraction` and `min_interior_foreground_fraction` budgets can enforce stronger design policies. Stale source/bundle policy, duplicate or nonexistent selectors, tampered pixels and unverified crop calibration are rejected.

Built-in map surfaces (`shapeMap`, `filledMap`, and `map`, as well as `azureMap`) now receive a second, narrower signal: the middle 76% of width and 66% of height must contain some visibly contrasting plotted ink once the source-bound crop is reviewable. A title or thick decorative border can no longer turn a completely white map plot into a mere sparse-layout warning. The receipt records `map_plot_foreground_pixels` and fraction without exposing image content. Small surfaces, patterned/uncertain backgrounds, and maps with *some* plot content still follow the conservative review path: this is a high-confidence **empty-plot** check, not a universal map-coverage score or geographic correctness proof.

## Outcomes and repair loop

| Pixel result | Meaning | Command exit |
|---|---|---|
| `fail` | A confidently near-blank data visual or an explicit source-bound occupancy/padding budget breached | 1 |
| `review_required` | Large internal void, tiny content or skewed padding is plausible, but no design budget permits automated rejection | 0 |
| `unknown` | No reliable uniform perimeter/background; metrics would be unreliable | 2 |
| `not_applicable` (per region) | Thin/small decorative separator, shape or image; no data plot occupancy to judge | Aggregated with other region statuses |
| `no_pixel_issue_proven` | No issue caught by these pixel rules; *not* visual approval | 0 |

Every result sets `visual_acceptance: not_run`. A plot with labels rendered over each other, subtle text truncation, image-based map shading or an unusual patterned background can require other checks even if this gate is clear.

For a `fail`, identify the exact `page_id`/`visual_id`, `budget`, rendered crop dimensions, measured fraction and suspect formatting. Repair only an isolated, disposable PBIR candidate (plot-area/padding, visual height, title, label sizing or renderer binding as appropriate), then validate it, reload into the selected preview host, recapture, rebuild regions, rerun the pixel audit and independently inspect the whole affected page including neighbors. Re-running on old screenshot bytes cannot validate a repair. Any filter, data, model or interaction changes need their respective semantic and UI gates too.

## Tested negatives

- Rendered data visual entirely empty; map plot empty beneath a visible title/frame; decorative blank shape not falsely failed.
- Extremely small shape map/card: review by default, explicit minimum width/height budget can fail.
- Lopsided left/right padding and large interior void between header and footer.
- Thin or thick outline spanning the entire visual does not conceal a sparse, undersized plotted mark; a policy may demand minimum overall and interior foreground density.
- Tiny legitimate decorative shape is not a fatal pixel decoder error; an unreadably small data visual stays `unknown`. Transparent RGBA pixels cannot create imaginary content.
- Checkerboard/patterned perimeter makes the measurement `unknown`, not fabricated precision.
- Stale source and screenshot bundle, unrecognized/duplicate selectors, invalid budgets, modified crop PNG and a crop swapped immediately **after** the first verification.
- CLI returns a failing exit code on a source-bound blank-card fixture without claiming a complete review.

The implementation intentionally **does not automatically edit a user report**. It provides precise evidence and a safe candidate repair route; P12's specific Deep Dive height/title/padding repair is distinct from this general-purpose detector.
