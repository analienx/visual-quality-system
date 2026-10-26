# Engineering update · 26 October 2026

**Visual Quality System — Power BI first · engineering preview · not a production release**

**Status: integrated to `main`, green hosted checks, but independent `powerbi-core` G2/G4/G6 remains open.** This is the latest consolidated engineering release note, not a GitHub Release, a new semantic version, or an authorization to deploy.

[Start with an AI agent](AI_AGENT_QUICKSTART.md) · [How autonomous repairs work](AGENT_AUTOFIX_ARCHITECTURE.md) · [Real Power BI showcase](REAL_THEME_SHOWCASE.md) · [Full changelog](../CHANGELOG.md) · [Release acceptance #16](https://github.com/analienx/visual-quality-system/issues/16)

## What changed for users

| Change in `main` | User benefit | Verified merge |
| :--- | :--- | :--- |
| **Agent-first experience and premium README** | New users can discover VQS through a single *fix my report* prompt, local MCP or CLI configuration, concrete limits, and a clear component diagram | [PR #85](https://github.com/analienx/visual-quality-system/pull/85) · [`c36a7e1`](https://github.com/analienx/visual-quality-system/commit/c36a7e189f232d83fc80e76a8970a8536b3fc3a8) |
| **Power BI Desktop source attestation** | Opt-in fail-closed source-identity check before strict live DAX and Windows UIA, to avoid attributing evidence to the wrong report | [PR #83](https://github.com/analienx/visual-quality-system/pull/83) · [`48757e5`](https://github.com/analienx/visual-quality-system/commit/48757e570da52f465a2f69b6479c8b230d4a1e77) |
| **14 adaptive theme families in both Light and Dark** | Reversible PBIP candidates plus genuine, source-bound native screenshots across **28 modes** and their categorical/control colors | [PR #81](https://github.com/analienx/visual-quality-system/pull/81) · [`9770a52`](https://github.com/analienx/visual-quality-system/commit/9770a52f934daf45c72b1081e11b87009f95ea0b) |
| **PBIPDocumenter engineering consumer guide** | Fail-closed source-review integration, bounded packaging parity and an independent Word scope; no production migration claims | [PR #84](https://github.com/analienx/visual-quality-system/pull/84) · [`8aade94`](https://github.com/analienx/visual-quality-system/commit/8aade94a944ec85d2c2aab3f50b79572cf5ac10e) |
| **Post-merge documentation reconciliation** | Accurate theme-engine/gallery/changelog state on `main`, without losing earlier engineering provenance | [PR #82](https://github.com/analienx/visual-quality-system/pull/82) · [`a80e414`](https://github.com/analienx/visual-quality-system/commit/a80e414a6a56f9c07cb952926fb831ffa583e25b) |

### The default agent workflow

Ask an authorized coding agent to *fix supported quality issues* rather than merely enumerate findings. The existing coordinator can inspect actual PBIR/TMDL source, synthesize **allowlisted typed** repairs, apply them to an isolated candidate, verify the diff and remeasure. The agent can explain the outcome as **Fixed / Verified / Still blocked**.

```console
vqs run "path/to/Sales.Report" --mode repair --scope static --run-root "./private-vqs-runs" --run-id "sales-autofix-001"
```

This is **source-level candidate fixing**. It does not promise that every defect is automatically fixable, that every report passes native Desktop checks, or that the original report is ever silently overwritten. Microsoft's authoring validation, rendered-page evidence, live DAX and selection checks remain separate gates. Promotion and production certification need explicit approval.

The project README now directly links both the [five-minute agent setup](AI_AGENT_QUICKSTART.md) and [the full component architecture](AGENT_AUTOFIX_ARCHITECTURE.md). Its homepage keeps the seven real featured theme Light/Dark pairs with a dedicated 14-family gallery.

### Verification evidence and scope

- **Themes:** source preflight **28/28**; **140** real Desktop full-page captures across five pages per mode; **364/364** documented native chart/closed-dropdown/legend pixel checks; **56** public WebP previews plus SHA-256 provenance. These numbers apply to the **default-state synthetic Contoso gallery**, not cross-report usability certification.
- **Loaded-file guard:** tested wrong-PBIP/PID, ambiguous Bridge registry, changed source, unsaved state and `datasetReference.byPath` model identity; supported strict DAX/UIA refuses unproven identity. The native disposable saved-state positive remained **blocked** because Desktop reported `hasUnsavedChanges=true`; no positive attestation or interaction acceptance was fabricated.
- **Agent quickstart/README:** MCP startup, tool discovery, actual synthetic report inspection, homepage artifact links and **all 14 featured Light/Dark image links** were checked. The final docs PR passed Windows/Linux CI, Microsoft report-authoring workflow and R6 oracle. This is **engineering integration evidence**, not independent G2/G4/G6 review.
- **Corporate Spend:** a private diagnostic experiment derived **two** missing schema declarations and **five** missing native field references from existing PBIR source, reducing the Microsoft CLI's **13 baseline errors to six** without touching original report/model data. Five named `midColor` and one outer-padding validator mismatch remain unresolved; Azure Maps sign-in is a distinct native-report blocker. **No candidate from this experiment has been certified or merged.**
- **Consumer integration:** [merged PR #84](https://github.com/analienx/visual-quality-system/pull/84) ([`8aade94`](https://github.com/analienx/visual-quality-system/commit/8aade94a944ec85d2c2aab3f50b79572cf5ac10e)) now delivers the pinned standalone consumer guide, fail-closed result validation and installed-package contract. On two unrelated source projects, the VQS/PBIPDocumenter source inventories match exactly by page, visual and field binding. **Actual consumer migration, native outcome parity and rollback are still open in #17**, and independent G2/G4/G6 remain separate.

## Open decisions and release boundaries

| Area | State | Why |
| :--- | :--- | :--- |
| Adaptive Light/Dark **feature implementation** | **Merged / issue #80 closed** | Owner-approved feature is implemented with source-bound default-state evidence. |
| Independent **Power BI** G2 and G4 | **Open in [#16](https://github.com/analienx/visual-quality-system/issues/16)** | Requires real populated appearance and supported controls/DAX evidence on two unrelated PBIPs, including dynamic Light/Dark states where relevant. |
| G6 **production-release authorization** | **Not granted** | Needs an independent reviewer and explicit owner/publisher decision, beyond a successful PR merge. |
| PBIPDocumenter **consumer deployment parity** | **Open in [#17](https://github.com/analienx/visual-quality-system/issues/17)** | Source inventory parity exists; clean-host native parity, rollback and consumer migration remain separate. |
| Optional **Word/DOCX** component | **Separately scoped [#13](https://github.com/analienx/visual-quality-system/issues/13)** | Word pagination/output review must not block Power BI-only engineering integration. |

**No production tag or GitHub Release was created by these merges.** The last dated [21 October engineering notes](RELEASE_NOTES_2026-10-21.md) and [24–25 October theme history](RELEASE_NOTES_THEME_2026-10-24.md) are retained as historical snapshots. For the current product-facing state, use this 26 October summary plus the issue tracker.