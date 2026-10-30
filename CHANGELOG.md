# Changelog

## Unreleased - bounded native Corporate Region interaction

- Added exact-PID native Corporate Sales Region UI Automation and fail-closed DAX comparator.
- Verified real Europe / Latin America / Europe round trip on a separately saved disposable Corporate PBIP. All three collapsed ComboBox states and rendered KPI percentages matched independent region DAX, distinct from the other region; source remained unchanged.
- Used TogglePattern on the exact region option followed by ExpandCollapsePattern.Collapse. Invoke or SetValue alone had not committed the selection.
- Packaged the PowerShell adapter inside the wheel; no simulated mouse coordinates, no false G6 auto-approval.
- [Native G2/G4 acceptance](docs/V012_NATIVE_G_ACCEPTANCE.md) and [issue #120](https://github.com/analienx/visual-quality-system/issues/120).

## Unreleased - next G2/G4 evidence and safe native rebaseline

- Added strict read-only two-native-Save provenance auditing: a material first-Save transition stays blocked, while a *separate* second Desktop session may attest a new exact saved source without relaxing the original guard.
- Added exact-PID Desktop Bridge page-capture source binding, including source and model hashes/mtimes before and after screenshot collection and all native page IDs.
- Added repeatable local-only source/PNG acceptance-subject manifests with explicit distinction between hash-only evidence and native source-bound evidence; all human reviewer and owner G6 fields remain false.
- Independently reproduced Corporate Spend offline-geo source normalization and verified a second strict Save plus 3/3 source-bound native pages. Additional Corporate region G4 actuation and human/owner approval remain outstanding.
- [Reproduction and evidence boundaries](docs/V012_NATIVE_G_ACCEPTANCE.md) | [G6 gate issue #16](https://github.com/analienx/visual-quality-system/issues/16).

## v0.1.1 - agent-first usability (30 October 2026)

- **Clean-install authoring:** distribute the hash-locked Microsoft authoring skill resources inside the wheel; verify the same approved SHA and pinned CLI on preflight. `vqs doctor` now reports the real authoring readiness instead of presence-only success. No validator downgrade or auto-install.
- **One command:** `vqs fix <report.pbip>` uses the existing repair coordinator, resolves the actual report and unique model, generates private run IDs, preserves the source, and prints a decision-ready result. `vqs run --summary` is opt-in; its existing full JSON contract remains default.
- **Agent context:** compact MCP structured output for protocol versions supporting it, with full sealed evidence preserved on disk; keep explicit `pass/fail/blocked`, original preservation and no automatic promotion.
- **Protocol compatibility:** legacy stdio clients remain operational; add 2025 handshake and 2026 stateless discovery/per-request metadata, correct result envelopes, and output schema hints.
- **Theme agent workflow:** `vqs_theme` exposes existing preview/apply/audit through MCP with disposable candidate output required for writes; no additional theme families.
- **Acceptance:** six installed-wheel runner configurations (Ubuntu/Windows, Python 3.11-3.13) and all 14 protected checks passed. Real Contoso PBIP auto-repair, modern/legacy MCP, theme preview/apply/audit, and Microsoft authoring were exercised. Original files remained unchanged. Native Desktop G2/G4/G6 acceptance stays separately gated. [Release evidence](docs/RELEASE_NOTES_v0.1.1.md).


## Versioned production distribution · v0.1.0 (28 October 2026)

The owner authorized publishing a **supported-scope installable distribution**. Its versioned wheel/sdist and SHA-256 checksums are available from the [GitHub v0.1.0 Release](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.0). This is a **local source-review/CLI/MCP product**, not a hosted API or a Power BI tenant rollout. Its production support boundary is source-grounded checks, deterministic triage, supported disposable candidate repair and evidence/agent protocol; advanced native Desktop interactions remain proof-gated engineering preview.

**Important:** public software distribution is **not** independent report-level G2/G4/G6 acceptance. Shape Map country clicking, true Tooltip hover, generalized native repair reload and optional Word/DOCX certification remain outside the supported production scope. See [the full release contract](docs/PRODUCTION_DISTRIBUTION_v0.1.0.md) and [actual reproducible Contoso example](docs/VERIFIED_CONTOSO_SHOWCASE.md). Production publication must not close [#16](https://github.com/analienx/visual-quality-system/issues/16) or [#17](https://github.com/analienx/visual-quality-system/issues/17).


## Public five-page synthetic Contoso reference — 28 October 2026

**Owner-authorized public publication of a fully source-bound fictional Power BI example.** This is an **engineering-preview exhibit**, not a signed production release or software version/tag. The separate private Corporate Spend report, its data, private model/cache and private interaction receipts remain excluded.

- **The artifact is usable.** [Open the full PBIP](examples/contoso-retail-verified/Contoso%20Retail.pbip), including its explicitly fictional model cache, to see populated native visuals without an external data service. All 12 M partitions are internally synthetic; private file paths/credentials are excluded. Both the public PBIR source and strict native-saved ZIP are included because Microsoft Desktop Save drops two schema metadata declarations.
- **The media actually belongs to the report.** Five authentic full Desktop PNGs and five cropped WebP previews are published with individual SHA-256 hashes, crop boxes and source identity: [verified five-page showcase](docs/VERIFIED_CONTOSO_SHOWCASE.md) and [machine-checkable manifest](docs/media/contoso-verified/PROVENANCE.json). CI fails on a changed source, ZIP/model/content mismatch, absent page, missing or changed screenshot, or accidental local settings.
- **The engineering checks are specific.** Genuine saved-source witness, 2024+Europe live four-KPI DAX, **8/8 native Year/Region UIA actions + baseline** and source/model bytes unchanged throughout the interaction test. The last separate automated pixel review found **zero P1/P2 visual observations** on these five images; it is **not** a different authorized human reviewer. Microsoft's authoring CLI validated the normalized project (0 errors / 0 warnings).
- **The established 14-family gallery stays correct.** The existing 28 Light/Dark modes and 56 source-bound real screenshots continue to refer to their own historical Contoso/PBIR candidate hashes. We do **not** swap out the old sample or falsely claim those older images were captured from the new final reference.

### Precise boundaries

This change approves publishing the synthetic **example**, **not** a production release. Shape Map country-specific selection, genuine hidden Tooltip hover and arbitrary third-party Desktop interactions are still outside confirmed G4 scope. A distinct authorized human G2/G4 reviewer and publisher G6 owner approval are not recorded. Issues [#16](https://github.com/analienx/visual-quality-system/issues/16) (core acceptance) and [#17](https://github.com/analienx/visual-quality-system/issues/17) (consumer release) remain open until their actual unmet gate conditions are resolved.

Read the [agent auto-fix guide](docs/AI_AGENT_QUICKSTART.md), [architecture](docs/AGENT_AUTOFIX_ARCHITECTURE.md), [full public example](docs/VERIFIED_CONTOSO_SHOWCASE.md), and [two-subject acceptance ledger](docs/POWER_BI_CORE_ACCEPTANCE_2026-10-28.md). Word/DOCX quality remains independent.


## Native saved-source provenance — 27 October 2026 (engineering preview)

**Latest evidence and limitations:** [27 October engineering notes](docs/RELEASE_NOTES_2026-10-27.md). Protected PRs [#97](https://github.com/analienx/visual-quality-system/pull/97) and [#98](https://github.com/analienx/visual-quality-system/pull/98) merged with required CI/authoring/R6 checks. Microsoft's native Desktop Save strips two metadata schemas; the new disposable-only auto-fix restores only those fields. A separate exact-PID/UIA Save provenance witness allows an explicitly verified native-save source route without weakening the original default age gate.

On two unrelated disposable Desktop PBIPs, real local `byPath` model/source attestation now has a **positive** witness. Fictional Contoso's source-bound Year/Region DAX and eight native actions plus baseline matched; the unrelated private report's native Region On → Off → On readback matched live region-filtered/unfiltered DAX. These are verified **engineering runs**, not independent G2/G4. Desktop becomes dirty again after supported UI interactions despite unchanged physical source, so strict terminal saved-state attestation correctly blocks until the independent acceptance contract is resolved. There is **no production tag or G6 approval**; [#16](https://github.com/analienx/visual-quality-system/issues/16) stays OPEN.

## P1 Desktop native Year control compatibility — 27 October 2026

- Power BI Desktop 2.159 exposed Year slicer options through `TogglePattern` instead of the older `SelectionItemPattern`. The native Windows adapter now supports both, verifies exact selected state and permits only the intended toggle direction; the Python attestation layer recognizes only `TogglePattern.ToggleOn` for Year selection and `TogglePattern.ToggleOff` for clearing.
- After upgrading Desktop, the real disposable Contoso report passed **9/9 native Year/Region UI Automation steps** with live DAX agreement. Strict loaded-file source attestation remained blocked because the Desktop host continues to report unsaved changes even after clean launch. This patch does **not** authorize G2/G4/G6 certification or a production tag; independent acceptance remains [issue #16](https://github.com/analienx/visual-quality-system/issues/16).

## Agent-led Power BI engineering integration — 26 October 2026

**Current consolidated notes:** [26 October engineering update](docs/RELEASE_NOTES_2026-10-26.md). This is an **engineering preview**, not a production tag or independently approved release.

- **Agent-first auto-fixing / premium onboarding:** [merged PR #85](https://github.com/analienx/visual-quality-system/pull/85) (merge [`c36a7e1`](https://github.com/analienx/visual-quality-system/commit/c36a7e189f232d83fc80e76a8970a8536b3fc3a8)) makes the README an agent-led repair landing page and prominently links the [5-minute MCP/CLI setup](docs/AI_AGENT_QUICKSTART.md) and [component-by-component auto-fix architecture](docs/AGENT_AUTOFIX_ARCHITECTURE.md). Supported typed source fixes go to isolated candidates with verification, not automatic report overwrites or production promotion.
- **Power BI Desktop source assurance:** [merged PR #83](https://github.com/analienx/visual-quality-system/pull/83) (merge [`48757e5`](https://github.com/analienx/visual-quality-system/commit/48757e570da52f465a2f69b6479c8b230d4a1e77)) adds opt-in, fail-closed exact-PBIP OS/Bridge identity and saved-state verification, including declared local semantic model source checks. A native disposable report with unsaved state was correctly **blocked**, not falsely accepted.
- **Themes:** [PR #81](https://github.com/analienx/visual-quality-system/pull/81) and follow-up documentation [PR #82](https://github.com/analienx/visual-quality-system/pull/82) are merged. 14 Light/Dark families, 28 modes, source-bound authentic gallery and associated static/native default-state checks are in `main`. **Implementation issue [#80](https://github.com/analienx/visual-quality-system/issues/80) is closed**; its outstanding dynamic state and independent release acceptance obligations were consolidated into still-open [#16](https://github.com/analienx/visual-quality-system/issues/16).
- **PBIPDocumenter engineering handoff:** [merged PR #84](https://github.com/analienx/visual-quality-system/pull/84) ([`8aade94`](https://github.com/analienx/visual-quality-system/commit/8aade94a944ec85d2c2aab3f50b79572cf5ac10e)) now ships a version-pinned consumer integration guide, fail-closed CLI/manifest example and installed-package parity tests. Independent source-inventory parity is supported on two unrelated reports; actual consumer migration, native parity and production G6 remain open in [#17](https://github.com/analienx/visual-quality-system/issues/17) and [#16](https://github.com/analienx/visual-quality-system/issues/16).

**Hosted verification:** the merged README/agent-guide PR #85 passed Windows/Linux CI, Microsoft authoring and R6. These results establish supported **engineering checks**, not independent two-PBIP G2/G4 or release-owner G6 acceptance.

## Adaptive themes integrated into main — 26 October 2026

Owner-approved [PR #81](https://github.com/analienx/visual-quality-system/pull/81)
was merged to `main` at [`9770a52`](https://github.com/analienx/visual-quality-system/commit/9770a52f934daf45c72b1081e11b87009f95ea0b).
The 14-family / 28-mode adaptive-theme feature, its exact-source native
Contoso evidence (140 captures, 364/364 pixel/control checks) and the
56-image public gallery are now integrated. The original authoring commit
`6bb62da` remains in Git history for provenance. The full local test suite
passed 1,860 tests (11 skipped), and all PR CI, authoring and R6 jobs passed.

**Release boundary:** this was approval to merge the **feature**, not
independent `powerbi-core` production acceptance. The two unrelated
PBIP G2/G4 scenarios and broader release G6 remain open in
[issue #16](https://github.com/analienx/visual-quality-system/issues/16).
The implementation issue [#80](https://github.com/analienx/visual-quality-system/issues/80)
has since been **closed as completed**; its unverified P3 interaction checks
were explicitly moved to issue #16, **not marked passed**.


## Native gallery verified against current authoring source — 25 October 2026

- **Source:** GitHub authoring commit [6bb62da](https://github.com/analienx/visual-quality-system/commit/6bb62da26d7589dca492571fa5f2ee444e369117) and [workflow run 40224195761](https://github.com/analienx/visual-quality-system/actions/runs/40224195761). All 2,352 downloaded candidate files matched the local candidate set.
- **Pre-capture QVS:** 28/28 approved Light/Dark modes passed with zero categorical-color findings.
- **Native Desktop:** 140/140 genuine five-page captures; **364/364** source-specific pixel checks passed (308 charts, 28 closed dropdowns, 28 line legends). Graphite Red had zero suspect green/teal pixels across its ten pages under the documented screening rule.
- **Publication:** 56 authentic derived WebP previews and 28 palette/control swatches; the provenance file binds source, candidate, model, palette, raw captures and public-image digests.
- **Boundaries:** open flyouts, broad G2/G4 interactions, unrelated PBIPs and explicit owner G6 promotion are **not approved** by this evidence. PR #81 remains draft and unmerged.



**Native line-legend polish:** Fixed implicit black line-series legends on dark theme surfaces by applying the explicit, contrast-checked theme token. New source/visual regressions verify bindings and label-color role stay intact; the exact-source native recapture is documented above.

## Complete approved-theme native gallery — 25 October 2026 (PR #81 draft)

The README now highlights seven curated Power BI theme families instead of
showing the entire long catalog above the product documentation. A dedicated
[14-family Desktop gallery](docs/REAL_THEME_SHOWCASE.md) shows **all 28
Light/Dark variants** with **56 authentic report screenshots** (two
representative pages per mode), backed by **140 private full-page native
captures** from the exact GitHub-generated PBIP candidates. The complete
palette reference includes **28 separate color/control previews**, with
distinct themed dropdown and selection surfaces.

The generic Organic color direction is anchored in cobalt and vivid magenta
with green and sky-blue accents; Sunny retains orange, peach and grey
in its appearance roles. Their categorical data colors were adjusted
for readability separately from lighter brand-inspired control backgrounds.
All 28 modes passed source QVS acceptance *before* capture, followed by
**140 native chart-series pixel checks + 28 dropdown checks**. A single
unexpected Electric Atelier Dark rendering was discarded and recaptured,
rather than lowering the screenshot tolerance. All generated public assets
are hash-bound to source/candidate/model/palette identities.

This is a validated candidate and gallery update; separate G2/G4 interactive
review and G6 merge approval remain outstanding.

## Native category-pixel acceptance correction, 25 October 2026 (PR #81, unmerged)

A second native screenshot review found two genuine quality-control gaps:
the gross-margin target chart rendered *Electronics* and *Sports &
Outdoors* in exactly the same below-target red, and the 40/9
multi-category separation allowed near-duplicates in the seven-category
charts. The new QVS HIGH finding `color.category_conditional_shared_status`
prohibits the wildcard conditional bar fill from silently passing as
categorical identity. The 4–7-category screening bounds are now
CIELAB ΔE76 >=45 and approximate color-vision distance >=15,
while 2–3 categories retain >=50 and >=19.

Contoso target bars now encode three distinct categories while preserving
the 35% reference line, GM values and DAX. The former cumulative regional
waterfall has been explicitly changed to a color-distinct regional
variance **column comparison** (same variance DAX and grouping; no implicit
waterfall total). Graphite Red remains green-free. All 28 candidate
modes passed the updated QVS hard gate **before** Desktop capture.

The corrected subtitle and native screen acceptance gate were published
in source commit `587eda95c46770bdffd0c20992506c8bfbb94426`. After native model refresh, 50 real
Power BI Desktop screenshots were independently verified with 100
category/series chart-region pixel checks across the ten featured modes.
Thirty WebP previews and eighteen color swatches were regenerated and
verified by SHA-256 at exactly that source revision.
This is a draft engineering candidate, **not a production G2/G4/G6 signoff**.

**Deep-dive region single-color source flaw:** Replaced the three identical default-orange regional sales bars with uniquely scoped native colors. QVS now fails source validation on categorical bar/column visuals missing per-category assignments altogether. Expanded per-mode native evidence to all five pages: 11 chart regions × 28 modes, plus actual dropdown and legend colors (364 pixel checks). Any incomplete/blank native screenshot is quarantined and re-captured; an exit code alone is not visual acceptance.

## Unreleased candidate — 2026-10-24 (draft PR #81; NOT on main)

**Adaptive Power BI report themes:** 14 newly approved palette families in paired
Light and Dark modes (28 new variants), additive to four unchanged legacy
presets. Bounded `vqs theme inspect/preview/apply/audit` safely generates
new PBIP candidates without altering source reports, semantic bindings or
business meaning. Native Desktop review identified and corrected two
appearance defects: a hardcoded unscoped chart wildcard fill and low-contrast
automatic legend/subtitle text. The existing supported chart and numeric
gradient handling, source/model invariance checks and rollback remain intact.

**Verifiable public showcase:** 50 actual populated Desktop page captures
from ten featured Sunny, Organic, Graphite Red, Indigo Ember, and Petrol & Gold Light/Dark candidates,
with 30 cropped WebP previews published in the
[real gallery](docs/REAL_THEME_SHOWCASE.md). The other 9 families appear as
18 original token-color swatches in the
[approved library](docs/APPROVED_THEME_LIBRARY.md)—not claimed as native
report screenshots. Hashes, candidate/model/source identity and exact
rendering commit are recorded in the
[public gallery manifest](docs/images/adaptive-showcase/PROVENANCE.json).
The homepage and [documentation landing page](docs/README.md) were simplified
for first-time users and independent reviewers.

**24 October categorical readability correction:** a visual review exposed
weak separation across many bar/line series. Removed an erroneous test that
*required Graphite Red to remain nearly monochromatic*; re-optimized all
28 categorical eight-color sets, preserving each first accent and numeric/
business encodings. Added tested CIELAB and approximate color-vision
simulations (Machado matrices applied in linear-light RGB), required
new-preset load-time validation, and two read-only
`vqs premium` source-risk findings. Native full-page captures for all ten
showcased Light/Dark modes, plus the three-page public gallery per mode and
the other 18 palette swatches, have been **regenerated from the GitHub-hosted
`dddae21` artifacts**, with new SHA-256 provenance.

**Quality boundary:** full GitHub CI, Microsoft
authoring validation and source audit were green during preparation.
GitHub CI checks and independent visual/interaction G2/G4 review remain
separate from production signoff. Draft PR #81 **must not merge** without
the separate owner G6 approval. [Theme release-candidate record](docs/RELEASE_NOTES_THEME_2026-10-24.md).

**25 October category-level QA correction:** Existing theme-wide color
separation missed the real Electronics/Sports & Outdoors pair and a flat
Retail/Online wildcard. QVS premium now resolves PBIR scoped category names
and active ThemeDataColor assignments, emits HIGH severity findings
`color.category_series_collision` and
`color.category_wildcard_shared_fill`, and records exact RGB/distance/page/
visual evidence. The 28-mode Microsoft authoring job and its separately
invocable pre-capture gate require **zero** such findings before publishing
a screenshot-ready candidate. Rebalanced all 28 category ramps while
retaining the Organic blue/pink/green/sky-blue and Sunny orange/grey
visual vocabularies. Source-bound `dddae21` candidates passed
28/28 with zero category collisions before real Desktop recapture.
The published 5-family gallery now contains 50 native page captures,
30 downscaled public screenshots and 18 swatches.

## Unreleased — 2026-10-21 (main branch; Power BI engineering preview, no GitHub Release)

> This is an **engineering integration**, not a production release or an independently accepted Power BI product. See the [21 October Power BI engineering evidence and release-candidate notes](docs/RELEASE_NOTES_2026-10-21.md).

### Power BI core — published on `main` (acceptance independent)

- **Mixed-size native PBIR pages:** support distinct per-page canvas dimensions (including tooltip pages) during capture and review-bundle verification without assuming a single pixel-to-PBIR transform. Exact per-page source identity is mandatory; unverifiable geometry remains `blocked`. After Windows was unlocked, `vqs capture --live-data` succeeded for **all three** pages of a real converted Microsoft Corporate Spend PBIP and **all five** pages of Contoso Retail, with individually hash-verified, re-verified private bundles. Source/model evidence and limited native interactions are present; **pixel-coordinate calibration and independent release acceptance remain blocked**. See the associated capture PR and issue #16.

### Integrated in `main`

- **PR #63 (merged):** Power BI becomes VQS's primary product and independently gated `powerbi-core` acceptance scope. Optional Word/DOCX has its own `word-docx` gate; historical `combined` records still work.
- **PR #64 (merged; `f24660c`):** native Power BI Desktop QA and scoped assurance, including full-page rendered checks, source/model interaction traces, .NET UI Automation for supported controls, and constrained composition repair in disposable candidates.
- **PR #66 merged:** newcomer-first README, GitHub/Windows execution guidance, Power BI-first architecture. **PR #67 merged:** portable Windows symlink negative control. **PR #68 merged:** bubble-map-only label policy; no false Shape Map warning.
- **PR #69 merged:** source-hashed owner-authored premium design preflight, top-three measured advice, and advisory `assurance` integration.
- **PR #70 merged:** page-specific source-bound capture dimensions for mixed report/Tooltip sizes; missing viewport calibration stays blocked.
- **PR #71 merged:** exact doubled-DPI (six-row/12px) Desktop dotted-border detection plus independent sidebar proof; all five real Contoso pages captured and losslessly cropped as **verified report-only canvases** while unknown universal geometry remains blocked.
- **README showcase reproducibility:** committed the exact five-page Contoso Retail PBIP and 12-table, self-generating synthetic TMDL semantic model behind all five public screenshots. A fresh Power BI Desktop open and refresh reproduced real KPIs and the Shape Map without a published ABF cache. New CI regression guards page identities, source and model SHA-256, and all published image digests.
- **21 October live validation:** two unrelated PBIPs, **8/8 native pages**, genuine populated Modeling MCP probes, **9 Contoso Year/Region events** and Corporate **Europe→Latin America→Europe** interaction with pixel-identical screenshot restoration. No private business evidence uploaded. [See the actual engineering run](docs/RELEASE_NOTES_2026-10-21.md).
- **Not approved for production:** two unrelated PBIP engineering subjects now exist; independent G2 visual review, reliable per-visual pixel calibration, country-map/G4 scope, and trusted G6 reviewer/owner release authority remain blocked.

### Pending independent acceptance / not tagged for release

- **Premium P19 (#65):** the historical local candidate `8a31cde` was not recoverable and is not a remote GitHub commit. A smaller, separately reviewed implementation now adds `vqs premium` with source-bound design intent, focused geometric/explicit-style diagnostics, top-three advice, and advisory integration in `vqs assurance`. The current merged functionality is [PR #69](https://github.com/analienx/visual-quality-system/pull/69) with green hosted checks—not the missing historical commit. The separate optional three-perspective model critique is **not shipped**; existing opt-in screenshot review remains available. No G2/G4/G6 approval is implied.
- **Word/DOCX native work:** draft branch/PR sequence (including #62); still independently gated. No Word/DOCX tagged release.
- **Fabric/web adapter:** deferred (#18).

### Historical development notes

The entries below are preserved as **point-in-time candidate-branch records**. Their `Unreleased` headings and “not merged” labels reflect the status when authored; they are **not current `main` status**. Check the merged PRs and the engineering release note above for current integration truth.

---

## Unreleased (work/wp02-integration-r2 — R6 E01-E08, draft PR #31, NOT merged)

- R6 trust remediation for issue #22 on the integration candidate
  branch (draft PR #31, unmerged; no work package verified):
  - E01 scoped projection identity: one binding per projection
    keyed by page/visual/role/projection; missing `queryRef`
    blocks as `query_ref_missing` + `actual_unknown`.
  - E02 gate-specific producer capability: `vqs.check/1` observes
    G0 only; `run_check` strips caller seal keys, seals the actual
    observation, and binds its own envelope.
  - E03 suite binding for G6 via canonical suite digest.
  - E04 reviewer/editor/promotion split: review binds both run
    ids; promotion has no registered authorities and blocks.
  - E05/E06 verified review authority: whole-source completeness
    needs a verified transport or live report inventory; static
    adjudication never passes (`image_review_required` ceiling).
  - E07 Microsoft-guided authoring: new `vqs/powerbi/author` port
    (auto/microsoft/direct); pbir-cli/BPA legs removed from
    doctor, probes, and `pbip_acceptance.py`; repair seals
    `authoring.json`.
  - E08 truthful public surface: `docs/JOURNEY.md` (oracle-tested
    installed-command walk), ADR 0001, README/CLI/USER_GUIDE/
    ARCHITECTURE status corrections.
- P1-U7 typography declaration rule: `format_declaration_consistency`
  proves effective values (explicit declarations prove themselves;
  inherited readings may carry a render-adapter-proved `effective`).
  Proven-different fails; mixed explicit/inherited with an unknown
  effective value is unknown (`needs_render_evidence`), never a
  visual-quality fail; all-default passes; proved-equal passes with a
  hygiene-only notice kept separate from the verdict. Narrow typed
  `format.unset_override` (preferred when safe) and `format.set_explicit`
  ops bind, apply, verify, and synthesize only with a proved effective
  value plus named provenance; unproven bindings need the owner.
  Tests `tests/test_u7_typography.py`; `scripts/smoke.py` honest
  blocked (rule unknown on the mixed mini_report fixture, not fail).
- P1 items 32-37 install/version hygiene and authoring correction:
  new `vqs --version` and `python -m vqs` (`vqs/__main__.py`); `vqs
  doctor` reports an `installation` check (package version,
  import/package root, engine/tool schemas, git SHA when
  discoverable) that flags stale editable installs without ever
  modifying them; the Microsoft authoring identity is recorded as
  the `powerbi-report-author` executable from
  `@microsoft/powerbi-report-authoring-cli` in probe/validate
  records, doctor, and docs; the legacy `--skip-pbir` alias is
  removed (no pbir.tools hook remains). Tests
  `tests/test_p1_install.py` plus `tests/test_doctor.py` updates.
- P1 items 30-31 live answer regression: the coordinator baseline now
  persists the query/scope/result evidence per DAX question, so the
  `answer_regression` stage re-asks the identical scoped query against
  the candidate (previously the rebuild lost DAX/scope and could only
  block); non-empty filters/period stay fail-closed with the exact
  blocker. Tests `tests/test_p1_answer_regression.py`.
- Oracles `tests/test_r6_e01_bindings.py` … `tests/test_r6_e08_journey.py`
  (two-project journey included); hosted lanes
  `.github/workflows/authoring.yml` (real-CLI probe) and
  `.github/workflows/r6-oracles.yml` (per-oracle counts).
- No ledger, issue, or PR state advances here: independent Codex
  acceptance review stays pending.

## Unreleased (agent-first review candidates — NOT merged)

- Six draft PRs with green hosted CI (3.11/3.12/3.13) await Codex
  review; none is merged and no work package is verified:
  WP-00 baseline audit (#24 @ `e684078`), trust remediation #22 /
  WP-01 contracts slice (#25 @ `34a768f`), unified PBIR/TMDL facts
  (#26 @ `2e26fa1`), shared CLI/MCP engine (#27 @ `a8fe7c9`),
  runtime/data interfaces (#28 @ `f2dc7af`), visual candidate
  repair + answer preservation (#29 @ `d1f1c4d`).
- Ledger carries draft-PR evidence pointers; workflow states stay
  `planned`/`active` per the DAG prerequisite gate.
- New `docs/TEMPLATE_AUTHORING_CONTRACT.md` defines the post-repair
  authoring milestone (contract only, no implementation).

## Unreleased (work/vqs-hardening-insights)

- `vqs measure` now records a per-page insight inventory (visual,
  title, bound measures/dimensions/roles) and runs three new checks:
  `insight.no_duplicate_grain` (same/contained insight twice on one
  page fails), `chart.decomposition_tree_dimensions` (Analyze plus at
  least two distinct ExplainBy dimensions), and
  `chart.map_location_binding` (map needs a location column; TMDL data
  category proves or withholds the geographic verdict).
- Honest-facts hardening: per-page palette assignments omitted until
  explicit per-visual series colors are measurable; contrast pairs each
  page's text with its own background; unit classification proves only
  percent (`%`) and carries other formats verbatim; cohort nulls cover
  only visuals declaring the owner object; cycle gate is case-insensitive,
  reports self-loops and string/prefix-safe M edges, and counts tables.
- Capture/bundle/evidence hardening: quoted shell fallback, bridge
  payload shape guards, save-state and source-staleness checks,
  traversal-safe render names, pack/unpack rollback, header/inventory
  cross-checks, tamper re-verification.

## Unreleased (work/xpage-layout-maps)

- New rules: `insight.no_cross_page_duplicate_grain` (one breakdown
  must not repeat on another page; bare cards exempt as the summary
  pattern), `layout.no_visual_overlap`, `layout.visuals_within_page`,
  and `chart.map_location_labels` (bubble maps must show category
  labels unless a heatMap layer carries the encoding).
- `vqs measure` inventories geometry, page bounds, label configuration,
  and a per-visual `customized` flag; `pbip_acceptance.py` reports a
  `pbir bpa` summary section (titles/sizing/alt-text stay BPA's lane).
- Shared grain validation core between the two duplication rules.

## Unreleased (work/topclass-repo)

- Top-class repo front door: rewritten README (badges, quickstart,
  transcript, architecture diagram), repo description/topics.
- `vqs capture`: Bridge screenshots bound to exact PID/path/source
  with `capture-manifest.json`; honest blocked reasons.
- `vqs bundle pack/verify/unpack`: portable review evidence for
  cross-machine/agent handoff with re-hash verification.
- `request-review` templates stamp `image_source_sha256` per page so
  adjudication checks real binding instead of false-failing.
- Hygiene: `docs/USER_GUIDE.md`, `CONTRIBUTING.md`, this changelog,
  CI workflow, `examples/quickstart.py`, `scripts/smoke.py`,
  versioned `.agents/skills/vqs/` skill.

## 2026-09-26 — No-cycles gate and acceptance runner (`ecdcdfd`)

- `vqs/powerbi/cycles.py` + `vqs cycles`: static DAX/M/`let`
  acyclicity gate with synthetic TMDL fixtures. Contoso: 55 objects,
  17 queries, zero cycles, matching the live-engine verdict.
- `scripts/pbip_acceptance.py`: `vqs measure` plus optional
  `pbir validate --all` in one JSON verdict.

## 2026-09-26 — WP-19 measurement adapter (`b3bed75`)

- `vqs/powerbi/measure.py` + `vqs measure`: text contrast, palette
  assignments, format-declaration cohorts with explicit default
  nulls, metric units, sorted model bindings.
- `vqs doctor`: capability reporter (always exit 0, installs nothing).
- Ledger/tests/STATUS to the honest 14-package truth (WP-19 active,
  independently verified stays 0).
- Recorded Power BI tool-interface decision: Modeling MCP primary,
  Bridge for Desktop, direct PBIR facts, pbir-cli optional DLL-free,
  ADOMD none.
- Contoso parity: 4 sections, 63 cohorts, 59 units, 25 bindings.

## 2026-09-26 — DES-06 format consistency (`abadf14`)

- `typography.format_declaration_consistency` rule: declaration-only
  cross-visual consistency cohorts.

## Earlier

- Offline VQS core: pipeline, CLI (`inventory`, `request-review`,
  `status`, `check`, `validate-plan`, `adjudicate-bundle`),
  acceptance core, ledger DAG validator, TMDL parsing with quoted
  identifiers.


**25 October native chart clarity completion:** Seven categorical Contoso visuals
now use native per-category PBIR scope selectors referencing theme series
colors; these are category identity encodings rather than numerical ramps.
The genuine country Shape Map remains a quantitative FillRule example.
Graphite Red's positive bar and waterfall increase use theme-aware blue
rather than green, with predicates, thresholds, measure bindings and negative
red unchanged. The label now explains business value without naming a color.
The public gallery adds Indigo Ember and Petrol & Gold to the original
three-feature family comparison, for 50 total private native page captures
and 30 public screenshot derivatives from the new exact-head candidate revision.