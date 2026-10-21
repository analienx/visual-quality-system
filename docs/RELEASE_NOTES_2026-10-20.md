# Engineering release notes — 20 October 2026

> [!NOTE]
> **Historical snapshot.** The premium preflight and mixed-size page capture have since merged, and two unrelated PBIPs now have native engineering evidence. Read the [current 21 October status](RELEASE_NOTES_2026-10-21.md) before drawing conclusions from this archived snapshot.

**Visual Quality System · Power BI-first · version `0.0.1a0` · pre-alpha**

> [!CAUTION]
> **This is a source-backed engineering update, not a production release.** There are **no published GitHub Releases/tags** for VQS at this date. The current `main` branch includes the Power BI-first architecture and native QA integration; independent G2/G4/G6 release acceptance is still blocked. Do not interpret merged code, a green CI run, or a demo screenshot as approval for unattended production use.

[Get started](../README.md#start-in-60-seconds) · [CLI](CLI.md) · [Architecture](ARCHITECTURE.md) · [Acceptance](ACCEPTANCE_MATRIX.md) · [Full changelog](../CHANGELOG.md)

## The headline

**VQS now has a coherent Power BI-first path from source diagnosis through disposable repair to real Desktop evidence.** The major change is not a visual effect: it is the ability to tell users **what was measured, what was actually rendered and clicked, what was changed, and what remains unproven**.

| Milestone on `main` | What changed | Evidence |
| :--- | :--- | :--- |
| **Power BI as the primary product** | Explicit `powerbi-core` acceptance independent of Word/DOCX; historical `combined` compatibility retained | [Merged PR #63](https://github.com/analienx/visual-quality-system/pull/63) |
| **Native Power BI QA** | Rendered-content/blank-map checks, loaded-model and interaction evidence, candidate composition reflow, source-bound assurance, native UI Automation adapter | [Merged PR #64](https://github.com/analienx/visual-quality-system/pull/64) |
| **Usable developer entry** | `vqs triage` produces source-backed findings and optional safe plans; `vqs doctor` diagnoses local capability; one workflow can be run through `vqs run` | [README](../README.md) · [Quickstart](QUICKSTART.md) |
| **Honest scope-specific release gates** | Power BI: G0–G4 + independently authenticated G6; Word: G0/G1/G5 + independent G6 | [Acceptance matrix](ACCEPTANCE_MATRIX.md) |

**Merged baseline:** `f24660c094a28ad189489e47ce3a03acd37ac9cc` on `main` (PR #64). The documentation in this update refers to that verified baseline; later candidate branches are not silently counted as integrated code.

## Why this matters to a report author

### 1. A real first result without Desktop

A developer with Python 3.11+ can clone the repository, install it locally, and diagnose the synthetic Power BI fixture or a local enhanced-format `.pbip` / `.Report` using `vqs triage`. Results identify concrete page/visual problems and evidence gaps; analysis does not modify the source.

~~~bash
python -m pip install -e ".[test]"
vqs triage tests/powerbi/fixtures/mini_report --out quality.md
vqs triage path/to/YourReport.pbip --out quality.md --plan-out candidate-plan.json
~~~

The second command exports a plan only when an allowlisted candidate is derivable; absence of a plan is an explicit, safe outcome. Structural checks do **not** imply visual approval.

### 2. A safer correction loop

VQS can validate a typed plan, execute bounded visual edits on a disposable report candidate, verify the resulting file diff, and retain the source/evidence identity. Microsoft's Report Author CLI is a supported validation interface; Modeling MCP addresses semantic observations, not layout editing.

The **original PBIP is not an acceptable repair target**. No implicit DAX, filter, RLS, model-data, or source modification is permitted by a cosmetic-fix claim.

### 3. Evidence from the real Windows application

The merged core adds or integrates:

- Desktop Bridge capture and exact report/process checks.
- Live model-readiness evidence from Microsoft's Modeling MCP, bound to the relevant Desktop instance when available.
- Native .NET UI Automation for controls that actually expose the necessary accessibility patterns and readback.
- Runtime/render checks for empty map content, title/layout defects, and UI-induced semantic changes.
- Source-bound evidence bundles and separate independent review responsibilities.

This is **not** a universal Desktop automation API. Some controls expose only a generic Plot-area accessibility node; country selection cannot be assumed to work everywhere. Headless GitHub runners can validate source and test logic, but they do not magically execute authenticated Power BI Desktop.

## Proof we have — and proof we still need

An isolated, data-populated **five-page Contoso** Power BI candidate was captured and reviewed during engineering integration. Cosmetic fixes addressed oversized titles, matrix clipping/scrolling, and alignment; Microsoft authoring validation found **0 errors and 0 warnings**. A source/model/PID-bound native UIA sequence passed **9/9 Year/Region checks**. A further guarded, one-off U.S. Shape Map selection/clear was observed with live DAX and readback parity.

These are **engineering observations on one report**, not independent release approval. See the [privacy-safe evidence report](POWER_BI_CORE_NATIVE_EVIDENCE_2026-10-20.md) for exact scope, source safety, and remaining conditions.

| Acceptance area | Current claim | Release verdict |
| :--- | :--- | :--- |
| G0 · Source and exact process identity | Contoso engineering evidence available | Not a blanket multi-project pass |
| G1 · Populated native report | All five Contoso pages rendered from bound live model | Engineering evidence only |
| G2 · Independent aesthetic/readability review | Implementer reviewed whole pages; separate qualified reviewer not yet bound | **Blocked** |
| G3 · Safe mutation | Bounded source-preserving cosmetic candidate demonstrated | Promotion still independently gated |
| G4 · Real interactions | Nine Year/Region actions; one-off map-country witness | **Independent generalized acceptance blocked** |
| G6 · Release suite | Second unrelated PBIP, independent verifier, authenticated authority and negative controls still missing | **Blocked** |

No static-only command, AI opinion, or merge event changes these release states.

## Coming next: premium dashboard experience

The [P19 premium-quality initiative (#65)](https://github.com/analienx/visual-quality-system/issues/65) addresses the remaining distinction between a **valid report** and a **visually excellent and analytically useful dashboard**:

1. **Design contract:** consistent hierarchy, typography, spacing, surface palette and density, with explicit evidence-backed exceptions.
2. **Calibrated perception:** three complementary native-page review perspectives—composition, visual language, and analytical usefulness—without confusing image impressions with semantic truth.
3. **High-impact fix list:** prioritize only the three most consequential, actionable improvements; re-evaluate a repaired candidate rather than optimizing superficial warning counts.

**Publication state:** code was implemented and locally tested at `8a31cde`, but **has not been pushed/merged to `main`** and the `vqs premium` CLI must **not** be advertised as installable from this repo. Issue #65 tracks the remaining remote-publication and independent review steps.

## Word is separate; Fabric is deferred

- **Power BI core** can advance independently of Word. Its acceptance profile is `powerbi-core` and still needs G0–G4 plus separate G6 authority.
- **Word/DOCX assurance** is an optional, separately gated logical component (`word-docx`). Basic OOXML inspection exists; native pagination/TOC/figure work remains in draft candidates such as [PR #62](https://github.com/analienx/visual-quality-system/pull/62). It is **not yet a separate Python wheel** and must not block Power BI-only acceptance.
- **Fabric/web app quality adapters** are deferred to a later phase ([#18](https://github.com/analienx/visual-quality-system/issues/18)).

## Compatibility and privacy

| Question | Answer |
| :--- | :--- |
| Python | **3.11 or newer**; package identifies as `0.0.1a0`, pre-alpha |
| Install | Clone and install locally with `python -m pip install -e ".[test]"`; this is not a PyPI/GA release announcement |
| Static Power BI analysis | Cross-platform, no cloud authentication or Desktop needed |
| Native Power BI evidence | Authorized Windows host, actual Power BI Desktop and installed Microsoft integrations |
| Cloud uploads | None for static diagnosis; opt-in remote image review requires explicit consent |
| Sensitive artifacts | Keep customer data, screenshots, model caches, machine paths and tokens outside the repository and public GitHub issues |
| Outcome semantics | `pass` = evidence suffices for **that check**; `fail` = demonstrated defect; `blocked` = insufficient evidence/capability |

## What to do next

- **New developer:** follow the [one-minute quickstart](../README.md#start-in-60-seconds).
- **Report owner:** use the [user guide](USER_GUIDE.md) before touching a real PBIP, and preserve its original.
- **Windows/Power BI integrator:** review the [tool responsibility matrix](ARCHITECTURE.md#2-how-vqs-actually-interacts-with-power-bi-desktop).
- **Reviewer or release owner:** use the [G0–G6 acceptance matrix](ACCEPTANCE_MATRIX.md) and require independent evidence.
- **Contributor:** read [CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md); no synthetic fixture or self-review should be promoted to release proof.

*Engineering status reviewed against GitHub `main`, merged PRs #63/#64, and issue #65 on 20 October 2026. This document is intentionally not a GitHub Releases publication.*
