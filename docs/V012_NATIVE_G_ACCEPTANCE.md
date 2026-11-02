# VQS next-release native G2/G4 acceptance: source-bound workflow

**State:** engineering validated on disposable local projects on 30 October
2026. **Not a v0.1.2 release, human G2/G4 signoff or owner G6 promotion.**
The immutable published v0.1.1 remains unchanged.

## Why Corporate Spend native Save needed two stages

The newer offline-geo candidate had replaced Azure Map with a native bar, but
its mobile layout still contained stale map controls. Native Desktop Save
correctly removed those and upgraded its schema. It also changed active-page
state, normalized two PBIP/PBIR schema declarations and reserialized JSON.
The original strict source witness **blocked**, as it should: mobile layout
changes are not automatically innocuous.

A separate disposable copy of the actual first-saved source was reopened in
a new Desktop process. The *second* genuine native Save passed the unchanged
65-source-file attestation: zero changed metadata or visuals. The real OS,
Bridge, source/report/model and exact Desktop PID attestation subsequently
passed. This is a new exact source revision, NOT a waiver of the first Save.

## Reproduce using private, disposable PBIPs only

Use existing `scripts/desktop_native_save_witness.py` to make two actual
native Save receipts with **separate Desktop processes**, retaining the first
failed receipt and diff privately. After inspecting and accepting the exact
first-save source changes as a deliberate new candidate revision:

```powershell
python -m vqs.powerbi.native_rebaseline `
  "C:/scratch/first-candidate" "C:/scratch/first-save.json" `
  "C:/scratch/stabilized-candidate" "C:/scratch/second-save.json" `
  --output "C:/scratch/native-rebaseline-audit.json"
```

The read-only audit demands byte-identical source continuity into the new
candidate and a strictly attested, unchanged second Save. It returns
`stabilized_candidate_needs_independent_acceptance` and enumerates each
first-save change for review. It **never** approves first-save semantics or
claims human G2, report G4, or owner G6.

## Independently pin every Desktop native screenshot to its exact PBIP

```powershell
python -m vqs.powerbi.native_capture_provenance `
  "C:/scratch/stabilized-candidate" --pid 12345 `
  --output-dir "C:/scratch/new-native-pages" `
  --receipt "C:/scratch/native-capture-proof.json"

python -m vqs.powerbi.acceptance_subjects `
  "C:/scratch/stabilized-candidate" `
  --native-receipt "C:/scratch/native-capture-proof.json" `
  --output "C:/scratch/source-and-capture-pin.json"
```

The native producer checks Windows OS PID ownership, current Bridge PBIP
and report path, all page IDs and native PNGs, and unchanged source
hashes/timestamps across capture. It denies extra/missing PNGs and changed
model/visual source. The separate manifest verifier replays source and image
hashes against the saved receipt. Both artifacts stay **private**.

For pre-existing PNGs without a native source receipt, `--capture-dir`
is hash-only and explicitly labels source binding **unattested**. This avoids
manufacturing source provenance from a filename or matching image hash.

## Observed results

| Subject | Fresh native evidence | Remaining gate |
|---|---|---|
| Fictional Contoso | Saved source; DAX 4 Year states/Europe four KPIs; 8/8 Year/Region actions plus baseline; 5 first-open + 5 post-interaction native pages | Formal human G2/G4 and owner G6 not signed |
| Private Corporate Spend offline-geo final | First Save correctly blocked; second strict saved-source and local model identity PASS; six DAX regional rows/Europe+Latin America arithmetic; new 3/3 exact-PID source-bound pages | Fresh bounded region interactions and authorized G2/G4/G6 outstanding |

Native **country-specific Shape Map clicks** and **true contextual Tooltip
hover** are not supported/certified. An owner must explicitly approve
excluding them or an implemented native adapter must prove them with real
DAX/visual interaction. Rendering the Tooltip page directly is NOT hover
proof. The Contoso sparse decision-signal region, matrix density, technical
prior-year legend, and limited country-map quantitative value remain G2 P2.

No private Corporate source, screenshot, semantic cache or unredacted DAX
receipt may be added to the public repository. This workflow does **not**
self-certify human or owner approval. See issues #16 and #115-#118.


## Corporate Region actual native interaction (30 October candidate)

The private Corporate Spend source contains one named Sales Region ComboBox.
InvokePattern on its list item and ValuePattern.SetValue did not commit the
region. The supported sequence is to expand that exact-PID ComboBox, find
the unique exact-name ListItem, call TogglePattern.Toggle(), verify the other
Region is unselected, and then call ExpandCollapsePattern.Collapse().
Only then does the displayed slicer selection update.

The packaged PowerShell adapter is at
`vqs/powerbi/native_scripts/corporate_region_uia.ps1`.
Using a private strictly verified saved-source receipt:

```powershell
python -m vqs.powerbi.corporate_region_acceptance `
  "C:/scratch/disposable-corporate" `
  --pid 12345 `
  --native-save "C:/scratch/native-save.json" `
  --output "C:/scratch/native-corporate-region-g4.json"
```

A bounded Europe / Latin America / Europe sequence independently verifies
native PID, source and model identity, unique region options, committed
collapsed selection, target on/other off, rendered variance KPI, independent
scoped live DAX (and distinction from the other region), source snapshots
before/after each action, and terminal Bridge dirty-state.

All three native steps passed on a fresh disposable Corporate session on
30 October. This is bounded engineering G4, not an authorized human G2/G4
signature or owner G6 approval. Corporate raw figures and receipts remain
outside Git. Shape Map country selection and contextual tooltip hover
remain separate.

## Disposable-runner Desktop probe (Power BI Desktop 2.159, November 2026)

`.github/workflows/windows-desktop-probe.yml` installs Power BI Desktop, the
Desktop Bridge CLI and the pinned authoring CLI on an ephemeral GitHub Windows
runner, opens a **copy** of the fictional Contoso PBIP and publishes only a
JSON summary (booleans, counts, no screenshots). Observed, run 41399601781:

| Question | Observation | Consequence in code |
| --- | --- | --- |
| Is a freshly opened PBIP clean? | No: `hasUnsavedChanges: true` before any action | Capture correctly refuses until a witnessed native Save |
| Does the first native Save verify? | Saved (`unsaved_before: true` -> `unsaved_after: false`) but `verified: false` | Expected: first Save stays a blocked transition; rebaseline flow applies |
| Does `screenshot-all` dirty a saved report? | No: `false` before and after; source bytes unchanged | `native_capture_provenance.capture` now **requires** a clean flag after capture; `bound_subject` refuses receipts without it |
| Full VQS native capture on the saved copy | `pass`, 5/5 pages, post-capture flag `false` | - |
| Command-line casing | OS keeps the launch casing; `Path.resolve()` returns disk casing | Region receipts compare physical files (`normcase(realpath())`) |
| Attestation dependencies | Worked with `psutil` **absent** | Save witness and strict attestation use built-in CIM (`vqs.powerbi.os_process`) |

This is engineering evidence about Desktop behaviour on a disposable copy. It
is not G2/G4 review, G6 promotion or acceptance of any customer report.

## Owner-laptop native run (Windows 11, 2 November 2026)

PR #124 head, Bridge CLI 1.0.0, authoring CLI 0.5.0, Modeling MCP
0.5.0-beta.16, a **copy** of the fictional `examples/contoso-retail` in a
non-ASCII scratch folder. Owner answers (all `size:10D`, duplicate grain
`accept`) were chosen by the owner, not the agent. Private receipts and
screenshots stay outside Git.

| Step | Observation | Consequence |
| --- | --- | --- |
| Test suite | 2189 passed, 15 skipped; `test_installed_*` need the venv `vqs` first on `PATH` (a stale global editable install otherwise answers) | Run the suite from an activated venv |
| `vqs fix` → template → `--decisions` | Blocked with 5 questions, then `accepted_with_waivers`, 7 `changes`, `adopt` present; `auto` and `microsoft` backends identical, `validate` pass | - |
| Native Save keeps VQS edits | First Save reserialized 30 files (rebaseline transition, `verified: false`), all 7 `10D` declarations survived | - |
| Candidate has no data | `examples/contoso-retail` ships no model cache, so the native render shows `(Blank)` and empty visuals; plain `vqs capture` still passes as render identity | `modeling` now records `data_population: unproven` with a `--live-data` next action; `--live-data` refuses unpopulated data |
| Refresh via exact-PID Modeling MCP | `RefreshWithXMLA` returns `content: []` on success; all 12 tables blank before, populated after; Bridge reports unsaved afterwards | A new Save is needed after a refresh |
| Modeling MCP leaves a source fingerprint | After a refresh, the next Save adds `"MCP-PBIModeling"` to `PBI_ProTooling` in `model.tmdl`; the witness blocks that model change. Ad-hoc `Get` plus a query on an *unpopulated* model also marked Desktop unsaved | Rebaseline once in a separate Desktop session |
| `--live-data` on a never-touched report | Copy of `contoso-retail-verified` (cache, no marker): witnessed Save verified, then `vqs capture --live-data` 5/5, `modeling: ready`, Desktop still clean, source unchanged | VQS's own readiness path does not dirty a populated report |
| Desktop version | Bridge 1.0.0 status has no `desktopVersion` | Capture falls back to the PID's `PBIDesktop.exe` ProductVersion (`desktop_version_source: os-executable`) |
| Same-session second Save | Witness refuses before invoking Save: source changed after launch | As designed: use a new Desktop process |
| Stabilized session | Refresh + witnessed Save `verified: true`, 0 changed files; `--live-data` capture 5/5, `modeling: ready`; strict provenance 5/5, clean after capture; rebaseline audit `stabilized_candidate_needs_independent_acceptance` | - |
| `vqs gate` | Candidate vs original: 0 new, 4 fixed; natively saved candidate identical (no spurious findings); deliberate 14D regression: exactly 1 new, exit 1 | Base-bound answers now acknowledge unchanged findings only; never a new one |
| `adopt` on the scratch copy | Promote pass, backup byte-identical to the original; repeat promote refused on digest drift | - |

Engineering evidence on a disposable fictional copy only: not G2/G4 review,
G6 promotion or acceptance of any customer report.
