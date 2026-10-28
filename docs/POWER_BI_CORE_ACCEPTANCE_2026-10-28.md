# Power BI core · release acceptance snapshot
*28 October 2026 · real Desktop / real Model / separate private evidence*

**Release disposition: NOT APPROVED.** The engineering source, DAX and native-interaction proof is substantially complete for two unrelated reports. Independent authorized visual signoff, precise supported-feature boundary and owner/publisher G6 approval have **not** been granted. This is a deliberately honest release-governance record, not a plan for further architecture.

## What was actually exercised

| Subject / proof | Contoso Retail (fictional, Dark final pilot) | Corporate Spend (private, unrelated model) |
| :--- | :--- | :--- |
| Source and local model identity | **PASS**; source/PID/Bridge, true UIA Save witness, no original modifications | **PASS**; distinct native PID/model and source-bound Save |
| Live model / DAX | **PASS**; four Year states and separately pinned 2024+Europe **Sales, Units, YoY, GM** | **PASS**; separate Europe vs all-region Actual/Plan/Variance/percentage contexts |
| Native actions | **8 real Year/Region actions + 1 read-only baseline**; all four Europe KPI readbacks match executed DAX | **2 native Region toggles + 1 read-only baseline**; on/off/on KPI readback matches both DAX scopes |
| Terminal report integrity | Whole PBIR/model hashes + mtimes unchanged; same OS/Bridge identity. Post-interaction dirty flag recorded, **not waived** | Whole PBIR/model hashes + mtimes unchanged; same OS/Bridge identity; dirty flag also kept distinct |
| Real native pages | **5/5** full PNG files, hash-verified and individually inspected, local Modeling ready | **3/3** real PNG files, hash-bound to the second source |
| Final selected state | Year 2024 visible in actual dropdown; 2023/2025 unchecked; selected white icon visibly contrasted | Europe On → Off → On readbacks in actual UI Automation |
| Full visual/premium reviewer approval | **NOT SIGNED**; bounded improvements verified, residual presentation findings below | **NOT SIGNED**; live tooltip-hover and country input not verified |
| Owner G6 | **BLOCKED** | **BLOCKED** |

Evidence is privately sealed under the authorized Windows scratch acceptance area. **No Corporate source, raw values, screenshots or semantic cache are published in this repository.** The Contoso evidence was generated from complete *disposable* copies; the main gallery has NOT been silently replaced with screenshots of a differently authored PBIP.

## Why the final Contoso candidate is stronger

The earlier valid Dark candidate had a material presentation shortcoming on **Markets & drivers**: values were absent for regional movement, channel delivery and two category-contribution charts. A **single new disposable source candidate** copied its verified original model and changed only four same-type native chart `visual.objects.labels` groups using an already validated working bar reference. It also changed the Shape Map title from *Country sales · darker = higher* to **Country sales footprint**, because a quantitative scale was not displayed.

- Microsoft Report Author validation **0 errors / 0 warnings** after the existing *disposable-only* metadata normalizer. No TMDL, DAX, filter binding, coordinates, category hues or source-owner files changed.
- In one native Desktop pilot PID **97888**, **all four new groups rendered useful values without label clipping**. The 3 Regional sales category hues remained distinct and the map remained populated.
- A genuine native UIA Save established strict source and local model identity. Live same-revision four-Year plus Europe four-KPI DAX **PASS**. The very first native G4 run correctly **BLOCKED** due to a hardcoded old map accessibility title; no action was falsely counted.
- A bounded native UIA adapter fix recognizes **exactly two reviewed accessible names** for the same known Shape Map title (old and current), rejecting both absent and ambiguous. It does not match arbitrary Group nodes or loosen PID, numeric/field/KPI checks.
- The corrected same-PID G4 run **PASS**: 8 actions + baseline, all four Europe KPI equalities, strict pre-action source, unchanged full file manifests, and terminal dirty state honestly recorded.
- Fresh all-five-page native screenshots were recaptured from that *same* final pilot and image CRC/SHA verified; no report reopens used to clear filter-induced dirty state.

The new pilot is **not** yet committed as the default public gallery/report because doing so without rebuilding every gallery screenshot and provenance would be misleading. This is reproducible acceptance evidence, not permission to overwrite the production or demonstration PBIP.

## Adversarial G2 review: residual findings and proposed disposition

A separately invoked automated visual reviewer **examined five native screenshots as image pixels** (not just filenames). It found genuine usability concerns. It is a useful challenger, **not a legally or organizationally independent human reviewer**. The corrected current candidate was visually re-inspected for the two material findings:

| Observation | Current engineering disposition | Required before independent premium G2 PASS |
| :--- | :--- | :--- |
| Markets bars lacked readable per-category numeric values | **FIXED in native pilot**: all four charts now render value labels; full category and Total lists remain readable | Reviewer confirms current screenshot and no regressions on all five pages |
| Shape Map title suggested a calibrated numeric color scale without a displayed legend | **MISLEADING TEXT FIXED**; now accurately called *Country sales footprint* | Reviewer decides whether a sparse country-footprint map meets visual-information-value standard or requires a different supported visual |
| Previously near-invisible selected Year checkbox / repeated regional bar colors | **FIXED and native inspected** in selected and baseline states | Distinct reviewer signoff on exact final revision |
| Executive *Decision signals* empty space; internal `GM Target Gap Label` / `Reporting Year Sales LY` wording | **OPEN P2** presentation polish | Confirm copy and minimum useful signal density; do not rename model measures blindly |
| Customer matrices have substantial unused vertical space | **OPEN P2** density/spacing | Review with actual Desktop viewport, preserve readable Total and category rows |
| Cross-page Region-grain reuse and explicit vs inherited font-size declarations | **OPEN design/evidence** (source-only VQS correctly blocks guesswork) | Verify overview/detail intent and actual effective rendered style before any edit |

**Critical distinction:** Microsoft Shape Map supports value-based color saturation and categorical legends depending on the configured field wells; that does not establish that this specific sparse map provides a calibrated numeric scale. Native country-click semantics are unsupported in this pilot; its actual visuals and screenshot should be accepted/rejected on what is visible, not on imaginary interactions. Microsoft official [Shape Map documentation](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-shape-map).

The empty right *Filters* pane is Power BI **Desktop chrome** in a capture, not evidence that the report's PBIR contains a blank visual. It may be closed for publish-quality screenshots; do not arbitrarily edit the original report to remove application chrome.

## Explicit supported scope for this engineering profile

**Proven within the tested subjects:** PBIR source integrity, bounded original-safe repair, populated native screenshot capture, local Modeling readiness, exact Year/Region slicer and accessible Region bar interaction, four-KPI DAX parity, source/file identity, multi-version consumer wheel rollback.

**Not accepted as implemented:** unsupported Shape Map *country-specific click*, hidden Tooltip page *real contextual hover*, arbitrary unrelated custom visuals or generic cross-report UIA navigation. Any first-release exclusion must be **explicitly authorized in the owner capability matrix**, not silently declared PASS.

## Release decision checklist (not signed)

- [x] Source-bound, real populated native page and local DAX evidence for **two unrelated PBIPs**
- [x] Contoso exact-current-source 4-KPI Year/Europe interaction proof; Corporate percentage select/clear/reset
- [x] Real user-agent static auto-fix candidate plus source-safe blocked-case evidence
- [x] Installed PBIPDocumenter consumer native capture, source SHA and rollback proof (merged [PR #21](https://github.com/analienx/pbidocumenter/pull/21))
- [x] Distinct source-bound final Contoso native screenshots and candidate-only color/label correction
- [ ] A **distinct authorized reviewer** signs G2 for the final image revision and G4 supported scope
- [ ] Owner approves precise release scope / exclusion of untested Shape Map click and Tooltip hover
- [ ] Remaining premium-design findings are either actually corrected or intentionally accepted by reviewer/owner
- [ ] Owner/publisher independently authorizes **G6 production promotion**
- [ ] Public release tag/package published only after approvals; user-source and private data exposure checked

Current state: **G0/G1 engineering PASS; G3 proven bounded; G4 engineering PASS for specifically exercised actions; G2 conditional/unsigned; G6 BLOCKED.** No production tag.

[Acceptance gate #16](https://github.com/analienx/visual-quality-system/issues/16) · [Consumer gate #17](https://github.com/analienx/visual-quality-system/issues/17) · [Full criteria](ACCEPTANCE_MATRIX.md) · [Real agent repair limits](AUTO_REPAIR_TRIAGE_2026-10-28.md).
