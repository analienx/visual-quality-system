# VQS v0.1.2 — verifiable decisions and regression gates

**Scope: Power BI static source review, safe candidate repair and the PR gate.**
This release packages the functionality merged after v0.1.1 and corrects what a
review of the whole `v0.1.1..main` delta found. It adds **no** native Desktop
capability. Shape Map country clicking, contextual tooltip hover, generalized
native repair reload and Word/DOCX certification remain outside the supported
scope, and no report-level G2/G4/G6 acceptance is claimed or implied.

## What a user gets that v0.1.1 did not have

### Answerable owner decisions

A blocked `vqs fix` now hands back questions instead of a dead end. Each carries a
stable `decision_id` bound to the reviewed source digest, the question in plain
words, and typed options — concrete edits or an explicit `accept` waiver.

```console
vqs fix "Contoso Retail.pbip"                       # blocked, with questions
vqs decisions template --run-id <id> --out answers.json
# choose one option per question, then:
vqs fix "Contoso Retail.pbip" --decisions answers.json
```

On the committed fictional Contoso report this turns *blocked, no candidate* into a
verified candidate with exactly 7 declared PBIR changes and no regressions.

**Agents must show the options to the owner and wait.** An agent never picks an
option or an `accept` waiver itself; see [AGENTS.md](../AGENTS.md).

### Legible results and one explicit adoption step

A result now says what was edited and how to adopt it, so neither a person nor an
agent has to reconstruct internal run ids:

- `changes` — page, visual, property, operation, and `from` → `to` for every
  candidate edit.
- `adopt` — the exact `vqs promote` command and `vqs_promote` arguments.

Adoption stays an explicit owner step. It replaces the original and keeps
`<report>.vqs-backup`. Nothing in a `fix` run promotes anything.

### A pull-request quality gate

`vqs gate HEAD --baseline BASE` reviews both revisions with the same deterministic
engine and fails **only on findings the change introduces**, compared at finding-subject
granularity, so a pre-existing issue never blocks an unrelated pull request.

- Exit `0` nothing new · `1` new findings · `2` blocked.
- `--sarif` writes SARIF 2.1.0 for GitHub code scanning; `--github` prints
  `::error` annotations.
- `--emit-baseline` stores a portable baseline so CI needs no second checkout.
  Without `--baseline` that call is a capture, not a comparison, and exits `0`.
- A **blocked** gate still writes SARIF and annotations, as one
  `vqs.gate.blocked` error naming the reason.

### Honest capture and data statements

`vqs capture` without `--live-data` says what it does not prove: `modeling` carries
`data_population: unproven` plus a `--live-data` next action, because a cache-less
candidate renders `(Blank)` everywhere and still captures. No `data_readiness` is
fabricated. Capture manifests fill `desktop_version` from the PID's own
`PBIDesktop.exe` ProductVersion when the Bridge omits it, recording
`desktop_version_source`.

## Corrections you should know about

Two behaviours changed in ways you may notice. Both move toward the documented
contract.

1. **A fully waived run with missing evidence now reports `blocked`, not `pass`.**
   Previously, because `run_check` reports `fail` whenever any check fails — which
   masks a co-existing `blocked` finding in the verdict — waiving every failing
   check could return `verdict=pass`, `acceptance=true` and
   `outcome=accepted_with_waivers` while blocked findings remained in the sealed
   evidence. Owner waivers may clear a demonstrated failure; they may never clear
   missing evidence. The summary now names the unprovable checks in
   `unwaivable_findings` and explains itself in `blocked_reason`.

2. **`vqs gate <report> --emit-baseline <file>` now exits 0.** It used to write the
   baseline and then exit 1, because with no `--baseline` every existing finding
   counts as new — so the documented "store a baseline" CI step went red on
   success.

The rest of the review fixes are listed in the [changelog](../CHANGELOG.md): a
forged `owner-decision:` proof in a hand-written plan is refused; one overlap
conflict keeps one subject identity regardless of how much geometry the facts
carry; the Microsoft metadata gate admits both real PBIR formatting layers instead
of discarding a whole answered plan; native capture compares content identity
rather than timestamps; an interrupted Desktop PID lease is recoverable; PID
attestation shares one probe and one command-line parser; the Windows Desktop probe
pins its Desktop version and refuses an unverified installer.

## Install

```console
pip install visual_quality_system-0.1.2-py3-none-any.whl
vqs doctor
```

Zero runtime dependencies, Python ≥ 3.11. The hash-locked Microsoft authoring skill
resources ship inside the wheel; `vqs doctor` reports the real authoring readiness
rather than presence-only success, and never downgrades a validator or auto-installs
one.

## What was actually verified

| Gate | Environment | Result |
| :--- | :--- | :--- |
| Full test suite | Linux, Python 3.13 | **pass** — 2200 passed, 21 skipped, `ruff` clean |
| Clean-install chain | fresh venv, wheel only, no source on path | **pass** — 19/19 assertions |
| `fix` → template → answered `fix` → `changes` → adoption | installed wheel, disposable copy of the fictional report | **pass** — 5 questions, 7 declared changes, `.vqs-backup` kept |
| `gate` → SARIF, stored-baseline round trip | installed wheel | **pass** — SARIF 2.1.0, driver version 0.1.2, capture and re-compare both exit 0 |
| Negative controls | installed wheel | **blocked, as required** — stale answers, unusable answers, unparseable answers, forged owner-decision proof |
| Original preservation | recursive digest before/after | **unchanged** |
| Ubuntu + Windows × Python 3.11–3.13 clean wheel | GitHub runners | see the release commit's CI run |
| Windows Desktop probe | — | **not run** for this release; its pinning change is config-only and unverified until a Windows runner executes it |
| Native G2/G4, owner G6 | — | **not run** |

## What this release is not

- It is **not** native Desktop acceptance. No Desktop process, render, interaction
  or live DAX was involved in producing it.
- A green suite and a green gate are **static source evidence**. A green gate means
  "this change introduced no new finding we can measure", not "this report is good".
- It resolves none of the open native issues.
  [#115](https://github.com/analienx/visual-quality-system/issues/115),
  [#116](https://github.com/analienx/visual-quality-system/issues/116),
  [#117](https://github.com/analienx/visual-quality-system/issues/117),
  [#120](https://github.com/analienx/visual-quality-system/issues/120) and the
  independent report release gate
  [#16](https://github.com/analienx/visual-quality-system/issues/16) stay open. The
  [reconciliation](V012_ISSUE_RECONCILIATION.md) maps each stated criterion to the
  evidence that exists and names what is still missing.
- #117 in particular is **unchanged by shipping this**: a source-only release
  neither implements native country-click and tooltip hover nor excludes them. That
  needs an owner decision.

## Integrity

Verify the artifacts you install against the checksums published with the GitHub
release, and the release tag against the exact commit it was built from.

| Artifact | SHA-256 |
| :--- | :--- |
| `visual_quality_system-0.1.2-py3-none-any.whl` | `80a87be76b56ad25784d4c72ee4e4c74375593b526447090c60cb9fe3ead403d` |
| `visual_quality_system-0.1.2.tar.gz` | `b958ba4dfa3fb7cd4921f2dc5eb36eacffa6230e2af33cde58edf443331e6eb6` |

Those digests are for the artifacts built from the release commit. Rebuilding from a
different commit produces different digests; re-record them rather than reusing
these.

## Further reading

[Quickstart](QUICKSTART.md) · [CLI reference](CLI.md) ·
[User guide](USER_GUIDE.md) ·
[Owner decisions and the PR gate](OWNER_DECISIONS_AND_PR_GATE.md) ·
[Acceptance matrix](ACCEPTANCE_MATRIX.md) ·
[Open-issue reconciliation](V012_ISSUE_RECONCILIATION.md) ·
[Native evidence and limits](V012_NATIVE_G_ACCEPTANCE.md)
