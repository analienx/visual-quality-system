# WP-00 baseline — environment, tools, and fixture inventory

**Program:** [#4](https://github.com/analienx/visual-quality-system/issues/4).
**Work package:** WP-00, [issue #5](https://github.com/analienx/visual-quality-system/issues/5).
**Kind:** baseline audit. **Status:** observed. No work package is marked verified by this baseline.
**Coordinator branch:** `work/wp00-agent-first-coordinator` (isolated worktree; `main` untouched).

**Probed:** 2026-10-03. **Base:** `main` at `5fda4e56bf7fa3d229e168db42508b90145b781e`
(merge PR #23; coordinator worktree clean at same SHA).
**Host (local observations, non-authoritative):** Windows 10.0.26200. **Python:** 3.12.10.
**Node:** 24.19.0. **npm:** 11.17.0. **git:** 2.55.0.windows.3. **gh:** 2.100.0.

## Authoritative evidence (GitHub-hosted CI)

Public-repo contract: local runs are development observations only. Acceptance evidence
comes from GitHub-hosted Actions at the exact candidate SHA.

- CI run **36322211286** at base `5fda4e5` (push to `main`, 2026-09-27): **success**,
  all 3 matrix jobs green.
- `python -m pytest -q`: **212 passed** on each of Python 3.11, 3.12, 3.13 (0 failed).
- `python -m ruff check .`: **All checks passed** on all 3 jobs.
- `tests/test_roadmap_report.py` (ledger DAG validity, reporter counts) passed inside that
  suite. Direct CLI runs of `scripts/roadmap_report.py --check` / `--format markdown` are
  **not_run** on hosted CI (the workflow does not invoke them); by code inspection of
  `vqs/ledger.py`, `next_runnable == ["WP-00"]` and independently verified = **0/14**
  (13 WP-00..WP-12 plus WP-19; WP-13 deferred). The #5 planning comment predates WP-19,
  hence its `0/13` figure.
- Portable CI does **not** certify Desktop rendering, live model data, Word pagination,
  or any runtime gate. Those remain `not_run`/`blocked` (see matrix).

## Capability matrix

| Tool / capability | State | Evidence basis |
| --- | --- | --- |
| Pure-Python VQS core (`vqs inventory/measure/cycles/check/...`, ledger validator) | available | Hosted CI 212 passed + ruff clean at base |
| Packaged install (`pip install ".[test]"`) | available | CI installs then tests on 3 Pythons |
| `vqs status` / `scripts/roadmap_report.py` ledger logic | available | CI via `test_roadmap_report.py`; direct CLI not_run on hosted |
| Power BI Desktop binary | present (local obs.), automation unproven | `PBIDesktop.exe` present; a Desktop process is running but must not be touched without explicit user authorization; no open/save-state verification performed |
| Desktop Bridge CLI (`powerbi-desktop`) | present 1.0.0 (local obs.), live use unproven | Version probe only; no capture performed |
| `pbir` CLI | present 0.9.32 (local obs.) | Version probe only |
| Modeling MCP (`powerbi-modeling-mcp` 0.5.0-beta.16) | present (local obs.), live connectivity unproven | npm listing only; no model connection opened |
| Semantic-model query/refresh provider | blocked (none authorized) | No DAX/refresh run; `cache.abf` must never enter the repo |
| Interactive Word (`WINWORD.EXE` 16.0.20430.20118) | present (local obs.), pagination runs not_run | File-version probe only; needs exclusive lease per #9 |
| Headless pagination backend (`soffice`/LibreOffice) | blocked (missing) | Not on PATH |
| `python-docx`/`lxml` OOXML inspection | unknown (was blocked, needs re-probe) | `lxml` now imports locally, reversing the 2026-09-24 App-Control observation; no OOXML run performed |
| GitHub Actions CI for this repo | available | `.github/workflows/ci.yml`, green at HEAD |

Missing capability yields `blocked`, never a claim of availability.

## Source inventory at base

- **Package:** 26 modules under `vqs/` — `acceptance`, `capture`, `cli`, `design_rules`,
  `doctor`, `evidence`, `ledger`, `pbir`, `pipeline`, `policy`, `run_store`,
  `adapters/ports`, `contracts/{types,validate}`, `data/tmdl`, `document/{inspect,render}`,
  `powerbi/{cycles,desktop,insights,measure}`, `repair/allowlist`,
  `review/{adjudicate,bundle}`, `stories/oracles`. Python floor `>=3.11`.
- **CLI (11 commands):** `inventory`, `measure`, `cycles`, `capture`, `bundle`
  (`pack`/`verify`/`unpack`), `doctor`, `request-review`, `status`, `check`,
  `validate-plan`, `adjudicate-bundle`. Exits 0/1/2 = pass/fail/blocked.
- **Tests:** 27 modules — 22 under `tests/`, 4 under `tests/powerbi/`
  (`test_cycles`, `test_insights`, `test_measure`, `test_measure_cli`), 1 e2e
  (`tests/e2e/test_program_ledger_e2e.py`). Committed fixtures: `mini_report`,
  `mini_model`, `cycle_model`, `clean_model`, `insight_report` (all synthetic).
  Tests generate PNGs in `tmp_path` via stdlib; no binary/customer data committed.
- **Scripts:** `roadmap_report.py` (read-only ledger validator/reporter),
  `pbip_acceptance.py`, `smoke.py`.
- **Docs:** program, acceptance matrix, ledger/agent protocol, architecture, CLI/user
  guides, plus this baseline. `.github/`: PR template, work-package issue template, CI.
- **Merged history:** PRs #20 (review hardening + insights), #21 (doctor/acceptance),
  #23 (cross-page duplication/layout/BPA) all merged with green CI.
- **Sensitive scan:** no `*.abf`, `*.png`, `*.pdf`, credentials, or caches in the tree.

## Prior-work inventory (read-only; preserved untouched)

- Old checkout `visual-quality-system-review22` at `e4778fa`
  (`work/code-review-hardening-22`, based at `7154f01` = PR #21) holds the
  in-progress #22 remediation: commit `0bd1303` (acceptance/capture/contracts/
  pipeline/adjudication hardening + tests) and commit `e4778fa` (reviewer authority,
  new `vqs/authoring/` ports, run-store rework), plus uncommitted design-rule/insight
  changes. Three paths are unmerged against PR #23 (`README.md`,
  `scripts/pbip_acceptance.py`, `tests/test_pbip_acceptance.py`).
- Supervisor #22 comments record outstanding P0 repros against that WIP (fabricated
  acceptance incl. self-consistent fake evidence, `subjects:null` crash, terminal/seal
  invariant breaks) and a 244-passed/21-failed local dev run with interface mismatches.
- Disposition: port only understood, contract-derived slices into new owned lanes;
  never reset/stash/commit/resolve/cherry-pick the old checkout. Its unmerged state is
  not evidence of anything except work in progress.

## Fixture inventory, privacy, and definitions

- Public tree holds synthetic fixtures only (see above); real run evidence stays under
  ignored private `runs/`. No customer report/cache/image to public Git, ever.
- **Synthetic fixture A (retail):** `agent_first_retail` — PBIP with sales measures
  (revenue, units, distinct customers), 5-brand comparison bar with scroll, monthly
  trend line, product table, date slicer, one seeded axis-format defect; TMDL model
  with a multiline measure and one calculated column.
- **Synthetic fixture B (operations):** `agent_first_ops` — unrelated schema/layout/
  domain (warehouse throughput: lines/hour, error rate, shift dimension), heat-map
  table, KPI cards, different theme; seeded contrast defect on one card.
- **DOCX fixture plan (sanitized):** 3+ page synthetic document with headings, caption,
  split table, section break, embedded synthetic chart; plus a deliberate orphan-heading
  variant. Renderer/backend recorded per run; Word-exact claims stay blocked until a
  supported validation path exists.

## Task / path / dependency matrix (agent-first lanes)

| Lane / issue | Owned source paths | Depends on |
| --- | --- | --- |
| Baseline WP-00 #5 (this doc) | `docs/BASELINE.md`, `roadmap/` | — |
| Trust #22 / WP-01 #6 | `vqs/contracts/`, `vqs/policy.py`, `vqs/acceptance.py`, `vqs/run_store.py`, `vqs/ledger.py`, `vqs/evidence.py`, `vqs/review/`, `scripts/pbip_acceptance.py` + owned tests/fixtures | WP-00 |
| Facts WP-01/WP-05/WP-19 | `vqs/pbir.py`, `vqs/data/`, `vqs/powerbi/{measure,cycles,insights}.py`, `vqs/design_rules.py` + owned tests/fixtures | agreed trust contract |
| CLI/MCP WP-02/WP-12 | `vqs/cli.py`, `vqs/pipeline.py`, `vqs/__init__.py`, `vqs/mcp/` (new), `vqs/config.py`, `pyproject.toml` + owned tests/fixtures | trust contract |
| Runtime WP-03/WP-05/WP-07 | `vqs/adapters/`, `vqs/capture.py`, `vqs/doctor.py`, `vqs/powerbi/desktop.py`, `vqs/powerbi/modeling.py` (new) + owned tests/fixtures | trust + facts contracts |
| Repair WP-06/WP-09/WP-10 | `vqs/repair/`, `vqs/stories/oracles.py` + owned tests/fixtures | trust + facts |
| Docs/integration WP-11/WP-12 | `docs/`, `README.md`, `CHANGELOG.md`, `.agents/skills/vqs/`, `roadmap/`, templates, `ci.yml` as needed | all candidate lanes |

One writer per lane/checkout; shared-contract changes need an interface proposal plus an
independent read-only contract review before implementation. Fabric Apps #18 stays deferred.

## Risks and rollback

- Single shared Windows GUI host: Desktop/Word runs serialize on one exclusive lease;
  pure source/rules work proceeds in parallel in separate worktrees.
- A PBIDesktop process is currently running on this host; no lane may drive, capture,
  or kill it without explicit per-run user authorization.
- Prior #22 WIP overlaps PR #23 files; naive porting reintroduces conflicts or the
  supervisor's P0 repros. Mitigation: re-derive from contracts, add the repros as
  negative regressions first.
- Rollback: this baseline touches only `docs/BASELINE.md` and `roadmap/` on
  `work/wp00-agent-first-coordinator`. No `main` writes, no production edits, no
  migration. Delete the branch to roll back.

## Next actions

1. Independent verifier reproduces the pinned CI evidence (run 36322211286) and reviews
   this inventory; #6 contracts freeze before parallel #7/#8/#9-style lanes.
2. Final lane: consider extending hosted CI with `roadmap_report.py --check` so the
   #5 direct-CLI runs become authoritative instead of not_run.
3. Trust lane (#22): add all four supervisor repros as negative regressions before
   claiming any P0 tranche complete; honest WP-19 ledger representation per #22 P1-15.
