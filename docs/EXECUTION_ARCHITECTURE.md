# Execution architecture — how VQS actually runs

**Decision status:** historical implementation blueprint (original
Power BI + Word combined-release assumptions retained for traceability).
For the **current Power BI-first component boundaries, implemented
Windows accessibility and independent Word release profiles**, use
[the illustrated architecture](ARCHITECTURE.md), which now supersedes
this document on runtime/status claims. Primary target: Windows Power
BI Desktop/PBIP. Word is optional; Fabric Apps/Rayfin remains deferred.
Neither requires hosting VQS inside Fabric or rewriting as cloud
microservices.

## 0. Three boundaries we must not blur

1. **Analytical specification**: what a persona needs to decide; question, available metrics, filters, baseline and verified expected answer, domain defaults, permitted uncertainty and evidence. An inferred story is a candidate, not an owner-approved requirement.
2. **Artifact-specific authoring**: PBIR/TMDL and Power BI Desktop for a report; TypeScript/React/CSS/Rayfin config for Fabric Apps; OOXML for Word. These are different languages and runtimes. They share a contract and design rules, **not** a universal visual-editing API or uniform screenshots.
3. **Independent assurance**: evaluator and verifier consume the same pinned contract but must not treat a successful editor operation, AI opinion, HTML screenshot or green build as proof of correct business meaning. The verifier checks actual user-facing output and task answers on the exact candidate revision.

## 1. Concrete runtime: a modular monolith with isolated tool workers

VQS currently ships as a **Python >=3.11 CLI/library** (see
`pyproject.toml`) with typed contracts, deterministic rules, pytest
and Ruff. The Python coordinator owns run state, evidence, safety
policy and verdicts. Power BI Desktop Bridge and native .NET UI
Automation are external, Windows-only capabilities. Microsoft
Modeling MCP is a semantic tool and Microsoft Report Author CLI is a
report metadata/validation tool. A separate pinned Node/TypeScript
Playwright worker is **future Fabric/web scope**, not a present
Power BI requirement.

For current use, `vqs run`, `triage`, `measure`, `capture`,
`request-review`, `repair`, `verify`, `doctor` and related tools
are present (see [CLI](CLI.md) and [README](../README.md)). The
historical `vqs run --artifact ... --kind powerbi|fabric-app --profile`
syntax was a **target example**, not a verified current CLI invocation.
Use `vqs --help` and the current tests. `review` is read-only,
`propose` only generates diffs, repair changes disposable candidates,
and independent promotion remains blocked without external authority.

Use **one process, no broker, no Kubernetes, no microservices** initially. Keep a SQLite WAL run index (run id/status, artifact hash, phase, issues, approvals, tool versions) and an append-only JSONL event log inside each run directory; write each phase's large JSON/PNG/trace evidence as content-addressed files under `runs/<run-id>/objects/<sha256>`. Atomic temp-write + rename, a file lock per artifact and a PID-scoped lock per Desktop instance prevent concurrent overwrites. SQLite indexes artifacts by `(source_revision, contract_hash, environment_hash, interaction_state_hash)`; caches are hints only and must not short-circuit mandatory fresh-render or data-readiness gates. If database/event log diverges, reconstruct from immutable run manifests; never infer pass from a partial run.

A future server can wrap the **same CLI/jobs**, using Postgres and a queue *only when multi-user scheduling or remote runners are needed*. A Fabric-hosted app may present VQS findings later, but its preview TypeScript backend is not the place to run Windows Desktop or an unrestricted Python authoring agent.

### Repo layout to implement incrementally

```text
vqs/
  contracts/       # Pydantic: Artifact, Story, Question, ViewState, DesignProfile, Evidence, Finding, PatchPlan
  core/            # run lifecycle, CAS + SQLite index, policy, normalized graph, safety, evaluation
  stories/         # evidence-supported conditional defaults + domain packs; question-coverage tests
  design/          # effective palette/tokens, layout, typography, chart/encoding and contrast rules
  powerbi/        # CURRENT: PBIR/TMDL, Desktop Bridge, Windows UIA, authoring
  visual/         # CURRENT: perceptual/layout/coverage/pixel rules
  adapters/web/    # source manifest/parser, build/test adapter, Playwright IPC wrapper, DOM evidence
  document/       # CURRENT OPTIONAL: OOXML, native Word, PDFium pages, TOC
  components.py   # CURRENT: Power BI / Word / combined release-scope registry
  integrations/    # optional Fab Inspector, Draco, authoring/model tools; subprocess + version contracts
  vision/          # opt-in reviewer, source-linked regions and conflicting-finding adjudication
  repair/          # candidate worktree, typed patch operations, allowlist, rollback, promotion
  cli.py
workers/web/       # TypeScript @playwright/test harness; versions pinned in lockfile
profiles/           # generic policies and optional domain/design packs, no business data
schemas/            # versioned JSON Schema interoperability contracts
fixtures/           # small synthetic PBIR and React/Rayfin app projects, never real client data
tests/              # pure unit + adapter contract + Windows/Desktop + browser acceptance tiers
```

The tree above mixes current and future directories on purpose.
`adapters/web`, `workers/web` and `core/` are still architectural
targets, **not shipped modules**. No import of PBIPDocumenter's
application or a local Contoso fixture from the portable core;
PBIPDocumenter remains a downstream consumer. Word and Power BI
now have independent release profiles. External tools must report
`available|unsupported|failed|not_run` and precise versions.

## 2. Common evidence contract, not a common UI schema

The shared concept is a **task-backed evidence graph**: `persona → decision → question → answer specification → measure/data lineage → artifact component(s) → interaction state(s) → actual observation(s) → verified finding(s) → candidate patch → regression result`. Cross-surface IDs are stable *within a pinned source revision*, not guesses based on visual titles or DOM position.

An `ArtifactRevision` records `kind`, Git commit or isolated-tree digest, model/source digest, artifact path, schema/renderer/tool versions, environment (OS/locale/timezone/browser/display DPI/theme/viewport), authorized data scope, effective identity/RLS and capture timestamp. A `ComponentRef` is a tagged union: `powerbi:{report_id,page_id,visual_id}` OR `web:{route,stable_test_id,component_path}` OR `docx:{section,element_ref}`. Keep source-specific geometry units (`PBIR canvas`, `CSS px`, `Word points`) tagged; never silently convert them. Source and data hashes need distinct fields: the source code hash cannot establish live data freshness.

A `ViewState` records page/route, viewport, slicer/filters or URL/query params, user role, locale, focused state and all relevant interaction steps. A `QuestionContract` contains explicit or inferred provenance, persona, task, required measure/dimension/baseline/time population, expected result via a read-only query/oracle or an explicitly unresolved requirement, evidence sufficiency, allowed analytical interpretation, and supported navigation/action path. Each rule declares required facts and returns `pass|fail|unknown|not_applicable` with actual measurements and limitations; only the final gate maps mandatory `unknown` to `blocked`.

A `Finding` includes source revision + view state + tool/rule version + locator + severity + raw evidence references + measured symptom + hypotheses + independently verified cause (if established) + proposed typed operations + acceptance tests. The arbiter preserves contradictory observations and reviewer disagreement; it never counts duplicate model claims as distinct data proof. Preserve privacy: hash business data/evidence in the private run store; exclude them from public commits, CI logs and default model prompts.

**Example canonical flow:** `visual_id=product-quality-growth` is bound to the `margin_by_brand` question and scoped DAX oracle. PBIR says a clustered bar and specifies axis format; model query returns 5 brand groups; Desktop capture and crop show only 4. A rule issues `visible_categories < queried_categories` with screenshot and query provenance. A bounded height/layout patch must prove 5/5 visible **and** neighbor table unchanged. Pure pixel similarity alone would not suffice.

## 3. Run state machine and actual jobs

Every execution has `DISCOVER → CONTRACT → FACTS → STATIC_CHECK → RENDER → OBSERVE → TRIAGE → (PLAN → PATCH → VALIDATE → RENDER → REGRESSION → REVIEW)* → RESULT`. Each transition has typed inputs/outputs, a deadline, retry class (`transient`, `deterministic`, `unsafe`) and immutable evidence. `BLOCKED` is distinct from `FAILED`; timeouts, absent authenticated data, unsupported renderer, unsaved Desktop changes and inaccessible Fabric portal **never** become green. Planning may stop at `PROPOSED` until approval, and `review` mode cannot start any write or deployment.

1. **Discover** source files, tool versions, pages/routes, field/measure/chart inventories, media targets and test IDs. Build a capability matrix from actual installed CLI `--version`, Desktop Bridge manifest and app package lock; reject unsupported operations early.
2. **Contract** load owner stories/design tokens; generate conditional candidate questions only after enough verified model metadata exists. Store a question→component→data-oracle coverage matrix; do not fail exploratory use for missing owner-specified stories that were never supplied. Owner rules have priority over defaults.
3. **Facts** parse artifact sources and styles. Make scoped read-only model/data queries only for required facts with explicit authorization. Record model identity, effective filters, RLS, units, period and timestamp. Do not use an imported cache as evidence of repeatable refresh.
4. **Static check** run native rules + optional upstream validators. Do not let a textual AI description substitute for computed contrast, chart role compatibility, overlapping bounds, missing bindings or failed tests.
5. **Render + observe** invoke platform-specific runner for each contracted page/route, viewport, interaction state and role. Capture complete page, component crops, source-bound DOM/SVG or PBIR geometry, relevant accessibility tree, rendered text/value observations, console/network failures, and optional vision findings. Each image references exact source + state + renderer versions.
6. **Triage** cluster findings by actual component and symptom; qualify `measured`, `visually observed`, `hypothesis` or `unsupported`. Prioritize breaking data, incorrect answers and inaccessible user journeys before cosmetic changes. Independent reviewer cannot override model-data facts.
7. **Plan/patch** generate a typed operation plan with preconditions and postconditions. Show a diff and expected semantic impact. Apply only allowlisted edits to an isolated copy, never arbitrary model-generated shell commands/JavaScript or broad string substitutions. Approval gate for measure changes, story changes, deployments and destructive schema changes.
8. **Validate/regress** run schema/build/static tests first; then re-run fresh populated renders, question oracles, navigation states and affected neighbors. Require explicit invariants and no newly introduced defects; roll back candidate if violated. Keep the pre-change evidence for comparison, never copy old PNGs into a new manifest.
9. **Result** emit a machine-readable summary (`pass|fail|blocked|proposed`) and JSON + human-readable diff/findings with exact source, environment and data scope. Promotion is separate from candidate validation and has its own approval and audit event.

Run budgets: default one diagnostic pass, then at most three narrow repair rounds per defect cluster; stop on unchanged source, identical defect fingerprint, repeated transient error or model disagreement. Allow resume from verified artifact snapshots, not silent rerun of side-effecting edits.

## 4. Power BI adapter: exact source, actual Desktop and controlled edits

**Static facts:** PBIR pages/visuals/query roles/filters/sorting/theme and per-visual overrides; TMDL model metadata and measure formatting; model data and scoped DAX only through a connected authorized read-only endpoint/Modeling MCP. Normalize Fab Inspector JSON (if installed) without assuming it evaluates layout aesthetics. Use Microsoft report authoring CLI for schema/formatting capability detection and validation; feature flag any undocumented property. Effective visual formatting can be conditional or inherited; when not resolvable mark `unknown` and inspect actual render instead of pretending an absent JSON property is a default value.

**Windows runner (partly implemented):** use a disposable PBIP
candidate (report plus semantic model), verify project/model
references and exact Desktop **PID + canonical PBIP path**, check
Bridge manifest and saved state, validate PBIR, then serially
`reload --pid PID` and `screenshot[-all] --pid PID` (never
parallel against one PID). Reopen instead of reloading when model
or theme state requires it. Check page IDs, data readiness and full
canvas per capture scale. The Bridge exposes application state,
manifest, capture, reload and an `open <report>` CLI wrapper; it is
**not** a per-visual live formatting/DOM/click API. Native Windows UI
Automation is a **separate interaction and geometry witness**.
The remote Windows control tool launches/monitors local commands
but is not Bridge transport. Source hashes and report pixels must
be bound to DAX oracle scope and UIA actions. See the Microsoft
[Desktop Bridge overview](https://learn.microsoft.com/en-us/power-bi/developer/agentic/power-bi-desktop-bridge-overview)
and [P16 native UIA witness draft PR #56](https://github.com/analienx/visual-quality-system/pull/56).

**Power BI operations (versioned recipes):** `SetThemeToken`, `SetVisualProperty`, `SetVisualBounds`, `SetAxisFormat`, `SetVisualSort`, `ReplaceVisualFromTemplate`, `AddVisualFromTemplate`, `BindProjection`, `AddPageFromTemplate`. Each recipe declares visual types/schema versions, allowed paths/value domains, exact field-role expectations, source hash, affected-visual set, semantic-impact classification, reference-preservation (IDs/bookmarks/interactions), and rollback diff. Do not claim that arbitrary XML/JSON edits, filters, custom visuals, AI visuals or live Desktop controls are universally writable. Preserve correlation-vs-ranking intent when choosing chart replacements. After a change: schema validation → no lost bindings → scoped DAX oracle unchanged unless approved → Desktop reload/reopen → all affected page/neighbor screenshots → independent review.

**Interaction testing (P16 implemented in unmerged draft PR #56):** Desktop Bridge still
does **not** expose a general slicer/click/drillthrough API. VQS
now uses bounded, native Windows **`SelectionItemPattern`**
via `vqs/powerbi/desktop_uia.py` and
`scripts/windows/contoso_native_uia.ps1`, with action readback,
accessibility geometry and live DAX oracle matching. Real Contoso
Year/Region **9/9** actions were observed; that does not attest
the exact loaded-file identity or a Shape Map country click.
Map UIA exposes only a broad Plot area, and pixel input is
blocked on locked desktop. The unsupported country journey
remains `blocked`; WinApp CLI is prospective, not integrated.

## 5. Fabric Apps (Rayfin) adapter: code-first web application, not PBIR

Fabric Apps (preview) use the Rayfin SDK: backend data models and application logic are **TypeScript**; frontends may be React, Vue, Angular, Svelte or JS. A project typically has `rayfin/rayfin.yml`, `rayfin/data/*.ts`, `src/` and `package.json`. A Python-based *separate analytics service* may be a future integration, but **do not assert that Python is a native Rayfin backend or that a Fabric App is a Power BI report item**. Frontend analytical views may query semantic models. Microsoft already supplies a Fabric data-app template with centralized styling, common chart/format primitives and Playwright validation. Extend its capability; do not replicate its auth handshake or claim VQS owns the app server. See [Fabric Apps overview](https://learn.microsoft.com/en-us/fabric/apps/overview), [project structure](https://learn.microsoft.com/en-us/fabric/apps/project-structure), [FAQ](https://learn.microsoft.com/en-us/fabric/apps/faq) and [semantic-model data-app template](https://learn.microsoft.com/en-us/fabric/apps/data-apps-template).

**Source adapter:** read `package.json` + lockfile, `rayfin/rayfin.yml` (never secrets), TS/TSX component tree, router, central design tokens/CSS variables/Tailwind config, chart library usage, format utilities, declared semantic-model IDs and question→route→component bindings. Prefer explicit `data-vqs-id` / accessible names on major controls, charts and KPI cards; use a compile-time AST pass (TypeScript compiler or ts-morph) to find supported components and token usage, but do not pretend arbitrary React rendering can be fully understood statically. Treat user-defined callbacks, canvas charts and dynamic CSS as observable-at-runtime unless instrumented.

**Browser worker:** run a pinned Playwright Test/Chromium project in a disposable local app checkout. Start the app with a declared command (`npm ci`, configured `npm run dev` or `npm run build` + preview) under a fixed `baseURL`, secrets from OS/CI secret store, deterministic seed/fixtures, fixed locale/timezone/viewport/device scale/font set, reduced motion and disabled animations during stable captures. Wait on explicit app-ready/data-loaded assertions, not `networkidle` alone. Execute declared tasks (route, click/filter, compare, drilldown, back, focus/keyboard, responsive sizes). Capture screenshot + DOM boxes + computed CSS/token values + accessibility role/name/tree + console/page errors + failed requests + performance timings + `trace.zip`. For SVG charts, inspect plotted groups/ticks/text and bounded positions via stable selectors; for canvas/WebGL use the chart library's *supported* accessible data/config export or a test-only instrumentation hook, otherwise keep `data_unobserved` and use pixels plus independent data oracle. Never fake tick values from OCR. Playwright screenshot snapshots are regression signals, **not** the aesthetic evaluator; pin OS/browser/fonts and review intentional baseline updates. See [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots).

**Fabric-specific authenticated validation:** `npm run dev` can show local frontend while talking to Fabric backend; do not assume local stub/mock results reproduce tenant permissions, RLS or deployed portal behavior. For staged deployment, require a permitted Fabric capacity/workspace, enabled preview workload, correct SSO and model permissions; run `npx rayfin up --dry-run`, require approval for `npx rayfin up --workspace STAGING`, then inspect `npx rayfin up status --json`. No default production deployment and no `db apply --force`. Test the **deployed, Fabric-portal-hosted app under an authorized identity** separately from local UI. Current Microsoft documentation notes that some semantic-model-backed Fabric Apps cannot run queries from a standalone browser tab outside the portal; Playwright must enter the supported portal surface or record an environment blocker. Do not try to bypass iframe/CSP/SSO restrictions or reuse personal session cookies in CI. See [Fabric deployment](https://learn.microsoft.com/en-us/fabric/apps/deploy-app) and [data-app template limitations](https://learn.microsoft.com/en-us/fabric/apps/data-apps-template).

**Web operations:** start with safe `UpdateDesignToken`, `UpdateChartConfig` on explicitly supported libraries, `UpdateFormatMap`, `UpdateLayoutClass` and `InsertVettedComponent` in a known template. Use AST-aware edits and ordinary Git patches with file/path allowlists; do **not** permit arbitrary generated React component replacement without a source/build/security review. `npm run typecheck`, unit tests, lint, component tests and route-level Playwright regression run before any staged deployment. Data correctness uses a source-backed independent query oracle under the same authorized identity, not just visible KPI text.

## 6. Design intelligence: one intent model, surface-specific measurement

The reusable evaluator takes `QuestionContract + DesignProfile + normalized component/data facts + rendered observation`; never a single generic screenshot prompt. Common checks: color role collisions and semantic consistency, categorical palette distinguishability, text and non-text contrast where computable, font hierarchy, intentional whitespace, grid rhythm, label density, choice of chart for task, visible categories vs expected count, units/precision, comparative baseline, meaningful error/empty states, navigation/task coverage. VQS computes effective colors from PBIR theme+overrides where possible; the web adapter uses *actual computed style and DOM geometry* per browser state. Alpha blending/conditional colors are measured at their applied background; unresolvable dynamic visuals are `unknown` until rendered/instrumented. Do not enforce an arbitrary universal palette count or one aesthetic for all domains.

**Question oracles** should be simple and explicit: verified DAX for a Power BI measure + filter scope; a sanctioned backend query/fixture for a web app. Store result digests/aggregate expected values in private evidence; validate output equality within domain-specific rounding/tolerance. For `why`, label explanatory associations/hypotheses rather than causal proof; for forecasts, demand eligible history, method, uncertainty and backtesting. For UX, a headless agent may execute *instrumented* task scripts, but only representative users can substantiate claims of improved human task time or satisfaction. Overall feeling is judged by a capable independent visual model **against design tokens, persona, page/route objective and measured layout**, followed by source-level verification of its concrete observations. No AI-generated universal score releases an artifact.

## 7. Model/agent contract and cost control

The deterministic coordinator selects providers from a **capability registry** (`vision`, `text`, `max_images`, `context`, `data_policy`, version); never route images to a text-only model. Use a strong image-capable model only for targeted ambiguous layout, color hierarchy and composition reviews, passing bounded page/crop images and redacted facts **with explicit consent**. A cheaper text model can propose a typed repair plan from known defects. Two independent reviewer passes are optional for high-impact/ambiguous changes, not a substitute for static/data checks. Disagreement opens a finding, not a pass.

Apply **incremental invalidation**: on a changed visual, rerun its source/design checks, fresh affected-page render, and neighbor/interaction contract; on changed theme or shared styles, rerender all pages/routes under target viewports; on changed measure or model, invalidate all dependent oracles and charts; on changed auth/RLS, rerun affected roles. Never skip full-page verification after a visual edit. Limit tool calls with explicit timeouts, max candidate rounds and a per-run cloud budget. A review-only run is reproducible offline except optional live data/vision gates, whose absence is visible.

## 8. First implementation slices and acceptance (no speculative platform claims)

**Slice A — demonstrable P0 on Windows:** isolate and port the PBIPDocumenter Desktop Bridge, source-bound crops, structured PBIR facts and existing constrained recipe into VQS; fix missing scale-specific canvas capture and result provenance; create a *second unrelated* synthetic PBIR fixture. A CLI run must start from clean source, return 1–3 exact visual defects with evidence, apply an allowlisted edit in a disposable candidate, show a source diff, reopen populated Desktop and verify the defect plus adjacent visual and DAX oracle. Include blocked tests for unsaved/wrong PID, empty report and partial screenshot.

**Slice B — actual design evaluator:** implement a versioned `DesignProfile` (palette roles/semantic colors/fonts/spacing/viewport), effective PBIR formatting facts, source+pixel color assertions, visual component layout/bounds and a small curated benchmark of verified defects/false positives. Compare upstream governance adapter outputs with VQS findings; introduce model only for genuinely interpretive checks. Do not mark VQS P0 complete until all mandatory rule coverage and real render evidence are present.

**Slice C — web adapter without Fabric credentials:** add a small **synthetic React analytical app** using a pinned chart library, central tokens, stable VQS IDs and a deterministic dataset. Playwright tests must detect and *repair* a real token contrast defect and an overflowing chart without rewriting the app wholesale; verify route interactions, keyboard access and expected values at desktop and mobile viewports. Run locally on Linux/Windows independent of Fabric capacity.

**Slice D — Rayfin staging:** create a separate disposable Fabric Apps project from the **official data-app template**, use a permitted capacity/staging workspace and authorized semantic model. Confirm local frontend/backend integration, model queries, portal-only auth/render behavior, role-based task checks and CLI dry-run/status. Then apply one controlled styling repair and validate the deployed staged app. If preview capacity/workload/permission is unavailable, record `blocked` and do not claim deployed acceptance from the React fixture.

**Slice E — decision contract and distribution:** question/task
schema, conditional story families, traceability and deterministic
oracles across surfaces. Power BI core can be independently
assessed through `release_scope=powerbi-core` without a DOCX.
The optional Word component uses `word-docx`; historical
`combined` remains backward compatible. PBIPDocumenter consumes
the pinned VQS core once verified, without being folded into it.

**Operational support matrix:** offline PBIR inspection works without Desktop or Fabric; real PBIR visual acceptance requires licensed Windows Desktop and a populated authorized model; local React/TypeScript review requires a runnable app/browser; Fabric-hosted acceptance requires allowed preview capacity, deployment identity and portal access; cross-tenant autonomous deployment is out of scope. Publish the gate that ran, the gate that was not run and its reason. No claim that `python` executes inside Rayfin, that Desktop Bridge automates clicks, that Playwright bypasses Fabric SSO, or that a mock semantic model proves real data validity.
