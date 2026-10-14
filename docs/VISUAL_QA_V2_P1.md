# VQS 2.0 — P0/P1: source-bound visual evidence (implemented)

This note documents code on feature branch
\`work/vqs-specialist-evidence-r1\` stacked on draft PR #42
(\`e013c55504f6af47212bc50782f7856a41641f6c\`).
It does not imply completed P2–P8 release acceptance.

## New operator workflow

Do not upload review bundles or crop sidecars to public GitHub.
They can contain sensitive business data and customer identifiers.

~~~console
vqs regions build C:\private\review-bundle C:\private\visual-regions --report C:\private\Contoso.Report --target Markets_drivers/market-sales --target Stores_customers/customer-health --target d9bc3b8f90439bcc/sales-by-country --padding-px 24

vqs regions verify C:\private\review-bundle C:\private\visual-regions --report C:\private\Contoso.Report

vqs regions plan C:\private\review-bundle C:\private\visual-risk-plan.json --report C:\private\Contoso.Report
~~~

\`build\` consumes the *existing verified v1 review bundle*, checks the
source/revision and membership/pixel proof, reads hashed PBIR inventory,
and creates a **separate private derived sidecar**. It will not overwrite
pre-existing output. Failed incomplete sidecars are retained for explicit
private cleanup rather than risking deletion of a foreign directory. Each crop stores the true page/visual ID and type,
PBIR rectangle, exact rational scale, outward-rounded target and
padded-context rectangles, original canvas SHA-256, crop SHA-256, and
decoded pixel equality proof. There is no Pillow dependency; PNG
re-encoding uses the existing bounded decoder and a lossless
8-bit encoder. \`verify\` independently reconstructs the geometry and
decodes/computes every crop's original pixel rows, and rechecks provenance.

\`plan\` emits read-only spatial graph, specialized routing *candidates*,
and a coverage ledger showing \`planned_not_executed\` vs
\`not_applicable_to_type_or_geometry\`. No geometric intersection or
scrollbar generates a vision FAIL automatically. Overlays/z-order and
effective text properties stay explicitly uncertain.

## Actual private Contoso proof — 14 October 2026

The 5-page real private capture in
\`C:\Workspace\scratch\vqs-i5-verified-review-bundle\`
was reused read-only; its source remains a private disposable clone
rather than being copied to this public repository.

| Observed visual | Exact PBIR selector | Native PNG crop | Scale |
|---|---|---:|---|
| Markets & drivers — clipped Sales KPI label | \`Markets_drivers/market-sales\` | 404 × 164 | 6/5 |
| Stores & customers — Customer mix & margin matrix overflow | \`Stores_customers/customer-health\` | 529 × 323 | 6/5 |
| Deep-dive insights — Sales by country map label crowding | \`d9bc3b8f90439bcc/sales-by-country\` | 760 × 312 | 6/5 |

The independent pixel verifier compared all three crops against the
actual decoded report-only canvases. Each crop was also visually
inspected; all show the appropriate target. Full-page Desktop screenshots
remain unchanged and separate. **This proves input identity and cropped
pixels, not automated defect detection or repair.**

## Fail-closed cases and performance

Blocked conditions include unverified canvas transform, missing or
duplicated page/visual ID, NaN/infinite/negative or off-canvas
coordinates, nonuniform scaling, source revision drift, missing/altered
PNG bytes, manipulated crop metadata, undeclared extra sidecar files,
symlinks, traversal, and existing output destinations; routing-plan
output is created exclusively so a race cannot overwrite someone else's file. Supports real
fractional PBIR geometry via \`Fraction(str(value))\` with outward
rounding rather than guessing integer positions. PNG pixel comparison
is exact, not perceptual; context padding is clamped to the page bounds.

\`verify_regions\` keeps only **one source raster page** decoded at a time, not
all pages or one decode per visual. Original bundle membership remains unchanged, so v1
pack/verify/reviewer compatibility is preserved.

## Scope deliberately not claimed

- No specialist image AI rerun yet, no automatic repair, no visual PASS.
- Risk signals are routing hints, not evidence of visible occlusion.
- No unsupported Power BI Desktop viewport calibration claims.
- No source-addressed Microsoft-formatting change or verified matrix/map fix.
- No full scoped filters/period/RLS semantic parity.
- No second genuinely unrelated complete PBIP accepted yet.

Next vertical milestone: \`kpi_clipping\` and
\`table_matrix_overflow\` specialist ports, with the **same full-page
context + measured target crop**, required-field output contracts,
pinning actual executed model/effort, independent two-pass comparison
against the existing I8 baseline, approved privacy posture and distinct
reviewer/fixer identities. One real candidate repair follows only
after the specialists are genuinely better at localization and defect
classification.


## P0 toolchain capability probe (read-only, 14 Oct 2026)

\`vqs doctor\` and the installed commands confirmed:

| Capability | Observed | Significance |
|---|---|---|
| Microsoft report authoring CLI | 0.5.0 / installed | Available for later typed candidate repair; no authoring changes in P1 |
| Power BI Desktop Bridge | 1.0.0 / installed | Proven from prior capture; no Desktop instance running during the P0 probe |
| Microsoft Modeling MCP | Installed, live version unknown | No new live DAX query claimed by P1 |
| Full five-page Contoso report-only canvas | Verified at 1536x864 vs 1280x720 PBIR | Proven rational scale 6/5; supports source-addressed crops |
| Fully supported filtered/period/RLS execution | Not proven | Must remain NOT_RUN/BLOCKED in future regression |
| Second genuinely unrelated complete PBIP | Not yet identified | P7 remains open, do not substitute a renamed clone |

Neither the Microsoft CLI binary nor its skills were automatically upgraded.
\`powerbi-report-author\` must be used for later supported PBIR authoring,
while this phase is read-only evidence extraction only.

## Independent phase code review

A separate read-only Muse high-effort review identified a possible
foreign-directory deletion race in failed crop rollback and excessive
memory retention across pages. Both were fixed **before phase acceptance**:
failed output is left invalid for explicit cleanup (no recursive removal),
routing JSON is opened with exclusive creation, symlink destinations are
rejected, and the independent verifier now holds one decoded source page
at a time. Regression tests cover a competing writer's existing marker,
symlink refusal (skipped where Windows privilege is unavailable),
metadata injection and multi-visual one-page decode reuse.
