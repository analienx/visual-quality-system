# VQS Power BI — engineering progress, 27 October 2026

**Status: Engineering preview. No production release, tag or G6 signoff.**
[Release gate #16](https://github.com/analienx/visual-quality-system/issues/16) remains open. The mandatory independent G2/G4 review and owner/publisher G6 decision have **not** been granted.

## What has actually changed on protected main

| Change | Protected PR | Scope and proof |
| :--- | :--- | :--- |
| Safely repair missing Desktop-saved PBIP/PBIR schema declarations | [#97](https://github.com/analienx/visual-quality-system/pull/97) | Only two declared JSON files in a disposable PBIP; default dry run; local `byPath` semantic model validation; source SHA-256 receipts; negative tests |
| Prove a real, saved, source-bound Windows Desktop report after native Save | [#98](https://github.com/analienx/visual-quality-system/pull/98) | OS PID/path + single Bridge registration + real `InvokePattern` Save + before/after hashes + schema-equivalent metadata-only changes; unchanged default pre-open source gate; private opt-in witness consumed by strict DAX/UIA |

Both PRs passed protected CI (including Windows), official Microsoft authoring probes, and R6 checks before merge. **A merged engineering PR is not independent G2/G4 acceptance or production approval.**

The compatibility issue was also [independently reported upstream](https://github.com/microsoft/skills-for-fabric/issues/105) for Microsoft Desktop 2.158. We reproduced the missing-schema behavior on Desktop **2.159.883.0**. The workaround is not proof the Microsoft serializer is fixed.

## Real Windows acceptance progress (private evidence)

- **Fictional Contoso:** freshly source-attested `byPath` model and Desktop file **pass** after a genuine native Save. Four live Year DAX states **pass**. Real Year/Region filter control interaction and KPI readbacks **pass** for **eight actions plus one read-only baseline**. A window initially minimized was recovered via exact-PID/path-bound WindowPattern, not blind clicks. Overall release and map interaction acceptance stay **blocked**.
- **Second unrelated private PBIP:** the first native Save **correctly failed source attestation** because Desktop rewrote active-page state and legacy mobile map properties. A separate settled-source disposable copy was then source-attested successfully; actual Modeling MCP Europe and unfiltered DAX values matched native Sales Region On → Off → On accessibility toggle and restored rendered percentage readback. This is **engineering evidence**, not a general-purpose automatic map replacement.
- **Important remaining behavior:** Power BI marks both sessions **unsaved after report UI interactions**, even after restoring the slicer state. The underlying physical source hash and modification inventory can remain unchanged, but a new strict terminal saved-state attestation must **block**. The bounded native UIA workflow now observes the terminal OS/Bridge/report identity and exact source **bytes and timestamps** as a separate *interaction transaction*; a dirty terminal remains `status=blocked` and `loaded_file_attested=false` for a **new** saved-file attestation. The original strict pre-action check is not weakened. This is code/test evidence only until a fresh real transaction is recorded and independently reviewed; do not claim full G4 or repeat Desktop Save/reopen solely to clear UI dirty state.
- One private settled candidate had **0 authoring errors and 1 schema-endpoint-unreachable warning**. A missing Microsoft remote schema response cannot be silently recorded as 0 warnings.

Private report sources, caches, screenshots, Windows receipts and data never belong in the public repository. Fictional Contoso screenshots already in the public gallery have their separate source/capture provenance; historical static/native-gallery images do not imply independent interactive acceptance.

## G2 engineering correction — native slicer checkbox (27 October)

The **Saffron & Spruce Dark** real expanded Year flyout displayed checkbox
indicators at approximately **1.8:1** contrast against the item surface.
A previously isolated seven-slicer private trial showed a readable light icon
but was not a source-managed product fix. The theme engine now gives slicer
`selectionIcon.color` an explicit `slicerForeground` role and synthesizes it
for missing native icon groups, without changing filter behavior or editing
original sources. The role is contrast-screened at **>=3:1** against
`slicerBackground` in all 14 approved families and both modes.

Engineering proof: **76 focused theme tests passed**; a fresh, isolated
fictional Contoso Saffron Dark candidate contains **7/7** explicit light
checkbox indicator colors and passes Microsoft Report Author `validate` with
**0 errors / 0 warnings**, including schema checks. The previously captured
native trial improved the unselected indicator. A subsequent single final
combined candidate was captured in real Power BI Desktop, with source-known
unselected and 2024-selected expanded-list states. **Both are visually readable**;
the selected white square and unchecked white outlines contrast with the dark
item background. This is fresh real engineering capture evidence, **not**
independent G2 or G6 approval.

## Source-grounded G2 color + full Europe-filter G4 correction

Fresh adversarial review discovered the Dark `Deep-dive insights` Region bars
all yellow despite distinct Light palette categories. A strict **source-grounded,
candidate-only** selector restoration now rejects mismatched query/field or
nonunique palette slots, preserving three verified category bindings. A **real
native Desktop screenshot** now renders Europe yellow, North America green,
and Asia Pacific red, also in Year 2024. The final isolated combined candidate
was further checked with a corrected 80px Year slicer container and seven
explicit accessible selector icons; Microsoft validator **0 errors/0 warnings**.

The native Contoso Europe interaction previously skipped 3/4 KPI comparisons.
Now a separate pinned 2024+Europe DAX query checks **Sales, Units, YoY and GM**;
no native input action proceeds without its source/model/PID-bound, complete
four-value oracle. A single real source-attested Windows/Desktop G4 run
returned **8/8 native actions plus baseline PASS**, confirmed Year/Region KPI
values and unchanged source hashes/timestamps across the transaction.

A genuine native Save reserialized one `visual.json` without changing its
parsed meaning. A new **strict** witness requires pre-Save exact visual bytes
(hash+size anchored to the frozen inventory) and whole-object semantic equality
(duplicate keys/nonfinite JSON rejected). Other source/model mutations still
block; the old default strict source gate remains unchanged. The same Windows
PID's strict saved-file attestation passed after the reconciled single Save.

Complete bounded reproduction, negative tests, SHA receipt handling and
independent-review limits are documented in
[P1 G2/G4 corrective evidence](P1_G2_G4_CORRECTIVE_EVIDENCE_2026-10-27.md).
[PR #103](https://github.com/analienx/visual-quality-system/pull/103)
merged with **2010 full-suite tests passing, 14 skipped**, Ruff, mypy,
Microsoft authoring real-CLI and protected **CI/DAX/R6** all passing.
A subsequent distinct private **Corporate Spend** acceptance run provided
previously missing strict saved-source/native Sales Region On → Off → On
receipt (2 actions + 1 read-only baseline), independently executed Europe
and unfiltered DAX parity, unchanged PBIR/TMDL SHA+mtime across actions,
terminal OS/Bridge identity and **3/3 new native page captures**.
See [Corporate native G4 evidence](P1_CORPORATE_NATIVE_G4_EVIDENCE_2026-10-27.md).
That private Corporate candidate had **0 authoring errors / 1 remote-schema-endpoint warning**, not 0/0.
Owner-supported map/tooltip scope, formal distinct reviewer and G6
**remain open**. No production tag.

## Release gates that remain

1. **Independent G2:** all five populated Contoso pages in Light/Dark including expanded dropdown/filter states, and all three populated pages of the unrelated private report, reviewed independently for contrast, labels, missing content and actual visual correctness.
2. **Independent G4:** supported native filter sequence with same-context DAX and independently reviewed event receipts on both unrelated PBIPs. Resolve or explicitly scope the post-interaction dirty state without weakening fail-closed source identity; unsupported interactions must remain marked blocked.
3. **G6 owner/publisher decision:** after independent reviewer evidence and supported-scope reconciliation, ask for a fresh explicit production signoff. Only then update the production changelog/tag and close [#16](https://github.com/analienx/visual-quality-system/issues/16). Consumer installation/native parity [#17](https://github.com/analienx/visual-quality-system/issues/17) remains separately open. Word/DOCX [#13](https://github.com/analienx/visual-quality-system/issues/13) never blocks Power BI-only release.

## Operator documentation

- [Five-minute AI agent auto-repair quickstart](AI_AGENT_QUICKSTART.md)
- [Automatic-fix architecture and component contract](AGENT_AUTOFIX_ARCHITECTURE.md)
- [Native Desktop saved-source witness runbook](NATIVE_DESKTOP_SAVED_SOURCE_WITNESS.md)
- [Schema normalization compatibility and boundaries](P1_DESKTOP_SAVE_SCHEMA_COMPATIBILITY_2026-10-27.md)
- [Strict Desktop source attestation contract](DESKTOP_SOURCE_ATTESTATION.md)
- [G2/G4 corrective engineering verification and remaining gates](P1_G2_G4_CORRECTIVE_EVIDENCE_2026-10-27.md)
- [Corporate Spend source-bound native G4 evidence and unsupported-scope matrix](P1_CORPORATE_NATIVE_G4_EVIDENCE_2026-10-27.md)

See [26 October engineering history](RELEASE_NOTES_2026-10-26.md) for the prior snapshot. This document supersedes its acceptance-status section, not its historical events.
