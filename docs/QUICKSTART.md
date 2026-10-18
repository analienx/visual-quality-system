# VQS developer workflow quickstart (pre-alpha)

One engine behind two adapters: the `vqs` CLI and the optional `vqs-mcp`
stdio server call the same tools with the same envelopes and verdicts.
Every command below is implemented behavior against static sources;
anything needing live Desktop, Word pagination, or cloud data blocks
with the reason instead of guessing.

Install once (this also verifies the packaged entry points), then
confirm what is running:

```console
pip install .
vqs --version
python -m vqs --version
vqs doctor
```

`vqs doctor` reports external capabilities and install identity
(package version, import root, engine/tool schemas) and never
installs, modifies, or gates anything: a stale editable install is
reported obvious, never auto-repaired. Exit codes: `0` pass,
`1` demonstrated violation, `2` blocked (environment, capability,
or input prevents a verdict).

## Start with an actionable report diagnosis

Give VQS a whole local `.pbip` project or `.Report` folder and it
will produce a short prioritized worklist: measured visual failures,
precise page and visual identities, evidence not yet available, and
only the typed fixes it can prove. This command does **not** modify
your report or authorize release.

```console
vqs triage path/to/Existing.pbip --out report-quality.md
vqs triage path/to/Existing.pbip --format json --out report-quality.json --plan-out candidate-plan.json
```

The first command writes a human-readable report with friendly page
and chart names. The second optionally exports a typed plan **only
when** the synthesizer has a safe candidate; missing plan is not an
error, and rendered checks remain explicitly unverified. Project
`byPath` model references are resolved automatically when the local
model definition exists; no Fabric service connection is inferred.

To apply an approved typed plan, use a **disposable** report folder and
run `vqs repair` followed by `vqs verify`. For actual Desktop/design
acceptance, continue with the image and model checks below; source-only
triage cannot judge whether an intentional overlay is visually right.

### Live Desktop images: raw vs report-only

`vqs capture <Report> <private-renders> --pid <candidate-desktop-pid>`
keeps the original Bridge PNGs and, when the screenshot contains the
**measurable three-row dotted page borders and a separate Desktop Filters
pane divider**, also produces `canvas-<pageId>.png` images with
`canvas-evidence.json` and `capture-manifest.json.canvas_review`
hashes/crop coordinates. This is **conditional**: unfamiliar host chrome,
nonuniform scale, missing borders or mismatched page geometry stay
`canvas_review.status=blocked`, never an invented crop. Its
`complete` status means only *all page frames located*; it is **not**
an independent design review, data-readiness, answer, or RLS pass.
Raw captures keep their independent source/PID binding and calibration.

### Actual reviewer input (not Desktop chrome)

When all page crops are measured, vqs bundle pack now includes BOTH
the original Desktop-window screenshots and the exact lossless canvas-only
images. vqs bundle verify independently remeasures every raw screenshot,
checks the crop bytes/pixels row by row, and exposes
review_images[page_id] (image, sha256, pixels, crop,
effective_scale, source_image) with
review_image_basis=verified_canvas. A reviewer provider should call
vqs.review.bundle.verify(bundle_dir) and inspect those verified
review_images; it must never trust unverified standalone image paths.
When no crop is available the same API explicitly returns
review_image_basis=raw_desktop_window, not a pretend clean image.
The transport remains blocked without genuine data_readiness.

### Opt-in independent Muse image reviewer

Verified review bundles now have a real image-capable reviewer provider.
Muse must be installed and authenticated locally. Report PNGs may contain
customer data; they leave the machine ONLY with explicit
--allow-remote-images consent:

    vqs review-images ./private-bundle --report ./MyReport.Report --allow-remote-images --out ./private-review.json

VQS launches a new Muse session for each verified report-only PNG, with
workspace writes, shell and web tools disabled, and no session log.
Each page must return six structured checks for clipping, overlap,
legibility, spacing, chart content, and hierarchy, bound to that
page's verified image SHA-256. Wrong hashes, missing or malformed
answers, or provider failure block instead of inventing results.
The output is **advisory**: it does NOT prove semantic correctness,
RLS, slicer states, accessibility, or release readiness.

The coordinator can use the same provider with
--reviewer vqs.review.muse:muse_reviewer, if the operator explicitly
sets VQS_ALLOW_VISION_UPLOAD=1 for that process. Missing consent
blocks remote image upload. The manual request-review form remains.

File hashes prove image provenance. Muse supplies a fallible independent
visual judgment. The release-authority registry remains intentionally
empty: a model response can never self-appoint release approval.

### Real Modeling MCP compatibility

The local Modeling MCP adapter resolves Windows npm .cmd launchers and
understands Microsoft's data result envelopes for local-instance
discovery, connection, model statistics and DAX rows. With
VQS_MODELING_AUTO=1, vqs capture binds live model discovery to the
exact selected Desktop PID through an OS-attested process-parent
relationship: Microsoft reports the msmdsrv.exe engine PID, while
the matching Desktop host is its live parent PBIDesktop.exe. VQS
refuses another model even if it has data. A clone without a
discoverable OS-bound semantic model stays blocked; it cannot inherit
an unrelated Desktop model's readiness.
A successful populated probe checks one named table twice and only
covers the selected model/context, not arbitrary slicer states or RLS.

**First-open model initialization:** For a run-owned
disposable candidate (owned_candidate=True) with
VQS_MODELING_AUTO=1, vqs capture first renders a single page into a
disposable temporary directory. Power BI Desktop may not start its
msmdsrv.exe engine until that page is rendered. The
warm-up screenshot is deleted and is never reviewer evidence.
Use the explicit --live-data option on vqs capture or
vqs verify-runtime instead of setting VQS_MODELING_AUTO=1 manually.
After binding the engine to the original selected Desktop through
its OS-attested parent PID, VQS probes live populated data BEFORE
the authoritative screenshot-all and repeats the same readiness
AFTER capture; any drift, unpopulated response, different Desktop
or source change blocks the manifest. Injected modeling ports and
user-owned Desktop instances are never given a warm-up. This does
not by itself prove all report measures, period, filters or RLS.

For actual data-populated candidate previews when the sealed VQS repair
model is definition-only, `vqs prepare-preview` calls the same
`vqs.repair.preview.materialize_populated_preview` engine. For example:

```console
vqs prepare-preview ./Original.pbip ./typed-candidate.Report ./private-preview --visual definition/pages/P1/visuals/V1/visual.json
```

It creates a **run-owned private complete PBIP copy**, retains the original
local model cache, and overlays only explicitly declared visual edits
without changing the original/model/query. The copied `.pbi` cache may
contain data: it **cannot be placed inside a Git checkout and must never
be committed, promoted, published or attached to a public issue**.
Cache presence alone does not prove freshness, filter context or semantic
answer equivalence. See its focused tests before integrating it into an
automatic runtime route.

## 1. The one-command workflow (start here)

`vqs run` owns the whole sequence — inspect, review, propose, repair,
verify, remeasure — in one sealed run with per-stage evidence
(`review`, `propose`, or `repair` modes stop earlier; `static`,
`desktop`, or `release` scopes add runtime legs that block precisely
when Desktop/Bridge capability is missing). Keep run roots private
and gitignored.

```console
vqs run path/to/Example.Report --mode repair --run-root runs --run-id flow-1
vqs run path/to/Example.Report --mode review --run-root runs --run-id rev-1
```

## 2. Expert: individual tools (debug)

The commands below expose each stage separately for debugging. They
are the expert interface: prefer `vqs run` unless you are diagnosing
one stage. Run IDs are confined to the run root (`../..` and
absolute IDs block).

`inspect` measures check-ready facts (read-only). `review` seals them
to a verdict under `--run-root <id>/` (`manifest.json`,
`findings.json`, `events.jsonl`).

```console
vqs inspect path/to/Example.Report --model path/to/Example.SemanticModel/definition
vqs review path/to/Example.Report --model path/to/Example.SemanticModel/definition --run-root runs --run-id rev-1
vqs review --facts facts.json --run-root runs --run-id rev-facts
```

`run-status` re-validates the seal before reporting, so tampered runs
block instead of replaying stale verdicts. `resume` revalidates sealed
provenance: unchanged sources re-run, changed sources/config block.

```console
vqs run-status runs rev-1
vqs review --facts facts.json --run-root runs --run-id rev-2 --resume-from rev-1
```

`propose` triages the sealed findings of a review run into
plan-eligible work items. Findings VQS can bind safely (small
geometry overlaps and outside-page visuals with measured facts,
explicit leaf bindings with proven old/new values) become
deterministic typed candidates with a complete plan document;
anything ambiguous becomes `needs_owner_decision` and is never
guessed. Caller facts are accepted only when their digest matches
the sealed run, so stale sources block.

```console
vqs propose --run-root runs --run-id rev-1
vqs propose --run-root runs --run-id rev-1 --facts facts.json --out plan.json
```

Write a JSON plan against the allowlist (see `vqs validate-plan` to
check one without executing). `repair` validates, copies the original
into a fresh candidate root, applies the operations, and seals a repair
run binding the plan, before/after digests, and applied edits. The
original is never modified; refusals remove owned partial copies and
seal a blocked run. `verify` then proves the candidate differs solely
by the declared edits.

```console
vqs repair plan.json --original path/to/Example.Report --candidate-root cand-1 --run-root runs --run-id rep-1
vqs verify --run-root runs --run-id rep-1
vqs verify --original path/to/Example.Report --candidate cand-1 --edits runs/rep-1/repairs.json
```

`verify-runtime` binds a Desktop instance to the sealed candidate
(never the original): pass `--pid` for a user-owned instance, or omit
it and VQS opens the disposable candidate itself through the Bridge
`open` contract and binds the freshly observed PID. Either way it
reloads, captures, and seals the runtime evidence separately.
`promote` then requires an explicit `--owner-approval` consent string
(recorded consent, not identity proof), recomputed digests, a
preserved backup, and seals the promotion separately; without
approval, with drift, or with unresolved runtime regressions it
refuses and touches nothing. `--scope` gates the evidence: `static`
(default) promotes on static verification only and says so;
`desktop` needs the bound runtime verification plus a passing
post-promotion recheck; `release` stays blocked without a trusted
reviewer authority.

```console
vqs verify-runtime --run-root runs --run-id rep-1 --pid 4242
vqs verify-runtime --run-root runs --run-id rep-1
vqs promote --run-root runs --run-id rep-1 --owner-approval "owner: accept static repair" --runtime-run-id rt-1
vqs promote --run-root runs --run-id rep-1 --owner-approval "owner: accept desktop repair" --runtime-run-id rt-1 --scope desktop
```

Minimal plan shape (adapt selectors/values to the real visual; the new
value must differ from the current one):

```json
{
  "operations": [{
    "type": "typography.size", "target": "visual",
    "selector": {"page": "P1", "visual": "cardx"},
    "path": ["visual", "objects", "labels", 0, "properties", "fontSize", "expr", "Literal", "Value"],
    "value": "26D",
    "writes": ["definition/pages/P1/visuals/cardx/visual.json"]
  }],
  "write_targets": ["definition/pages/P1/visuals/cardx/visual.json"],
  "rollback": "re-materialize from original"
}
```

## 3. Same workflow over MCP

`vqs-mcp` speaks newline-delimited JSON-RPC 2.0 on stdio (one response
per request, exit 0 on EOF); `vqs mcp` launches it. Tool names are
`vqs_inspect`, `vqs_review`, `vqs_propose`, `vqs_repair`, `vqs_verify`,
`vqs_verify_runtime`, `vqs_promote`, `vqs_run_status`, `vqs_run`.
Blocked verdicts are normal results, never transport errors.

```console
vqs-mcp
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "example-client", "version": "1.0.0"}}}
{"jsonrpc": "2.0", "method": "notifications/initialized"}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "vqs_review", "arguments": {"report_dir": "path/to/Example.Report", "run_root": "runs", "run_id": "rev-1"}}}
```

Every session opens with `initialize` (the server speaks
`2024-11-05`; a mismatched `protocolVersion` is refused) followed by
the `notifications/initialized` notification. `initialize` requires
typed `clientInfo` (`name` and `version` as nonempty strings);
requests without it are refused with `-32602`. `tools/list` and
`tools/call` before that handshake are rejected with `-32002` and
create nothing on disk; malformed arguments (wrong types, wrong
array elements) fail with `-32602` before the engine runs.

## Honest boundaries

- Static scope only: `desktop`/`release` scopes, live renders, and Word
  pagination are unavailable here and block with the prerequisite.
- Synthetic fixtures prove contract handling, never live visual or data
  approval. Missing data, timeouts, unsupported drivers, stale captures,
  and reviewer disagreement are blocked/unknown, never pass.
- Never commit run roots, bundles, renders, or customer report data;
  keep them under gitignored storage.
