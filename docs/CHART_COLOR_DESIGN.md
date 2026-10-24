# Chart palette design review — researched color systems

**Status:** implemented as curated, dark-background adaptations in VQS
issue #80. Exact output still requires GitHub-hosted authoring and real
Desktop screenshot confirmation before G2/G6 release signoff.

## Credible design references (and what is not claimed)

- **Cynthia Brewer's ColorBrewer**: Brewer received the International
  Cartographic Association 2023 Carl Mannerfelt Gold Medal; color scales
  originated from cartographic perceptual research. Award attribution
  concerns her work, *not these new VQS color combinations*.
  https://cartogis.org/2023/09/29/dr-cynthia-cindy-brewer-receives-ica-carl-mannerfelt-gold-medal/
- **IBM Carbon**: an award-winning design-system family, with curated
  categorical sequences in light/dark and neutral layer hierarchy. Carbon
  explicitly says order should maximize neighboring color distinction.
  https://www.carbondesignsystem.com/building-blocks/data-visualization/color-palettes
  https://ifdesign.com/en/winner-ranking/project/carbon-for-ai/688500
- **Tableau 10**: Maureen Stone and Cristy Miller redesigned palettes
  to balance usability, legibility and beauty.
  https://www.tableau.com/blog/colors-upgrade-tableau-10-56782
- **Paul Tol**: tested qualitative bright/muted schemes intended to
  retain distinguishing cues under color-vision deficiencies. VQS uses
  this work as *guidance*, not exact Tol swatches or a CVD certification.
  https://sronpersonalpages.nl/~pault/
- **Datawrapper**: never use sequential ramps for nominal categories;
  use luminance progression for ordered numeric values; avoid too many
  simultaneous categories and always retain legends/direct labels.
  https://www.datawrapper.de/academy/what-to-consider-when-choosing-colors-for-data-visualization
- **Microsoft Power BI**: a theme's ordered dataColors apply to chart
  series. Explicit visual formatting overrides that default; hence
  existing PBIR numeric FillRule stops also need source-bound conversion.
  https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes

These VQS palettes are **original adaptations informed by the above
design research**, not copies of award-winning artworks, not award
winners themselves, and not formally evaluated under all kinds of CVD.

## Four dark chart identities

The white/light preset is deliberately unchanged. The same applies to
canvas/card/text/interaction tokens for the four dark styles. We change
only eight ordered chart category colors and the sequential color ramp:

| Dark preset | Data category colors (ordered) | Numeric min → mid → max |
| --- | --- | --- |
| Executive Blue | #78A9FF, #3DDBD9, #BE95FF, #FFB784, #FF7EB6, #A7F0BA, #F1C21B, #82CFFF | #46688D → #76A9D8 → #C5E0F7 |
| Graphite Mint | #80CEB9, #E0B77D, #A6AEE1, #C0D287, #DA9AA4, #83BCD8, #D2B4B7, #A9B8BD | #4E786E → #7EBBAA → #C1E5D8 |
| Warm Basalt | #E1B37C, #79BBAE, #D58C70, #BAD083, #93B7CF, #D8A1B9, #CABCA3, #B2A1CA | #866D52 → #C4A075 → #E9CEA3 |
| Slate Lavender | #B6A0E9, #7ABCE1, #D99DC5, #8FC2A9, #E1BF91, #BDD38E, #DCA39A, #D6CBDE | #736890 → #A89AD5 → #DED1F2 |

Interpretation: Executive uses IBM-style cool blue/teal with distinctive
warm secondary categories; Graphite Mint anchors soft sea-green with
wheat, periwinkle and coral; Warm Basalt uses amber/copper/sage with
muted mineral accents rather than saturated cyan/purple; Slate Lavender
anchors violet/periwinkle with dusty rose/seafoam and light gold.

**Usage rules:** single-series chart = category[0]; categorical lines
and bars follow the eight-color ordered array; numeric bars and Shape
Maps use the sequential value ramp *only when a numeric bound exists*.
The converter preserves measure identity, thresholds, dynamic business
predicates, per-category selectors and waterfall polarity fills.

## Automated design gates

GH-hosted tests enforce: 8 unique series, ≥3:1 nontext chart-to-card
contrast on all series, CIELAB ΔE76 ≥20 among first four series and
≥15 for any pair, 2.8:1 visibility of the darkest gradient stop,
strictly increasing ramp luminance, unique first-category and ramp
identity among presets, unchanged light mode, and Contoso fixture
gradient mapping without altering Conditional business rules.

These numeric checks are *necessary but not sufficient*. CIE76 distance
does not guarantee perceptual harmony, semantic fidelity, color-vision
accessibility or legend legibility at small sizes. Repeat Desktop
captures/independent QC before publishing claims of visual acceptance.
