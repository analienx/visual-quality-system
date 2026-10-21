# Engineering preview · 21 October 2026

**Visual Quality System — Power BI core · `0.0.1a0`**

> [!IMPORTANT]
> **An evidence-backed engineering candidate, not a tagged or independently approved production release.** All named code PRs are merged into `main` and hosted CI has passed. G2 independent design acceptance, complete country-map interaction scope, pixel-to-PBIR geometry calibration and G6 owner/verifier approval remain open.

[Get started](../README.md#see-value-in-one-minute) · [Premium preflight](PREMIUM_POWERBI.md) · [Architecture](ARCHITECTURE.md) · [Full acceptance matrix](ACCEPTANCE_MATRIX.md) · [GitHub evidence issue #16](https://github.com/analienx/visual-quality-system/issues/16)

## The change that matters

**VQS has now been exercised on two truly different, populated Power BI projects, end to end up to an independent approval decision.** A developer can inspect PBIP/PBIR, receive ranked issues, declare a small premium design contract, then gather and seal real Desktop screenshots and actual live DAX/interaction observations without editing the original report.

| Available in `main` | What users get | Merged evidence |
| --- | --- | --- |
| Power BI-first engine | Source/model rules, typed repair contracts, separate Power BI release profile | [PR #63](https://github.com/analienx/visual-quality-system/pull/63) |
| Native quality assurance | Exact Desktop/PID, source-bound images, Modeling MCP, Windows UIA and composed assurance | [PR #64](https://github.com/analienx/visual-quality-system/pull/64) |
| Better trust in map findings | Bubble-map labels are not falsely enforced on Shape Maps | [PR #68](https://github.com/analienx/visual-quality-system/pull/68) |
| Premium preflight | Source-hashed owner intent, KPI spacing, explicit typography, density/focal checks, top-three advice | [PR #69](https://github.com/analienx/visual-quality-system/pull/69) |
| Mixed-size page evidence | Normal pages + Tooltip retain their distinct canvas sizes; unproven transforms stay blocked | [PR #70](https://github.com/analienx/visual-quality-system/pull/70) |
| Verified report-only pixels | Recognizes doubled-DPI six-row dotted page borders, independently checks sidebar, produces lossless private report-only crops | [PR #71](https://github.com/analienx/visual-quality-system/pull/71) |

The earlier [PR #66](https://github.com/analienx/visual-quality-system/pull/66) upgraded onboarding and architecture; [PR #67](https://github.com/analienx/visual-quality-system/pull/67) corrected a Windows symlink test-fixture problem. The older unpublished premium candidate `8a31cde` was *not* recovered; the separately reviewed, smaller implementation in #69 is what actually shipped on `main`.

## Real Desktop exercise — two PBIPs, eight pages

<details open>
<summary><strong>Contoso Retail · five-page native review</strong></summary>

- **Subject:** real five-page PBIP with 54 visuals, all canvas dimensions 1280 × 720.
- **Evidence:** captured **5/5 native pages**, and independently remeasured **all five actual report-only canvases** at 3072×1728 pixels / 2.4× scale on a second clean disposable Desktop clone. Successful repeated Modeling MCP data query, source SHA-256 `0e94efc38bd1ec852e4e079afb13b626ec586d5a9506ea607f691dfffa60c847`.
- **Interaction:** newly executed multi-year DAX oracle and **9 native Year/Region UIA events** agreed, including KPI and card alignment readings.
- **Integrity:** source-bound raw-window bundle successfully packed and independently reverified; the newer clean-canvas bundle also verified `review_image_basis=verified_canvas`, SHA-256 `0f56785c8e20ce9c58c978c45a438b24da3d2cf84a71bb2c622d769166e3d430`. Original engineering bundle digest `26151ceabaf140037677f259979ba7b98a4d0aaf2c1e2569a6fb3894c2d6cf19`.
- **Visual review by implementer:** readable KPI rows, charts, matrices and actual country geography in the Shape Map; *not* an independently approved G2 review.
- **Safety:** tested a source-equal private disposable copy with a separate Desktop PID; the previously open unsaved Contoso session was not modified.

</details>

<details open>
<summary><strong>Corporate Spend · independent three-page Microsoft sample</strong></summary>

- **Subject:** Desktop-converted PBIX→PBIP, 20 visuals, two 1920 × 1080 pages and a **600 × 450 Tooltip**; source SHA-256 `f9d935bf532161d72160ed55ce263e6cdd09cbf2836f4a9f3a2f484349554697`.
- **Evidence:** captured **3/3 native pages**, repeated live Modeling MCP query, packed and verified private bundle `b8016b6c4b5df27972d4589326c73805bd46a60dcf5004c4f8f4ab6435daa80c`.
- **Interaction:** real Windows accessibility-based `Sales Region` selection **Europe → Latin America → Europe**. Live DAX and screenshot figures agreed: **Europe $2,129,759 / 6.78%** vs **Latin America −$534,753 / −13.08%**.
- **Restoration proof:** original and restored whole-window screenshot SHA-256 hashes **identical**; selected image differed. One initial UIA read was stale until dropdown collapse/refresh settled, which is why a single instantaneous response is insufficient evidence.
- **Visible limitation:** IT Spend Trend's **Azure Maps visual requires sign-in**, so the first page is *not* fully useful without an account. This is a real environment-dependent user-visible defect, not something a source-only check may waive.
- **Other finding:** a possible source-overlap between some slicer/textbox elements was not established as a visible collision in the observed captures; no unsafe auto-repair was attempted.

</details>

**Privacy boundary:** screenshots, local paths, `.pbi` model caches, underlying data and numerical receipt files remain on the authorized Windows computer; only hashes, counts and verified general findings are documented here.

## First successful user journey

```console
# Offline: inspect and prioritize
vqs triage MyReport.pbip --out quality.md

# Optional: declare intended page hierarchy (edits your own JSON, not PBIP)
vqs premium MyReport.pbip --init-contract design-intent.json
vqs premium MyReport.pbip --contract design-intent.json --out premium.md

# On a permitted Windows Desktop with a live model:
vqs capture MyReport.Report private-renders --pid <EXACT_DESKTOP_PID> --live-data
vqs bundle pack MyReport.Report private-renders private-bundle --fixer-id reviewer-candidate
vqs bundle verify private-bundle --report MyReport.Report
```

**What counts as success:** an exact current source identity, a populated actual model, all expected page captures and a byte-valid evidence bundle. **What is not implied:** a visually beautiful report, calibrated per-visual pixel crop, generalized DAX/RLS correctness or independent release authority.

## The honest G0–G6 decision

| Gate | Evidence as of 21 October | Product-level verdict |
| --- | --- | --- |
| **G0 · Source and custody** | Two actual source hashes, exact report/PID binding, sealed image inventories | Engineering evidence |
| **G1 · Real populated model** | Both Desktop instances answered stable repeated DAX probes | Engineering evidence |
| **G2 · Design and pixels** | All eight real pages captured; **Contoso 5/5 report-only canvases separately measured and sealed**; Corporate clean-canvas/Bridge universal transform missing, Azure Maps sign-in visible, independent reviewer still pending | **Blocked for production** |
| **G3 · Safe repair** | Typed allowlisted repair and rollback contracts, private candidate tested in earlier runs | Engineering evidence, not blanket acceptance |
| **G4 · Same-task interactions** | Nine Contoso UIA events and source-bound Corporate region select/restore verified | **Limited-scope pass; country-map/generalization blocked** |
| **G5 · Word/DOCX** | Separate optional component; not required for the Power BI-only profile | Not in release scope |
| **G6 · Independent approval** | No registered separate trusted reviewer/owner promotion authority; no independent signed multi-project verdict | **Blocked** |

Contoso's new verified report-only crops have independently measured borders and pane separation, with an observed effective scale of 12/5. This proves those specific full-page pixels exclude Desktop chrome; **it does not certify each visual's rectangle**. The Bridge still does not supply a universal viewport/DPR transform, so `geometry_calibration=blocked` remains correct. Corporate Spend's report-only crop also remains unproved. Full native-window screenshots are useful as raw evidence but should not be silently treated as clean canvases.

### Steps to formally promote Power BI core

1. **Independent reviewer** inspects current hash-matched full-page captures (all eight pages) and adjudicates visible limitations, including the Azure Maps login-required area and Corporate static overlap. Record actual findings, not scores invented by the implementer.
2. **Release owner** explicitly defines supported G4 interactions and any map limitations; unsupported country selection cannot silently become a pass.
3. **Technical verifier** resolves per-visual pixel calibration if mandatory for the declared G2 scope, or narrows the reviewed claim and documents why a clean viewport is not required. Never report an unknown transform as measured.
4. **Independent owner/promoter** signs the declared `powerbi-core` G6 evidence scope. Require that negative controls, privacy and source hashes agree and that all mandatory checks are either passing or explicitly removed from the product promise with authorized rationale.

Until those steps are completed, this project is a **working engineering preview**, not a certified production quality gate. Do not close [acceptance issue #16](https://github.com/analienx/visual-quality-system/issues/16) on implementer testimony.

## Compatibility and next step

- Python 3.11+, Windows optional for static diagnostics, actual Windows Power BI Desktop and Microsoft integrations for native evidence.
- Source analyses are offline. Optional remote image review requires explicit consent; a model opinion is advisory and cannot sign release authority.
- Power BI core is independent of Word/DOCX. No Fabric/web expansion is in scope.
- **No more feature expansion for release candidate.** Fix only demonstrated, user-visible regressions and obtain the independent release evidence above.

*Engineering evidence date: 21 October 2026; checked against `main` merge `c54f0ca` and the private two-report native validation. This page is not a GitHub Release publication.*
