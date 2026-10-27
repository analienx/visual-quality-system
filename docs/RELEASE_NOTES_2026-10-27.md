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
- **Important remaining behavior:** Power BI marks both sessions **unsaved after report UI interactions**, even after restoring the slicer state. The underlying physical source hash and modification inventory can remain unchanged, but a new strict terminal saved-state attestation must **block**. Do not suppress the dirty flag or call this fully certified G4.
- One private settled candidate had **0 authoring errors and 1 schema-endpoint-unreachable warning**. A missing Microsoft remote schema response cannot be silently recorded as 0 warnings.

Private report sources, caches, screenshots, Windows receipts and data never belong in the public repository. Fictional Contoso screenshots already in the public gallery have their separate source/capture provenance; historical static/native-gallery images do not imply independent interactive acceptance.

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

See [26 October engineering history](RELEASE_NOTES_2026-10-26.md) for the prior snapshot. This document supersedes its acceptance-status section, not its historical events.
