# Contributing to VQS

## Setup

```bash
pip install -e ".[test]"
python -m pytest
python -m ruff check .
```

Python ≥3.11. The package has zero runtime dependencies; keep it
that way — external tools (pbir, Bridge, MCP) are detected via
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

## PR rules

- Follow [.github/pull_request_template.md](../.github/pull_request_template.md):
  evidence table, tests run *and* tests not run, hashes, negative
  controls. Doc-only PRs say so and never advance a capability to
  `verified`.
- One work package per PR; link the WP issue. Ledger transitions
  (`planned`→`review`→`verified`) need independent proof — the
  author is never the verifier.
- Never commit business data, real screenshots, `.abf` caches,
  credentials, `.vqs-runs/`, or machine-local paths. Fixtures must
  be synthetic (see `tests/powerbi/fixtures/`).
- Keep the offline core offline: no network calls from `vqs/`
  (Bridge/MCP/pip are out-of-process and optional).

## Style

Ruff (`line-length = 110`) is the whole style guide. Prefer small
typed modules with docstrings stating the contract, like
`vqs/powerbi/measure.py` and `vqs/powerbi/cycles.py`. Tests pin
exact extraction values, not vibes.
