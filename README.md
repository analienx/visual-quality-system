# Visual Quality System

**Make Power BI reports trustworthy, readable, and ready for review.**

[![CI](https://github.com/analienx/visual-quality-system/actions/workflows/ci.yml/badge.svg)](https://github.com/analienx/visual-quality-system/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)](pyproject.toml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache--2.0-147D64)](LICENSE)
[![Stage: pre-alpha](https://img.shields.io/badge/Stage-pre--alpha-F2A93B)](docs/RELEASE_NOTES_2026-10-20.md)

VQS is an open-source, **Power BI-first quality and safe-repair system**. It inspects real Power BI Project (PBIP/PBIR) sources, explains problems by page and visual, checks semantic-model evidence, and can verify narrowly scoped changes in a **disposable candidate**. On Windows, it adds populated Power BI Desktop captures and real interaction evidence.

It is designed for the uncomfortable gap between **“the report is technically valid”** and **“people can actually trust and use this dashboard.”**

> [!IMPORTANT]
> **Pre-alpha engineering software, not a certified production quality gate.** Static checks and candidate workflows are usable today. Independent aesthetic review (G2), generalized interaction acceptance (G4), and independent multi-project release approval (G6) are **not complete**. No tagged GitHub release has been published. [See the current engineering release notes](docs/RELEASE_NOTES_2026-10-20.md).

## Start in 60 seconds

No Microsoft account, Power BI license, Windows machine, cloud endpoint, or customer data is needed for a **local static trial**.

**Requirements:** Python 3.11+ and Git. Run these commands from a fresh clone:

~~~bash
git clone https://github.com/analienx/visual-quality-system.git
cd visual-quality-system
python -m pip install -e ".[test]"
vqs --version
vqs triage tests/powerbi/fixtures/mini_report --out quality.md
~~~

Open `quality.md`. You now have a page/visual-aware, prioritized diagnosis of the included synthetic Power BI report. It separates detected source issues from things that still need actual rendered evidence.

Try it on your own **local** enhanced-format PBIP:

~~~bash
vqs triage path/to/YourReport.pbip --out quality.md --plan-out candidate-plan.json
vqs doctor
~~~

- `vqs triage` **reads** the project and writes a report. It never edits the original.
- `--plan-out` emits an allowlisted typed plan **only if VQS can prove a safe proposal**. No file means no safe automatic proposal; do not manufacture one.
- `vqs doctor` reports available Microsoft/Desktop integrations; it does not install, repair, or authorize them.
- To run an orchestrated, source-only review, use `vqs run path/to/YourReport.Report --mode review --run-root runs --run-id first-review`.

**Exit-code convention:** `0` successful command or supported check, `1` proven violation, `2` blocked/unknown (missing evidence is never silently treated as success). See the [CLI reference](docs/CLI.md) for command-specific behavior.

## What you can do

| Workflow | Why it matters | Execution |
| :--- | :--- | :--- |
| **Diagnose** — `triage`, `measure`, `cycles` | Find page-level layout errors, inconsistent declared formatting, inappropriate chart bindings, duplicated insight grain, and DAX/M dependency cycles | Offline, cross-platform |
| **Plan + repair** — `propose`, `repair`, `verify` | Produce an allowlisted, traceable change; apply it to an isolated copy; prove the diff stayed within the plan | Mostly offline; Microsoft authoring validation is capability-dependent |
| **Observe reality** — `capture`, `assurance`, native UIA | Bind full-page Desktop pixels, populated model evidence, slicer interactions, and actual Power BI process identity | Windows + Power BI Desktop + relevant tools |
| **Review independently** — `bundle`, `request-review`, `adjudicate-bundle` | Transport hash-verified evidence to a different reviewer; preserve `pass` / `fail` / `blocked` distinctions | Portable evidence; trusted visual judgment still required |
| **Integrate** — `vqs run`, `vqs-mcp` | Use the same underlying contracts from an installed CLI or local MCP adapter | Local/CI orchestration |

VQS checks more than whether a dashboard's JSON parses. A source-valid report can still have blank maps, cropped tables, inconsistent typography, unreadable cards, wrong answers, or misleading interactions. Each kind of claim needs the **right evidence**.

### Power BI-first architecture

~~~mermaid
flowchart TB
  S["PBIP / PBIR sources<br/>TMDL · DAX · M"] --> Q["VQS quality engine<br/>facts · findings · typed repair"]
  Q --> C["Disposable candidate<br/>allowlisted diff + verification"]
  C --> W["Native Windows witness<br/>Desktop Bridge · Modeling MCP · UIA"]
  Q --> E["Sealed evidence<br/>source hashes · page/visual IDs"]
  W --> E
  E --> J["Independent review<br/>G0–G4 + G6 release scope"]
  J -. "separate optional scope" .-> D["Word / DOCX assurance<br/>G0 · G1 · G5 · G6"]
  classDef blue fill:#eaf2ff,stroke:#7396d2,color:#193d70
  classDef dark fill:#234f9b,stroke:#18396e,color:#ffffff
  classDef teal fill:#e6f5f6,stroke:#6babb0,color:#17444a
  classDef amber fill:#fff4e2,stroke:#c99b55,color:#614316
  classDef green fill:#e4f6ed,stroke:#55a77c,color:#185438
  class S blue
  class Q,C dark
  class W,E teal
  class J green
  class D amber
~~~

**Who does what?**

- **VQS** owns source-aware quality rules, isolated repair plans, evidence integrity, and truthful gate decisions.
- **Microsoft Report Author CLI** checks supported report metadata and structural authoring constraints.
- **Microsoft Modeling MCP** supplies authorized semantic-model/DAX observations.
- **Power BI Desktop Bridge** identifies and captures the *actual* Desktop instance; **Windows UI Automation** reads and invokes accessibility-exposed controls. These are distinct interfaces, not interchangeable.
- **Remote Windows orchestration** can start tools on an authorized machine, but is neither a Power BI data API nor independent proof. Microsoft's **WinApp CLI is not a shipped VQS adapter**.
- **GitHub Actions** can run static analyses and reproducible tests. It does **not** provide a substitute for an authenticated, populated interactive Power BI Desktop session.

See the [architecture diagrams, capability matrix, and deployment boundaries](docs/ARCHITECTURE.md).

## What “premium quality” means here

A dashboard should feel deliberately designed **and** answer the right business question. The next [premium audit initiative (#65)](https://github.com/analienx/visual-quality-system/issues/65) concentrates effort where a visible improvement is most likely:

1. **Design system, not isolated warnings.** Review spacing rhythm, alignment, type scale, density, visual prominence, and color together, with report-specific exceptions.
2. **Independent full-canvas visual judgment.** Combine measurable PBIR geometry with real screenshot evidence, not one generic vision prompt or a falsely “green” static score.
3. **Three meaningful fixes, not fifty opinions.** Rank by impact on comprehension, severity, and evidence; propose bounded, reversible changes and check them again after rendering.

**Availability:** these premium features have a locally tested engineering candidate; they are **not yet merged into `main`**, and `vqs premium` is **not a published command**. The merged core already provides source-backed layout/format and native evidence capabilities. The next milestone is independent premium review and verified publication, **not** a decorative score.

## Choose the workflow that fits your environment

| Environment | Start with | What it can *actually* prove |
| :--- | :--- | :--- |
| macOS / Linux / GitHub-hosted runners | `vqs triage`, `vqs measure`, `vqs cycles`, Python tests | Source facts, static defects, typed change boundaries |
| Windows without a running Desktop | Same commands + `vqs doctor` | Static results and readiness diagnostics |
| Authorized Windows + Power BI Desktop | `vqs capture`, `vqs assurance`, Modeling MCP and UIA evidence | Bound native pixels and specific supported interactions |
| Independent human/image-capable reviewer | Verified `vqs bundle` + page-by-page visual judgment | Aesthetic/readability findings on verified pixels; **not** automatic semantic or G6 approval |

To perform a real candidate repair, follow the [step-by-step developer quickstart](docs/QUICKSTART.md) or [user guide](docs/USER_GUIDE.md). **Never operate on your only copy of a PBIP.** Real renders, local `.pbi` caches, model data, and user paths stay private and outside Git.

### Evidence in practice

The [20 October Power BI engineering case study](docs/POWER_BI_CORE_NATIVE_EVIDENCE_2026-10-20.md) documents a five-page Contoso report: source-grounded typography/table repairs, freshly populated native captures, and nine real Year/Region interaction checks. It also documents what still needs independent sign-off. No real customer screenshots or local model caches are committed to this repository.

## Release components and limits

| Component | Scope | Today |
| :--- | :--- | :--- |
| **Power BI core** | `powerbi-core`: two unrelated PBIPs, G0–G4, independent G6 | **Pre-alpha; release blocked** on independent evidence |
| **Word / DOCX** | `word-docx`: document-specific G0/G1/G5, independent G6 | Optional, separately gated; native extensions still in draft development |
| Legacy combined | `combined`: both component families | Backward compatibility, **not** a shortcut around any gate |
| Fabric / web apps | Later adaptation | Deferred |

This is a **logical separation inside one Python distribution**, not an assertion that Word has already shipped as its own installable package. A Word failure must not block a Power BI-only release, and a Power BI pass must not certify Word.

## Documentation and help

| I want to… | Read |
| :--- | :--- |
| Install and run a real static diagnosis | [Quickstart](docs/QUICKSTART.md) · [User guide](docs/USER_GUIDE.md) |
| Look up a flag or verdict | [Full CLI reference](docs/CLI.md) |
| Understand the Microsoft/Windows architecture | [Architecture](docs/ARCHITECTURE.md) |
| Understand acceptance criteria and blockers | [G0–G6 acceptance matrix](docs/ACCEPTANCE_MATRIX.md) |
| See what changed and what's truly available | [Engineering release notes](docs/RELEASE_NOTES_2026-10-20.md) · [Changelog](CHANGELOG.md) |
| Follow work or report a problem | [Issue tracker](https://github.com/analienx/visual-quality-system/issues) · [Delivery ledger](roadmap/work_packages.json) |
| Contribute safely | [Contributing](CONTRIBUTING.md) · [Agent execution contract](AGENTS.md) |

## Safety, support, and contributing

- **Local by default.** Static analysis runs without uploading business data. Remote image review is opt-in; screenshots may contain sensitive facts and require explicit consent.
- **No self-approval.** Authors, reviewers, and release owners have separate responsibilities. A model-written review does not grant itself release authority.
- **No secret data in issues or PRs.** Never commit screenshots from business reports, `.abf` / `.pbi` caches, customer tables, tokens, or workstation paths.
- **Contributions welcome.** Python 3.11+, `python -m pytest`, `python -m ruff check .`, source-bound tests, and truthful status notes. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security:** please report suspected vulnerabilities privately to the repository owner rather than posting credentials or sensitive evidence in a public issue.

Apache-2.0 © VQS contributors. [License](LICENSE) · [Notice](NOTICE).
