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
