# Changelog

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
