# Power BI repair and acceptance evidence — 22 October 2026

**Issues [#14](https://github.com/analienx/visual-quality-system/issues/14) and [#16](https://github.com/analienx/visual-quality-system/issues/16).** This is an engineering candidate witness, **not** independent G2/G4/G6 production approval. Word/DOCX is separately scoped.

## Native before/after: exact fictional Contoso report

The archived pre-repair report and the generated typed-repair candidate were both opened in **separate, disposable Power BI Desktop instances** with the **same self-generated, populated semantic model**. The original archive stayed unchanged.

| Evidence | Before | Repaired candidate |
| --- | --- | --- |
| Report-tree SHA-256 | 5cbee9f77c1eeb033875317b9b70b8525360df0b93b8d68e7ee7383189dc0d48 | 5853e2894762cc7cb458cdc242479e4f71791e2939da63413e14ca48594f13e6 |
| Report/model source SHA-256 | 0aabd401d0fb2973263a77faa8349b552e7a74325b3154499c0aeef40d29bdc3 | 5cec4526f39bf0b40673603feeb8d1a3d6e9fbf28c4d850a28ed09772129363e |
| Semantic TMDL identity | identical | 82375f803829b1abbd348036083a9c3e722176d878d7a3eb0ca50f280d444e7b |
| Layout composition rule | **fail** | **pass** |
| Real populated Desktop images | 5/5 pages, 5/5 verified report-only crops | 5/5 pages, 5/5 verified report-only crops |

The **13 preconditioned typed operations** changed **eight visual-definition files**, retained DAX and chart field bindings, and passed candidate confinement checks. Microsoft Report Author CLI found **zero errors and zero warnings**. The measured difference is a removed redundant Year title, shorter KPI row and better aligned country map / channel / regional-sales panels. The raw baseline and repaired Desktop PNGs remain private for independent visual review.

**Private repaired bundle:** Independently verified using the existing VQS bundle verifier. Bundle SHA-256: e0964ceed2d9c7cd4c47e354f1dd4acb169f9c7e606a8cd92c33c19f6ab2c2fa. The review-image basis is **verified_canvas**, five images at 3072 × 1728 physical pixels and 12/5 effective page scale. This certifies pixel transport, **not** aesthetic quality.

**Actual data and interactions:** Repeated Modeling MCP DAX readiness passed. Four-year live DAX oracle passed; Sales = **6,820,496.73** at All and **6,200,451.60** at 2024. A separate real .NET UIA recorder performed **9/9 Year/Region actions** and matched displayed KPI/region values to DAX, restoring All. The associated runner fix also restores the visible Year flyout to **Collapsed** after selecting a year; live 2024→All selection passed with $6.20M→$6.82M and 105 focused tests passed.

### A deliberately blocked approach

The first candidate opened with an unpopulated model: VQS **refused capture**. After refreshing, native Desktop **Save** rewrote extra report metadata/resources outside the eight approved files, so that saved report was **not** accepted as a confined candidate. A new pristine typed candidate was instead opened with only a matching, refreshed *fictional model cache* copied privately; its report tree retained the exact planned SHA-256 and its TMDL digest matched the source. This second clean Desktop instance provided the verified capture. No unapproved Power BI rewrites were whitelisted or committed.

## #14 versus #16: release gates

| Gate | Current proof | Remaining |
| --- | --- | --- |
| G0/G1 | Source and model identity, populated data, two distinct clean Desktop report subjects | Engineering proof, not third-party signoff |
| G2 | Real full-page images and source-bound report-only crops for before and after | **Blocked:** separate authorized reviewer must inspect visual quality, clipping, map and adjacent panels |
| G3 | Literal-old preconditions; 13 typed ops; eight-file confinement; untouched source; Microsoft validation | Bounded Contoso repair proven. No generalized template-replacement capability claimed |
| G4 | All/2023/2024/2025 DAX oracle, 9/9 real Year/Region UIA events and restoration | **Blocked for complete scope:** general Shape Map country interaction and separately reconciled loaded-file authority |
| G6 | Source-hashed evidence transport and two distinct PBIP engineering subjects (Contoso + Corporate Spend) | **Blocked:** independent reviewer, separate owner/publisher authorization, Corporate Spend clean-canvas and Azure Maps sign-in limitations |

## Independent reviewer handoff

1. Transfer the **private**, real baseline and repaired review bundles through an authorized channel. Re-run VQS bundle verification against the exact local report sources and compare all five report-only images at the same data/filter context.
2. Inspect the actual repaired Deep-dive and neighboring four pages for readable glyphs, map content, alignment, legend/card hierarchy, rows and totals. Never turn an implementer's visual observation into G2 signoff.
3. Re-run the signed DAX and Year/Region interaction checks, confirm the restoration and exact source/loaded-file identity, and independently inspect the structurally unrelated Corporate Spend PBIP. Treat unsupported country Shape Map access and Azure Maps sign-in as visible limitations requiring an explicit scoped decision.
4. Record a reviewer identity **different from the implementer** and a distinct, authorized G6 owner/publisher decision. A model-generated aesthetic judgment or green CI alone is not that authority.

**Privacy:** High-resolution PNGs, ABF caches, model/session endpoints, JSON interaction receipts and machine-specific paths stay outside this public repo. This handoff does not grant remote-image upload consent.
