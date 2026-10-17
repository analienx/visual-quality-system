# VQS 2.0 — No-login Contoso country map replacement

**Date:** 2026-10-17
**Status:** Verified candidate only; no original report edits or release approval.

## What was actually replaced

The obsolete Bing Maps visual on the `Deep-dive insights` page,
`definition/pages/d9bc3b8f90439bcc/visuals/sales-by-country/visual.json`,
is replaced with Microsoft's built-in **Shape Map** using native
`Dim Store.Country` and `Fact Sales.Reporting Year Sales` fields.

The custom world geography is versioned at
`assets/maps/world-countries-110m-vqs.topojson` (ISC licence). The
PBIR points to immutable commit `3c3120cae5c50cf37f611446c76b258cf40bc1fe`;
the custom map has been adjusted so *United States* matches
Contoso's model rather than *United States of America*. The other
four countries are Canada, United Kingdom, Germany and Australia.

The rendered design uses a pale-to-deep blue sales intensity gradient,
preserves the title/position/frame, and requires **no Microsoft 365,
Azure Maps or organizational account**. **An internet connection is
required to retrieve the public GitHub TopoJSON URL.**

## Complete candidate

- Full report + semantic-model ZIP:
  `tests/fixtures/contoso-retail-no-login-shapemap.zip`
- Machine-readable fixture receipt:
  `tests/fixtures/contoso-retail-no-login-shapemap.manifest.json`
- Exact tested visual JSON:
  `assets/maps/contoso-sales-country-shapemap-visual.json`
- Command:
  `python scripts/migrate_contoso_country_map.py <original-project-dir> <fresh-candidate-dir>`

This migration refuses to overwrite existing output, rejects mismatched source
visuals, validates field bindings and geography keys, and requires an exact
known Contoso baseline. It never mutates the source or changes model contents.

## Verified evidence

**Microsoft's real authoring CLI 0.5.0:** 0 errors and 0 warnings on the
candidate. Source baseline: 0 errors and 1 legacy-Bing warning.

**Live Power BI Desktop:** independently opened run-owned candidate with
populated Modeling MCP readings (Dim Customer probe 12 rows); screenshot
on `Deep-dive insights` showed rendered world-country outlines and
sales-driven shading, no login prompt, and normal neighboring KPI/chart
values. Private screenshot:
`C:\Workspace\scratch\vqs-shapemap-offline-20261016\world-all5-gradient-fresh\d9bc3b8f90439bcc.png`.

**Code and scope:** 11 focused acceptance/refusal tests; single permitted
PBIR visual file change; complete sample includes 5 pages, 54 visuals,
and the original model cache. Machine-local settings excluded.

## Important limitations and honest acceptance

Shape Map is **still labeled preview** by Microsoft. It works, is documented,
and is available without authentication, but this is *not* a claim of
general-availability support. It shades *regions* rather than using
bubble size, so the original Bing map design is intentionally changed.

A separate trial authored a Microsoft-certified Deneb map with all geography
inline and unchanged source fields. In a fresh Power BI Desktop session the
visual could not run: Desktop displayed *To see this custom visual, add it to
this report first*. That route requires proper custom visual registration
before migration; no broken Deneb candidate is shipped.

No claim yet for automated interactive cross-filter behavior, tooltip
value exactness under changed year filters, Power BI service export,
or general release/promotion readiness. The release gate stays blocked
until independent checks are performed.

## Further engineering direction

For fully generally available/certified delivery with no sign-in, investigate
loading the **certified** Deneb package through an authorized report import
procedure, using an inline geography and dynamic Country/Sales bindings.
It supports Power BI export and does not require external services, but
the custom visual needs to be registered first. Do not switch to the
uncertified standalone edition, or to unsupported raw `visualType`
substitutions, merely to silence validation warnings.
