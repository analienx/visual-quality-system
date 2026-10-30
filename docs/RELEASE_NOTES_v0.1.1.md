# Visual Quality System v0.1.1 - Agent-first Power BI repairs

**Release date:** 30 October 2026.
**Distribution:** GitHub Release wheel and Python source archive, accompanied
by SHA-256 checksums. No PyPI release, hosted service or Power BI tenant
deployment is implied.

## What is new

- **One command for safe candidate repair.** `vqs fix Report.pbip`
  accepts a PBIP file, a single-report project root or a report directory;
  discovers its unambiguous semantic model; runs the established sealed
  coordinator; and returns concise fixed, needs-review, blocked and
  regression information. Original source is never overwritten.
- **Reliable clean-wheel authoring.** Include 88 approved Microsoft report
  authoring skill documents with SHA-256 attestation and pinned authoring
  CLI v0.5.0 preflight. `vqs doctor` reports actual readiness.
  Microsoft binaries are not bundled. The upstream MIT license notice
  accompanies the documentation in every distribution archive.
- **Agent interoperability.** MCP 2026-07-28 stateless discovery and
  structured responses with output schemas, alongside existing legacy
  2024/2025 handshake and text output. Detailed inspect/propose/repair
  evidence remains accessible. The new `vqs_theme` tool exposes
  preview and safe disposable-candidate apply/audit.
- **Decision-ready results.** `vqs run --summary` emits a compact
  source-only result; the advanced unabridged JSON format remains the
  default for `vqs run` and is saved in private evidence.
- **Cross-platform release proof.** Actual wheel-installed executables
  validated on six independent GitHub runner environments.

## Getting started

Download the appropriate assets from the
[GitHub v0.1.1 Release](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.1).
The wheel is cross-platform Python 3.11+ and the source archive enables
rebuilding the distribution. Verify SHA-256 checksums from `SHA256SUMS`
before installation.

```bash
python -m pip install visual_quality_system-0.1.1-py3-none-any.whl
npm install -g @microsoft/powerbi-report-authoring-cli@0.5.0
vqs --version
vqs doctor
vqs fix "C:/Reports/Sales.pbip"
```

Without the pinned Microsoft CLI, source-only review can still be used,
but the default production authoring preflight blocks rather than silently
degrading to an unverified writer. Advanced explicit
`--authoring-backend direct` is a separately described static-only
route, **not** equivalent to official structural validation.

## Independent verification

[GitHub Actions: six-platform installed-wheel run](https://github.com/analienx/visual-quality-system/actions/runs/40966581372)
and [merged E2E workflow PR #113](https://github.com/analienx/visual-quality-system/pull/113).

| Runner | Python | Installed wheel / authoring / repair / MCP |
|---|---|---|
| Ubuntu 24.04 | 3.11 | PASS |
| Ubuntu 24.04 | 3.12 | PASS |
| Ubuntu 24.04 | 3.13 | PASS |
| Windows Server 2025 | 3.11 | PASS |
| Windows Server 2025 | 3.12 | PASS |
| Windows Server 2025 | 3.13 | PASS |

All six generated evidence JSON files were downloaded and independently
inspected. In each job the fictional Contoso PBIP had a seeded 6-pixel
KPI overlap corrected to a disposable verified candidate
(x=314 to x=320), with **zero new regressions** and the original
project hash unchanged. The outcome remained
`improved_not_accepted` because inherited typography and deliberate
overview/detail grain are still owner-dependent design decisions.
Non-repairable Contoso returned `blocked` with no fabricated fix.
A theme was previewed, applied and audited to a separate candidate.
Legacy and modern MCP executable workflows both passed.
The [PR passed all 14 protected checks](https://github.com/analienx/visual-quality-system/pull/113).
The Windows on-device full local regression: 2,048 passed, 15 skipped.

## Supported vs. deliberately excluded

**Supported:** PBIR/TMDL source analysis, report-model discovery,
source-provable allowlisted candidate repairs, official CLI structural
checks within the pinned Microsoft command scope, sealed evidence,
legacy/modern agent protocol, read-only review and candidate-only
theme application/audit.

**Not certified:** interactive Power BI Desktop controls and rendering
for arbitrary user reports; independent G2/G4/G6 report-level visual
and data acceptance; generalized native candidate reload; country-level
Shape Map selection or hidden tooltip hover; Word/DOCX acceptance.
A static-source repair result is never a report production signoff.
Report promotion remains a separately authorized operation.

## Third-party licensing

VQS code is Apache-2.0 licensed. The bundled reviewed Microsoft
Skills for Fabric *documentation* is copyright (c) 2026 Microsoft
Corporation, MIT licensed. The original upstream
[MIT license](https://github.com/microsoft/skills-for-fabric/blob/bc42aaf734771bf752c1d7082dd91e5a6ca72b9f/LICENSE)
ships in `vqs/approved_skill/MICROSOFT_SKILLS_FOR_FABRIC_LICENSE.txt`.
The lock retains Microsoft upstream commit
`bc42aaf734771bf752c1d7082dd91e5a6ca72b9f`
and 88-file SHA digest
`82a19935d88def4600522430fa61cbdcee689f9d3e76db2a57b1eea0983b1eda`.
Microsoft tools are external dependencies; VQS is not endorsed by Microsoft.

## References

- [Main README](../README.md)
- [AI agent setup](AI_AGENT_QUICKSTART.md)
- [CLI reference](CLI.md)
- [Release acceptance record](V011_USABILITY_RELEASE_PLAN.md)
- [Automated installed-wheel acceptance](../.github/workflows/v011-runner-e2e.yml)
