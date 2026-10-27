# Strict native-Save source provenance — bounded engineering workflow

**27 October 2026 | Issue #16 | Power BI-only, disposable candidates**

Power BI Desktop **2.159.883.0** frequently flags a freshly opened local PBIP as
`hasUnsavedChanges=true`; a genuine native Save turns it false but rewrites
PBIR/model metadata after process start, triggering the existing strict source
age gate. Power BI Desktop may remove two schema declarations at native Save
(see [schema repair](P1_DESKTOP_SAVE_SCHEMA_COMPATIBILITY_2026-10-27.md)).

VQS now offers an **explicit opt-in native-save provenance route** that
requires a complete real Windows Save witness. **The default pre-open source
age attestation is unchanged, still fail-closed.** No source mtime rewriting
or flag override is used.

## Native saved-source witness (private evidence only)

Use a copied, populated PBIP and its source-matched **local byPath model**
inside an explicitly provided scratch root. Do not run on an original PBIP.
The Desktop instance must already be open for that exact .pbip, show a
ready Bridge registry with exactly the expected PID/report, and have
`hasUnsavedChanges=true`. The source cannot have changed since launch.

The producer performs exactly ONE native Power BI UI Automation Save via
`InvokePattern` on the named `AutomationId=save` control, with the verified
Windows process command-line path, title and non-ambiguous button geometry.
It does not simulate keyboard shortcuts, blind clicks, change other windows,
or repeat Save after a transient Bridge status error. The after-Save Bridge
must report `hasUnsavedChanges=false`.

```console
python -m scripts.desktop_native_save_witness DISPOSABLE_PROJECT \
  --desktop-pid REAL_PID --disposable-root PRIVATE_SCRATCH_ROOT \
  --invoke-native-save --output PRIVATE_SCRATCH_ROOT/native-save.json

python -m scripts.desktop_source_attestation DISPOSABLE_PROJECT \
  --desktop-pid REAL_PID \
  --native-save-witness PRIVATE_SCRATCH_ROOT/native-save.json \
  --output PRIVATE_SCRATCH_ROOT/loaded-source.json

python -m scripts.contoso_p14_live_oracle DISPOSABLE_CONTOSO_PROJECT \
  --desktop-pid REAL_PID --attest-loaded-file \
  --native-save-witness PRIVATE_SCRATCH_ROOT/native-save.json \
  --output PRIVATE_SCRATCH_ROOT/attested-dax.json

python -m scripts.contoso_p16_native_interaction DISPOSABLE_CONTOSO_PROJECT \
  --desktop-pid REAL_PID --attest-loaded-file \
  --native-save-witness PRIVATE_SCRATCH_ROOT/native-save.json \
  --oracle PRIVATE_SCRATCH_ROOT/attested-dax.json \
  --output PRIVATE_SCRATCH_ROOT/attested-uia.json
```

The result contains exact before/after SHA-256 **and mtime_ns** for each
PBIR/model source file plus pre/post raw metadata, expected process creation
time, PID, local model reference, native Save UIA control and action
interval, and the live Bridge clean-state transition. Only the PBIP wrapper
and report `definition.pbir` can have byte changes—and only schema-only,
JSON-semantically equivalent ones. All other report/model source content
must be identical. Stale, wrong PID/path/model, changed DAX/report source,
changed post-Save file timestamps, in-memory dirty state, untrusted action
type and missing source inventories **BLOCK**. Dynamic verification is
performed again before strict DAX/UIA; routine invocations with no
`--native-save-witness` keep the older strict age requirement.

The receipt is **first-party local process evidence**, not a cryptographic
attestation of inaccessible Desktop memory or proof of independent reviewer
authorization. The source/save event is engineering G0 support—not G2 visual
quality, all G4 interactions, or G6 production signoff.

### Windows live engineering result (27 October)

The saved Contoso scratch session passed a native Save witness, strict
loaded-file/declared local model source, four live Year DAX states, and
**8 actual Year/Region UIA actions + one baseline** after an explicitly
PID-bound non-input window restoration. UIA returned `native_uia=pass`
and `interactive=blocked`; country map and independent G2/G4 review are
not certified. Actual private receipts stay on the authorized computer.
Corporate Spend's independent subject and full G2/G4 acceptance are not
covered by this Contoso result.

**Never** use receipt success as an excuse to close issue #16, publish a
production tag, promote PBIPs, or disclose caches/screenshots/source data.
Independent human G2/G4 and a separate owner G6 decision remain mandatory.
