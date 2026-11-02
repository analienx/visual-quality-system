# Contributing to VQS

## Setup

```bash
pip install -e ".[test]"
python -m pytest
python -m ruff check .
```

Python ≥3.11. The package has zero runtime dependencies; keep it
that way — external tools (Microsoft Report Author CLI, Desktop Bridge, Modeling MCP) are detected via
`vqs doctor`, never imported.

## Gates (must pass before review)

```bash
python -m pytest -q
python -m ruff check .
```

CI runs the same on 3.11–3.13. A change that touches CLI behavior
needs a test proving the exit code and the output shape; see
`tests/test_validate_commands.py` and `tests/powerbi/` for the
pattern. New `vqs` commands also need a `docs/CLI.md` section and,
when they start a workflow, a `docs/USER_GUIDE.md` passage.

### Real Desktop behaviour (optional, Windows)

Questions that only real Power BI Desktop can answer (saved-state flags,
command-line casing, Bridge behaviour) go through
`.github/workflows/windows-desktop-probe.yml`. It installs Desktop, the
Bridge and the pinned authoring CLI on an **ephemeral** runner, opens a
*copy* of the fictional Contoso PBIP, and uploads only a JSON summary
(booleans and counts, never screenshots). It runs when
`scripts/windows_desktop_probe.py` or the workflow changes, or manually.
Record findings in
[V012_NATIVE_G_ACCEPTANCE.md](docs/V012_NATIVE_G_ACCEPTANCE.md); probe
output is engineering evidence, not G2/G4/G6 acceptance.

The main CI workflow also accepts manual dispatch, so a branch can use the
Windows leg without opening a PR.

## PR rules

- Follow [.github/pull_request_template.md](.github/pull_request_template.md):
  evidence table, tests run *and* tests not run, hashes, negative
  controls. Doc-only PRs say so and never advance a capability to
  `verified`.
- One work package per PR; link the WP issue. Ledger transitions
  (`planned`→`review`→`verified`) need independent proof — the
  author is never the verifier.
- Never commit business data, real customer screenshots, `.abf` caches,
  credentials, `.vqs-runs/`, or machine-local paths. Fixtures must
  be synthetic (see `tests/powerbi/fixtures/`). The only permitted README
  images are explicitly owner-approved, privacy-reviewed **downscaled
  previews of fictional demo reports**, documented with provenance and
  checksums in `docs/media/showcase/ASSET_PROVENANCE.md`. They are not
  source-bound acceptance evidence; full native captures remain private.
- Keep the offline core offline: no network calls from `vqs/`
  (Bridge/MCP/pip are out-of-process and optional).

## Style

Ruff (`line-length = 110`) is the whole style guide. Prefer small
typed modules with docstrings stating the contract, like
`vqs/powerbi/measure.py` and `vqs/powerbi/cycles.py`. Tests pin
exact extraction values, not vibes.
