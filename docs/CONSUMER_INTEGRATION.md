# Integrating VQS with PBIPDocumenter (Power BI first)

**Status:** engineering integration contract for `powerbi-core`, not a release certificate. This guide uses the existing published `vqs` CLI and MCP surfaces instead of introducing a second parser or protocol. Word/DOCX remains an **independent optional** `word-docx` component and must not block a Power BI-only integration.

## Pin the implementation, not just the pre-alpha version string

VQS is currently pre-alpha (`0.0.1a0`); no 1.0 stability or tagged production release has been certified. On a clean host use an explicit reviewed Git commit SHA or a vetted local wheel. Example for the 26 October engineering integration baseline:

```console
python -m pip install "git+https://github.com/analienx/visual-quality-system.git@48757e570da52f465a2f69b6479c8b230d4a1e77"
python -m vqs --version
vqs doctor
```

Check `vqs doctor` for imported distribution identity, installed version, stale editable install detection and optional Microsoft/Desktop backend availability. The default source-only `review` path does **not** require Desktop and cannot substitute for native screenshots. A missing optional backend is a **capability limitation**; do not turn it into success.

## One read-only call for the existing Power BI report

```console
vqs review "C:/projects/Example.Report" --run-root "C:/private/VQS/runs" --run-id "pbipdocumenter-0001"
```

The report argument is the `.Report` directory, **not** a PBIX file or an arbitrary screenshots folder. Use a unique `--run-id` and private `--run-root` for every attempt. The command emits a JSON envelope on stdout with `verdict`, `coverage`, `findings`, `blocked_reasons`, `next_actions`, `provenance` and `run_dir`. The terminal manifest is sealed under `<run-root>/<run-id>/manifest.json`, accompanied by the event log and findings. The exact report/model digest must be recorded alongside PBIPDocumenter's own source revision; don't treat matching folder names as source identity.

**Non-negotiable result mapping:**

| Process exit | Envelope verdict | Consumer action |
| --- | --- | --- |
| `0` | `pass` | May record bounded source-check pass; **not G2/G4/G6 certification** |
| `1` | `fail` | Surface actual findings and fail the corresponding consumer quality gate |
| `2` | `blocked` | Preserve exact capability/source limitation and block downstream approval |
| anything else / missing or malformed JSON / exit-verdict mismatch | no trusted verdict | **blocked**, never success |

Example adapter using only standard Python and the existing CLI:

```python
import json
import subprocess
from pathlib import Path

def review_pbip(report_dir: Path, private_root: Path, run_id: str) -> dict:
    result = subprocess.run(
        ["vqs", "review", str(report_dir), "--run-root", str(private_root),
         "--run-id", run_id],
        capture_output=True, text=True, timeout=180, check=False, shell=False,
    )
    try:
        envelope = json.loads(result.stdout)
        verdict = envelope["verdict"]
        expected = {"pass": 0, "fail": 1, "blocked": 2}[verdict]
        manifest_path = Path(envelope["run_dir"]) / "manifest.json"
        assert manifest_path.resolve().is_relative_to(private_root.resolve())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert result.returncode == expected
        assert manifest["sealed"] is True and manifest["status"] == verdict
        assert manifest["run_id"] == run_id
        assert manifest["artifacts"]["source_sha256"] == envelope["provenance"]["source_sha256"]
    except (ValueError, KeyError, AssertionError, OSError, TypeError):
        return {"verdict": "blocked", "reason": "invalid or unsealed VQS result"}
    return envelope
```

For consumer implementations, also verify the manifest's hash chain with VQS's existing evidence verifier rather than trusting a caller-controlled JSON filename. Keep stdout JSON separate from stderr. Never infer `pass` from a zero process exit without validating the envelope and provenance.

## Core versus optional Word

Use the `powerbi-core` release scope for Power BI work. This requires **two genuinely unrelated PBIPs** with current G0/G1/G2/G3/G4 plus independent G6 evidence; Word/DOCX is **not mandatory**. The older `combined` profile remains for compatibility and must be requested explicitly by future consumers; existing programmatic acceptance calls without a scope retain the historical combined behavior.

`word-docx` is independently gated by OOXML, actual pagination, figures and G5. Do not silently claim a Word result from a passing PBIR review, and do not require a DOCX artifact for Power BI quality review.

## Migration and release boundary

1. Pin both the incumbent PBIPDocumenter prototype and the VQS package commit. Run **the same report revision**, model hash, filters/role, and authorized data against each.
2. Compare findings, status, page/visual inventory, provenance and private native screenshot receipts. Any unavailable capability or unsupported report feature remains `blocked`; do not substitute a generic sample image.
3. Keep existing PBIPDocumenter output path and rollback route until an explicit parity report and a separate clean-host Windows native run pass. The pre-alpha VQS package and Power BI authoring CLI are separate dependencies; test their actual versions before promotion.
4. Only migrate the consumer when parity and rollback work; never automatically publish a report, DOCX, model or private visual evidence as a side effect of source inspection.
5. Product release requires independent G2/G4/G6 under [issue #16](https://github.com/analienx/visual-quality-system/issues/16). The optional Word release remains separately tracked. **No engineering PR merge or passing unit suite grants production-release approval.**

No original PBIP/semantic source, `.pbi/cache.abf`, customer screenshots, credentials, private paths or rendered reports should be committed to this public repository or uploaded to GitHub Actions artifacts.
