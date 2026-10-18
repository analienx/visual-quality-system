# VQS × Microsoft powerbi-report-cli — implementation blueprint
**Audit date:** 2026-10-10
**Scope:** analienx/visual-quality-system, PR #31 at 5225a8d + dependent PR #33 at 24301e1; issue #22 and issue #32.
**Status:** verified source audit + proposed engineering program. NOT implementation acceptance.
**Normative hierarchy:** repo acceptance matrix and safety contracts > bounded user authorization > pinned agent/editor instructions > implementation convenience.

## 0. Executive decision

**Keep a single Python VQS quality/repair coordinator, a single typed safe PBIR writer, the Microsoft official skill as the mandatory authoring/design reference, the Microsoft Report Author CLI as the authoritative PBIR metadata/schema checker, Microsoft Modeling MCP as the semantic truth service, and exactly one VQS-owned runtime preview controller.**

Do not rebuild VQS as a second arbitrary Power BI author, do not let an autonomous editor bypass the candidate/allowlist contract, do not introduce pbir.tools, and do not let an assistant's skill-compliance assertion count as runtime attestation.

**Distinguish three independent decisions:**
1. Is the requested PBIR edit *well specified and permitted*? Source-bound intent, compatible schema, safe typed operation and owner policy.
2. Did the *mutation execute as intended*? Isolated candidate, minimal allowed diff, original and model unaffected, Microsoft PBIR validation.
3. Is the *result good and trustworthy*? Matching loaded Desktop data, correct question/answer/scope, fresh full-page renders, visible-category and interaction regression, independent perceptual review and separate owner-controlled promotion.

A successful stage cannot substitute for a later stage. For every mandatory acceptance criterion, missing evidence is BLOCKED; a demonstrable violation is FAIL. Static evaluation can be useful when Desktop is unavailable but cannot claim Desktop or release acceptance.

## 1. Source and evidence baseline

### 1.1 Exact branches / state

- PR #31: source hardening and U1–U7 composition; branch work/wp02-integration-r2 at 5225a8d, OPEN/DRAFT, not independently live-accepted.
- PR #33: Microsoft skill baseline integration; branch work/ms-report-skill-vqs-r1 at 24301e1, based on #31, OPEN/DRAFT.
- Official skill snapshot: microsoft/skills-for-fabric, commit bc42aaf734771bf752c1d7082dd91e5a6ca72b9f, skill metadata 1.0.5, 88 files.
- Microsoft npm package: @microsoft/powerbi-report-authoring-cli at 0.5.0 on the connected Zephyrus. It is a public preview, not a stable API contract.
- Original Contoso remains read-only: C:\Workspace\repos\PbiDocumenter\examples\contoso-retail\Contoso Retail.pbip. A real CLI validation found 3 errors + 3 warnings: missing schema in .pbip/definition.pbir, mismatched registered theme filename/name, two short Subtitle textboxes, and deprecated legacy map.
- Hosted PR #33 exact-head status observed October 10: R6 oracle SUCCESS, ordinary CI FAIL on Ubuntu 3.11/3.12/3.13 (Windows PASS), real authoring probe FAIL Ubuntu (Windows PASS). Linux fails skill snapshot integrity despite Windows identity success. Local Windows with globally installed real CLI: full suite 51 FAIL / 1078 PASS / 7 SKIP, because AUTO invokes real validation of intentionally incomplete synthetic PBIR fixtures. Focused integration: 32 PASS / 1 platform SKIP and Ruff PASS.
- Hosted green CI for earlier PR #31 is portable source verification, not real Desktop data/render proof. No work-package ledger promotion is warranted.

### 1.2 Broader repo inventory: reuse vs change

| Subsystem | Current audited implementation | Planned change |
| --- | --- | --- |
| Public CLI | vqs/cli.py exposes vqs run, static/desktop/release, editor backend and optional runtime parameters | Central typed RunRequest, skill/toolchain preflight, explicit assurance modes, parity with MCP |
| MCP | vqs/mcp/server.py + schemas.py dispatch engine tools but omit some CLI options | Share request parsing/validation and route every equivalent field; no logic duplication |
| Coordinator | vqs/coordinator.py, 1,511 lines, U1–U7 inspect/review/readiness/capture/propose/repair/verify/reload/answer regression/recapture/handoff/remeasure | Add preflight, metadata compilation, explicit authoring-validation and preview phases, hard gates and provenance; split oversized stage functions without changing the public contract |
| Source facts | vqs/pbir.py, vqs/powerbi/measure.py, vqs/design_rules.py | Preserve the deterministic rules; add effective-property and design/task contracts, only where proven by sources/metadata |
| Planning | vqs/repair/synthesize.py | Integrate Microsoft capability checks before assembling typed operation; add provenance and semantic-impact classification; still refuse ambiguous edits |
| Mutation | vqs/repair/execute.py + allowlist.py | Remains sole bounded writer; add capability preconditions and model/report-impact assertions; do not replace with raw agent JSON editing |
| Authoring tool | vqs/powerbi/author/mscli.py and adapter.py | Separate writer from validator, add JSON diagnostic and CLI version contract, typed metadata-read operations, candidate validation and evidence |
| Environment identity | scripts/report_skill.py, vendored Microsoft skill, vqs/install.py and doctor.py | Cross-platform vendor snapshot; lock source/vendor/CLI separately; enforce per-run version/skill identity |
| Desktop | vqs/repair/runtime.py, vqs/capture.py, vqs/powerbi/desktop.py | One PreviewPort with exclusive per-run ownership and source/PID/lease; compare Microsoft preview with VQS Bridge, no dual-driving |
| Modeling | vqs/powerbi/modeling.py (MCP client, readiness, DAX query) | Versioned query scope contract, role/filter/period handling, controlled answer baseline/regression and refresh semantics |
| Independent review | vqs/review/port.py, bundle + adjudication | Real independent image-capable provider, required check coverage and provenance, zero-observation negative control, authenticated release authority separate |
| Evidence | vqs/run_store.py, vqs/contracts/*, vqs/pipeline.py | Toolchain/skill/semantic/preview identity sealed into manifest + artifacts, resume/drift invalidation and normalized stage outcomes |
| CI | .github/workflows/authoring.yml, ci.yml, r6-oracles.yml, skill-refresh workflow | Separate pure unit / real CLI / valid PBIR / Windows native Desktop / adversarial acceptance lanes |
| Contract/UX docs | AGENTS.md, .agents/skills/vqs/SKILL.md, docs/CLI.md, JOURNEY.md, ARCHITECTURE.md, EXECUTION_ARCHITECTURE.md, ACCEPTANCE_MATRIX.md | Enforce entry contract and reconcile aspirational/stale claims; keep capability coverage visibly truthful |
| Roadmap | roadmap/work_packages.json + STATUS.md; #22, #32, WP-03/05/06/07/09/10/11/12 | Record dependency/evidence without advancing package status merely because code, tests or an issue exist |
| PBIPDocumenter/Word | Separate PBIPDocumenter consumer; DOCX rendering/inspection unfinished | Future consumer integration after Power BI core; do not make DOCX block the first real Contoso vertical slice |

### 1.3 Important findings beyond PR #33

- run_workflow in vqs/coordinator.py has authoring_backend but does not call the skill lock or CLI version attestation before proposal/mutation. AGENTS.md instructions are not an enforceable production gate.
- pipeline._execute_repair applies source changes before author_adapter.run_backend; metadata-assisted feasibility checks are absent from synthesis and plan validation.
- adapter.select conflates “direct writer” with “direct validation fallback.” The source writer is already the same VQS typed executor regardless of CLI selection.
- MCP vqs_run omits CLI fields such as authoring_backend, pid, renders_dir, live_answers and dax_questions (where applicable); MCP vqs_repair also omits authoring controls. Defaults and evidence differ by entry point.
- _unsupported_scope_answers in coordinator specifically handles filters and period. ModelingPort checks its own typed roles but end-to-end RLS/visual-scope equivalence is not certified. Do not infer same-task equivalence from a DAX text/hash alone.
- LocalBridgePort.open/status/reload and capture already exist with fresh PID/path/lease protections. The official Microsoft preview --host desktop resolves by folder and has no --pid argument. It cannot be swapped into a PID-locked workflow without a new proof of equivalent binding and ownership.
- Official Microsoft preview forbids unsafe reload when host reports unsaved data and mandates selected-host routing. VQS separately protects pre-existing user-owned instances and allows a narrow run-owned freshly opened instance quirk. Reconciliation must preserve the stricter boundary for user-owned work.
- ReviewPort is a typed protocol, not a registered production reviewer. Its _check_observations accepts an empty list; review_bundle then tallies zero blocked/fail and computes visual PASS. Add explicit required coverage; never interpret no observations as acceptance.
- config.py declares design_profile as stored/opaque, not fully consumed by the quality rules. Design advice is not a source-measured profile or verified rendered result.
- Stale descriptions in docs/ARCHITECTURE.md, EXECUTION_ARCHITECTURE.md, DEFAULT_STORIES_AND_AUTOMATED_DESIGN.md and ACCEPTANCE_MATRIX.md still refer to run as future or all cases as planned. They must be updated *after* evidence, not through optimistic edits.
- Word pagination, PBIPDocumenter two-project parity, Fabric Apps are separate lanes. This project is not a general report-generation agent; VQS is independent validation and bounded improvement.

### 1.4 External authority boundaries

Microsoft powerbi-report-cli official skill:
- planning: user requirements and approved report specification, not unattended greenfield build before approval;
- design: chart-task/semantics, page identity, visual hierarchy, typography, whitespace, colors and accessible layouts;
- authoring: PBIR/PBIP edits using known schemas and metadata, after-batch validation, loaded-current-source preview and screenshot review;
- management: separate Fabric report publishing/upload/download/rebinding, never implicit in local repair.

Microsoft Modeling MCP provides semantic-model discovery, DAX validation and live queries. It does NOT give Microsoft report skill an implicit license to edit TMDL/model/RLS. VQS's on-disk parser remains source truth; live MCP responses prove loaded model/data conditions separately.

## 2. Target architecture

### 2.1 One user-visible transaction

Request from VQS CLI, VQS MCP, or an invoking agent
→ Common RunRequest parser and policy
→ Scope/permissions resolution and exact source/model identity
→ Approved Microsoft skill/CLI/version capability attestation
→ VQS static inspection and deterministic finding inventory
→ Optional approved design/story contract
→ Microsoft CLI metadata/catalog/format/expr evidence for impacted visual properties
→ VQS typed RepairPlan compiler and dry-run + risk classification
→ VQS-owned disposable project/model workspace
→ Source-bound typed patch via VQS only
→ Microsoft CLI structured validation on the entire candidate
→ VQS own candidate-only preview lease (single chosen backend)
→ Microsoft Modeling MCP model/role/period + baseline/regression evidence
→ Fresh per-page render inventory (all pages for report-wide changes)
→ Deterministic VQS remeasure and cross-page/neighbor/task checks
→ Verified transport bundle for independent image-capable reviewer
→ Run summary: execution, remaining quality, new regressions, uncertain gates
→ Explicit owner-controlled promotion with backup/rollback; never publish.

Report-wide formatting/theme changes require all-page reviews; a narrow visual geometry change requires the affected page and neighboring objects plus any semantically related pages. Structural validation alone is not a completion criterion.

### 2.2 Distinct contracts: editor, validator, runtime, evaluator

Define explicit narrow ports:
- ReportMetadataPort: read-only catalog/types/roles, formatting objects/properties/selectors, expression encoders/decoders, static PBIR summaries and schema-version compatibility.
- ReportValidationPort: read-only validate(candidate) returning normalized diagnostics and structural verdict, with exit/status consistency.
- TypedMutationPort: VQS apply_plan only, bounded to allowed candidate file targets and preconditions.
- PreviewPort: status/open/reload/capture/close-if-owned capability with source, PID, project identity, lease and data-context binding; one selected implementation per run.
- ModelingPort: current interface plus explicit readiness, scoped question batch and expected-answer comparison.
- IndependentReviewPort: sealed complete capture bundle → required per-page/per-check observations from a separately identified provider.
- QualityPolicy: deterministic rule definitions and mandatory gate decisions independent of any authoring skill.

The Microsoft CLI is metadata + validation + possibly preview; it is *not* a generic source mutation engine. VQS is not responsible for implementing Microsoft's entire authoring CLI. Do not add unbounded shell/JSON instructions to the repair executor.

### 2.3 Disentangle mutation backend from validation assurance

Replace the overloaded internal field authoring_backend with two distinct concepts while retaining CLI compatibility:
- mutation_engine = vqs_typed only (report-only v0.1);
- validation_provider = microsoft_cli or native_static (offline coverage only);
- assurance_level = portable | desktop | release;
- required_capabilities = set derived from operation/scope (skill, metadata, authoring CLI, Bridge or proven preview, Modeling MCP, reviewer, authority).

In a portable synthetic test, the explicit native_static path may pass the VQS pure safety contract but sets authoring_validation=not_run/unsupported, never “Microsoft validated.”
In normal human report repair, require pinned skill + genuine Microsoft validation. A missing CLI yields BLOCKED for required assurance, not a silent PASS.
In desktop/release assurance, no direct-only fallback may satisfy the validation or rendering gates. Existing --authoring-backend auto|microsoft|direct flags map through a backwards-compatible translator and show a deprecation warning only when the new contract is ready; do not change public semantics without a compatibility test suite and migration note.

### 2.4 Minimum typed structures

RunRequest/1 (all values schema-validated): report/project/model paths, mode, scope, permissions, run root/id, resume id, authoring assurance, approved design profile, selected preview provider, optional model answer queries, reviewer identity, owner approval separately.
SkillAttestation/1: official upstream repository+path+immutable revision, content snapshot SHA, metadata skill version, installed skill path and digest, tested CLI package+version/path/executable SHA, schema/catalog revision, checked timestamp, compatibility policy.
AuthoringCapability/1: visual type, role constraints, formatting object/property selectors, expression kinds, schema version, exact queried CLI output digest, supported/unknown status.
PlanOperation/2: visual/page locator, original source digest, leaf old/new, typed operation id, required metadata evidence, semantic-impact level, affected pages, allowed writes, preconditions, invariant checks, refusal reasons.
ValidationEvidence/1: candidate tree digest + exact command/version, normalized JSON diagnostics (severity/code/path/file), original stdout artifact digest, counts, exit code, policy decision and warnings disposition; no raw business data in public CI.
PreviewLease/1: run id, project/report/model path, original/candidate digest, PID if Desktop, preexisting PID inventory, own/open timestamp and status, save-state policy, source/data/viewport/scale/page bindings, exclusive lock.
AnswerOracle/1: DAX/query id/hash, declared role/filters/period, connected loaded-model identity and data readiness, timestamp, result digest, before/after equivalence mode, permitted tolerance and explicit unsupported flags.
ReviewRequirement/1: required pages/checks and state, source/capture digests, image capability, reviewer identity and authority, per-item observations, independent assignment, completeness verdict.
RunOutcome/1: separate execution verdict, structural validation verdict, desktop+model readiness, quality before/after, resolved/remaining/new findings, blocked/failed stages, unsupported coverage, candidate status and promotion status.

Do not copy raw external responses into arbitrary top-level data without schema/size/path checks. Internal Pydantic/dataclass conventions should match existing versioned VQS contracts; start additive, migrate with compatibility tests.

## 3. Critical dependency order

Do NOT wire the preview or add visual generator features before Phase 0 portable CI and Phase 1 contracts are stable.

- Phase 0: freeze head, independently triage portable CI, make official skill and real CLI validation deterministic cross-platform.
- Phase 1: one typed RunRequest and capability/preflight gate for CLI/MCP/coordinator; separate writer and validator.
- Phase 2: read-only Microsoft metadata port, feasibility-aware plan synthesis, typed recipe compiler and source-proof records.
- Phase 3: strictly bounded candidate validation, recheck/resume seals and safe warning triage.
- Phase 4: one desktop PreviewPort + loaded model/data oracle, real candidate open→reload→capture evidence.
- Phase 5: independent design/quality review, cross-page/task/interaction regressions and honest outcome.
- Phase 6: two unrelated PBIP and Word/PBIPDocumenter acceptance only after Power BI core evidence; tracked separate.
- Phase 7: documentation/roadmap reconciliation and independently reviewed release decision.

Each phase is a separately reviewable commit or small PR. Keep PR #31/33 drafts until their own acceptance conditions are fulfilled; do not merge just because this blueprint is approved.


## 4. Phase-by-phase engineering work orders

### Phase 0 — Correct portable Microsoft skill + CLI contract (release blocker)

**Goal:** With identical Git checkout, Linux and Windows must produce the same skill identity and validation outcomes regardless of whether global Microsoft CLI tools happen to be installed.

Affected files:
- scripts/report_skill.py; .agents/skills/powerbi-report-cli-upstream.json; .gitattributes;
- .github/workflows/authoring.yml, microsoft-report-skill-refresh.yml, ci.yml;
- vqs/powerbi/author/mscli.py and adapter.py;
- tests/test_report_skill_integration.py, test_r6_e07_authoring.py; new real-authoring fixture tests.

Tasks:
0.1 Reproduce current hosted Linux failure. Capture computed sha256/file count/version and compare vendor checked-out bytes against canonical upstream Git blobs. Inspect .gitattributes, core.autocrlf, worktree/index CRLF conversion and sync origin. Do not simply relax integrity checks.
0.2 Canonicalize vendor snapshots from Git tree byte content (not arbitrary local checkout filtering). Select LF-stable upstream blob bytes or enforce -text for the vendor subtree with a canonical normalized sync; include a manifest of per-file hashes, count and upstream commit. The same manifest must verify on both OSes. Test deliberate LF/CRLF mutation, missing file, inserted file, symlink, renamed file, malformed metadata and lock tampering.
0.3 Verify upstream path and revision. The collection exposes both canonical plugin packaging and a skills/powerbi-report-cli path; do not assume moving package layout from the old location is a content update without comparing the actual referenced skill identity. Detect an upstream relocation with an explicit migration state.
0.4 Prevent the weekly refresh from asserting a commit SHA it has not cryptographically sourced. Acquire upstream commit from the checked-out repository, enumerate exactly the vendored subtree, and create a proposal PR only if content identity has changed. Do not auto-merge, auto-run unreviewed instructions, or update @latest mid-run. Keep previous lock snapshot recoverable, and validate rollback behavior under mid-sync failure.
0.5 Validate real CLI executable and NPM distribution integrity. CI pins 0.5.0 and Node runtime; production pins tested version plus known good tool identity and records global PATH shadowing. Separate CLI/runtime availability from mere package-name string matching.
0.6 Create two disconnected test lanes: fast portable unit tests force explicit synthetic validation and never contact an installed real CLI; real-authoring lane installs the pinned CLI on Ubuntu and Windows and runs a genuinely valid scaffolded fixture and several deliberately invalid fixtures. Avoid catch-all success probes that merely print “backend=missing” and exit zero.
0.7 Fix the real CLI JSON adapter tests: success without warnings, success with structured warnings, diagnostic error, malformed envelope, schema-count mismatch, null/booleans, nonzero exit despite success, timeout, truncated stdout, Windows .CMD with spaced/unicode path, Linux executable, and warnings requiring explicit disposition.
0.8 Add a one-line verdict summary to CI artifacts: pinned skill revision/digest, CLI version, valid fixture PASS, invalid fixture FAIL, actual test count, and ignored/skipped status; hosted CI cannot be GREEN if a required tool is absent.

Exit:
- Hosted Linux three legs and Windows leg green at EXACT SHA.
- Real-authoring lane proves valid fixture accepted and invalid fixture rejected on both platforms.
- Windows with globally installed real CLI runs entire *portable* suite identically to Windows without it; validation paths are explicit.
- PR #33 remains draft until full independent audit; original Contoso stays unmodified.

Adversarial controls: corrupt one vendor file; set a different npm version on PATH; inject warning-like words into JSON; flip exit to 0 with result failed; remove .platform or definition.pbir from valid PBIP. All expected BLOCKED/FAIL in appropriate gates, never silent fallback.

### Phase 1 — One public contract + enforced capability preflight

**Goal:** Every public authoring route follows the same version and permission policy; no “agent remembered to read the skill” requirement masquerades as a programmatic gate.

Affected files:
- new vqs/contracts/authoring.py or equivalent versioned contract;
- vqs/cli.py, vqs/mcp/schemas.py, vqs/mcp/server.py, vqs/coordinator.py;
- vqs/config.py, vqs/doctor.py, vqs/install.py, vqs/run_store.py;
- tests/test_cli_tools.py, test_mcp.py, test_u2_run.py and new parity/skill tests.

Tasks:
1.1 Freeze RunRequest/1 and each mode/scope combination. Expose fields consistently across CLI and MCP: report, model, mode, scope, run root, candidate root, plan, render output, Desktop PID, authoring assurance, live answer flag+question contracts, data permissions, reviewer, fixer, resume. Unsupported options fail explicitly, not ignored.
1.2 Create one normalize_request() for CLI/MCP. Do not duplicate defaults, fallback decisions, or authorization logic in the two transports. Require an exact same canonical request digest and stage plan from matching CLI/MCP inputs; exclude transport-only output paths from semantic identity when justified.
1.3 CapabilityResolver inspects and pins installed VQS module/package/source SHA, exact skill/vendor hash, required Microsoft CLI version, source report schema, available reader/model/preview/reviewer; maps operation type and requested scope to REQUIRED/OPTIONAL/NOT_APPLICABLE capabilities.
1.4 Define assurance policy. Review-static needs source parsing only and must work offline; proposing an edit using Microsoft catalog requires skill/metadata; modifying real PBIR requires verified skill and genuine Microsoft validation; desktop scope additionally requires a safe preview host and authorized data; release requires authentic independent authority. A direct-only mode remains for portable tests and explicit dry-run evidence but never satisfies a stronger claim.
1.5 Add a preflight stage before the first write, including capability summaries with absent/unverified/supported states, exact version/source digests, authoring-mode reference ID and immutable run environment. If the skill is newer upstream but local approved bytes unchanged, report UPDATE_AVAILABLE separately; keep running the approved revision.
1.6 Route every legacy command that writes report content through one authoring policy guard: vqs repair, vqs run --mode repair, MCP vqs_repair, MCP vqs_run; audit future repair entry points. Avoid a user-facing “always read skill” demand for static data measurements, which should remain deterministic/offline.
1.7 Seal preflight before repair; resume rechecks both project/model and relevant toolchain versions/digests. A changed skill/CLI/provider between original and resumed repair requires a new candidate run or explicit revalidation, not reusing prior PASS evidence.
1.8 Make vqs doctor accurate and actionable: installed CLI/skill revision/path, missing/pinned mismatch, available metadata surfaces, Bridge/MCP versions and permissions; read-only, no auto-install.

Exit:
- CLI/MCP equivalence tests assert same normalized request, stage status and failure semantics.
- Stale skill/CLI, wrong model/roles, unsupported requested preview, missing reviewer block before mutation.
- Read-only run succeeds when Microsoft CLI is absent without pretending authoring was validated.
- No source/promotion side effects on policy/preflight failure.

Negative controls: MCP drops a field, injected unrecognized field, spoofed SkillAttestation object, unchanged filename but different report digest, resumes under changed CLI, consent text falsely asserted as authenticated release identity.

### Phase 2 — Microsoft metadata-assisted authoring compiler

**Goal:** A legitimate source-provable defect becomes a safe repair plan whose formatting/schema properties are grounded in actual Microsoft metadata, not memorized PBIR JSON shape.

Affected files:
- new vqs/powerbi/author/metadata.py, capabilities.py, diagnostics.py (names illustrative);
- vqs/repair/synthesize.py, vqs/repair/allowlist.py, vqs/repair/execute.py;
- vqs/pbir.py, vqs/powerbi/measure.py, vqs/design_rules.py;
- tests/test_repair_scenarios.py and new contract fixtures.

Tasks:
2.1 Read-only metadata port wraps documented CLI commands: catalog list/describe; formatting list-objects/describe-object/describe-property/effective-properties; expr encode/decode; theme encode; preview-visuals/pages/filters/themes. Execute via bounded argv, not shell-expanded user text, with independent timeout/output limits and structured JSON/error interpretation.
2.2 Resolve report schema version, installed CLI capabilities, required visual types, roles, projections, formatting objects, selector IDs and enum values. Cache metadata by CLI digest+schema+visual type+query command, never by visual title alone. Cache records are source evidence, not approval.
2.3 Classify synthesized operations:
- geometry/layout: source position/canvas and overlapping neighbors; metadata queries only where the actual touched property requires them;
- leaf formatting: exact object/property/selector/type and expression encoding from CLI;
- theme changes: registered theme, effective override hierarchy and all-page impact;
- visual type/binding change: required role cardinality, task semantics, model fields, category/aggregation/filter impact. Owner decision needed when analytical meaning changes;
- unsupported/unknown default: no guessed fix. Return clear owner decision.
2.4 Implement compiler output as versioned PlanOperation with source and metadata query digests, preconditions, exact files to write, measured old/new values, intended visual outcome, semantic-impact classification, affected page IDs and required regressions. Do not accept free-form LLM write instructions.
2.5 Preserve the existing conservative synthesize/allowlist kernel. Put a thin metadata-aware validation step between synthesis and execution, not a second repair engine. Use versioned recipes for specific visual types rather than blanket generated JSON.
2.6 Add intent/design handoff: if the request is a redesign, a Microsoft design brief/profile can propose desired changes. It must be owner-approved or explicitly authorized as a constrained automated improvement; the VQS compiler only instantiates independently measurable, role-safe operations. Re-rendering cannot prove whether an unapproved change answers the desired business question.
2.7 Add semantic invariants: exact queryState projections, measure references, aggregation, sort, Top N, filter context, roles, model references, interaction/default state, report/theme consistency. Report-only styling/position changes preserve these bytewise or via normalized semantic equality.
2.8 Use CLI text measure with exact installed font only as advisory for resizing buttons/textboxes. A labeled approximate font metric cannot become a pixel-geometry PASS without actual calibration/render proof.

Exit:
- Metadata-backed repair plan for a known subtitle height/format defect generated without hand-authored JSON; unrelated visual/source/model unchanged.
- An unknown formatting property, broken visual role, deprecated-map replacement without intent, or unsupported feature emits owner decision/refusal rather than mutation.
- Fuzz/negative tests for path escape, selector change, casefolded visual ID collision, unknown inherited override and conflicting plans.
- Generated plan captures proof necessary to revalidate if CLI/source/schema changes.

### Phase 3 — Candidate validation and sealed evidence

**Goal:** VQS applies the plan on a true disposable PBIP project and structurally verifies the same bytes it will open in Desktop.

Affected files: vqs/pipeline.py, vqs/repair/execute.py, vqs/repair/regress.py, vqs/powerbi/author/adapter.py, vqs/run_store.py, vqs/evidence.py, tests/test_repair_execute.py, test_r6_e07_authoring.py.

Tasks:
3.1 Stage full project safely, preserving required .pbip/project metadata and supported byPath semantic model; exclude .pbi/local caches, secrets, untracked customer resources, unsupported external references, junctions and symlinks as declared in existing safety policy. Candidate root must not resolve to original; no user-owned file overwritten.
3.2 Before apply: record original report/model SHA, plan SHA, skill/tool versions, metadata evidence, permissions. Apply typed mutation only in isolated candidate; assert exact allowed patch path and target JSON pointer after materialization.
3.3 After apply: compute candidate report/model tree digests, actual changed file set, normalized semantic-impact diff. Assert byPath project model bytes preserved for report-only edits.
3.4 Run genuine Microsoft validate on the *candidate .Report or owning .pbip as supported*. Normalize error/warning severity, file and JSON pointer, verify that diagnostic paths resolve inside the candidate/project (path-traversal safe).
3.5 Use explicit warning adjudication: whitelist only known reviewed low-risk warnings with scope, reason, issue ID and reviewer/owner policy; do not expose a blanket flag for all warnings in desktop/release acceptance. Deprecated visual or theme inconsistency is not harmless by default.
3.6 Seal validation toolchain and output, including candidate digest at validation, phase and read-only command. If source changes before runtime opening, revalidate or block.
3.7 Make report integrity tests deliberately prove rollback: crash between staged rename, candidate edited after seal, model digest modified, extra file, invalid schema/field selector, original changed meanwhile.

Exit:
- Complete, isolated candidate verified by Microsoft CLI; exact source diff and model equality proved.
- No structural FAIL or unreviewed warning can advance into a Desktop acceptance stage.
- Repair executed / structure valid / quality accepted are three separate fields, never one PASS string.

### Phase 4 — One bounded live Desktop and semantic runtime

**Goal:** Candidate report is opened/loaded and rendered by exactly one known host with matching source, model, PID, render scope and data readiness.

Affected files:
- vqs/repair/runtime.py, vqs/capture.py, vqs/powerbi/desktop.py, vqs/coordinator.py;
- vqs/powerbi/modeling.py and associated typed scope contracts;
- new vqs/powerbi/preview/port.py and provider adapters only if needed;
- tests/test_u4_promotion.py, test_capture.py, test_r17_viewport.py, Windows read-only host probes and disposable Contoso e2e.

Tasks:
4.1 Probe the Microsoft preview host with read-only capability discovery and compare its actual v0.5.0 status/open/reload/capture outputs to VQS Bridge 1.0.0. Microsoft CLI Desktop preview addresses reports by owning folder/project, not PID; establish whether PID and exclusive lease can be independently resolved and recorded. Never infer instance selection from report title.
4.2 Choose one implementation under PreviewPort for the whole run:
- preferred when identity meets VQS standards: Microsoft CLI preview wrapper with VQS-enforced exact process/source binding and ownership;
- otherwise supported Windows choice: existing VQS-owned Bridge for open/PID/reload/capture, with an explicit compatibility deviation against the standalone skill's preview prescription;
- service/headless host is a separate approved capability with true model workspace binding and privacy; no automatic remote publishing or cloud screenshot exfiltration.
Do NOT alternate providers mid-run or operate a second host simply to tick the Microsoft skill box.
4.3 Acquire exclusive candidate lease and cross-check pre-open processes/PIDs, original report and user-owned unsaved state. For VQS-owned new Desktop instance, prove fresh PID and matching exact candidate currentFilePath/reportDir; preserve the narrow false-unsaved-state telemetry exception only when origin and source digests are proven.
4.4 Verify reload completed and loaded source digest matches candidate. Distinguish report-only layout reload from TMDL/model reload plus model processing; report-only current phase should not opportunistically process or mutate the model.
4.5 Require Modeling MCP readiness and authorized scoped queries where needed. Record model id, role(s), filters, period, query hash, data snapshot/readiness and same-answer comparator. Explicitly block filters/period/RLS combinations not fully represented on both live Desktop view and MCP query.
4.6 Capture every affected page, with complete page inventory and image hashes, source/PID ownership, renderer version and scale. Render identity may PASS with viewport geometry unknown; pixel-to-PBIR geometry assertions require authoritative transform/calibration. Never derive transform from PNG dimensions alone.
4.7 Recheck the candidate report/model digest after Desktop operations (Power BI may update project metadata). If Desktop auto-writes changed bytes, produce a separate observed drift/authorized-normalization decision, not a silent input overwrite.
4.8 Do not drive pre-existing Desktop instances as a proof shortcut; no reload of original Contoso; do not kill unrelated windows. Deadline and retry budget should be bounded and expressed in events, not blind GUI clicks.

Exit:
- Real disposable Contoso candidate opened by VQS and bound to new PID + exact project + source/lease; live data/readiness and fresh affected-page render evidence stored privately.
- Wrong PID, edited original, unsaved user instance, stale source, bad model scope, partial screenshot, guessed transform or incomplete page inventory block.
- If Modeling MCP not reachable, return a useful structural candidate with desktop/semantic acceptance BLOCKED, not report PASS.

### Phase 5 — Genuine quality assessment, reviewer, regressions and UX

**Goal:** Demonstrate that a source edit improved actual usability, did not corrupt the analytical task, and can be judged independently.

Affected files:
- vqs/coordinator.py, vqs/review/port.py, vqs/review/bundle.py, vqs/review/adjudicate.py;
- vqs/design_rules.py, vqs/powerbi/measure.py, vqs/stories/*;
- docs/PRODUCT_AND_DESIGN_CONTRACT.md and DEFAULT_STORIES_AND_AUTOMATED_DESIGN.md;
- acceptance fixtures G1/G2/G4/G6.

Tasks:
5.1 Establish design brief acceptance inputs: the intended report audience, visual task, chart meaning, typography scale, whitespace, alignment/padding, color/contrast semantics, navigation and supported interactions. Microsoft's design mode can propose, but cannot self-approve arbitrary aesthetic changes.
5.2 Review deterministic findings first: within-canvas placement, overlaps, effective typography values, unit/percent precision, clipped labels, text/background contrast, cross-page duplicated grain, semantics of palette, missing category/map location, and relevant anti-patterns. Do not hardcode a fashionable palette or claim universal WCAG compliance from partial probes.
5.3 Add bounded metadata-driven checks where missing. Theme and explicit override resolution must preserve UNKNOWN for inherited values not proven effective; dynamic conditional formatting requires a verified context or rendered observation.
5.4 Produce a required visual-review coverage matrix by affected page and check, not merely a list of images. Require an image-capable reviewer identity different from fixer with observed details and locator for each mandatory check. **Zero observations, missing pages/checks, unknown image capability, malformed payload or timeout must BLOCK**; note the present zero-observation bug.
5.5 Review full page plus targeted crops of affected visual and adjacent objects; include data/state context. Perceptual findings are hypotheses unless verifiable in source/pixels. Reviewer cannot override a deterministic failure, and fixer cannot approve its own output.
5.6 Remeasure candidate against baseline; classify fixed, remaining, new/regressed, unknown and explicitly out-of-scope. Compare before/after scoped DAX answers, numbers, category visibility, aggregations, filters/sort and neighboring visuals. Same totals under different filters do not establish equivalence.
5.7 User-facing result should expose one clear scorecard: execution / Microsoft validity / Desktop readiness / answer equivalence / visual review / quality delta / promotion state. No faux percentage improvement from qualitative reviewer prose. Include precise next action and candidate location, private evidence link/id.
5.8 Iteration policy: only another *new disposable candidate* with new preconditions and sealed evidence; bounded attempts. A bad visual edit cannot be accepted because the compiler produced a syntactically valid edit. Do not auto-promote.
5.9 Before declaring release-quality, separately design authenticated trusted reviewer/approval authority; local unsigned reviewer_id and owner consent string cannot substitute for attested human identity.

Exit:
- The known Subtitle repair shows before/after loaded render improvement, no changed model answer or adjacent visual/crop regressions, and reviewed source-bound observations.
- An unrelated regression is found even if the original defect disappears.
- Every claimed quality dimension maps to a source/render/query/check evidence object and verifier authority, or to explicit BLOCKED.

### Phase 6 — Consumer & cross-artifact acceptance (separate track)

Power BI core vertical slice **must precede** DOCX and PBIPDocumenter integration:
6.1 Run the complete public user route on TWO unrelated real, authorized/disposable PBIPs, not merely synthetic twins. Prove G0–G4 and independent G6 semantics, including wrong-PID and missing-data controls.
6.2 When ready, consume VQS as a pinned library/CLI/MCP from PBIPDocumenter rather than copying its quality rules or Microsoft skill into the application. Versioned handoff: report+model digest, bound quality findings, all-page capture refs, candidate repair outcome and allowed-publication status.
6.3 Word is its own adapter: real backend/font/locale, DOCX→PDF/all-page PNG, OOXML and pagination checks, safe candidate changes, full rerender, figure references bound to report source and questions. No claim that the Microsoft report skill validates Word pages.
6.4 Keep Fabric Apps/Rayfin/Playwright deferred under WP-13, explicitly excluded from the Power BI + DOCX first-release test.
6.5 Only after WP-11 matrix and owner-controlled promotion proof may WP-12/PBIPDocumenter integration advance.

## 5. CI and acceptance matrix

Design CI as **capability tiers**, not one test command that changes behavior based on whichever binaries happen to be on PATH.

| Tier | Environment | Tooling | Must prove | Fails on |
| --- | --- | --- | --- | --- |
| T0 pure Python | Linux/Windows 3.11–3.13 where supported | no real CLI, frozen fake | request contracts, hashes, rules, typed edits, fail-closed semantics | any portable regression |
| T1 skill supply-chain | Linux + Windows | pinned vendor bytes/manifest, no active Desktop | same hash/metadata/commit and update candidate | platform hash drift, tampering, missing file |
| T2 real Microsoft CLI | Linux + Windows pinned Node/npm | @microsoft CLI 0.5.0; valid/invalid PBIR samples | valid accepted, negative cases rejected, parsed warning/error JSON, roles/formatting metadata | missing CLI, wrong package version, false-positive warning, bad diagnostics |
| T3 candidate integration | Linux + Windows | candidate creator + CLI; approved fixture | exact allowlist, metadata-informed plan, source/model parity, rollback | hidden writer change, model drift, stale source |
| T4 real Desktop & Modeling MCP | authorized Windows only | live Desktop Bridge or proven preview, MCP and populated model | run-owned candidate PID, scoped DAX baseline/regression and native all-page captures | PID drift, data absent, scope mismatch, calibration assumptions |
| T5 independent review | image-capable independent provider | sealed review bundle + required checks | perceptual observations, cross-page and task regression, traceable decisions | reviewer alias, zero observations, stale image, omitted page |
| T6 first-release acceptance | controlled test environments | two unrelated PBIPs, DOCX backend | G0–G6 and explicit owner promotion boundary | incomplete mandatory evidence or undocumented unsupported feature |

T0 should not install Microsoft's CLI at all. T2 intentionally installs it and uses valid structural fixtures; no environmental AUTO switching. T4 should be separately triggered/authorized and never run against the original Contoso by default. CI artifacts carry sanitized digests/results, not screenshots containing business data.

### Mandatory new test classes

- Cross-platform SHA: LF, CRLF, UTF-8 BOM, file order, missing/extra vendor docs, symlink and tampered metadata.
- Real CLI envelope: counts, errors, warnings, non-zero exits, malformed output, timeout and no executable.
- Source mutation: wrong branch/source digest, path traversal, symlink, unsafe selectors, semantic model edits, lost filter, unknown inherited formatting, large overlap/no free slot.
- Capability/routing: CLI vs MCP same config, missing permission, reviewer identity spoof, source drift on resume, existing user-owned Desktop with unsaved work.
- Preview: no owning pbip, wrong PID, stale matching title, unsaved quirk only for new owned PID, screenshot from wrong report, mismatched data scope and partial page.
- Answer: same DAX on different roles/date/filter, blank model, wrong aggregation/denominator, equal answer under mismatched scope.
- Reviewer: empty/duplicate/missing-per-check observations, untrusted image provider, unreviewed cropped neighbor, model rejects, blurry/un-calibrated geometry claims.
- Promotion: static consent cannot claim Desktop/release acceptance, original/candidate drift, backup collision, rollback recovery, unauthenticated owner text.

## 6. One executable vertical slice and user acceptance test

A strong first true end-to-end case is **one conservative, seeded Subtitle text-height defect in disposable Contoso**, chosen because the Microsoft real validator already pinpoints Subtitle warnings while VQS already has bounded geometry repair support.

1. Read-only source/report/model inventory on the ORIGINAL; preserve original source digest and current Desktop PID/saved state; never reload original.
2. Prepare an approved disposable Contoso full project copy, including necessary project metadata, model byPath resolution and no .pbi caches.
3. Run static VQS review and Microsoft CLI validation on the candidate baseline. Do not attempt repair of all three existing structural errors at once: establish a valid project fixture as a prerequisite, isolate the one measured Subtitle defect, classify remaining errors separately.
4. Load skill preflight and relevant authoring mode reference. Inspect actual textbox formatting/height metadata and old/new PBIR geometry.
5. Invoke public vqs run --mode repair --scope desktop. It must synthesize a one-op safe plan without hand-authored repair JSON; exact source tree and owner policy bind it.
6. Apply only to disposable candidate. Microsoft validation must pass on the *complete* candidate project for the chosen acceptance surface; unresolved pre-existing errors remain an explicit gating blocker rather than silently ignored.
7. Open candidate using one runtime provider; prove new PID and exact candidate path and report/model source digest; never drive the pre-existing original instance.
8. Execute MCP readiness and baseline same-question DAX when scope supported and authorized; record scope + results before edit/runtime as appropriate.
9. Reload candidate safely, collect fresh full-page affected screenshots; reject viewport/calibration unknown for geometry-pixel rules, but permit source/render identity-level review where appropriate.
10. Independent reviewer examines the Subtitle and adjacent page, and checks that layout problem was resolved without new clipping or visual imbalance.
11. Run verified candidate diff/model preservation/answer regression and VQS remeasure. Return improved_not_accepted if unrelated findings remain; do not pretend one warning fix makes a poor report good.
12. Seal complete evidence and stage ledger. Do not promote original during tests; promotion-specific negative tests run only on synthetic/disposable trees.

If no legitimate, source-bound repair candidate can be synthesized because the known original fails unrelated Microsoft structural checks, first build a valid synthetic scaffold and run this same public flow there; **do not weaken the validator** or broaden the mutation into fixing unrelated original defects.

Second acceptance fixture: an unrelated domain/report with different visual types, filters, theme and model graph to show the framework is reusable and not Contoso-specific.

## 7. Priority, dependency and delegation

| Work order | Priority | Requires | Safe independent lane | Review deliverable |
| --- | --- | --- | --- | --- |
| W00 cross-OS vendor identity and CI root cause | P0 | PR #33 base | supply-chain/CI only | exact SHA + Linux/Windows proof |
| W01 real valid-PBIR fixture + test isolation | P0 | W00 or parallel isolated fixtures | tests/fixtures | portable and genuine-CLI matrices green |
| W02 normalized CLI/MCP request and preflight | P0 | W00 identity contract | contracts, CLI/MCP | parity tests and negative unauthorized calls |
| W03 split mutation / validation ports | P0 | W01/W02 | authoring adapter | no AUTO fixture nondeterminism |
| W04 metadata port and typed compiler | P1 | W02/W03 | authoring metadata/planning | authoring plan grounded in tested schema |
| W05 candidate seal and warnings policy | P0 | W03/W04 | pipeline/repair | validated complete candidate/source receipt |
| W06 single preview lifecycle and loaded model | P0 | W02/W05 | Windows runtime/MCP | disposable open→capture real evidence |
| W07 scope-aware question/answer regression | P1 | W06 | modeling/tests | same-scope evidence, no fake RLS equivalence |
| W08 perception/quality review completeness | P0 | W06/W07 | review/design | independent negative corpus and outcome |
| W09 public one-command real slice and second PBIP | P0 acceptance | W00–W08 | independent verifier | G0–G4 truth matrix |
| W10 DOCX + PBIPDocumenter WP-11/12 | later | W09 | separate doc/consumer | two PBIPs + DOCX acceptance |
| W11 docs/ledger/status reconciliation | continuous | exact evidence | docs/integrator | no stale implementation claims |

**Concurrency:** W00, W01 and request-contract specification of W02 can proceed in parallel, each in separate worktree, but only one agent edits shared vqs/pipeline.py, vqs/coordinator.py or Desktop PID at once. W04 metadata and W06 preview may research independently before shared interface freeze. Schema changes use a single integrator approval; no multiple Muse sessions writing one checkout.

Every work package must specify: base SHA, branch, editable/read-only paths, contracts frozen, tests to fail before the fix, exact expected negative result, authorized tools/privacy, acceptance oracle and independent reviewer. Host commands preferentially use Python; no PowerShell scripts unless Windows-native operation requires one. Editor does not self-verify its own successful release.

## 8. Risk register and mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Skill snapshot differs between OSes | critical | pinned Git blob/canonical bytes and two-OS hash CI |
| Preview tool chooses wrong Desktop report/PID | critical | pre/post instance inventory + exact candidate path/digest + one lease |
| A real CLI presence silently converts portable tests into failures | high | explicit validator injection, never ambient AUTO in tests |
| Microsoft skill update changes action safety or CLI contract | critical | proposal-only update, independent diff review, pinned compatibility test |
| A validated report has blank/stale answers | critical | Modeling MCP populated/refresh/scope oracle; mandatory G1 |
| A repair improves alignment but changes metrics/filter context | critical | queryState/semantic diff + same-question answer and categories |
| Unsupported filter/RLS is silently ignored | critical | versioned scope contract and fail-closed unsupported states |
| Image reviewer returns zero or self-approves | critical | required coverage, identity separation, authenticated release authority |
| Screenshot identity is mistaken for PBIR pixel calibration | high | separate render binding vs geometry-transform evidence |
| Unknown warning waived globally | high | diagnostic-specific policy, named owner/adjudicator and run receipt |
| Source/skill/CLI changes on resume | critical | immutable attestation and fresh candidate after drift |
| Unreviewed upstream docs act as executable instructions | high | vendor update PR + allowlisted reference mode + deterministic ports |
| An agent tries to fix all Contoso errors in original | critical | read-only original, single-disposable candidate, scoped plan |
| Dynamic skill adds unapproved Fabric publishing | critical | explicit management consent, no implicit publish/pack |
| Quality UX becomes an endless screenshot-loop | medium | fixed deterministic preconditions, bounded candidate iterations, stable whole-page+crop review |
| Doc and PBIPDocumenter integration masks incomplete PBI proof | high | separate feature gates, Power BI core acceptance first |

## 9. Definition of done / no-go criteria

**Engineering integration (Phase 0–3) may be called implemented** only when exact-head hosted portable and real-Microsoft-CLI CI pass, the skill and CLI are attested identically cross-platform, public CLI/MCP calls have equivalent authoring gates, candidate validator uses structured diagnostics, and all synthetic/real feature tests pass. This is NOT yet Desktop acceptance.

**Power BI core may be called practically usable** only when a normal operator invokes ONE public vqs run on a real disposable PBIP without hand-authored repair JSON and receives source-bound actionable findings, a safe improved candidate or honest refusal, Microsoft validation, a fresh bound Desktop render, scoped data-oracle answer evidence, independent review and explicit quality delta. A missing runtime/reviewer leaves higher scope BLOCKED.

**Release may be called accepted** only when the first-release G0–G6 matrix is independently checked on two unrelated PBIPs plus DOCX, privacy and rollback controls are proven, authority is authenticated, and the owner expressly approves the final promotion. A success-shaped PR comment or model reasoning is never sufficient.

**Immediate no-go:** Do not merge PR #31 or #33; do not update work-package verified states; do not run unattended changes to original Contoso; do not claim all Microsoft authoring/preview features are integrated merely because its skill is copied and a CLI executable is present.

## 10. Repository change index (final implementation map)

- Supply chain: .gitattributes, .agents/skills/powerbi-report-cli-upstream.json, .agents/skills/powerbi-report-cli/**, scripts/report_skill.py, .github/workflows/microsoft-report-skill-refresh.yml.
- Public API: vqs/cli.py, vqs/mcp/server.py, vqs/mcp/schemas.py, vqs/coordinator.py, vqs/config.py, versioned vqs/contracts/.
- Microsoft authoring: vqs/powerbi/author/mscli.py, adapter.py, new metadata/capabilities/diagnostics modules.
- Deterministic VQS core: vqs/pbir.py, vqs/powerbi/measure.py, vqs/design_rules.py, vqs/repair/synthesize.py, allowlist.py, execute.py and regress.py.
- Runtime/model: vqs/repair/runtime.py, vqs/capture.py, vqs/powerbi/desktop.py, modeling.py; add a PreviewPort only if existing runtime abstraction cannot be extended without duplication.
- Assurance: vqs/run_store.py, vqs/evidence.py, vqs/review/port.py, review bundle/adjudication, vqs/pipeline.py, tests and acceptance corpus.
- Documentation/agent routing: AGENTS.md, .agents/skills/vqs/SKILL.md, docs/MICROSOFT_REPORT_SKILL.md, docs/ARCHITECTURE.md, EXECUTION_ARCHITECTURE.md, CLI.md, JOURNEY.md, ACCEPTANCE_MATRIX.md, DEFAULT_STORIES_AND_AUTOMATED_DESIGN.md; roadmap/work_packages.json and STATUS.md.
- Consumer only after core: PBIPDocumenter VQS integration and DOCX module with separate readiness proofs.

## 11. Authority and useful links

- Issue #32 (Microsoft skill integration): https://github.com/analienx/visual-quality-system/issues/32
- Draft PR #33 (skill baseline): https://github.com/analienx/visual-quality-system/pull/33
- Issue #22 and PR #31 (Power BI core independent review): https://github.com/analienx/visual-quality-system/issues/22 and https://github.com/analienx/visual-quality-system/pull/31
- Microsoft official collection: https://github.com/microsoft/skills-for-fabric
- Microsoft current Power BI Report Skill overview: https://learn.microsoft.com/en-us/power-bi/developer/agentic/power-bi-report-skill-overview
- Microsoft report authoring metadata and preview reference: included, pinned under .agents/skills/powerbi-report-cli/references/authoring/
- Existing VQS release requirements: docs/ACCEPTANCE_MATRIX.md, docs/IMPLEMENTATION_PROGRAM.md, docs/LEDGER_AND_AGENT_PROTOCOL.md.
