# Git ledger, agent orchestration and reporting protocol

**Program:** [#4](https://github.com/analienx/visual-quality-system/issues/4) · [Implementation stages](IMPLEMENTATION_PROGRAM.md) · [Machine ledger](../roadmap/work_packages.json) · [Acceptance matrix](ACCEPTANCE_MATRIX.md). This is a **protocol to implement**, not a claim that the `vqs status` or ledger validator CLI already exists. As of the planning snapshot, issue creation and docs alone constitute no verified implementation.

## 1. Four records; one source of evidence truth

1. **Git tracked plan** `roadmap/work_packages.json`: stable work-package IDs, versioned dependencies, scope, issue URLs/numbers, owner *lane*, tracked implementation state, required evidence types and target gates. Changes are reviewed like code; never mark a work package `verified` because an agent writes 'done'. `roadmap/STATUS.md` is a readable *snapshot*, not an independently maintained source of truth. Add `vqs plan validate` and `vqs status --json|--md` in WP-02; until it exists, updates require manual independent reconciliation.
2. **GitHub issues**: a bounded unit of work, conversation, blockers, decisions, human review, PR links, pointer to actual evidence. Epic #4 and existing #1–#3 express program goals; issues #5–#18 own executable slices. Issue close/open is workflow communication, never proof of test or a phase pass. GitHub-native sub-issue and dependency relationships should mirror the JSON DAG if an authorized CLI/API supports them, but their absence does not silently erase JSON prerequisites.
3. **Git branches and PRs**: source changes, independent reviews, CI results, exact merged commit SHAs, source and schema version. One issue/PR by default; small subagent commits allowed on separate feature branches. No direct agent writes to `main`; documentation bootstrap may have been placed there before this protocol, but executable work must follow it. `AGENTS.md` and `.github/pull_request_template.md` enforce handoff content. A green static CI job does not imply Desktop or Word renderer acceptance.
4. **Run evidence**: local private `runs/<id>/` outside Git, with append-only `events.jsonl`, `manifest.json`, status and CAS content hashes, tool/backend versions, source+data+view state, actual DAX answers, report/page screenshots or PDF/page PNGs, normalized findings, before/after diff, independent verifier identity and verdict. A public Git commit references **sanitized evidence manifest IDs**, not customer images or tokens. The raw evidence remains inspectable in an authorized local or private artifact store with expiry; public synthetic fixtures may be separately committed. If proof expires, a previous result is historical, not freshly verified.

**Precedence when records disagree:** raw signed/hashed run evidence plus pinned source and verifier > reviewed Git package ledger snapshot > GitHub issue/PR status > agent commentary. Do not retroactively relabel a failed run as green by editing a markdown table. Every new test attempt has a new evidence ID and terminal result.

## 2. Status is multidimensional, not a single progress percentage

A work-package **workflow state** is one of `planned`, `ready`, `active`, `review`, `blocked`, `failed`, `verified`, `deferred`. **Verification** is separately `not_run`, `partial`, `failed`, `blocked`, `verified`. **Capability** is independently `available`, `unavailable`, `unsupported`, `unknown`; **coverage** is `mandatory`, `optional`, `out_of_scope`; **artifact result** is `pass`, `fail`, `blocked`, `not_applicable`, `not_run`. The run may have a successful Python test suite while the Windows rendering gate is blocked; preserve both facts.

Transitions: `planned → ready` when all hard dependencies are verified and fixture/tool capability is known; `ready → active` on explicit issue claim+exclusive worktree lease; `active → review` when PR has tests and evidence; `review → verified` only after independent acceptance, merged exact commit and reference updates. Any nonterminal state may become `blocked` with reason + unblock action; a verified result invalidates to `ready`/`blocked` when its dependent contract, source, tool or environment changes. `deferred` requires explicit owner scope change to become planned. A failed test is **failed**, not blocked: `blocked` means evidence or capability cannot currently be obtained. `not_applicable` requires documented criterion and reason; it cannot waive mandatory source/data truth.

Record each package's `issue`, `lane`, `assigned_agent` (nullable), `depends_on`, `input_schema`, `output_schema`, `owned_paths`, `status`, `verification`, `pr`, `candidate_commit`, `verified_commit`, `evidence_uri`, `environment_digest`, `blocker`, `unblock_action`, `started_at`, `verified_at`, `latest_review` (nullable values where unknown). **Do not require dummy IDs or invented dates to fill these fields.** JSON schema enforcement and stale-status detection belong in WP-01/WP-02. `snapshot_utc` is the last ledger *edit time*, not proof that tool capability was rechecked then.

### Minimum per-part reporting view

For every component, show: `planned / implemented-unverified / verified / failed / blocked / deferred`, GitHub issue, exact PR/commit, tests **run vs passed vs failed vs skipped**, required capability and blocker, last real evidence ID and age, owner lane and next actionable dependency. Never report aggregate '80% done' by counting README sections or issue closures. If a roll-up is required, report **N/M packages independently verified**, **N mandatory gates blocked**, and verified phase ID; treat deferred Rayfin outside first-release denominator. A package with tests green but no real Desktop/Word evidence is partial, not verified.

## 3. Concrete GitHub organization and issue creation

Hierarchy: one program epic #4; historical epics #1 extraction, #2 story scope, #3 runner/web intent; the bounded issues #5–#18 map 1:1 to WP-00..WP-13. For issues created in the future, choose a 1–3 working-session deliverable (up to ~one reviewable PR), not a vague six-month epic. Create issue using `.github/ISSUE_TEMPLATE/work_package.yml`: stable WP id, platform, phase, owner lane, hard deps, owned paths, source/read/emit contracts, exact success and failure fixtures, measurable exit gate, risk/privacy/rollback and which agent independently verifies. Labels are optional decoration (`area:powerbi`, `area:word`, `kind:adapter`, `kind:rule`, `kind:acceptance`, `status:blocked`); never create them blindly unless repository labels exist. Native GitHub sub-issues can be added under #4, and native **blocked-by** relationships can mirror the ledger through an authorized CLI/API: [GitHub sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues), [dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies). The connector used for initial issue creation did **not** itself establish native parent/blocked-by relations; issue prose and the JSON dependency graph are authoritative until checked.

New issue protocol: (a) search existing issues and ledger for overlap; (b) assign new WP id only for truly new scope, otherwise split a too-large existing issue into bounded child tasks; (c) identify which schema version and prior verified package it consumes; (d) choose one agent owner + independent reviewer and separate editable path set; (e) write acceptance *before* code, include at least one failure/blocked case; (f) create issue, add it to JSON+status in same planning PR, check DAG acyclicity; (g) only then dispatch agent. If a decision changes architecture, create an ADR (`docs/adr/NNNN-short-title.md`) explaining context, options, evidence, choice, migration impact and revalidation; do not silently rewrite history.

GitHub Projects can provide a helpful filtered board/roadmap (`Phase`, `Surface`, `Agent`, `Status`, `Dependency`, `Evidence last verified`, `Blocked reason`). Do not treat it as a second independently editable ledger. If a Project is not created or accessible, issues and JSON still support the program. Project custom fields are supported per [GitHub documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects). Milestones may label release gates instead of arbitrary dates; prefer evidence-triggered milestones to speculative completion promises.

## 4. Agents and subagents: exact roles and path isolation

**Integrator/dispatcher** (one named accountable agent): reads latest `main`, issue DAG, test run and host availability; chooses ready work; freezes shared contracts first; assigns issue, branch, editable paths and lease; reconciles conflicts; never marks own code independently verified. **Contracts/core**, **Windows Desktop**, **Word renderer/OOXML**, **semantic/data**, **design rules**, **visual reviewer**, **Power BI repair**, **intent/oracles** are specialist owner lanes, not simultaneous collaborators in one checkout. **Independent verifier** must not author a change it approves; inspects actual raw screenshots/page PDFs and signed test outputs. The only exception is an owner-authorized self-approval of *code* under the conditions in [AGENTS.md](../AGENTS.md) (explicit owner authorization, a highest-effort code review with every finding fixed or answered, green CI on the final head); it is recorded as such, never as independent or human G2/G4 review, and never approves pixels or G6. **Security/privacy reviewer** inspects cloud transfer, sensitive fixture and subprocess risks on relevant PRs. **Release steward/user** controls final approval and promotion.

For each subagent, dispatcher issues an immutable `TaskEnvelope`: WP id, issue URL, base commit SHA, input schema version, owned paths, read-only paths, **no-go directories**, allowed tools and model/provider privacy class, precise fixture IDs, acceptance commands, max iterations/timeout, success evidence names, return format. Subagent reports `Claimed→WorktreeReady→Implemented→LocalTests→EvidenceCreated→PRDraft→ReviewRequested`; it does **not** claim global release. If path ownership conflicts, pause one subagent or split the task; contract file changes require integrator-mediated interface-change PR before downstream agents continue. No shared Python shell with arbitrary agent-constructed command execution; use adapter allowlists and command provenance.

Worktree pattern after latest verified base: `git worktree add ../vqs-wp06 -b work/wp06-design <base-sha>` and `git worktree list`; **one branch per issue**, no simultaneous agent edits in the same directory, no `git worktree remove -f` on a workspace containing uncommitted evidence. Windows Desktop and interactive Word must be scheduled via separate **exclusive resource leases** (`host=zephyrus`, `app=PowerBI`, `pid=...` or `app=Word`); only one agent may manipulate a given Desktop process. Agents can code pure source/rules in parallel while GUI tests serialize. Never assume file hash consistency across an unsaved Desktop session.

For cross-agent handoff, deliver a short status note in the issue: exact base/HEAD SHA, files touched, schema changed (yes/no), CLI invocation and versions, synthetic test assertions + failures/skips, local private evidence ID, opened PR, unresolved gaps, dependency requests. Another agent must be able to reproduce the result without guessing which Desktop window or DOCX revision was used.

## 5. Pull request pipeline and promotion permissions

An implementation PR targets `main` from `work/wpNN-purpose`, default **draft** while implementing. Required sections in `.github/pull_request_template.md`: linked WP issue, acceptance scope and exclusions, contracts, touched paths, reproducible commands, exact raw evidence identifiers, security/privacy, compatibility and rollback, independent reviewer. The reviewer re-runs pure unit/negative tests in a separate worktree. For GUI or renderer work, the verifier receives a sanitized manifest + a *separately authorized local evidence retrieval* and independently exercises the same candidate on the actual host. PR checks cover packaging/lint/type/schema/test fixtures; `Desktop gate = not run` stays visible even if hosted static checks are green. PR is eligible to merge only after issue's applicable mandatory acceptance and independent review. `Fixes #NN` can close issues automatically on merge, but the ledger may mark verified **only when evidence gate also passes**. PRs for research/docs cannot advance runtime feature statuses.

Suggested branch rules (apply only after admin/budget assessment): disallow direct agent pushes to `main`, require at least one independent human or delegated reviewer for critical merges, disallow unreviewed force pushes, check no bundled binary/private data, and require bounded local test reports. Never install a persistent self-hosted Actions runner on a personal Windows machine for a public repo. If GitHub Actions minutes are unavailable, retain explicit local test manifests and make CI state `not_run`; do not fake a green check or auto-merge. [GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use) details self-hosted risks.

## 6. Run evidence and source/data provenance

Example private layout (not committed):

```text
<private-run-root>/vqs/<run-uuid>/
  manifest.json                 # artifact, source/model/profile hashes, environment, capabilities
  events.jsonl                  # monotonically sequenced attempt events
  objects/<sha256>              # PNG/PDF/text/trace bytes + classified metadata
  facts/report.json             # normalized source + data facts
  evaluations/findings.json     # measured failures, perception, uncertainty, conflict
  plan/repair.json              # typed allowlisted operations and test oracle
  candidate/change.patch       # source diff and rollback recipe
  verify/result.json           # independent gates, same scope before/after, reviewer identity
```

Hash report source and semantic model definition separately; for actual data use scoped query snapshot, refresh identity, filters, locale/timezone and RLS role—not merely `cache.abf` existence. The Word evidence binds DOCX hash + render backend/version/fonts/page count and each page PNG hash, embedded report figure hash and linked PBIP source hash. A bitmap is not self-certifying: verify canvas completeness/viewport and figure identity. All claims include the tested `source_revision`, `environment_revision`, `contract_revision` and `view_state`. When any changes, revalidate affected gates; never recycle an old screenshot into a new pass.

Raw result redaction before issue comments and public PR: remove private paths/usernames, data values not synthetic, image content and auth headers, tokenized URLs, cookies, SQL/DAX with sensitive literal values. Public proof can be a non-sensitive manifest of synthetic fixture hashes and result categories; customer/private runs remain local or private authorized artifact store. Cloud-model submission is an explicit per-run opt-in, and every external tool/version/request is recorded.

## 7. Reporting cadence and escalation

At **start of every execution session** integrator reports current verified stage, ready work, active leases, last committed source/ledger snapshot and actual blockers. At **end of each PR or GUI verification attempt**, post concise `changed / tested / failed / blocked / next` status to the issue with source hash and evidence pointer; update JSON work-package state and generated STATUS view in a reviewable PR. At **phase boundary**, independent verifier signs an acceptance manifest; dispatcher posts a roll-up in #4 with N verified packages, uncovered mandatory gates and next ready issue. If a runtime bug changes a verdict (e.g., bad scale-2 crop), mark prior evidence invalid and reopen the affected package explicitly. A failed attempt is durable: do not erase it when a subsequent run succeeds.

Escalate immediately: wrong Desktop PID, unsaved source, suspicious credentials in a screenshot, Word renderer mismatch, unstable refresh, authoring plan changing a metric/question, unsupported filter navigation, duplicate visual ID, mixed artifact hashes, a reviewer evaluating their own edit without a recorded owner-authorized self-approval, or an agent seeking permission to merge/deploy. Such events stop the affected phase and document exact action needed; unrelated pure work may continue.

## 8. Sample status report format (illustrative, not a run result)

```text
Program: #4 | Ledger commit: <sha> | Phase: S2A
WP-03 #8: active; capability=available; verification=partial
Changed: desktop_adapter.py on work/wp03-desktop @ <sha>
Tested: 5-page capture attempt 1; tests 8 pass / 1 fail / 2 not_run
Failed: scale-2 crop missing right-side slicer; invalidates previous review
Blocked: independent re-review until recalibrated and source-bound PNGs exist
Evidence: private://vqs/<run-id>/manifest.json (authorized access only)
Next: fix crop, re-capture all pages, independent verifier; no release status advance
```

This protocol is meant to prevent exactly the failure mode of 'we iterated several times and still do not know what runs, what is broken, who changed the report, or whether the screenshots represent the current source.'