# VQS user guide

End-to-end workflows with copy-paste commands. Command details live in
[CLI.md](CLI.md); gates and test IDs in
[ACCEPTANCE_MATRIX.md](ACCEPTANCE_MATRIX.md).

## Setup

```bash
pip install -e ".[test]"
vqs doctor     # presence of pbir, Bridge, MCP, Desktop; never installs
python -m pytest
```

External tools are optional and detected, never required to install:
`vqs measure`, `vqs cycles`, and `vqs check` run on sources alone.
Screenshots need Windows + Power BI Desktop + the
[Desktop Bridge](https://www.npmjs.com/package/@microsoft/powerbi-desktop-bridge-cli);
live model work needs the
[Modeling MCP](https://github.com/microsoft/powerbi-modeling-mcp).

## Workflow 1: static review (no Desktop)

Measure facts from sources, run them to a sealed verdict, and gate
model cycles — all offline:

```bash
vqs measure path/to/Example.Report --model path/to/Example.SemanticModel/definition --out facts.json
vqs check facts.json --run-id review-01
vqs cycles path/to/Example.SemanticModel/definition
```

Exits: `0` pass/acyclic, `1` demonstrated violation (or a cycle),
`2` blocked (unreadable input, unknowns). `vqs check` seals runs
under `.vqs-runs/<run-id>/` (gitignored): the manifest carries the
terminal status plus a `verdict_sha256` digest.

Try it on the shipped fixtures (no PBIP needed):

```bash
vqs measure tests/powerbi/fixtures/mini_report --model tests/powerbi/fixtures/mini_model/definition
vqs cycles tests/powerbi/fixtures/cycle_model   # exit 1: known loops, see tests/powerbi/test_cycles.py
```

Or run the whole acceptance in one step:

```bash
python scripts/pbip_acceptance.py path/to/Example.Report --model path/to/Example.SemanticModel/definition
```

## Workflow 2: screenshot review (Desktop)

Capture every page through the Bridge, bound to the exact source
revision and Desktop instance:

```bash
vqs capture path/to/Example.Report path/to/renders
vqs request-review path/to/Example.Report path/to/renders --fixer-id you > template.json
```

`vqs capture` refuses to guess: several Desktop instances without
`--pid`, a wrong report, unsaved changes, or a missing page PNG all
block with the reason. Renders land next to
`capture-manifest.json` (source hash, page images, file hashes).
`request-review` re-verifies the binding and emits an **unapproved**
observation template — it never approves anything itself.

The reviewer (a human or an image-capable agent looking at real
pixels) then completes the template: one verdict + reason (≥32 chars)
per criterion per page, located failures (normalized region box,
visual id, severity, proposed fix), plus the `image_capability` and
`calibration` blocks. Only then:

```bash
vqs adjudicate-bundle template.json --run-id adj-01
```

Adjudication is static and strict: unfilled observations, missing
capability/calibration, self-review, or stale images block or fail.
A bare template can never pass — that is the point.

## Workflow 3: remote handoff (fixer → independent reviewer)

Pack evidence on the fixer's machine, verify it on the reviewer's:

```bash
# fixer
vqs bundle pack path/to/Example.Report path/to/renders path/to/bundle --fixer-id agent-a
# reviewer (any machine with the report, or none)
vqs bundle verify path/to/bundle --report path/to/Example.Report
vqs bundle unpack path/to/bundle path/to/copy
```

`verify` re-hashes every render, checks manifest/header/inventory
agreement, and `--report` rejects bundles stale against the live
source. Tampered or partial bundles fail closed.

## Verdict semantics

| Verdict | Meaning | Exit |
| --- | --- | --- |
| `pass` | Directly relevant current evidence satisfies the gate | 0 |
| `fail` | Demonstrated violation (bad pixels, cycle, broken binding) | 1 |
| `blocked` | Environment, capability, or data prevents a verdict | 2 |

`blocked` is never a soft pass: mandatory gates must resolve it
before acceptance (matrix §1). `unknown` is a diagnosis state, not a
verdict. A static unit-test pass never satisfies a render gate.

## Privacy rules

Renders may show business data. Keep renders, bundles, `.abf`
caches, credentials, and `.vqs-runs/` out of public git (all
gitignored by default). Never attach real screenshots to public
issues; use hashes, page/visual IDs, and finding descriptions.
Cloud submission of data or images needs explicit owner
authorization, recorded in the run.
