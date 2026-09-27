# Work package and scope

WP ID / issue: <!-- WP-NN, #issue -->
Target phase and surface: <!-- shared / Power BI Desktop / Word / cross-artifact -->
Base SHA / head SHA: <!-- exact immutable commits -->
Editable paths / schema versions consumed and emitted:

## What changed, and what deliberately did not

Describe the exact source-level change, expected design or analytical effect, and any rejected alternative. Is this code, documentation only, fixture only, or a real renderer result?

Workflow pointers: [USER_GUIDE.md](docs/USER_GUIDE.md) for review flows, `vqs bundle` for remote evidence handoff.

## Acceptance test evidence

| Test ID / gate | Fixture and environment | Command / manual method | Pass / fail / blocked / not run | Private evidence manifest ID |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

Tests run: <!-- N passing / N failing / N skipped, real Desktop/Word separately -->
Tests NOT run and why: <!-- do not convert missing Desktop / Word / data / image review to pass -->
Before/after source + model/query + render hashes: <!-- no raw private PNGs in PR -->
Exact Desktop PID/path or Word renderer/fonts version, where relevant:
Negative controls exercised: <!-- source stale / empty data / cropped page / wrong renderer / candidate regression -->

## Repair safety and source/data integrity

- [ ] Original user report / generated document remained byte-identical; edits are confined to a disposable candidate
- [ ] Typed allowlisted mutations, input contract, source diff and rollback documented (or not applicable, explained)
- [ ] Affected answer/filter/category/neighbor visuals and embedded figure provenance checked on a fresh render (or blocked, explained)
- [ ] No data/cache/auth/screenshot/private path or unreviewed third-party binary introduced in public Git
- [ ] Cloud data/image submission, if any, was explicitly authorized and recorded

## Independent review and release

Independent verifier (not the author), exact evidence and result: <!-- name/lane, review URL -->
Unresolved failures, blocked gates, model disagreement and limitations:
Proposed ledger transition: <!-- planned→review; review→verified only after independent proof and merged SHA -->
Does this PR change release scope / user-story semantics / renderer support? If yes, link owner decision.

**Do not merge or close a work package on static tests alone when its acceptance includes actual Power BI Desktop rendering or paginated Word pages. A doc-only PR cannot advance an implementation capability to verified.**