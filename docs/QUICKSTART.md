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
