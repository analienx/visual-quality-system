# Public showcase provenance

**Actual checked-in report:** [Contoso Retail.pbip](../../../examples/contoso-retail/Contoso%20Retail.pbip) · [reproduction and refresh instructions](../../../examples/contoso-retail/README.md).

**All five previews were regenerated from the corrected, source-identical PBIP on 22 October 2026**, using fresh native Power BI Desktop captures with populated fictional semantic data. Report source SHA-256: `37f812d1fdae338f82c7e1046d6771fa7451d664ff375f66e2331f261c670eca`. The TMDL model remains identical; the two measure bindings in the customer table are unchanged. Only the visual presentation labels were shortened to make the last row and total fully readable.

The five original 3915 × 2394 Desktop captures were each measured and cropped to the report-only canvas at x=0, y=334, width=3072, height=1728, then resized to 1600 × 900 WebP preview. All private raw native Desktop PNGs, per-process identifiers, semantic model caches and machine paths remain outside Git. These illustrations are not release acceptance certificates or a VQS application interface.

| Native page | Preview | Public WebP SHA-256 | Size |
| --- | --- | --- | ---: |
| Executive overview | [executive-overview.webp](executive-overview.webp) | `772c675561c63a2545166d992afa97f238575f2efab4e9020685a9b8f737baf3` | 54 KiB |
| Products & brands | [products-brands.webp](products-brands.webp) | `75ac73745b2bb598f0562dae180650ddfdf9a8af6f8915b4f9f87d823254bd55` | 66 KiB |
| Stores & customers | [stores-customers.webp](stores-customers.webp) | `4c0f0ee28832d9a8edafd6cd1fde76a73a322e955660a32fc759333c6ea7e191` | 58 KiB |
| Markets & drivers | [markets-drivers.webp](markets-drivers.webp) | `d9a4be5c749e1e3e9d878e548cec97c191188a6b6d9193b80a952845b4d758c6` | 49 KiB |
| Deep-dive insights | [deep-dive-map.webp](deep-dive-map.webp) | `8153b03b3e350d4040540c2f2a880b17457c1fdd8b59a7b2882df19accd8b635` | 54 KiB |

## Per-page render custody

The hashes below are SHA-256 of the **cropped report-only RGB pixel bytes** before WebP compression (not hashes of PNG container files). Original raw PNG hashes are retained in the private acceptance ledger.

- **Executive_overview**: `d2f52fd2fcb1e9d44a7262a15d10e3062dca7b2a9f6ae896cd6e836f9105a9fb` — Time trend, KPI signals and regional results.
- **Products_brands**: `df7fa02484c240e54c5be12ade5a7017ca4df4b5f57a9c6e88f8196c68e5c302` — Ranked products, category matrix and margin actions.
- **Stores_customers**: `7e962f5b91672252cd0b87cc14ef6647dd1aaee842e655440c3dfde9302d8042` — Readable customer segments, store sales, and two data matrices.
- **Markets_drivers**: `86053f62c46efebdaf36bde3c46798a7d991427c6c47cc67be23453516075f37` — Waterfall, channel sales and margin contributions.
- **d9bc3b8f90439bcc**: `63cad35eec9190725166d4b2856f7b1756acca27d1eededc07c487764f7cfb23` — No-sign-in Shape Map, channel donut and regional sales.

All content is self-generated fictional Contoso data. The visible data in the updated Stores & customers screenshot was independently checked on Desktop: Corporate, Consumer, Small Business and Total fit without scrollbars. Visual review remains separate from G4 interaction coverage and owner-controlled G6 release authorization.

The associated source digest and public files are asserted by `tests/test_public_showcase_example.py`.
