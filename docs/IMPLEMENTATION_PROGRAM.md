# VQS implementation program — Power BI Desktop + Word first

**Planning baseline:** 2026-09-23. **State:** a delivery plan, not completed functionality. **Program:** [#4](https://github.com/analienx/visual-quality-system/issues/4). **Machine-readable work ledger:** [`roadmap/work_packages.json`](../roadmap/work_packages.json). **Execution architecture:** [EXECUTION_ARCHITECTURE.md](EXECUTION_ARCHITECTURE.md). **Agent/status protocol:** [LEDGER_AND_AGENT_PROTOCOL.md](LEDGER_AND_AGENT_PROTOCOL.md). **Acceptance:** [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md). **Execution status (2026-10-03):** ten work packages carry unmerged draft-PR candidates with green hosted CI — see [roadmap/STATUS.md](../roadmap/STATUS.md); 0 independently verified; post-repair template authoring is defined in [TEMPLATE_AUTHORING_CONTRACT.md](TEMPLATE_AUTHORING_CONTRACT.md) and not implemented.

## 1. Deliverable and release boundaries

**Release VQS-PBI-DOCX-0.1:** A single-developer/local-first Python package that (a) inspects the actual enhanced PBIR and associated semantic model; (b) diagnoses measurable and perceptual chart/page design problems against the data, effective design profile and a minimal analytical task; (c) creates a **disposable, openable Power BI Desktop candidate** with safe source-level visual/style repairs and, only for validated cases, new template visuals; (d) proves the candidate loads actual data and answers the same scoped questions; (e) applies an analogous **all-page, true paginated DOCX quality check** to generated Word output; (f) checks embedded report images and facts refer to the same report revision; and (g) produces an independent `pass | fail | blocked` verdict backed by reproducible evidence. `review` is read-only, `propose` produces a plan/diff, `repair` edits only an isolated candidate, and `promote` requires explicit owner approval.

This does **not** promise automated repair of arbitrary Power BI visual formats, arbitrary Word page geometry, unsupportable browser-like Desktop interactions, generic causal inference or universally available model query access. The first release has an explicit feature/capability matrix: a required but unavailable capability returns `blocked` for that acceptance scope; an optional skipped check is `not_run`. Forecasting, broad story generation and Rayfin/Fabric Apps remain separate follow-on milestones, although the core contracts must not preclude them.

## 2. Repository reality before implementing

The independent VQS repo currently exposes `vqs inventory`, `vqs request-review`, a portable PBIR inventory, PNG/source evidence validation, policy observations and isolated axis/contrast/category-space primitives. The fuller Desktop/reviewer/repair prototype is in [PBIPDocumenter draft PR #12](https://github.com/analienx/pbidocumenter/pull/12). **These are not a verified standalone end-to-end release**. Historic [#1](https://github.com/analienx/visual-quality-system/issues/1) covers extraction, [#2](https://github.com/analienx/visual-quality-system/issues/2) stories/auto-design and [#3](https://github.com/analienx/visual-quality-system/issues/3) runner and a later web adapter. The bounded issues [#5–#18](https://github.com/analienx/visual-quality-system/issues/4) are this program's execution units. Do not copy old `109/109 tests` or single-page render claims into the standalone ledger as fresh acceptance evidence.

Treat a **working visual repair with real Desktop re-render** as the critical path; bring **Word renderer feasibility forward** in parallel so document requirements do not become a release-eve surprise. Implement analysis and data checks before authoring arbitrary new pages. Predefine measurement/negative fixtures before the first repair agent is allowed to edit a source report.

## 3. Why this sequence is technically necessary (verified external constraints)

- Microsoft [enhanced report format](https://learn.microsoft.com/en-us/power-bi/developer/embedded/projects-enhanced-report-format) documents editable page/visual PBIR JSON and schema validation. Its source schema is not proof that an image looks right or the semantic model is populated. Microsoft's [Desktop verification runbook](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-authoring/references/powerbi-desktop.md) requires an exact Desktop PID, report validation/reload and actual capture. Pin the installed CLI capability instead of assuming every preview command exists.
- Microsoft's [PBIP semantic-model folder documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset) distinguishes `.pbi/cache.abf` from the source model. Opening without a cache may load **zero data**; a cache can make the example look populated without demonstrating reproducible refresh. Test **first open**, **live query**, and **refresh** separately. Sensitive `.pbi/cache.abf` and `localSettings.json` are excluded from the public repo.
- Microsoft [Word automation guidance](https://support.microsoft.com/en-us/visio/considerations-for-server-side-automation-of-office) does not support unattended non-interactive Office automation. Prefer isolated LibreOffice headless → PDF → page PNG for reproducible automation, and separately test interactive Word fidelity when exact Word pagination is required. If backend equivalence cannot be shown for a fixture, declare that renderer-specific acceptance blocked; do not call LibreOffice a guaranteed exact Word layout oracle.
- [GitHub sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues), [issue dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies), [issue forms](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/about-issue-and-pull-request-templates) and [Projects custom fields](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects) provide a good UI, but the Git-tracked versioned ledger remains the source for explicit prerequisites/acceptance. GitHub issue *closed* must not masquerade as verified.
- GitHub's [self-hosted runner security guidance](https://docs.github.com/en/actions/reference/security/secure-use) warns against running untrusted public-repo PRs on persistent personal computers with credentials. **Do not connect a public VQS Actions runner to the user's Zephyrus**. Run Desktop/Word acceptance as manually approved, local, scoped jobs; add small static GitHub-hosted CI only if budget allows.

## 4. Scope-by-surface: shared contracts, distinct implementations

| Layer | Power BI Desktop | Word document | Shared |
| --- | --- | --- | --- |
| Artifact | PBIP `.Report` + `.SemanticModel`, PBIR/theme/TMDL; exact PID opened from scratch copy | DOCX OOXML ZIP, styles, sections, relationships, embedded images/figure references | `ArtifactRef`, source SHA, owner policy, sensitivity, run ID |
| Facts | Page/visual IDs, field bindings, explicit/inherited/conditional style, model query value/filter/RLS/refresh | Section/page size, style cascade/direct formatting, tables/paragraphs/figures, report-linked captions and source | `ComponentRef`, `DataScope`, `DesignProfile`, `QuestionOracle`, typed provenance |
| Layout | PBIR geometry and Desktop actual canvas/crop + target viewport | Actual paginated PDF/PNG + OOXML objects/section margins; renderer identity | Measured rules + independent perceptual reviewer; no screenshot-only root cause |
| Safe mutation | Allowlisted PBIR/theme properties, validated chart template | Allowlisted OOXML paragraph/table/style/pagination repair | Versioned `RepairPlan`, candidate-only writes, rollback and independent re-review |
| Acceptance | Fresh populated all-page/Desktop source-bound render, supported task answer, no neighboring chart regression | Every rendered page checked, no figure/caption/table regression, embedded report image and answer revision match | `pass/fail/blocked`; independent verifier with exact evidence and privacy boundary |

No `vqs/document` import of the Power BI Desktop worker; the cross-output consistency checker consumes **public typed facts** and figure provenance, not Power BI-specific implementation classes. Fabric web UI later implements another `ArtifactAdapter` without changing the DOCX/PBIR contracts.

## 5. Optimized stage and dependency DAG

```text
S0 BASELINE #5
  └─ S1 CONTRACTS #6
       ├─ S1 RUNNER/LEDGER #7
       ├─ S2A DESKTOP FEASIBILITY #8 ─┐
       └─ S2B WORD PAGINATION #9 ────┼──────┐
           #8 + #6 → S3 SEMANTIC FACTS #10    │
           #10 + #6 → S3 DESIGN RULES #11     │
           #7 + #8 + #10 → S4 REVIEW #12      │
           #7 + #9 + #6 → WORD GATE #13 ◄─────┘
           #7 + #8 + #10 + #11 + #12 → S5 PBIR REPAIR #14
           #6 + #10 + #11 → S6 MINIMAL STORY/ANSWER ORACLES #15
           #7–#15 (required scope) → S7 INDEPENDENT REAL E2E #16
           #16 → S8 PBIPDOCUMENTER CONSUMER/RELEASE #17
           #17 + owner approval → S9 RAYFIN/FABRIC WEB ADAPTER #18 [DEFERRED]
```

**Concurrency:** After #6 schema freeze, #7 (runner), #8 (Desktop spike) and #9 (Word spike) can run in *separate worktrees* concurrently because they own different package paths. #8 and interactive-Word steps in #9 share a Windows GUI license/desktop; a single **host lease** schedules those runs serially. After #10 fact schema freeze, #11 and #12 can run independently. #13 Word document work proceeds alongside PBIR design and repair. #15 pure story rules can start after #10 without waiting for all Desktop authoring, but its P0 acceptance is deliberately limited to baseline question and answer preservation; generalized domain packs and forecasts do not delay first release. Integration/release owner merges in dependency order after independent review, not whenever a model reports 'done'.

A stage is **ready** only when all hard dependency work packages are verified on compatible commits. Use the ledger's logical prerequisite IDs even if GitHub native dependency relationships are not yet configured. A scope-gated or deferred Rayfin issue is not a PBI/Word release blocker.

## 6. Stage-by-stage definition of done and execution handoffs

### S0 — #5: capture reality, build reproducible fixtures and capability inventory

The inventory agent reads the current code/PR, checks committed and untracked state, collects exact tool executable versions, runs existing tests from a clean environment, classifies everything as `implemented_verified`, `prototype_unverified`, `partial`, `missing`, `blocked` or `not_assessed`. Classify data sensitivity for every fixture. Create a tiny **synthetic** source PBIP with meaningful numeric measures, 5-category comparison, trend, table, slicer and deliberately defective axis; acquire a *second unrelated* PBIP with different schema/layout/domain. Create DOCX fixtures with 2+ pages, heading/caption/table/figure and an intentionally bad pagination variant. The public repo can store only fabricated source data and checksums, not real cached business models or personal screenshots. A local-only fixture manifest points to private test files by digest and capability, never a private absolute path in Git.

**Gate S0:** independent agent reproduces `pytest`, `ruff`, `vqs inventory` outputs and at least a no-Desktop failure, links real test transcript and logs tool limitations. No claim of baseline 'green' before doing this work.

### S1 — #6 contracts followed by #7 runner (parallelism begins after freeze)

Define versioned JSON/Pydantic contracts and invariants first. The chosen Python floor must match `pyproject.toml` and actual CI/runtime; do not silently change from current >=3.11 to >=3.12 without a migration test. Component keys are `(artifact_kind, source_revision, page_or_section_id, visual_or_object_id, view_state)`; use stable PBIR IDs and Word OOXML/paragraph/figure paths with a derived stable locator when native IDs absent. Evidence records `method, producer_tool+version, source_digest, data_snapshot/query_context, renderer/viewport, payload_hash, timestamp, classification, sensitivity`. Missing evidence is an explicit typed state.

Implement an append-only per-run JSONL event stream; content-addressed binary evidence stored *outside tracked Git* with optional short-lived private artifact link; SQLite WAL index can be rebuilt from events and must never be the only copy of proof. State transitions enforce prerequisites, allow safe retries with a new attempt ID and ensure orphaned/incomplete runs become blocked. Define `AgentResult` JSON format; constrain machine-affecting subprocess commands to declared adapter capabilities and no unbounded recursive tool access.

**Gate S1:** negative tests for crash recovery, stale hash, duplicate ID, false status promotion, two writers, wrong PID lock and personal-secret leak; independent reviewer confirms `vqs inventory` stays backward-compatible.

### S2A — #8 Desktop vertical feasibility spike, early and narrow

On the Windows host: make a disposable PBIP copy, verify published schema+installed authoring CLI, open by explicit PBIP path, select exact Desktop PID from Bridge state and require on-disk saved source agreement; test first-open data readiness by actual DAX query and visible populated KPIs, not an ABF hash. Capture at least one page and all pages at target viewport; verify true canvas boundaries independently per scale. Test `reload`/restart behavior and cross-check screenshot against current report + model hashes. **Negative controls:** unsaved state, empty first open, wrong PID, wrong page list, scale-2 cropped right edge, stale image, timeout and independent cache refresh failure. If bridge cannot drive slicers/drillthrough, record explicit capability gaps—do not build an imaginary interaction driver.

**Gate S2A:** real captured/validated PNGs and source manifest for a harmless fixture, independent inspection and demonstrated blocked results for negative controls. Failing tool version or data readiness triggers an explicit architecture revision rather than arbitrary unsafe automation.

### S2B — #9 Word pagination feasibility spike in parallel

Use sandboxed LibreOffice with unique user profile and controlled fonts/locale/paper/renderer version; render DOCX to PDF then to page PNG. Compare PDF page count and actual pagination against a licensed interactive Word export **when Word-exact behavior is mandatory and available**. Check page raster DPI, PDF source digest, bounding boxes where reliable and font substitution. Test empty page, paragraph orphan, table split, repeated header, section orientation and embedded chart fidelity. Deliberate bad fixtures must fail; renderer crash and incompatible font substitute block the intended quality gate.

**Gate S2B:** backend choice documented by supported rendering behaviors + honest `compatible | approximate | blocked`; no unsupported service-side Word COM. If automated Word rendering cannot meet the selected fidelity, ship a narrowed LibreOffice-backed gate that explicitly declares its output target; exact-Word release criterion remains blocked until a supported validation path exists.

### S3 — #10 source/data facts; #11 quantified design; #13 Word analysis (parallel)

#10 builds `VisualFact` and `ModelDataSnapshot` with true PBIR/TMDL refs, effective theme style (explicit override vs inherited theme/base vs conditional style), field roles, scope, model data values, refresh and RLS identity where authorized. Missing values remain unknown. #11 builds rule-function packages and synthetic golden tests **before** any model-assisted repair: percentages/tick precision, cardinality and label width, semantic palette reuse, sufficient contrast and saturation roles, misleading baselines/denominators, typography/grid/padding, table occupancy, style continuity and target-display readability. Use the version-pinned Power BI theme schema; do not overfit to five Contoso charts. #13 independently builds DOCX OOXML facts + page geometry/table/caption/figure/style rules and cross-report figure consistency on the tested renderer.

**Gate S3:** every finding has stable ID, location, actual quantitative input and a repeatable expected result; tests cover true-positive, true-negative, unavailable evidence and user override. No fabricated effective theme or Word pagination based solely on OOXML paragraph count.

### S4 — #12 actual perceived design and independent adjudication

Port full-canvas and per-visual image review with correct resolution calibration; run structured independent image-capable model on **both** current page and relevant crop with PBIR/data/profile facts. Reviewer reports *observed appearance and location*, not claims about exact DAX values or unmeasured root causes. A second reviewer can adjudicate high-impact subjective changes; model disagreement or unsupported clipping = investigate/blocked. Keep vision opt-in, provider capabilities discovered, time/cost bounded and sensitive data minimized; text-only model may draft repair plans but cannot certify pixels.

**Gate S4:** adversarial fixtures with false cropping, fake blank chart, hallucinated causal interpretation and same fixer/reviewer fail; every accepted defect has corroborating evidence or a clearly subjective review requirement.

### S5 — #14 narrowly typed, reversible Power BI editing; #13 Word repairs

Planner chooses `FixAxisFormat`, `SetThemeRole`, `SetVisualProperty`, `MoveVisual`, `ResizeVisual`, `ChangeChartType` (only with intent/oracle compatibility) or vetted `InstantiateVisualTemplate`. The source editor validates operation inputs against installed PBIR and theme schemas, applies only to isolated snapshot, outputs exact diff and updated hashes. Limit first pilot to one **real styling/legibility** defect and one verified chart encoding fix; avoid uncontrolled pages, RLS/measure rewrites or unsourced new metrics. Refresh/check data separately, reopen or reload exact Desktop PID, recapture *entire affected page*, compare all categories and adjacent tables, and independently review at viewing size. DOCX repair starts with approved style/spacing/page-break changes; render **every document page** after each accepted candidate.

**Gate S5:** real before/after evidence proves the seeded defect removed and no new high/critical issue; preserve question, values, references, all categories and table rows, and demonstrate rollback. Repeated failing repair is `fail/blocked`, never silently skipped.

### S6 — #15 question/decision minimum viable coverage (not an AI-generated-story detour)

Before changing chart *type*, bind its existing or owner-supplied analytical task. Build a minimal set of verified default questions from actual usable measures/dimensions (what, compared with what if benchmark exists, when if dates exist, segmentation and relevant decomposition) and test expected DAX answer/filter scope before/after. Explicitly distinguish descriptive contribution from causal 'why'. Extended default domain packs, forecast qualification, AI-answer parity and automated multi-page design belong to later iterations; do not hold the first visual-repair release hostage to speculative story generation.

**Gate S6:** two different domain fixtures, ambiguous measure negative test and a chart replacement refused when it would alter the declared task.

### S7 — #16 first independent all-artifact end-to-end acceptance

Freeze a candidate version, run two unrelated PBIP projects through clean first-open, populated model check, static and data rules, full Desktop capture, image review, one genuine source repair and rerender of all affected pages. Run one generated DOCX with embedded current report visuals through OOXML check, backend-specific pagination and review **of every page**; verify captions, units, text and cross-document figure/revision provenance. Capture at least one supported user filter state; unautomatable interaction states remain explicitly unsupported and cannot be marked tested. Include negative controls from [ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md), independent verifier signs based on raw evidence, not on the editing model's narrative.

**Gate S7:** both unrelated reports and DOCX satisfy declared mandatory criteria, with reproducible source and data hashes, no regressions and no unresolved mandatory blocked checks. If gate fails, keep draft/blocked and point to exact work package; partial success is never called a release.

### S8 — #17 consumer integration and release

Only after #16, build a pinned `vqs` distribution and typed `PBIPDocumenter` invocation. Retire duplicate prototype code **only after same-source parity tests**; leave original draft PR untouched until owner expressly decides merge/close. Publish exact support matrix, installation and rollback guide, privacy limits, sample usage and machine-readable release evidence. Low-cost static CI may run on hosted infrastructure if budget is approved; local/Desktop/Word acceptance is a separately authorized secure job, not an untrusted PR workflow running on a personal machine.

**Gate S8:** clean install, isolated real PBI+DOCX invocation, independent release review and explicit owner approval of candidate promotion. Avoid starting S9 implicitly.

### S9 — #18 web/Fabric Apps later (not on first-release critical path)

Reuse intent/evidence/rule contracts; new Node/Playwright worker and TSX/CSS/browser data/authorization oracles. First synthetic React app; Fabric portal staging only with tenant/capacity/SSO approval. No extra workers, Node or Rayfin dependencies in the Power BI/Word default install. New owner-approved breakdown after PBI/Word release.

## 7. Interfaces and release engineering rules

Every work package declares input contract version, owning files, output schema, exception types, called executable versions, capabilities and fixture independence. Agent code works through `InspectPort`, `DataPort`, `RenderPort`, `ReviewPort`, `AuthorPort`, `VerifyPort`, each with `probe() → CapabilityManifest` and JSON-serializable outputs. The coordinator—not the model—moves run states. When an upstream tool is absent: `optional` yields `not_run`, `mandatory` yields `blocked`. Negative fixtures are required before switching a new adapter from `experimental` to `verified`.

Use named release gates `G0 source+policy`, `G1 semantic data readiness`, `G2 measured+perceptual design`, `G3 isolated source mutation`, `G4 real rendered and data regression`, `G5 Word all-pages and report consistency`, `G6 independent verifier+owner promotion`. A *phase complete* claim refers to explicit packages+gates, not a passing pytest count alone. See acceptance matrix for exact proof requirements.

## 8. Decision log and rejected shortcuts

| Decision | Adopt | Explicitly reject / reason |
| --- | --- | --- |
| Architecture | One Python modular monolith, typed plugin ports and isolated Windows GUI worker | Early microservices, message broker, Fabric-hosted VQS core, full multi-agent mesh |
| Work tracking | Git-versioned work-package ledger + GitHub issues + immutable run evidence | Editable checklist whose author can claim success without tests |
| Parallelism | Separate worktree per issue; contract freeze; exclusive Desktop/interactive Word lease | Simultaneous agents editing one checkout/one open Power BI instance |
| Visual truth | Data + PBIR/theme facts + real rendered page/crops + independent perception | Screenshot-only LLM approval or PBIR JSON-only geometry pass |
| Word truth | Backend-pinned page rendering and optional independent Word-fidelity test | Unsupported non-interactive Word COM or OOXML-only pagination assumption |
| Repair | Typed allowlisted changes to disposable source then full regression | Free-form AI file edits, overwrite of original report, 'good enough' on first screenshot |
| Security | Local-only data and evidence, opt-in model transfer, controlled promotion | Public self-hosted Actions worker on a workstation with user credentials |
| Rollout | Power BI + Word working slice then domain/story depth then Rayfin | Implement all native Power BI and web app features before shipping useful repairs |

## 9. Research bibliography and revalidation triggers

Revalidate version/capability assumptions whenever Power BI Desktop, Bridge CLI, report theme schema, Word/LibreOffice backend or model provider changes. Primary references: [Microsoft PBIR](https://learn.microsoft.com/en-us/power-bi/developer/embedded/projects-enhanced-report-format), [PBIP semantic model](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset), [Desktop Bridge runbook](https://github.com/microsoft/skills-for-fabric/blob/main/skills/powerbi-report-authoring/references/powerbi-desktop.md), [Power BI theme schema](https://github.com/microsoft/powerbi-desktop-samples/tree/main/Report%20Theme%20JSON%20Schema), [Word unattended limitation](https://support.microsoft.com/en-us/visio/considerations-for-server-side-automation-of-office), [GitHub issue relationships](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies) and [runner security](https://docs.github.com/en/actions/reference/security/secure-use). All references support design decisions; installed features and tests **must still be probed on the target host**.