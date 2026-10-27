# VQS acceptance matrix — tests before claims

**Primary release scope: Power BI core.** Word/DOCX is a separate optional
component; the historical combined suite remains a compatibility profile.
See the [illustrated architecture](ARCHITECTURE.md),
[program](IMPLEMENTATION_PROGRAM.md), [agent/ledger protocol](LEDGER_AND_AGENT_PROTOCOL.md)
and [work packages](../roadmap/work_packages.json). The [22 October real before/after repair and independent-review handoff](POWER_BI_CORE_REPAIR_ACCEPTANCE_2026-10-22.md) records current #14/#16 engineering evidence and honest blockers. These are falsifiable
acceptance requirements, **not** claims of independently passing evidence.

## 1. Gate definitions and result semantics

`G0 source/contract/runtime`: correct artifact identity, schema, hashes,
capabilities and evidence storage. `G1 actual data/renderer readiness`:
Power BI model really populated/queryable at recorded filters/role, or
DOCX backend/version/fonts valid when Word is selected. `G2 design
evidence`: quantitative rules and independently reviewed real Power BI
render. `G3 repair safety`: typed allowlisted source change in isolated
candidate, diff and rollback. `G4 same-task regression`: same report
question, answer/filter scope, neighbor visuals and supported native
interactions on fresh Desktop. `G5 Word consistency`: validated OOXML,
native paginated output, every page inspected and source-bound figures
where applicable. `G6 independent acceptance`: separately sealed suite,
negative corpus, independent reviewer and owner-controlled promotion.

### Explicit component release profiles (implemented in `vqs/components.py`)

| Profile | Required subjects | Subject gates | Suite requirement |
| --- | --- | --- | --- |
| **`powerbi-core` (primary)** | Two unrelated PBIPs with distinct layouts; **no DOCX needed** | G0/G1/G2/G3/G4 for each report | G6 + Power BI negative controls |
| **`word-docx` (optional)** | At least one actual DOCX; no PBIP subject | G0/G1/G5 for each document | G6 + Word negative controls |
| `combined` (legacy default) | Two unrelated PBIPs **and** DOCX | All applicable G0–G5 | G6 + union of negatives |

Pass `release_scope` explicitly in a programmatic
`run_acceptance(record, evidence_store)` request. A missing scope retains
the **old combined behavior**, avoiding silent changes to existing
records. Invalid scope blocks; mixing DOCX into `powerbi-core` (or
PBIP into `word-docx`) fails; each scoped suite digest includes its
component name so evidence cannot be replayed across profiles.
**This is not a new CLI subcommand.**

The report/data/capture/review engines do not yet publish full trusted
G2/G4/G5/G6 producer evidence. `vqs.check/1` can attest **G0 only**,
and no independent reviewer or owner promotion publisher is registered;
these scopes make release boundaries correct, not artificially green.

For any mandatory criterion: `pass` requires directly relevant current evidence; `fail` means a demonstrated violation; `blocked` means environment/capability/required data prevents testing; `not_run` has no evidence; `not_applicable` needs stated legitimate reason. `unknown` is a diagnosis state, not a release verdict. Mandatory `blocked/not_run/unknown` precludes G6 approval; optional unsupported features appear in feature matrix and must not be marketed as tested. A static unit-test pass cannot satisfy a Desktop render or Word pagination gate.

## 2. Portable contracts, ledger and orchestration (WP-00..02)

| Test ID | Stimulus / fixture | Expected observable result | Gate |
| --- | --- | --- | --- |
| CORE-01 | PBIR and DOCX artifacts with distinct source revisions | stable typed surface-specific IDs, hashes and provenance; no collisions | G0 |
| CORE-02 | Source changed after image/review; image hash matches old revision | stale image/review rejected, not green | G0,G2 |
| CORE-03 | Two agents claim same artifact or Desktop PID | second claim refused/queued, no cross-report capture | G0 |
| CORE-04 | Kill runner between event write and index commit | run replay preserves previous events; incomplete attempt becomes blocked | G0 |
| CORE-05 | Missing capability, timeout, unsupported major schema | explicit blocked with missing capability and rerun action | G0 |
| CORE-06 | Same model edits and approves its own candidate | independent reviewer requirement fails | G6 |
| CORE-07 | Raw evidence contains secret, real data screenshot, username or cache | pre-publication leak check blocks commit/issue attachment | G0 |
| CORE-08 | Old `vqs inventory` and request-review usage | contract upgrade preserves documented existing behavior or documents migration with tests | G0 |
| CORE-09 | Issue marked closed, tests failed, no evidence manifest | ledger cannot become verified by issue state alone | G0,G6 |

## 3. Power BI real data and source facts (WP-03,05)

| Test ID | Stimulus / fixture | Expected observable result | Gate |
| --- | --- | --- | --- |
| PBI-01 | Scratch PBIP opens without `cache.abf`, visuals blank | data readiness fails/blocks despite valid PBIR and screenshot | G1 |
| PBI-02 | Scratch PBIP with cache, fresh refresh fails | first-open populated recorded separately; reproducible refresh is failed/blocked, not silently passed | G1 |
| PBI-03 | Live DAX returns 1,440 rows for synthetic model but rendered card blank | data/view discrepancy emitted for exact measure/filter and visual; no false pass | G1,G2 |
| PBI-04 | Two identical report filenames in different Desktop PIDs | exact PID + canonical path required; wrong target fails | G0,G1 |
| PBI-05 | Unsaved Desktop state or external PBIR edits while open | Initial strict saved-file attestation blocks dirty; an already-attested native interaction may *observe* a dirty terminal UI only when unchanged source hashes/timestamps and same live PID/Bridge/report/model are verified. Terminal dirty remains `status=blocked` for a **new** saved-file attestation; source drift or host change always blocks/fails the interaction. Do not reopen repeatedly solely to clear an interaction-induced dirty flag | G0,G4 |
| PBI-06 | Scale-2 screenshot viewport differs from scaled scale-1 coordinates | entire canvas includes right slicer and table; invalid crop fails calibration | G2 |
| PBI-07 | Page count/order or PNG hash differs from capture manifest | stale/incomplete render rejected for whole-report gate | G0,G2 |
| PBI-08 | Filter/role differs between DAX oracle and report view | answer comparison blocked or re-executed under equal data scope; not directly compared | G1,G4 |
| PBI-09 | Unknown effective theme property or dynamic conditional color | provenance `unknown` or measured rendered observation, never invented theme literal | G2 |
| PBI-10 | Structurally valid PBIR rejected by Desktop on open | candidate fails acceptance regardless of schema-only tests | G1,G4 |

## 4. Design and analytical truth (WP-06,07,10)

| Test ID | Stimulus / fixture | Expected observable result | Gate |
| --- | --- | --- | --- |
| DES-01 | Numeric X-axis values distinct but both format as `10%` | verified distinctness defect with actual values and formatted labels; not fabricated from pixels alone | G2 |
| DES-02 | Five categories in scrollable plot, four visible | category visibility defect when all five required, before/after count checked | G2,G4 |
| DES-03 | Proper large-text/small-text/essential-mark contrast vs deficient variants, including expanded native slicer checkboxes | resolved foreground/background/alpha checked with appropriate thresholds and applicability; check minimum 3:1 for functional icons in both unselected and selected live states. A source-managed `selectionIcon.color` patch alone is engineering evidence, not live G2 approval | G2 |
| DES-04 | Positive value green on page A, same state red on page B without declared semantic reason | cross-page semantic-color inconsistency localized; brand/profile overrides respected | G2 |
| DES-05 | Plausible-looking bar with misleading baseline, units or denominator | semantic/encoding finding using real underlying measure and filter | G1,G2 |
| DES-06 | Aesthetic reviewer alleges slicer clipped but full-canvas render shows fully visible | unsupported reviewer claim contested/rejected; no unjustified PBIR edit | G2 |
| DES-07 | Scatter transformed to ranked bar while user story requires correlation | plan rejected/needs owner intent approval; not treated as cosmetic success | G3,G4 |
| DES-08 | No date/target/causal evidence, automatic story generator proposes trend/target/causal claim | corresponding story not applicable/needs clarification; never fabricate metric/causation | G1,G4 |
| DES-09 | Equivalent source answer but different RLS, period or category filter | apparent equality cannot pass question oracle without same scope | G4 |
| DES-10 | No configured image-capable provider or no opt-in for private screenshot upload | perceptual mandatory gate blocked; no substitution of text-only reviewer | G2 |
| DES-11 | Source inventory declares no table/matrix; image reviewer emits matrix PASS | reclassify as source-verified `not_applicable`, report separately, do not increase passed check count; a contradictory matrix FAIL is blocked, not silently discarded | G2 |

## 5. Repair and no-regression (WP-09,10,11)

| Test ID | Stimulus / fixture | Expected observable result | Gate |
| --- | --- | --- | --- |
| FIX-01 | Allowed theme/axis change in disposable PBIP | exact approved property changed, source diff/rollback recorded, original byte-identical | G3 |
| FIX-02 | AI repair plan tries to run shell command or mutate unrelated DAX/RLS | allowlist rejects plan before execution | G3 |
| FIX-03 | Resize chart resolves duplicated tick but crops the adjacent action table | re-render whole page detects regression and refuses candidate | G4 |
| FIX-04 | Chart conversion eliminates original defect but hides fifth brand in scroll | category visibility oracle fails; candidate rejected | G4 |
| FIX-05 | Change removes defect but alters data fields/filter/answer | same-question oracle fails; require explicit approved semantic change | G4 |
| FIX-06 | Visual still references old source screenshot after edit | capture hash mismatch invalidates prior review; regenerate crops every iteration | G2,G4 |
| FIX-07 | Three repair retries all fail | bounded run terminal fail/blocked with full attempt history, no auto-approval | G4 |
| FIX-08 | Attempt to write to original PBIP or promote without owner approval | write guard blocks and original digest unchanged | G3,G6 |
| FIX-09 | Two independent PBIPs with different chart/data/layout | same typed repair API works when supported; unsupported feature handled explicitly | G4,G6 |

## 6. Optional Word component and cross-artifact truth (WP-04,08,11)

**G5 is not mandatory for `powerbi-core`**. It is mandatory only when
accepting `word-docx` or the historical `combined` profile.
For a standalone DOCX derived from Power BI, embedded figures must be
bound to an attested Power BI source revision; that link does not force
the full Power BI artifact into Word's separate acceptance subject set.

| Test ID | Stimulus / fixture | Expected observable result | Gate |
| --- | --- | --- | --- |
| DOC-01 | DOCX OOXML valid but last heading orphaned on page | actual page renderer catches; structure-only pass insufficient | G5 |
| DOC-02 | Table header splits from data row or across section break | report page+object location; constrained repair rerenders every affected page | G5 |
| DOC-03 | Embedded report image old, report PBIR recently repaired | figure hash/source provenance mismatch; mandatory cross-artifact fail | G5 |
| DOC-04 | Figure/caption uses wrong measure or units | expected report question/metric comparator fails | G1,G5 |
| DOC-05 | Missing font changes page count or creates clipping | backend/font environment recorded; render blocked/failed for intended target | G5 |
| DOC-06 | Same DOCX paginates differently in LibreOffice and interactive Word | explicit backend compatibility finding; do not claim Word-exact acceptance from LibreOffice output | G5 |
| DOC-07 | Rendered PDF contains blank/duplicate/missing page | page inventory mismatch fails | G5 |
| DOC-08 | One paragraph/style repair fixes a widow but creates a near-empty next page | independent whole-document re-review rejects regression | G5 |
| DOC-09 | Document generator has no associated current report revision | report-consistency mandatory gate blocked; standalone DOCX gate can remain separately assessed | G5 |
| DOC-10 | User DOCX contains macros or external linked resources | process under restricted policy, reject unsafe active content/external fetch unless expressly approved | G0,G5 |

## 7. Release acceptance: what independent verifier must hand back

Evidence set for **each** of the two unrelated PBIPs: source/ref digest and report open path/PID, model definition+authorized data scope and live answer samples, first-open+refresh assessment, all-page native render inventory and calibration, actual design findings with source refs, candidate source diff, fresh all-page/crop revision, unaffected neighbor/category coverage, supported user-task answers and limitations, negative tests, reviewer/editor separation, structured pass/fail/blocked matrix. **No raw private sample data should be committed to Git.**

For the **Power BI core**, the two unrelated PBIP evidence sets above
are mandatory and **DOCX evidence is not required**. For the **optional
Word component**, evidence for each generated DOCX consists of exact
DOCX hash, renderer/locale/font inventory, actual page count and
all-page PNG hashes, OOXML section/style/figure refs, linked report
image source hashes if the document contains report figures, paginated
defects and narrow repair diff, final all-page rerender, and independent
page/prose/figure review. The historical combined suite still needs
both classes.

Before closing [#16](https://github.com/analienx/visual-quality-system/issues/16),
independent verifier must answer **for each selected component
profile**: (1) Are all its mandatory gates passing on pinned source
versions? (2) Which tasks and states were actually exercised?
(3) Did the actual report or DOCX improve without corrupted
answers/figures? (4) Is an unsupported capability presented as tested?
(5) Can results be reproduced in a clean permitted environment?
(6) Are privacy, rollback and owner promotion requirements met?

A failure remains a failure until a new explicit run passes. An untested interaction can be declared out of first-release scope only in the owner-approved capability matrix; it cannot silently receive a pass.