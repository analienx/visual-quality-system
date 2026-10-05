# VQS developer workflow quickstart (pre-alpha)

One engine behind two adapters: the `vqs` CLI and the optional `vqs-mcp`
stdio server call the same six tools (`inspect`, `review`, `propose`,
`repair`, `verify`, `run_status`) with the same envelopes and verdicts.
Every command below is implemented behavior against static sources;
anything needing live Desktop, Word pagination, or cloud data blocks
with the reason instead of guessing.

Install once (this also verifies the packaged entry points):

```console
pip install .
vqs --help
```

Exit codes: `0` pass, `1` demonstrated violation, `2` blocked
(environment, capability, or input prevents a verdict).

## 1. Inspect, then review a report

`inspect` measures check-ready facts (read-only). `review` seals them to
a verdict under `--run-root <id>/` (`manifest.json`, `findings.json`,
`events.jsonl`); keep run roots private and gitignored.

```console
vqs inspect path/to/Example.Report --model path/to/Example.SemanticModel/definition
vqs review path/to/Example.Report --model path/to/Example.SemanticModel/definition --run-root runs --run-id rev-1
vqs review --facts facts.json --run-root runs --run-id rev-facts
```

## 2. Status and resume

`run-status` re-validates the seal before reporting, so tampered runs
block instead of replaying stale verdicts. `resume` revalidates sealed
provenance: unchanged sources re-run, changed sources/config block.

```console
vqs run-status runs rev-1
vqs review --facts facts.json --run-root runs --run-id rev-2 --resume-from rev-1
```

Run IDs are confined to the run root (`../..` and absolute IDs block).

## 3. Propose work items

`propose` triages the sealed findings of a review run into plan-eligible
work items. There is no automatic plan author: each actionable item
needs an owner-authored plan.

```console
vqs propose --run-root runs --run-id rev-1
```

## 4. Author a plan, repair in isolation, verify

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

## 5. Same workflow over MCP

`vqs-mcp` speaks newline-delimited JSON-RPC 2.0 on stdio (one response
per request, exit 0 on EOF); `vqs mcp` launches it. Tool names are
`vqs_inspect`, `vqs_review`, `vqs_propose`, `vqs_repair`, `vqs_verify`,
`vqs_run_status`. Blocked verdicts are normal results, never transport
errors.

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
