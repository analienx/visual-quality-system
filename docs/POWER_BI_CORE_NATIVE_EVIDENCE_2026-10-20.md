# Power BI core — native visual repair and evidence, 20 October 2026

Status: **engineering-proven in an isolated, populated Desktop candidate;
not independently release-accepted**. This document contains no real report
screenshots, semantic-model cache, customer measurements or local paths.

## Observed defects and source-bound repair

All five report pages were captured **before** the change. Visual inspection
identified concrete quality faults despite an otherwise valid PBIR:

| Page | Observed defect | Exact permitted cosmetic change | Fresh Desktop result |
| --- | --- | --- | --- |
| Markets & drivers | `Sales` KPI title and two category/chart titles inherited large Power BI defaults while peers explicitly used 12/14-point titles | Copy only title formatting tokens from same-type, same-page peer; preserve title text, visual query and position | Consistent KPI/chart-title hierarchy on the entire page |
| Stores & customers | Right-hand `Customer mix & margin` matrix was only 400 canvas units wide; long headings and all segment rows required horizontal/vertical scrollbars. Left matrix had excessive empty width | Split the bottom panels into 608/608 with a 16-unit gutter; normalize title style; suppress redundant subtitle; matrix header `growToFit`, row padding 5→2 and text 11→10 | All three customer segments, sales, margin and total visible without scrollbars or clipping |
| Products & brands | `Margin action list` inherited a large title despite a 14-point peer table title | Copy same-page peer's title formatting tokens, retaining original title text | Title hierarchy consistent; table contents and semantic bindings preserved |

The repair worked on a **new private copy** of the populated PBIP, never
on the source project or on an unsaved user-owned Desktop process. Six
visual-definition files changed; no DAX, Power Query, semantic model, RLS,
filters, data field mappings, report pages or source theme were edited.
Before/after SHA-256 hashes and the typed file allowlist are recorded in
the private candidate repair audit. Microsoft Report Author validation of
the resulting report returned **zero errors and zero warnings**.

## Independent engineering observations

- The local VQS run detected the previously invisible formatting cause:
  the source fact emitter now measures **`visualContainerObjects` title
  cohorts**, including peers that leave the font size inherited. A mixed
  explicit/inherited declaration demands render evidence; it cannot
  automatically prove the inherited effective font size.
- The upgraded pixel analyzer detects a map with a visible frame/title
  but no central plot ink. It does not claim to recognize countries or
  approve every nonblank map.
- A fresh Desktop Bridge process opened only the disposable candidate,
  bound its exact PBIP/report identity and source digest, and captured
  **five of five pages** at scale 2.
- Modeling MCP executed a repeated live data-readiness query and returned
  a populated model. Source identity was checked before and after capture.
- Native Windows UI Automation identified the actual Year slicer and Region
  bars. A formal **nine-event** sequence, checked against a fresh four-year
  executed DAX oracle on the same Desktop PID, **passed all nine scenarios**,
  including 2023/2024/2025, Europe selection, clearing and All restoration.
  The Sales KPI and regional bars followed the selected context. **Readback
  must allow for asynchronous visual refresh**—the first snapshot can be stale.
- A bounded read-only hit test at expected Shape Map country coordinates
  resolved to an **unrelated foreground window**, not Power BI Desktop.
  Thus a blind pointer click would have targeted the wrong app; no pointer
  event was injected. The map country interaction is correctly left blocked
  until a trusted, foreground-attested visual input adapter is available.
- A later formal recorder initially blocked while the disposable Desktop
  window was minimized: Bridge stayed connected, but UIA bounds were empty.
  A targeted `WindowPattern` restore of that **run-owned candidate only**
  returned it to Normal and made the complete nine-event recorder pass.
  Minimized windows now receive an explicit diagnostic; no adapter silently
  restores or focuses a user-owned Desktop window.
- The screenshots were reviewed as whole pages as well as individual
  repairs. The original visual problems above were actually removed.

No cached/simulated screenshot, same-agent assertion, schema-only check or
test fixture is counted as an independent visual acceptance decision.

## Gates still open

| Gate | Evidence today | Status |
| --- | --- | --- |
| G0 source/identity | Exact report/PID binding, digest and complete manifest | Engineering pass |
| G1 populated native report | 5/5 real pages; Modeling MCP live readiness | Engineering pass |
| G2 aesthetics and rendered text | Actual before/after screenshots reviewed by implementing agent; no independent reviewer | **Blocked** |
| G3 repair confinement | Disposable copy; bounded PBIR cosmetics; audited changes; CLI validation | Engineering pass; promotion separate |
| G4 interactive parity | Full 9/9 genuine Year/Region UIA + DAX parity; no Shape Map country click witness | **Blocked for complete scope** |
| G6 release | No independently attested second unrelated PBIP and separate verifier/owner promotion | **Blocked** |

Word/DOCX does **not** enter this `powerbi-core` gate. The next useful
work is an authenticated **map country selection** and a second
structurally unrelated PBIP through the same populated native
inspect→repair→render→semantic/UI→review pipeline. Improve the
renderer/canvas transform before claiming per-visual calibrated crops
where the Bridge does not expose an unambiguous viewport.

## Reproduce without compromising privacy

1. Check the pinned `powerbi-report-cli` skill/tool version and validate
   the candidate. Never modify a live original or use undocumented Bridge
   pointer APIs.
2. Materialize a **fresh private populated PBIP** preserving the original
   model cache, and apply only an owner-approved typed cosmetic diff.
3. Record an exact diff allowlist, source digest, run lease and new Desktop
   PID. Use the Bridge for status/open/capture and Modeling MCP for actual
   data readiness; capture all pages at a consistent scale.
4. Review full-page native before/after renders for clipping, spacing,
   white rectangles, typography, semantics, scrollbars and neighboring
   regressions. Compare real Year/Region UIA behavior with scoped live DAX.
5. Keep all PNGs, customer figures, ABF files and physical host paths
   private. Do not mark G2/G4/G6 passed without the specified independent
   evidence.

The contract lives in [Power BI architecture](ARCHITECTURE.md),
[P13 pixel checks](VISUAL_QA_V2_P13_PIXEL_CONTENT.md),
[P15 assurance](VISUAL_QA_V2_P15_ASSURANCE.md),
[P16 Windows UIA](VISUAL_QA_V2_P16_NATIVE_DESKTOP_UIA.md) and the
[release acceptance matrix](ACCEPTANCE_MATRIX.md).
