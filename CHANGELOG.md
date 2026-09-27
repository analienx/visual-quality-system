# Changelog

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
