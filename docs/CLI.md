# VQS command reference - versioned CLI/MCP

**Component boundary:** The CLI below is the primary **Power BI** VQS
interface. Word/DOCX native steps remain in separately invoked
`scripts/word_p*.py` and optional `.[word-pages]` dependency
group. The Python release validator `vqs.acceptance.run_acceptance`
supports explicit `release_scope=powerbi-core|word-docx|combined`;
this field is **not** a documented CLI flag. See
[architecture](ARCHITECTURE.md) and [acceptance](ACCEPTANCE_MATRIX.md).

Install the [v0.1.1 release wheel](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.1) with `pip install <wheel-file>` (use `pip install -e .` only for development) — this exposes the `vqs`
entry point. Every command below was executed against synthetic fixtures
during development; see `tests/test_pipeline.py` and
`tests/test_validate_commands.py` for runnable shapes.

Exit codes: `0` pass, `1` demonstrated violation, `2` blocked
(environment, capability, or input prevents a verdict). Nothing here
renders pixels, queries live data, or approves a
release — those need leased backends plus owner promotion.
Start with `vqs run` for the whole sequence in one sealed run
(`review`, `propose`, or `repair` modes stop earlier); the commands
below expose each stage separately for debugging (expert interface).
`vqs --version` prints the package version and `python -m vqs`
works anywhere the installed `vqs` does.


## Simplified fixing (v0.1.1 supported scope)

For a standalone .pbip file, one unambiguous report root, or a `*.Report`
folder, the new `vqs fix` command resolves the local model where possible,
runs the **existing** coordinator in static repair mode, and returns a compact
result while keeping all sealed evidence on disk. It never overwrites the original:

```console
vqs doctor
vqs fix "C:/Reports/Sales.pbip"
vqs fix "C:/Reports/Sales.pbip" --run-root "C:/private/vqs-runs"
vqs fix "C:/Reports/Sales.pbip" --report-out "C:/private/full-result.json"
```

By default, `vqs fix` writes private evidence under
`%LOCALAPPDATA%/VQS/runs` on Windows, or
`${XDG_STATE_HOME:-~/.local/state}/vqs/runs` on Unix.
An explicit `--run-root` overrides this. Run directories are never
automatically published or promoted.

Use `vqs run ... --summary` for a compact output with explicit workflow
flags. `vqs run` without `--summary` preserves the expert JSON contract.
Exit codes remain `0` pass, `1` fail and `2` blocked. A no-safe-candidate
decision is correctly blocked, **not** proof of automatic repair success.

The clean wheel embeds the previously approved, SHA-attested Microsoft authoring
skill. `vqs doctor` checks that skill and the pinned CLI together before an
expensive repair attempt; it does not install external tools or weaken validation.
Missing/nonmatching prerequisites must be corrected rather than silently bypassed.

For recent MCP clients, `vqs_run` supplies a compact typed tool response, and
`vqs_theme` supports presets, inspect, preview, apply to an explicit separate
candidate, and audit. The original `2024-11-05` handshake and full JSON tool
response remain supported for existing consumers.

## Answering owner decisions (`--decisions`)

*Step-by-step guide with real output, answers schema and troubleshooting:
[OWNER_DECISIONS_AND_PR_GATE.md](OWNER_DECISIONS_AND_PR_GATE.md).*

When a fix is blocked because the right answer is a design choice (which
font size a cohort should use, which of two overlapping visuals moves, or
whether a repeated breakdown is intentional), VQS never guesses. Every such
finding comes back as an **answerable question** with a stable
`decision_id` and concrete options:

* `size:<literal>` / `move:<visual>:<axis>:<value>`: pre-compiled,
  precondition-checked edits applied **only to the disposable candidate**;
* `accept`: keep the current design as intentional. This is a recorded
  owner waiver, **never** a pass.

```console
vqs fix "C:/Reports/Sales.pbip" --run-id sales-1          # blocked: N questions
vqs decisions template --run-id sales-1 --out answers.json
# owner fills "owner" and one "option" per question (empty rows are skipped)
vqs fix "C:/Reports/Sales.pbip" --run-id sales-2 --decisions answers.json
```

`answers.json` (`vqs.decision-answers/1`) pins the reviewed
`source_sha256`. A changed report, an unknown decision or option, or two
options writing different values to the same property **block** before
anything is applied. Applied options run through the normal repair, exact-diff
verification and remeasure. When every remaining failing check is fully
waived, the outcome is `accepted_with_waivers`; `quality_after` still reports
the literal rule result. Missing evidence (`blocked`/`unsupported` coverage,
oracle or model findings) can never be waived. MCP clients pass the same
document as `vqs_run` `decisions=`; agents must show the options to the owner
rather than choose them.

Answers authorize a disposable candidate and scoped waivers only. They are
not G2/G4 review, G6 promotion or release approval, and nothing promotes the
original.

## Live answer regression (v0.2 candidate)

`vqs run --live-answers` currently records the answer baseline as **blocked**
without opening the modeling connection. Existing answer artifacts do not
independently bind the queried model and Desktop PID to the reviewed source;
equal rows or a reachable server are insufficient. Legacy baselines are not
reused. [Issue #131](https://github.com/analienx/visual-quality-system/issues/131)
tracks the reviewed evidence contract needed to restore this capability.

Candidate reload and recapture also require Desktop readiness and permission;
recapture uses the PID from the latest successful candidate reload. A blocked
reload prevents recapture and live answer regression.

## Rendered before/after review (`vqs compare-renders`)

Compares source-bound page captures at pixel level and reports whether changed
pixels fall inside visual rectangles whose PBIR changed. The per-page findings
are observations to review; they do not by themselves establish whether a
repair introduced a regression.

```console
vqs capture "base/Sales.pbip"      base-renders  --live-data
vqs capture "cand/Sales.pbip"      cand-renders  --live-data
vqs compare-renders base-renders cand-renders \
  --baseline-report base/Sales.pbip --candidate-report cand/Sales.pbip
```

**Current status: the overall result is always `blocked` (exit 2).** The
existing capture readiness probe counts rows in one table; equal row counts do
not prove equal answers, filters, roles or interaction states. A stronger data
evidence interface needs independent review before a data-bound pass or fail
can be emitted. [Interface request #131](https://github.com/analienx/visual-quality-system/issues/131)
tracks that work. Per page the result carries the changed-pixel count and fraction,
the changed bounding box, the visuals the candidate edited, the rectangles the
difference was attributed to, and an `unexplained_box` for pixels outside the
edited rectangles. Page `pass` and `fail` refer only to this pixel-location
test; neither overrides the overall blocked result.

**It blocks rather than guesses.** A comparison is refused when either capture
declares `data_population: unproven` (a cache-less report renders `(Blank)`
everywhere and still captures, so comparing two blank pages proves nothing),
when readiness probe results differ or one capture was not populated, when a
capture is bound to a different source revision, when a captured PNG no longer
matches its manifest hash, when either capture omits or adds report pages, when
the source page canvases or capture scale differ, or when a canvas cannot be
measured. Mixed-size pages are measured independently against their source
dimensions. Matching
readiness hashes are not proof that the captures saw the same data.

`--margin N` dilates each edited visual's rectangle by N canvas pixels before
attribution. It is a **declared tolerance, not a measurement**, so it defaults
to `0` and the value used is recorded in the result. Raise it only with real
render evidence that Desktop draws a border or shadow outside a visual's
declared rectangle.

The result is not design approval or independent G2/G4 review or owner G6.

## Pull-request gate (`vqs gate`)

`vqs gate` reviews a head and a baseline revision with the same static engine
and fails **only on findings the change introduces**. Comparison uses
finding *subjects* (check + page/visual/cohort/pair), so pre-existing issues
never block unrelated pull requests.

```console
vqs gate head/Sales.pbip --baseline base/Sales.pbip --sarif vqs.sarif --github
vqs gate Sales.pbip --emit-baseline vqs-baseline.json      # store a baseline
vqs gate Sales.pbip --baseline vqs-baseline.json --decisions answers.json
```

Exit codes: `0` nothing new, `1` new findings, `2` blocked (unreadable head or
baseline). Capturing a baseline is its own operation, so
`--emit-baseline` *without* `--baseline` exits `0` once the file is written
and reports `baseline_written`; it does not report every existing finding as
new. `--sarif` writes SARIF 2.1.0 with `baselineState` new/unchanged for
GitHub code scanning; `--github` prints `::error` annotations. A **blocked**
gate still writes both, as a single `vqs.gate.blocked` error naming the
reason, so an unprovable revision is annotated rather than silent. `accept`
answers bound to the head revision excuse only their own subjects. Answers
bound to the reviewed base revision (the usual flow: answer on the original,
gate the candidate) excuse only subjects the base already had, never a new
one; a stored JSON baseline accepts no base-bound answers. Anything else is
counted in `unmatched_waivers`.

### Copyable GitHub Actions workflow

Copy [the consumer workflow](../examples/ci/powerbi-quality.yml) to
`.github/workflows/powerbi-quality.yml` in the report repository. Set
`VQS_REVISION` to a **reviewed full 40-character commit** that includes
`vqs gate`, and set `HEAD_REPORT` and `BASE_REPORT` to the report's paths
relative to each checkout. For a rename, use the appropriate different paths.
The workflow checks out the exact head and base SHAs from the pull-request
event, pins its actions, Python and build tools, and installs that VQS source
revision directly from GitHub. It requires Git and access to the VQS source.
The runner image and package index remain external inputs; a locked mirror or
verified release wheel is needed if your environment requires stronger supply
chain reproducibility.

The current published release is v0.1.1; the gate is post-v0.1.1 source and
must not be assumed to exist in that release. VQS is not currently published
as a PyPI distribution. Select and review the source commit yourself, or use a
future published release artifact after verifying its digest and capabilities.

The job deliberately uses `pull_request`, read-only repository permissions,
and no secrets or automatic SARIF upload. It writes SARIF to the runner's
temporary directory and emits GitHub annotations; retain or upload the SARIF
only after reviewing your repository's permissions and data policy. CI sends
the report source to the runner and may expose names and findings in logs and
annotations, so use it only where that processing is authorized. Forked PRs
have restricted tokens and must not be given privileged secrets to make this
example work.

The gate exits `0` when it finds no new static subjects, `1` for new findings,
and `2` when it cannot compare. A missing report, a newly added report without
a baseline, or an incorrect rename path must be handled explicitly; do not
turn exit `2` into a pass. If you choose a stored baseline instead, review its
origin and the different waiver semantics described above.

The gate is static source evidence; a green gate is not native Desktop, G2/G4
or G6 acceptance.

## Agent-first automatic candidate fixing

If an AI agent owns the task, use the **existing coordinator** rather than
stringing low-level commands together yourself. Run `mode=repair` (not
`review`), and let the agent inspect, synthesize an allowlisted plan, apply
the changes **only to a disposable candidate**, verify the exact diff and
remeasure. If no safe plan exists, the workflow returns `blocked` or
`no_safe_fix` instead of guessing.

```console
vqs run "path/to/Example.Report" --mode repair --scope static --run-root "./private-vqs-runs" --run-id "autofix-001"
```

The mode is also exposed via MCP `vqs_run` with `mode="repair"`.
`scope=static` verifies source conditions only. Real desktop and DAX
regression need an authorized Windows host and explicit runtime scope;
the coordinator never auto-promotes the original. A repair/verify stage may
pass while the **overall report remains blocked** by a different defect.
See the [single-prompt AI quickstart](AI_AGENT_QUICKSTART.md) and
[auto-fix component architecture](AGENT_AUTOFIX_ARCHITECTURE.md).

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

## vqs theme — adaptive Light/Dark theme engine

Candidate-only re-theming by semantic role (issue #80). See
[theme engine](THEME_ENGINE.md) and [theme audit](THEME_AUDIT.md).

```console
vqs theme inspect REPORT --out theme-inventory.json
vqs theme preview REPORT --mode dark [--palette executive.json] --out plan.json
vqs theme apply REPORT --mode dark [--palette executive.json] --candidate-root ./candidates/dark
vqs theme audit ./candidates/dark --out theme-audit.json
```

## vqs premium — source-bound design preflight

For actual PBIR/PBIP reports, identify **measurable** page-design opportunities without redesigning data or querying a model. Generate a template with empty audience/question/focal fields; edit that JSON to state the owner's intent and budgets. It is tied to the exact current report source hash, so changing the report invalidates the template until re-reviewed. Results identify real page/visual IDs and rank up to three actions; `status=advisory` is **not** G2 visual acceptance.

```console
vqs premium path/to/Example.pbip --init-contract intent.json
# Edit intent.json to declare the audience, decision, focal visual and optional density budget.
vqs premium path/to/Example.pbip --contract intent.json --out premium.md
vqs premium path/to/Example.pbip --format json
```

Rules: peer-card gutter consistency, explicitly declared peer chart-title size, owner-specified content-area budget and focal prominence. Exceptions must be declared by exact rule and page. Inherited values, actual pixels, semantics and visual beauty remain unverified until native render/independent review. Output/intent files must be new (no silent overwrites). Read [premium usage and acceptance boundaries](PREMIUM_POWERBI.md).

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
report path; a wrong report, several instances without `--pid`, or an
unreported save state block with the reason. A reported unsaved flag
blocks user-owned instances absolutely; a run-owned disposable
candidate (opened by the run itself with a fresh PID, exact path,
sealed source, and run lease) records the flag instead of treating it
as proof of user edits. Needs Windows, Desktop, and
the report open — otherwise use `vqs doctor` to see what is missing.
Viewport-less captures (the actual Bridge 1.0.0 contract) bind render
identity for whole-page review with geometry calibration honestly
blocked — no pixel-to-PBIR coordinate transform is claimed.

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
report author executable, Desktop Bridge, Modeling MCP, running
Desktop) plus install identity (package version, import root,
engine/tool schemas, git SHA when discoverable). Read-only and
informational: it installs and modifies nothing — a stale editable
install is reported obvious, never auto-repaired — and always
exits 0. VQS has no ADOMD dependency.

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
