# VQS command reference (pre-alpha)

Install once (editable): `pip install -e .` — this exposes the `vqs`
entry point. Every command below was executed against synthetic fixtures
during development; see `tests/test_pipeline.py` and
`tests/test_validate_commands.py` for runnable shapes.

Exit codes: `0` pass, `1` demonstrated violation, `2` blocked
(environment, capability, or input prevents a verdict). Nothing here
renders pixels, queries live data, or approves a
release — those need leased backends plus owner promotion.
Isolated static repair execution lives in the six-tool workflow
(see QUICKSTART.md); the original is never modified.

## vqs status

Read-only delivery-ledger snapshot; never modifies the ledger.

```console
vqs status
vqs status --format json --ledger roadmap/work_packages.json
```

## vqs inventory

Read a PBIR enhanced-format `*.Report` folder: pages, visuals, field
bindings, source hash. Read-only; not design approval.

```console
vqs inventory path/to/Example.Report
```

## vqs measure

Emit check-ready facts for a PBIR `*.Report` folder: text contrast,
format-declaration cohorts, a per-page insight inventory (which visual
delivers which measures/dimensions), duplicate-insight grain readings,
and decomposition-tree/map best-practice bindings, cross-page
duplication grain, layout geometry, and page bounds — plus metric units
and model bindings when `--model` points at a `*.SemanticModel`
definition folder. Read-only; anything the sources cannot prove is
omitted (per-page palette assignments stay absent until explicit
per-visual series colors are measured). Feed the output to `vqs check`.

```console
vqs measure path/to/Example.Report
vqs measure path/to/Example.Report --model path/to/Example.SemanticModel/definition --out facts.json
```

## vqs cycles

Static acyclicity gate for a `*.SemanticModel` definition folder:
builds the DAX measure/column reference graph and the M
query/`let`-binding graphs, and reports cycles. Exit 0 when acyclic,
1 when a cycle is found, 2 when the folder is unreadable. Pure static
analysis; the live-engine confirmation stays a Modeling MCP step.

```console
vqs cycles path/to/Example.SemanticModel/definition
```

## vqs capture

Capture every report page through the Desktop Bridge and write
`capture-manifest.json` (source hash, page images, file hashes) for
`vqs request-review`. Selects the Desktop instance by exact PID +
report path; unsaved changes, a wrong report, or several instances
without `--pid` block with the reason. Needs Windows, Desktop, and
the report open — otherwise use `vqs doctor` to see what is missing.

```console
vqs capture path/to/Example.Report path/to/renders
vqs capture path/to/Example.Report path/to/renders --pid 1234 --scale 2
```

## vqs bundle

Portable review evidence for cross-machine or cross-agent handoff: `pack`
assembles renders + manifest + inventory + header after re-validating the
evidence; `verify` re-hashes everything and rejects tampered, incomplete,
or stale bundles (`--report` also binds to a live report folder);
`unpack` copies and verifies. Bundles may contain business-data pixels:
keep them private, never commit them.

```console
vqs bundle pack path/to/Example.Report path/to/renders path/to/bundle --fixer-id agent-a
vqs bundle verify path/to/bundle --report path/to/Example.Report
vqs bundle unpack path/to/bundle path/to/copy
```

## vqs doctor

Report which external Power BI tools are present (Microsoft-guided
report author CLI, Desktop Bridge, Modeling MCP, running Desktop).
Read-only and informational: it installs nothing, and always exits
0. VQS has no ADOMD dependency.

```console
vqs doctor
```

## vqs request-review

Build a review template from a report plus a renders directory.
`capture-manifest.json` must carry three keys: `source_sha256` equal to
the report digest (stale sources block), `page_images` mapping every
PBIR page id to a unique PNG filename, and `files` mapping every PNG
to its sha256 (unbound renders block). PNGs must be at least 450px on
each side.

```console
vqs request-review path/to/Example.Report path/to/renders --fixer-id agent-a
```

Minimal `capture-manifest.json`:

```json
{
  "source_sha256": "<digest from vqs inventory>",
  "page_images": {"p1": "p1.png"},
  "files": {"p1.png": "<sha256 of p1.png>"}
}
```

## vqs check

Run a measured-facts JSON document to a sealed verdict under
`.vqs-runs/<run-id>/` (gitignored): `manifest.json` carries the terminal
status plus a `verdict_sha256` digest, with `event_count` matching the
event log. Facts sections: `rules` (the thirteen design rules),
`oracles` (question answerability, scope matching), `documents` (DOCX
well-formedness — structure only, never pagination), `models` (TMDL
inventory, binding resolution, optional freshness and RLS role).
Unknowns block; malformed entries block; duplicate `--run-id` is refused.

```console
vqs check facts.json
vqs check facts.json --run-root .vqs-runs --run-id check-01
```

Minimal passing `facts.json`:

```json
{
  "rules": {
    "typography.text_contrast": {"foreground": "#000000", "background": "#ffffff"}
  },
  "oracles": [{"oracle_scope": "a", "run_scope": "a"}]
}
```

## vqs validate-plan

Validate a repair plan *before* any execution. Any allowlist issue fails:
unknown or shell operations, unapproved model/DAX/RLS touches, writes
outside the disposable candidate root or to the original, dropped visual
ids, missing rollback.

```console
vqs validate-plan plan.json --original /orig/report --candidate-root /cand
vqs validate-plan plan.json --original /orig/report --candidate-root /cand --approve-change CHG-7
```

## vqs adjudicate-bundle

Adjudicate a review bundle on static checks only: reviewer separation,
image-capability presence, full-canvas calibration, per-page source
binding (stale images fail), observation completeness. Pixel judgment
itself needs a capable image reviewer plus real renders.
`--transport-bundle` (verified first) or `--report` (live inventory)
binds whole-source coverage; without either, coverage is unbound
and blocked. Static adjudication never passes: the ceiling is
`static_conformance: pass` with verdict `blocked` and rule
`image_review_required`.

```console
vqs adjudicate-bundle bundle.json --report path/to/Example.Report
vqs adjudicate-bundle bundle.json --transport-bundle path/to/bundle --report path/to/Example.Report --run-id review-01
```

## vqs inspect

Measure check-ready facts for a report into an envelope (read-only);
same engine as the `vqs_inspect` tool. Blocking coverage gaps
(unreadable sources) block instead of guessing.

```console
vqs inspect path/to/Example.Report --model path/to/Example.SemanticModel/definition --out inspect.json
```

## vqs repair

Validate a repair plan, materialize a disposable candidate, apply
typed visual edits only (the executor cannot touch model bytes),
and validate the candidate. Model/DAX/RLS targets fail closed
without an owner approval id. `--authoring-backend` selects the
validation route: `auto` (default) probes the Microsoft-guided
`powerbi-report-author` executable (documented distribution channel
`@microsoft/powerbi-report-authoring-cli`) and records any fallback,
`microsoft`
never falls back silently, `direct` is the explicit typed-writer
fallback. Microsoft rejection fails; warnings block unless
`--authoring-allow-warnings` is given; missing, timed-out, or
errored validation blocks. The run seals `authoring.json` and
carries a top-level `authoring` block.

```console
vqs repair plan.json --original path/to/Example.Report --candidate-root path/to/candidate.Report --run-root runs --run-id repair-1
vqs repair plan.json --original path/to/Example.Report --candidate-root path/to/candidate.Report --run-root runs --run-id repair-2 --authoring-backend direct
```
