# Power BI G2/G4 corrective verification — 27 October 2026

**Status:** engineering fixes validated on real populated disposable Contoso; independent organizational G2/G4, unrelated Corporate Spend G4, unsupported map/tooltip decisions, consumer signoff and G6 production remain **BLOCKED**. This is **not** a production release.

## 1. The adversarial defects, not feature scope

The source-hashed native Saffron & Spruce Dark `Deep-dive insights` captured three **identical yellow** region bars. Its `clusteredBarChart` retained the `Dim Store[Region]` field but lost three category-scoped `dataPoint` selector entries. The corresponding approved fictional Light Contoso source still held a fully reviewed mapping: `Europe→ThemeDataColor(2)`, `North America→(3)`, `Asia Pacific→(4)`. This was source/visual acceptance FAIL; the gradient/dataColors tests alone had missed it.

The existing native Year/Region UIA sequence checked only Europe Sales under Year 2024. It explicitly skipped Units, YoY and GM in that state, so an 8/8-action PASS **did not equal** 4/4-KPI G4 coverage.

Finally, Desktop's genuine native Save reserialized the repaired categorical PBIR visual as semantically identical JSON but with different bytes. The default strict byte-only Save witness correctly BLOCKED until *pre-Save source bytes, not just a declared hash*, could be securely reconciled. No source age, dirty state, PID or matching semantic model gate was disabled.

## 2. Bounded source-grounded correction

`python -m scripts.restore_categorical_colors --reference "approved fictional same-query visual.json" --candidate "disposable candidate visual.json" --receipt "private JSON"`

- Requires exactly identical query and visual type, same bounded categorical field, two or more unique category selectors, and unique trusted theme slot IDs.
- Refuses any reference/candidate overlap, existing candidate category overrides, unknown selector, different query, or duplicate category color slot. **Does not mutate the reference** or invent semantic categories.
- **Only** an explicitly disposable copy is patched; separately run Microsoft authoring `validate` and verify the real Desktop image before promoting anything.
- The existing theme engine's PR #101 native `selectionIcon.color` support was applied through `vqs theme apply --mode dark --palette-preset saffron-spruce`, adding indicators for **all seven classic slicers** while keeping scoped category fills. A bounded *disposable-only* 120px → 80px Year slicer height adjustment addressed the Deep-dive excessive blank-space issue.

## 3. Four-KPI live Year=2024 + Region=Europe contract

The new independently pinned, literal DAX query `PINNED_REGION_EUROPE_2024_SHA256` queries **Sales, Units, YoY and GM** under both explicit `TREATAS` filters for Year 2024 and Region Europe. It uses the **same** OS PID, locally declared byPath model, and source hash as the four-year oracle; it validates the region Sales answer against the independent 2024 group subtotal. The native runner **refuses to execute any UI actions** if the query, all four values, model, source, PID, or Year/Region contract is absent/mismatched. During Europe selection it now checks **all four** rendered KPI readbacks. Negative tests alter each previously unchecked KPI.

Historical 8 actions plus 1 baseline are not mislabeled 9 actions. The country Shape Map remains unsupported, and the final interactive release verdict still blocks.

## 4. Native Save identity: very narrow semantic-equivalent rule

A real Windows UIA Save on one disposable PID may legitimately reserialize an otherwise unchanged PBIR `visual.json`. Before invoking native Save, `desktop_native_save` records **exact complete pre-Save UTF-8 visual bytes** in a private receipt. `desktop_native_provenance.verify` accepts a changed source **only if**:

1. Path is precisely `*.Report/definition/pages/<page>/visuals/<visual>/visual.json`.
2. The captured pre-Save bytes match the previously frozen inventory's **SHA-256 and exact byte size**.
3. Strict JSON decoding rejects duplicate keys/nonfinite values and the entire parsed structure (including field, sorting, filters, scoped selectors, formatting) is identical pre/post Save.
4. The same PID, process creation timestamp, sole Bridge report, declared local model and single Save `InvokePattern`, clean saved-state transition, source file set, unchanged model, strict allowed Save-time window, and live post-Save hashes+mtimes still agree.

**Any substantive visual/model/source edit, unverifiable previous content, duplicate key, NaN, forged pre-Save bytes, changed source outside the witnessed interval, wrong PID or dirty initial state still blocks.** Ordinary strict attestation without a real native-Save witness is unchanged; post-interaction dirty does not become a fresh saved file.

## 5. Private real evidence (NEVER commit images, model/cache or numeric receipts)

- Source-approved Dark fixed screenshot: `p1-dark-source-repaired-native-deep-dive-20261027.png`, native Power BI PID 34228; clearly distinct yellow / green / red bars. The *single* genuine Save reserialized only metadata and an exactly JSON-equivalent visual. The preserved earlier source and public fictional reference were byte-wise reconciled against **the original pre-Save SHA-256**, then strict OS/Bridge loaded-source attestation passed without reopening or falsifying timestamps.
- Fresh same-PID real Modeling MCP source-attested four Year states plus independent Region Europe four-KPI query: `p1-dark-repaired-pid34228-four-kpi-live-oracle-20261027.json`, `semantic=pass`, `region_scope_semantic=pass`.
- Fresh source-attested native 8 actual UIA actions plus baseline, **all four** Europe KPI equalities, same model/source and unchanged after-action source inventory: `p1-dark-repaired-pid34228-four-kpi-native-uia-20261027.json`; `native_uia=pass`, `interactive=blocked` (unsupported capability/independent G6).
- One final private disposable Saffron & Spruce Dark candidate combines the fixes, validates using Microsoft authoring **0 errors, 0 warnings**, and captures **actual Desktop** expanded Year list in unselected and Year 2024 selected states with matching UIA listitem checked-state. The 2024 white selected indicator and white unchecked outlines are clearly visible; region bars remain three distinct colors under both Year states. Before/after page capture SHA-256 hashes stored separately under private scratch, never committed.
- **No repeated cycling** of old report copies: PID 34228 performed the strict DAX/UIA evidence; only after completion was it closed by verified owned path, and final-only visual candidate PID 39748 was launched for expanded-state proof.

## 6. Test and release boundary

- Local full VQS regression suite (current branch): **2010 passed, 14 skipped**, 0 failures.
- Ruff (all changed files), mypy on the modified core modules, Git diff checks, Microsoft authoring validation and protected GitHub CI required before merging.
- Unrelated **Corporate Spend** native Sales Region select/clear/reset still requires source-bound, self-contained standardized receipt. Tooltip hover context and Shape Map country interaction remain unsupported unless separately and expressly excluded by the owner.
- Same assistant cannot pretend to be a separate human reviewer; signed independent G2/G4 and separate **owner/publisher G6** release decision remain open. **No release tag and no automated #16 closure.**

See [issue #16](https://github.com/analienx/visual-quality-system/issues/16), [#102](https://github.com/analienx/visual-quality-system/issues/102), [#17](https://github.com/analienx/visual-quality-system/issues/17).
