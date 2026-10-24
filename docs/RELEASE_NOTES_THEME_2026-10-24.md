# Adaptive Power BI themes · release candidate · 24 October 2026

**Status: PR [#81](https://github.com/analienx/visual-quality-system/pull/81)
remains DRAFT and unmerged.** These are engineering candidate notes,
**not** a production release, independent G2 visual signoff or G6 merge approval.
The previous [21 October Power BI core notes](RELEASE_NOTES_2026-10-21.md)
remain valid for the code already in main.

## What is ready

- 14 **new approved** palette families × paired Dark/Light = **28** modes.
  They supplement four legacy families, giving 18 selectable identifiers
  without breaking the original default behavior.
- Reversible `vqs theme inspect/preview/apply/audit`, candidate confinement
  and manifest/source/model integrity invariants.
- Report/page/filter-card/slicer appearance plus deterministic categorical
  chart series, the unscoped wildcard chart fills observed in actual Desktop
  evidence, and supported numerical `linearGradient2/3` color stops.
  Bound business measures, filter selections, conditional thresholds and
  positive/negative meaning remain unchanged.
- Hosted CI, R6 and Microsoft official authoring validation for the exact
  feature head `db41011db7cd84452244f7e1e25e69aac45fb8e4` **passed**
  on 24 October 2026. Microsoft authoring validated **28 generated five-page
  Contoso PBIP candidates**; it does not evaluate pixels.
- [28 token-accurate design simulations](APPROVED_THEME_LIBRARY.md)
  and [25 genuine existing Desktop captures](THEME_GALLERY.md) are
  clearly separated, with provenance. The latter are *older colorways*.

## Finite remaining acceptance gates

1. **G2 native appearances:** capture and independently review both modes
   of representative new presets (especially Organic Palette, Sunny Palette
   and Graphite Red), then cover remaining themes to the approved extent.
   Check actual category differentiation, text, legends, density, gradients,
   card padding and map behavior—not just token contrast.
2. **G2 interactions:** verify expanded slicer dropdown, search, filter pane
   (Available/Applied) and selection states in actual Power BI Desktop.
3. **G6 release signoff:** separate owner approval after independent evidence
   review; PR must stay draft/unmerged until then.

**Known limits:** An official report-theme schema pass is not a Desktop pixel
pass; embedded images and opaque/custom visuals are not magically recolored.
Microsoft's pinned authoring validator rejects some global filter-pane theme
defaults, so the candidate applies supported page-level properties instead.
Real flyout styling still needs native review. Azure Maps sign-in limitations
of the separate Corporate Spend sample are not repaired by theme changes.

**Source integrity:** No company affiliation is asserted for the original
generic Organic Palette or Sunny Palette. Rewriting a feature branch and
deleting older Actions runs removes reachable advertised names but cannot
guarantee GitHub server-side garbage collection of unreachable commits.
