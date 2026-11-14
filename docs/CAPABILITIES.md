# VQS capabilities and limits

This page describes the published [v0.1.2 release](https://github.com/analienx/visual-quality-system/releases/tag/v0.1.2), not the unreleased v0.2 drafts. For installation and a first run, start with the [user guide](USER_GUIDE.md).

| Capability | What you can use today | Boundary |
| :--- | :--- | :--- |
| Source review | Inspect supported PBIR/TMDL facts and run source checks locally. | Source checks cannot establish what Desktop displays or that all data is correct. |
| Candidate repair | `vqs fix` applies supported, source-provable changes to a separate candidate and records evidence. | A successful repair stage can coexist with unresolved findings or an overall blocked result. |
| Owner decisions | Review offered questions, supply answers, and rerun. | An agent must not choose for the owner; a waiver cannot turn missing evidence into a pass. |
| Adoption | A verified result can provide an `adopt` command and MCP arguments. | Adoption is a separate owner decision. It rechecks bindings, replaces the original and keeps a backup. |
| PR gate | `vqs gate` compares source findings and can emit SARIF and GitHub annotations. | It is a static regression check, not native report acceptance. |
| Desktop and live data | Native capture and modeling tools have bounded capabilities when an authorized host and evidence are available. | The release does not certify arbitrary Desktop rendering, all interactions, live DAX parity or a whole report. |
| Word/DOCX | An optional, independently scoped component. | Word acceptance is not part of the Power BI release claim. |

VQS reports **pass** for the evidence-backed check that passed, **fail** for a demonstrated violation, and **blocked** when required evidence or capability is missing. Read the overall result and remaining findings as well as individual stage results. A source-verified candidate does not itself certify the report or authorize replacing the original.

For details and known output/shell limitations, see the [release notes](RELEASE_NOTES_v0.1.2.md), [owner decisions and adoption](OWNER_DECISIONS_AND_PR_GATE.md), and [CLI reference](CLI.md). The [acceptance matrix](ACCEPTANCE_MATRIX.md) defines the separate engineering gates; the [v0.2 roadmap](../roadmap/README.md) labels unfinished work.
