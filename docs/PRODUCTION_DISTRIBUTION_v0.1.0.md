# VQS v0.1.0 — production distribution / controlled supported scope

**Release date:** 28 October 2026. **Channel:** public GitHub Release, signed-by-repository release tag with installable Python **wheel** and **source archive**. No hosted web service, Power BI tenant deployment or PyPI publish is implied.

## What is being deployed

An operationally installable, versioned **Power BI source-analysis and safe candidate-repair engine**:
- Python 3.11+ `vqs` CLI (`doctor`, `review`, `triage`, supported `run --mode repair --scope static`, `premium`, theme tooling) and local stdio `vqs-mcp` for AI agents.
- PBIR/TMDL source checks, deterministic findings, typed/allowlisted source edits in **disposable candidates**, guarded against speculative semantic changes, sealed source/revision evidence, blocked/failed verdict distinction.
- Cross-platform CI and installed wheel smoke tests for the shipped CLI/MCP entrypoints; public fictional Contoso PBIP and exact-source native-image showcase as an additional reproducibility fixture **in the repository**, **not** embedded in the wheel.
- No mandatory network access, cloud service, Desktop, paid AI provider or secret required for the source-only runtime. Native Power BI validation remains an **optional authorized Windows** capability.

## What v0.1.0 does **not** certify

- It does **not** mark arbitrary repaired reports production-ready based on a static lint or generated candidate.
- Independent **authorized** human G2/G4 signoff for `powerbi-core` two-PBIP release acceptance is not on file; this owner-authorized distribution is **not** a claim that the report-level G6 policy has passed.
- Native runtime evidence is **bounded to the exercised Year/Region controls and two recorded PBIPs**, not arbitrary Desktop user interfaces or tenants. Country-specific Shape Map clicking, hidden Tooltip contextual hover, generic native repair-candidate reload and Word/DOCX G5 remain unsupported/unverified. Never automatically promote edited user reports.
- No service is running or deployed to a user's Power BI tenant; users install and run the wheel locally. **No PyPI publishing is claimed unless separately confirmed.**

## Install and rollback

Download `visual_quality_system-0.1.0-py3-none-any.whl` from the [v0.1.0 GitHub Release](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.0). Verify the SHA-256 listed in that release, then install in a new isolated environment:

```bash
python -m venv .venv
# Activate it for your operating system (or invoke .venv's python directly).
python -m pip install ./visual_quality_system-0.1.0-py3-none-any.whl
vqs doctor
vqs --version
vqs review /path/to/Project.Report --run-root /path/to/private-runs --run-id release-smoke-001
```

Native Desktop, Microsoft Modeling MCP, visuals, and browser integrations are separately installed/authorized; the wheel does not implicitly provision them. The assistant/agent must propagate `blocked` and `fail` outcomes without turning them into `pass`.

**Rollback:** preserve the old wheel or commit pin, then uninstall v0.1.0 in the isolated interpreter and reinstall the approved older wheel/commit; never use this release to force-rewrite PBIPs. The [previous `main` at public showcase merge](https://github.com/analienx/visual-quality-system/commit/36bbe2af364861be2765b0b82dc901c086048597) remains available as the last pre-versioned source reference. The v0.1.0 tag is immutable by release procedure.

## Promotion decision / governance

**Owner distribution authorization:** explicit in conversation on 28 October 2026: “Deploy production”. This **authorizes publishing this scoped installable distribution**, not granting fictitious G2/G4 human reviewer authority or supporting untested UI features.

**Engineering evidence:** protected CI (Linux 3.11/3.12/3.13 + Windows 3.12), R6 oracle, Microsoft authoring probe, full local regression, the immutable public fictional Contoso fixture and separately verified private second PBIP. The tag must point at the merged protected main commit *after* these checks pass. Release SHA256 assets must be checked and the freshly installed wheel must pass `vqs --version`, `doctor` and an actual source review or repair-blocked smoke. No production release is created on a failing protected check.

**Open acceptance:** [#16](https://github.com/analienx/visual-quality-system/issues/16) independent report-level G2/G4/G6; [#17](https://github.com/analienx/visual-quality-system/issues/17) generalized consumer native repair-candidate path; [#13](https://github.com/analienx/visual-quality-system/issues/13) optional Word. Do not close them merely because the installable core has been distributed.

See [product overview](../README.md), [agent quickstart](AI_AGENT_QUICKSTART.md), [actual five-page Contoso](VERIFIED_CONTOSO_SHOWCASE.md) and [acceptance matrix](ACCEPTANCE_MATRIX.md).
