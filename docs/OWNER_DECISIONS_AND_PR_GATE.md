# From "blocked" to a verified candidate: owner decisions and the PR gate

VQS never guesses design intent. Some findings can only be fixed by a person
choosing, for example *which* font size a group of visuals should share, or
whether a repeated breakdown on two pages is deliberate. Before November 2026
such findings were a dead end. Now each one is an **answerable question**: the
owner picks an option once, and VQS applies and verifies it in a disposable
candidate.

The second half of this guide covers `vqs gate`, which reuses the same
finding identity so pull requests fail **only on problems they introduce**.

> **Boundary.** Answers authorize edits to a *disposable candidate* and scoped
> waivers. They are not G2/G4 review, G6 promotion or release approval, and
> nothing here changes or promotes the original report.

## The three-step loop

```console
vqs fix "C:/Reports/Sales.pbip" --run-id sales-1           # 1. blocked, with questions
vqs decisions template --run-id sales-1 --out answers.json  # 2. owner fills one option per question
vqs fix "C:/Reports/Sales.pbip" --run-id sales-2 --decisions answers.json   # 3. apply + verify
```

`vqs decisions template` reads the sealed run from the same run root that
`vqs fix` used (pass `--run-root` if you used a custom one) and refuses to
overwrite an existing file.

### 1. What a question looks like

Real output for the committed fictional Contoso report
(`examples/contoso-retail`), taken from `needs_review` in the `vqs fix` result:

```json
{
  "decision_id": "dec-c3a1e541cbe3cb7c",
  "check": "typography.format_declaration_consistency",
  "question": "Which size should every visual in cohort pivotTable/grid.textSize use?",
  "cohort": "pivotTable/grid.textSize",
  "options": [
    {"id": "size:10D", "effect": "apply",
     "label": "Use 10 for all 2 visuals in pivotTable/grid.textSize (1 edit(s) in the candidate)"},
    {"id": "size:11D", "effect": "apply",
     "label": "Use 11 for all 2 visuals in pivotTable/grid.textSize (1 edit(s) in the candidate)"},
    {"id": "accept", "effect": "waive",
     "label": "Keep the current design as intentional (owner waiver; recorded, never a pass)"}
  ]
}
```

| Option kind | Offered for | What it does |
| --- | --- | --- |
| `size:<literal>` | Font/text-size cohorts whose members are all exactly addressable | Rewrites differing explicit sizes (`format.set_explicit`) and adds the size where a visual inherits it (`format.declare_explicit`, owner-only) |
| `move:<visual>:<axis>:<value>` | Large or ambiguous overlaps with no automatic nudge | Moves one visual flush to a side of the other; each option is checked in-canvas and overlap-free against every neighbour |
| `accept` | Every owner decision | Records an owner waiver for exactly that finding subject |

Values come only from what the report already declares. VQS never invents a
size that none of the visuals uses.

### 2. The answers file (`vqs.decision-answers/1`)

```json
{
  "schema": "vqs.decision-answers/1",
  "source_sha256": "<copied by the template from the run>",
  "owner": "Jane Doe (report owner)",
  "answers": [
    {"decision_id": "dec-c3a1e541cbe3cb7c", "option": "size:10D",
     "note": "Match the other pivot tables"},
    {"decision_id": "dec-df6a9a65eedd2422", "option": "accept"}
  ]
}
```

| Field | Rule |
| --- | --- |
| `schema` | Must be `vqs.decision-answers/1` |
| `owner` | Required, non-empty: who decided (recorded in sealed evidence) |
| `source_sha256` | The reviewed report digest. Edit the report and every id changes |
| `answers[].option` | One of the question's option ids. Rows left empty are skipped |
| `answers[].note` | Optional short rationale, sealed with the run |

Template rows also carry `question` and `choices` for convenience; VQS ignores
them when reading answers.

### 3. What happens on the answered run

1. The report is reviewed again and decisions are re-synthesized.
2. Answers are bound to them. **Any** of the following blocks the run before a
   single byte is written: a different `source_sha256`, an unknown decision or
   option, a duplicated decision, or two options writing different values to the
   same property.
3. Chosen edits join the plan and run through the normal repair pipeline:
   precondition-checked recipes, exact-diff verification, remeasure, regression
   comparison.
4. The summary reports `owner_decisions` (who chose what), `waived_findings`
   and the usual `resolved_findings` / `remaining_findings`.

On the Contoso report, answering four size questions and accepting the
duplicate breakdown produces exit `0`, a **verified** candidate with exactly 7
declared PBIR changes, typography resolved, no regressions and the original
untouched.

### Seeing and adopting the result

A verified run lists every edit in plain terms and gives the one command that
applies it:

```json
"changes": [{"page": "Products_brands", "visual": "product-opportunity",
             "property": "grid.textSize", "from": "11D", "to": "10D"}, "..."],
"adopt": {"command": "vqs promote --run-root \"...\" --run-id sales-2-repair --owner-approval \"<who: why>\" --scope static",
          "mcp": {"tool": "vqs_promote", "run_id": "sales-2-repair", "scope": "static"}}
```

Adopting is the owner's call. It re-checks both digests, replaces the original
report and keeps it as `<report>.vqs-backup`. Static scope is still not native
Desktop, G2/G4 or G6 acceptance.

### Outcomes

| Outcome | Meaning |
| --- | --- |
| `accepted` | Candidate passes with no waivers needed |
| `accepted_with_waivers` | Every remaining failing check is **fully** waived by the owner. `quality_after` still reports the literal rule result |
| `improved_not_accepted` | Something was fixed, something unwaived remains |
| `blocked` | Answers rejected, evidence missing, or nothing applicable |

A check counts as waived only when *every* one of its subjects was accepted.
Waiving one of two typography cohorts leaves the check open.

### What can never be waived

Missing evidence: `blocked`, `unknown` or `unsupported` findings (coverage,
oracle, model and render-evidence gaps). These have no `accept` option, and a
waiver list cannot turn them green.

### MCP agents

`vqs_run` returns the same questions in `needs_review`. Show the options to the
owner, and never choose for them. Then call `vqs_run` again with
`decisions={...}`, the same document as `answers.json`. Use
`decision_source_sha256` from the first result as `source_sha256`.

## Pull-request gate (`vqs gate`)

```console
vqs gate head/Sales.pbip --baseline base/Sales.pbip --sarif vqs.sarif --github
```

* **Identity.** Findings are compared by *subject*: check plus
  page/visual/cohort/pair. A known issue never fails an unrelated pull request.
  A new one always does, including missing evidence that the change introduces
  (`coverage:*`).
* **Exit codes.** `0` nothing new · `1` new findings · `2` head or baseline
  unreadable.
* **Outputs.** `--sarif` writes SARIF 2.1.0 with `baselineState` new/unchanged
  for GitHub code scanning. `--github` prints `::error` annotations. `--out`
  writes the full JSON.
* **Stored baselines.** `vqs gate main/Sales.pbip --emit-baseline
  vqs-baseline.json` writes a baseline that is reused with
  `--baseline vqs-baseline.json`, so no second checkout is needed.
* **Waivers.** `--decisions answers.json` excuses `accept` answers bound to the
  *head* revision. Answers for another revision match nothing and are counted
  in `unmatched_waivers`.

Typical result for a change that alters one card label size:

```json
{"verdict": "fail",
 "counts": {"new": 1, "unchanged": 5, "waived": 0, "fixed": 0},
 "new": [{"check": "typography.format_declaration_consistency",
          "subject": "typography.format_declaration_consistency|cohort=card/labels.fontSize"}]}
```

A ready-to-copy GitHub Actions workflow is in
[CLI reference: pull-request gate](CLI.md#pull-request-gate-vqs-gate).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `decision answers were written for a different source revision` | The report changed after the template was made. Re-run `vqs fix`, regenerate the template, answer again |
| `unknown or stale decision dec-…` | The id belongs to another run or revision. Use the template from the latest run |
| `pass either an owner plan or decision answers, not both` | `--plan` and `--decisions` are exclusive |
| `run predates answerable decisions` | The template run was made by an older VQS. Re-run `vqs fix` |
| A question has only `accept` | Not every member was exactly addressable, so a partial edit would leave the cohort inconsistent. Fix it in the source, or waive it |
| Gate reports `unmatched_waivers > 0` | The answers target another revision. Regenerate them against the head |
| Microsoft authoring backend refuses a size edit | The metadata gate admits `fontSize`/`textSize` on `visual.objects` only. Container-title sizes (`vco.title`) can be applied in `--scope static` with `--authoring-backend direct`; Desktop/release scope requires the Microsoft backend and keeps refusing them |
