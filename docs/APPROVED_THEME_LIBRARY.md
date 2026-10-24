# Approved VQS theme library — 28 Dark/Light variants

**Approved:** all 14 families in both modes (28 variants). Additive presets; defaults unchanged.

> These 28 SVG previews are **design simulations generated from the actual packaged theme tokens, not real Power BI screenshots**. All sample numbers are fictional. A separate GitHub-hosted job validates 28 actual five-page Contoso PBIP candidates with Microsoft's authoring CLI and schema. Independent screenshots and UX acceptance are separate.

| Dark | Light |
| :--- | :--- |
| **#05 Okabe–Ito Night · Dark** | **#05 Okabe–Ito Night · Light** |
| [![Okabe–Ito Night Dark token preview](images/approved-themes/okabe-ito-night-dark.svg)](images/approved-themes/okabe-ito-night-dark.svg) | [![Okabe–Ito Night Light token preview](images/approved-themes/okabe-ito-night-light.svg)](images/approved-themes/okabe-ito-night-light.svg) |

| **#08 Petrol & Gold · Dark** | **#08 Petrol & Gold · Light** |
| [![Petrol & Gold Dark token preview](images/approved-themes/petrol-gold-dark.svg)](images/approved-themes/petrol-gold-dark.svg) | [![Petrol & Gold Light token preview](images/approved-themes/petrol-gold-light.svg)](images/approved-themes/petrol-gold-light.svg) |

| **#09 Indigo Ember · Dark** | **#09 Indigo Ember · Light** |
| [![Indigo Ember Dark token preview](images/approved-themes/indigo-ember-dark.svg)](images/approved-themes/indigo-ember-dark.svg) | [![Indigo Ember Light token preview](images/approved-themes/indigo-ember-light.svg)](images/approved-themes/indigo-ember-light.svg) |

| **#12 Arctic Aurora · Dark** | **#12 Arctic Aurora · Light** |
| [![Arctic Aurora Dark token preview](images/approved-themes/arctic-aurora-dark.svg)](images/approved-themes/arctic-aurora-dark.svg) | [![Arctic Aurora Light token preview](images/approved-themes/arctic-aurora-light.svg)](images/approved-themes/arctic-aurora-light.svg) |

| **#14 Mediterranean Terra · Dark** | **#14 Mediterranean Terra · Light** |
| [![Mediterranean Terra Dark token preview](images/approved-themes/mediterranean-terra-dark.svg)](images/approved-themes/mediterranean-terra-dark.svg) | [![Mediterranean Terra Light token preview](images/approved-themes/mediterranean-terra-light.svg)](images/approved-themes/mediterranean-terra-light.svg) |

| **#15 Saffron & Spruce · Dark** | **#15 Saffron & Spruce · Light** |
| [![Saffron & Spruce Dark token preview](images/approved-themes/saffron-spruce-dark.svg)](images/approved-themes/saffron-spruce-dark.svg) | [![Saffron & Spruce Light token preview](images/approved-themes/saffron-spruce-light.svg)](images/approved-themes/saffron-spruce-light.svg) |

| **#18 Autumn Editorial · Dark** | **#18 Autumn Editorial · Light** |
| [![Autumn Editorial Dark token preview](images/approved-themes/autumn-editorial-dark.svg)](images/approved-themes/autumn-editorial-dark.svg) | [![Autumn Editorial Light token preview](images/approved-themes/autumn-editorial-light.svg)](images/approved-themes/autumn-editorial-light.svg) |

| **#19 Violet Ice · Dark** | **#19 Violet Ice · Light** |
| [![Violet Ice Dark token preview](images/approved-themes/violet-ice-dark.svg)](images/approved-themes/violet-ice-dark.svg) | [![Violet Ice Light token preview](images/approved-themes/violet-ice-light.svg)](images/approved-themes/violet-ice-light.svg) |

| **#25 Electric Atelier · Dark** | **#25 Electric Atelier · Light** |
| [![Electric Atelier Dark token preview](images/approved-themes/electric-atelier-dark.svg)](images/approved-themes/electric-atelier-dark.svg) | [![Electric Atelier Light token preview](images/approved-themes/electric-atelier-light.svg)](images/approved-themes/electric-atelier-light.svg) |

| **#26 Riviera Pop · Dark** | **#26 Riviera Pop · Light** |
| [![Riviera Pop Dark token preview](images/approved-themes/riviera-pop-dark.svg)](images/approved-themes/riviera-pop-dark.svg) | [![Riviera Pop Light token preview](images/approved-themes/riviera-pop-light.svg)](images/approved-themes/riviera-pop-light.svg) |

| **#30 Bold Eclectic · Dark** | **#30 Bold Eclectic · Light** |
| [![Bold Eclectic Dark token preview](images/approved-themes/bold-eclectic-dark.svg)](images/approved-themes/bold-eclectic-dark.svg) | [![Bold Eclectic Light token preview](images/approved-themes/bold-eclectic-light.svg)](images/approved-themes/bold-eclectic-light.svg) |

| **#31 Graphite Red · Dark** | **#31 Graphite Red · Light** |
| [![Graphite Red Dark token preview](images/approved-themes/graphite-red-dark.svg)](images/approved-themes/graphite-red-dark.svg) | [![Graphite Red Light token preview](images/approved-themes/graphite-red-light.svg)](images/approved-themes/graphite-red-light.svg) |

| **#32 Organic Palette · Dark** | **#32 Organic Palette · Light** |
| [![Organic Palette Dark token preview](images/approved-themes/organic-palette-dark.svg)](images/approved-themes/organic-palette-dark.svg) | [![Organic Palette Light token preview](images/approved-themes/organic-palette-light.svg)](images/approved-themes/organic-palette-light.svg) |

| **#33 Sunny Palette · Dark** | **#33 Sunny Palette · Light** |
| [![Sunny Palette Dark token preview](images/approved-themes/sunny-palette-dark.svg)](images/approved-themes/sunny-palette-dark.svg) | [![Sunny Palette Light token preview](images/approved-themes/sunny-palette-light.svg)](images/approved-themes/sunny-palette-light.svg) |

## Use as real selectable Power BI presets

```console
vqs theme presets
vqs theme preview "examples/contoso-retail/Contoso Retail.pbip" --mode dark --palette-preset organic-palette --out organic-plan.json
vqs theme apply "examples/contoso-retail/Contoso Retail.pbip" --mode light --palette-preset sunny-palette --candidate-root ./sun-candidate
vqs theme audit ./sun-candidate
```

Each approved palette has source-identical files in `vqs/palettes/` and `examples/theme-palettes/`. See [the approved palette selection manifest](APPROVED_THEME_SELECTION.json).

## Original, independently named color families

**Organic Palette** is a balanced blue, teal, rose and green-based palette
with independently designed Light/Dark surfaces and ordered chart series.
**Sunny Palette** is warm amber-led, with deliberately contrasting teal,
violet, olive, coral and blue series. Both are original VQS design choices:
no company affiliation, endorsement, official template, or brand claim.

**Graphite Red** uses red highlights with neutral greys for other categories;
greys still need labels because hue-free categories are not reliably separable.
Genuine good/bad business meanings are protected from arbitrary remapping.

## Verification and limitations

- Twenty-eight real Contoso PBIPs with five pages each are generated and run through the official native authoring CLI, theme JSON schema, VQS candidate audit and source invariance checks by [the hosted library probe](../scripts/theme_approved_library_probe.py).
- Every series color meets >=3:1 contrast on the card surface; text/control roles pass VQS palette contrast checks. Categorical hue distinctness and small-label legibility still require native Desktop visual review.
- The original [five-theme real Desktop screenshot gallery](THEME_GALLERY.md) remains unchanged. Do not conflate this palette SVG gallery with those authenticated native captures.
- The PR remains draft; user approval authorizes implementation and feature-branch publication, not release merge or G2/G6 certification.
