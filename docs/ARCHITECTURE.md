# VQS architecture: actual processes, contracts and acceptance

**Status: target implementation with a pre-alpha portable core.** The complete technical specification is **[EXECUTION_ARCHITECTURE.md](EXECUTION_ARCHITECTURE.md)**. Use that as the normative reference for implementers: CLI and worker protocol, state machine, data structures, file locks, exact Desktop PID, Playwright evidence, Rayfin staging, patch allowlists, test tiers and security. This page is its concise entry point, **not** evidence that the target runtime has shipped. The more integrated Windows report prototype remains in PBIPDocumenter draft PR #12.

## One product, two real execution paths

Choose a **modular Python coordinator** and isolated, replaceable platform workers—not microservices or an AI model with unrestricted shell access:

```text
CLI / pinned design + question contracts
    ↓
Python run coordinator → private SQLite run index + immutable evidence/event log
    ├─ common: story coverage, source/data identity, measured rules, risk/adjudication
    ├─ Power BI adapter → PBIR/TMDL + authorized DAX → locked Windows Desktop PID
    │                   → actual full-canvas capture → bounded PBIR patch → reopen
    ├─ Web/Fabric Apps adapter → TSX/CSS/Rayfin files + data oracle → Node Playwright
    │                   → DOM/computed CSS/chart/a11y/route states → vetted source patch
    ├─ optional independent vision reviewer for genuinely perceptual findings
    └─ independent verifier → data + page/route + journey regression → result
```

VQS must share the **question, design, evidence, finding and acceptance schemas** across surfaces, not assume that a PBIR `visual.json` is interchangeable with a React component. A component locator is tagged by artifact type; Power BI positions use PBIR canvas coordinates, web positions use actual CSS pixel geometry at a named viewport, and documents use paginated points. Every observation is keyed to source revision, exact state, identity/filter scope, renderer and tool versions. Source hash is not data freshness. `pass|fail|blocked` are distinct; proposed changes require their own approval/promotion boundary.

## Scope and ownership

| Subsystem | Technical owner and realistic behavior |
| --- | --- |
| `vqs.contracts` + `vqs.stories` | Typed owner/default story candidates and design profiles; question→measure/data oracle→component→interaction mapping. Unsupported/inferred meanings do not become user-approved requirements. |
| `vqs.core` | Phase state machine, capability manifests, source/content digests, run-local private immutable evidence, SQLite + JSONL, deterministic rules, exception handling, no hidden green fallback. |
| `vqs.adapters.powerbi` | PBIR and effective theme/visual facts, TMDL and read-only model queries; schema/first-open validation; exact saved Desktop PID/path, serial Bridge capture; source-bound crop; bounded visual/theme editing. No undocumented general Desktop click or per-visual live API. |
| `vqs.adapters.web` and `workers/web` | Fabric Apps/React source and build manifest, stable test IDs, chart bindings, real DOM/SVG/computed CSS, Playwright browser journeys, `axe-core`, responsive captures, console/network failures and typed TypeScript/CSS patch operations. Canvas chart internals need library instrumentation or stay unknown. |
| `vqs.design` + `vqs.vision` | Measured contrast/semantic-color consistency, chart and label density, hierarchy/layout; independent image reviewer only for composition, overall feeling and actual rendering, grounded in source+data facts. |
| `vqs.repair` | Typed versioned operations + preconditions + allowlist; disposable worktree, semantic-impact ledger, validate/build/refresh/oracle/render/review, rollback and human promotion gate. |
| Optional adapters | Fab Inspector governance, Microsoft authoring/model tools, optional Draco 2 where neutral chart mapping is supported, Rayfin deployment CLI, optional model providers. Versions and unsupported states are recorded. |

## Power BI tool interfaces (decided 2026-09-26)

Verified against the installed tools, not assumed:

- **Report/source facts:** direct PBIR/TMDL parsing (pages, visuals,
  positions, formatting, bindings, filters, DAX source, diffs).
  VQS owns this layer; see `vqs.powerbi.measure` and `vqs measure`.
- **Semantic model:** Microsoft local Power BI Authoring/Modeling MCP
  (`@microsoft/powerbi-modeling-mcp`) is the primary interface for live
  Desktop models — connect, tables/columns/measures/relationships, DAX
  Execute/Validate, model edits and transactions. It cannot touch
  report pages or layouts.
- **Desktop/render:** Power BI Desktop Bridge for instance
  control and source-bound screenshots.
- **VQS owns** quality logic, design rules, evidence reconciliation,
  repair planning, and acceptance.
- **Report-side validation is optional**: the Microsoft-guided
  `powerbi-report-author` executable (documented distribution channel
  `@microsoft/powerbi-report-authoring-cli`) validates candidates
  (`vqs/powerbi/author`, policies auto/microsoft/direct). R6 removed
  the former pbir-cli legs: Microsoft rejection fails, warnings
  block unless explicitly allowed, and outages block — failures
  never fall back silently, and VQS stays fully functional with the
  CLI absent via the recorded direct fallback.
- **ADOMD role: none.** VQS has no ADOMD.NET dependency and ships
  no ADOMD installer; `vqs doctor` reports tool discoverability as
  information only.

## A real run, not a diagram-only workflow

`discover → contract → facts → static rules → render → observe → triage → [plan → typed patch → schema/build/data tests → fresh full-page/route render → interaction/neighbor regression → independent review]* → pass|fail|blocked|proposed`. Default mode is **read-only review**. Proposed and applied changes are isolated from the input repository. The eventual `vqs run --artifact PATH --kind powerbi|fabric-app --mode review|propose|repair` is a **target CLI**, not a current command; currently `vqs inventory` and `vqs request-review` are exposed. See [the execution blueprint](EXECUTION_ARCHITECTURE.md#3-run-state-machine-and-actual-jobs) for file and process locks, budgets, retry classes and privacy.

**Power BI:** load a disposable project, verify source/model identity, obtain scoped data oracles, validate PBIR, select saved matching Desktop PID/path, capture every affected page and crops without Desktop chrome, identify exact visual ID, apply safe PBIR/theme changes and verify full page plus adjacent visual and analytical task. For any changed model or theme requiring reopen, do not assume report-only reload is sufficient. Current Desktop Bridge cannot assert arbitrary user click/drillthrough journeys; unsupported interaction coverage is visible.

**Fabric Apps:** treat Rayfin as a **TypeScript-backed web application hosted as a Fabric item**, not a PBIR report or native Python host. Local developer flow: inspect TSX/CSS/router/chart tokens, run configured build and local frontend with authorized backend/fixtures, Playwright tests fixed desktop/mobile viewport with DOM/computed-style and source-backed KPI oracles, apply vetted token/component patch, re-run typecheck/build/browser test. Staging flow separately requires available Fabric capacity, preview workload, Entra SSO and an authorized tenant/workspace; dry-run and explicit `rayfin up` staging deployment followed by **Fabric-portal-hosted** authenticated browser verification. The published data-app template documents a semantic-query limitation outside the portal: a local mock or standalone tab must not be declared equivalent to deployment. See [Fabric adapter details](EXECUTION_ARCHITECTURE.md#5-fabric-apps-rayfin-adapter-code-first-web-application-not-pbir).

## Why this stays useful as AI authoring improves

VQS is not a new chart generator competing with the first-party authoring skill. It owns the **independent question/decision contract and answer oracle**, effective visual language, actual user-state observations, verifiable defects, safe scoped patches and measured before/after acceptance. Editors and model providers can change; the same tests should reject an aesthetically improved but misleading chart, an incorrect KPI, a hidden fifth category, a broken mobile journey or a Fabric app that renders only with mocked data. An optional model can review color hierarchy, but cannot override failing measurable contrast or RLS-scoped answer checks.

## Build and acceptance sequence

**A:** standalone Windows Power BI before/after repair on two unrelated real populated projects including wrong-PID/blank/partial-canvas negative tests. **B:** effective theme, axis/color/geometry test corpus and independent interpretation. **C:** synthetic local React analytics app with Playwright + accessibility/DOM/chart facts, successful bounded token/layout fix and responsive/task regression. **D:** disposable *official* Fabric Apps data-app template in a permitted staging workspace with separate portal-authenticated semantic verification, or explicit capacity/preview blocker. **E:** shared domain story packs, question-oracle/journey contracts, pinned package and PBIPDocumenter consumer migration. Word remains its own renderer adapter. These are acceptance milestones, **not completed results**.

Security: no business data, screenshots, secrets or user profiles in public commits; explicit remote-model opt-in and private run storage. No default production deployments, arbitrary AI shell edits, `rayfin ... --force`, bypassing Fabric SSO/portal limitations, or claim of general WCAG certification from automated scans.

Additional context: [product/story contract](PRODUCT_AND_DESIGN_CONTRACT.md), [default analytical stories](DEFAULT_STORIES_AND_AUTOMATED_DESIGN.md), [tool integration](INTEGRATION_STRATEGY.md), [ecosystem research](RESEARCH.md), [README](../README.md).
