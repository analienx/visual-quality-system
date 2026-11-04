"""Runner-side, installed-wheel E2E. No editable checkout or fake Desktop proof.

Runs from a private directory outside the checkout and invokes the actual
vqs and vqs-mcp console entry points, including the pinned Microsoft CLI.
All example data is fictional. Every assertion is a release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import venv
import zipfile
from pathlib import Path

EXPECTED_VERSION = "0.1.2"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fingerprint(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise AssertionError(f"unexpected symlink in test source: {path}")
        if path.is_file():
            digest.update(path.relative_to(folder).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def run(command: list[str], cwd: Path, env: dict, *,
        allowed: tuple[int, ...] = (0,), timeout: int = 110) -> tuple[int, str]:
    started = time.monotonic()
    proc = subprocess.run(command, cwd=cwd, env=env, text=True,
                          encoding="utf-8", errors="replace",
                          capture_output=True, timeout=timeout, check=False)
    print(json.dumps({"command": Path(command[0]).name,
                      "arguments": [str(v) for v in command[1:4]],
                      "code": proc.returncode,
                      "seconds": round(time.monotonic() - started, 2),
                      "stdout_bytes": len(proc.stdout.encode("utf-8")),
                      "stderr": proc.stderr[-700:]}, ensure_ascii=False),
          flush=True)
    require(proc.returncode in allowed,
            f"unexpected exit {proc.returncode} for {command!r}: "
            f"stdout={proc.stdout[-1800:]!r}, stderr={proc.stderr[-1800:]!r}")
    return proc.returncode, proc.stdout


def json_command(command: list[str], cwd: Path, env: dict, *,
                 allowed: tuple[int, ...] = (0,), timeout: int = 110) -> tuple[int, dict]:
    code, output = run(command, cwd, env, allowed=allowed, timeout=timeout)
    parsed = json.loads(output)
    require(isinstance(parsed, dict), "console output must be one JSON object")
    return code, parsed


def mcp_exchange(binary: Path, requests: list[dict], cwd: Path,
                 env: dict) -> list[dict]:
    payload = "".join(json.dumps(req) + "\n" for req in requests)
    proc = subprocess.run([str(binary)], cwd=cwd, env=env, input=payload,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=75, check=False)
    require(proc.returncode == 0,
            f"installed MCP stdio exited {proc.returncode}: {proc.stderr[-1100:]}")
    require(not proc.stderr.strip(), f"MCP stderr: {proc.stderr[-400:]}")
    responses = [json.loads(line) for line in proc.stdout.splitlines()]
    expected = sum("id" in req for req in requests)
    require(len(responses) == expected,
            f"MCP frames: expected {expected}, got {len(responses)}")
    for response in responses:
        require("error" not in response,
                f"unexpected MCP protocol error: {response}")
    return responses


def owner_decisions_and_gate(vqs: Path, project: Path, pbip_file: str,
                             report_subpath: Path, private: Path,
                             env: dict) -> dict:
    """The v0.1.2 chain on the installed wheel, on a disposable copy.

    fix -> decisions template -> answered fix -> changes -> explicit
    adoption, plus gate -> SARIF. Asserts original preservation, the
    kept backup, stale-answer rejection and fail-closed behaviour.
    """
    runs = private / "decision-runs"
    before = fingerprint(project)

    # 1. An unseen report blocks with answerable questions.
    _, blocked = json_command(
        [str(vqs), "fix", str(project / pbip_file), "--run-root", str(runs),
         "--run-id", "d1"], private, env, allowed=(2,), timeout=120)
    require(blocked["verdict"] == "blocked" and blocked["candidate"] is None,
            f"unseen report must block without a candidate: {blocked}")
    questions = blocked.get("needs_review") or []
    require(bool(questions), "blocked run exposed no answerable question")
    for item in questions:
        require(str(item.get("decision_id", "")).startswith("dec-")
                and bool(item.get("question")),
                f"question missing a stable id or text: {item}")

    # 2. The answers skeleton, which must refuse to overwrite.
    answers_path = private / "answers.json"
    run(([str(vqs), "decisions", "template", "--run-id", "d1",
          "--run-root", str(runs), "--out", str(answers_path)]),
        private, env, allowed=(0,), timeout=60)
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    require(answers["schema"] == "vqs.decision-answers/1",
            f"unexpected answers schema: {answers.get('schema')}")
    require(len(answers["source_sha256"]) == 64, "answers carry no source digest")
    run(([str(vqs), "decisions", "template", "--run-id", "d1",
          "--run-root", str(runs), "--out", str(answers_path)]),
        private, env, allowed=(2,), timeout=60)

    # 3. The owner picks the smallest offered size, else waives.
    answers["owner"] = "installed-wheel release gate (disposable copy)"
    for item in answers["answers"]:
        sizes = [c for c in (item.get("choices") or [])
                 if str(c).startswith("size:")]
        item["option"] = sizes[0] if sizes else "accept"
    answers_path.write_text(json.dumps(answers, indent=2), encoding="utf-8")
    require(any(a["option"] != "accept" for a in answers["answers"]),
            "fixture offered no typed size option; revisit this proof")

    # 4. The answered run produces a verified candidate, changes and adopt.
    _, answered = json_command(
        [str(vqs), "fix", str(project / pbip_file), "--run-root", str(runs),
         "--run-id", "d2", "--decisions", str(answers_path)],
        private, env, allowed=(0,), timeout=180)
    require(answered["verdict"] == "pass", f"answered run not accepted: {answered}")
    changes = answered.get("changes") or []
    require(bool(changes), f"answered run reported no changes: {answered}")
    for change in changes:
        require({"page", "visual", "property", "op", "from", "to"} <= set(change),
                f"change is not decision-ready: {change}")
    adopt = answered.get("adopt") or {}
    require("vqs promote" in str(adopt.get("command")),
            f"verified candidate carries no adopt command: {answered}")
    require(adopt.get("mcp", {}).get("tool") == "vqs_promote",
            "adopt step omits the MCP promote arguments")
    require(answered["promotion_performed"] is False,
            "a fix run promoted without an explicit owner step")
    # The compact result omits this key entirely when nothing is unprovable;
    # a non-empty list would mean a waiver had cleared missing evidence.
    require(not answered.get("unwaivable_findings"),
            f"accepted run still carries unprovable checks: {answered}")
    require(fingerprint(project) == before,
            "answered repair mutated the original project!")

    # 5. Stale answers are refused on a changed source.
    probe = project / report_subpath / "definition" / "pages"
    victim = min(probe.rglob("visual.json"))
    original_bytes = victim.read_bytes()
    doc = json.loads(original_bytes.decode("utf-8-sig"))
    doc["_vqsStaleProbe"] = True
    victim.write_text(json.dumps(doc), encoding="utf-8")
    _, stale = json_command(
        [str(vqs), "fix", str(project / pbip_file), "--run-root", str(runs),
         "--run-id", "d3", "--decisions", str(answers_path)],
        private, env, allowed=(2,), timeout=120)
    require(stale["verdict"] == "blocked", f"stale answers were accepted: {stale}")
    require(any("different source revision" in str(reason)
                for reason in stale.get("blocked_reasons") or []),
            f"stale refusal does not name the revision mismatch: {stale}")
    victim.write_bytes(original_bytes)
    require(fingerprint(project) == before, "stale probe was not restored")

    # 6. Fail closed on unusable answers.
    bogus = private / "bogus-answers.json"
    bogus.write_text(json.dumps({
        "schema": "vqs.decision-answers/1", "owner": "x",
        "source_sha256": "0" * 64,
        "answers": [{"decision_id": "dec-0000000000000000",
                     "option": "no-such-option"}]}), encoding="utf-8")
    json_command([str(vqs), "fix", str(project / pbip_file), "--run-root",
                  str(runs), "--run-id", "d4", "--decisions", str(bogus)],
                 private, env, allowed=(2,), timeout=120)
    unparseable = private / "not-json.json"
    unparseable.write_text("not json at all", encoding="utf-8")
    json_command([str(vqs), "fix", str(project / pbip_file), "--run-root",
                  str(runs), "--run-id", "d5", "--decisions",
                  str(unparseable)], private, env, allowed=(2,), timeout=120)

    # 7. A hand-written plan may not claim owner-decision authority.
    forged = private / "forged-plan.json"
    forged.write_text(json.dumps({
        "schema": "vqs.repair-plan/1", "affected_pages": ["P1"],
        "operations": [{
            "type": "format.declare_explicit",
            "selector": {"page": "P1", "visual": "v"}, "target": "visual",
            "path": ["visual", "objects", "header", 0, "properties",
                     "textSize"],
            "old": None, "value": "11D", "effective": "11D",
            "proof": "owner-decision:dec-ffffffffffffffff:size:11D"}]}),
        encoding="utf-8")
    _, plan_blocked = json_command(
        [str(vqs), "fix", str(project / pbip_file), "--run-root", str(runs),
         "--run-id", "d6", "--plan", str(forged)],
        private, env, allowed=(2,), timeout=120)
    require(plan_blocked["verdict"] == "blocked",
            f"forged owner-decision proof was accepted: {plan_blocked}")

    # 8. gate -> SARIF, and the stored-baseline round trip.
    candidate = Path(answered["candidate"])
    sarif_path = private / "gate.sarif"
    gate_code, _out = run(
        [str(vqs), "gate", str(candidate), "--baseline",
         str(project / report_subpath), "--sarif", str(sarif_path),
         "--github"], private, env, allowed=(0, 1), timeout=150)
    log = json.loads(sarif_path.read_text(encoding="utf-8"))
    require(log["version"] == "2.1.0", "gate did not write SARIF 2.1.0")
    driver = log["runs"][0]["tool"]["driver"]
    require(driver["version"] == EXPECTED_VERSION,
            f"SARIF driver version {driver['version']} is not the installed one")
    for entry in log["runs"][0]["results"]:
        require(entry["baselineState"] in ("new", "unchanged"),
                f"unexpected SARIF baselineState: {entry}")
    stored = private / "gate-baseline.json"
    run([str(vqs), "gate", str(project / report_subpath),
         "--emit-baseline", str(stored)], private, env, allowed=(0,),
        timeout=150)
    run([str(vqs), "gate", str(project / report_subpath),
         "--baseline", str(stored)], private, env, allowed=(0,), timeout=150)

    # 9. Explicit adoption, on a separate disposable copy only.
    adopt_copy = private / "adoption copy"
    shutil.copytree(project, adopt_copy)
    arun = private / "adoption-runs"
    json_command([str(vqs), "fix", str(adopt_copy / pbip_file), "--run-root",
                  str(arun), "--run-id", "a1"], private, env, allowed=(2,),
                 timeout=120)
    a_answers = private / "adoption-answers.json"
    run([str(vqs), "decisions", "template", "--run-id", "a1", "--run-root",
         str(arun), "--out", str(a_answers)], private, env, allowed=(0,),
        timeout=60)
    payload = json.loads(a_answers.read_text(encoding="utf-8"))
    payload["owner"] = "installed-wheel release gate (disposable copy)"
    for item in payload["answers"]:
        sizes = [c for c in (item.get("choices") or [])
                 if str(c).startswith("size:")]
        item["option"] = sizes[0] if sizes else "accept"
    a_answers.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _, a_done = json_command(
        [str(vqs), "fix", str(adopt_copy / pbip_file), "--run-root", str(arun),
         "--run-id", "a2", "--decisions", str(a_answers)],
        private, env, allowed=(0,), timeout=180)
    pre_adopt = fingerprint(adopt_copy)
    run([str(vqs), "promote", "--run-root", str(arun), "--run-id",
         str(a_done["adopt"]["mcp"]["run_id"]), "--owner-approval",
         "installed-wheel release gate: disposable copy", "--scope", "static"],
        private, env, allowed=(0,), timeout=150)
    backups = list(adopt_copy.glob("*.vqs-backup"))
    require(len(backups) == 1,
            f"promotion did not keep exactly one backup: {backups}")
    require(fingerprint(adopt_copy) != pre_adopt,
            "promotion changed nothing on the adopted copy")
    return {
        "questions": len(questions),
        "declared_changes": len(changes),
        "answered_verdict": answered["verdict"],
        "answered_outcome": answered["outcome"],
        "stale_answers": "blocked",
        "bogus_answers": "blocked",
        "forged_owner_proof": "blocked",
        "gate_exit": gate_code,
        "sarif_results": len(log["runs"][0]["results"]),
        "adoption_backup": backups[0].name,
        "original_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    dist = args.dist_dir.resolve()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    temp = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()).resolve()
    private = Path(tempfile.mkdtemp(prefix="vqs-011-gh-runner-",
                                   dir=temp))
    # Remove the checkout from runtime import resolution. No hidden skill env override.
    env = os.environ.copy()
    for name in ("PYTHONPATH", "VQS_APPROVED_SKILL_ROOT", "PYTHONHOME"):
        env.pop(name, None)
    env["PYTHONNOUSERSITE"] = "1"

    # Derived from EXPECTED_VERSION so a version bump cannot leave this
    # gate globbing for the previous release's filenames.
    wheel_files = list(
        dist.glob(f"visual_quality_system-{EXPECTED_VERSION}-*.whl"))
    archives = list(
        dist.glob(f"visual_quality_system-{EXPECTED_VERSION}.tar.gz"))
    require(len(wheel_files) == 1 and len(archives) == 1,
            f"must build exactly one v{EXPECTED_VERSION} wheel and source "
            f"archive; found {sorted(p.name for p in dist.glob('*'))}")
    wheel, archive = wheel_files[0], archives[0]
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        reviewed = [name for name in names
                    if name.startswith("vqs/approved_skill/powerbi-report-cli/")
                    and name.endswith((".md", ".json", ".yaml", ".yml"))]
        require(len(reviewed) == 88, f"wheel must contain 88 locked skill files, got {len(reviewed)}")
        require("vqs/approved_skill/powerbi-report-cli-upstream.json" in names,
                "wheel must contain skill provenance lock")
        mit = "vqs/approved_skill/MICROSOFT_SKILLS_FOR_FABRIC_LICENSE.txt"
        require(mit in names, "wheel must carry upstream Microsoft MIT license")
        lic = z.read(mit).decode("utf-8")
        require("Copyright (c) 2026 Microsoft Corporation" in lic
                and "Permission is hereby granted" in lic,
                "vendored copyright and license not intact")
    with tarfile.open(archive, "r:gz") as z:
        names = z.getnames()
        reviewed = [name for name in names
                    if "/vqs/approved_skill/powerbi-report-cli/" in name
                    and name.endswith((".md", ".json", ".yaml", ".yml"))]
        require(len(reviewed) == 88, "source archive omits reviewed skill files")
        license_names = [n for n in names if n.endswith(
            "vqs/approved_skill/MICROSOFT_SKILLS_FOR_FABRIC_LICENSE.txt")]
        require(len(license_names) == 1, "source archive missing Microsoft license")
    print(f"Verified independent distributions: wheel={hashlib.sha256(wheel.read_bytes()).hexdigest()}, "
          f"sdist={hashlib.sha256(archive.read_bytes()).hexdigest()}", flush=True)

    venv_dir = private / "installed consumer venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    bindir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    vqs = bindir / ("vqs.exe" if os.name == "nt" else "vqs")
    mcp = bindir / ("vqs-mcp.exe" if os.name == "nt" else "vqs-mcp")
    run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        private, env, timeout=110)
    require(vqs.exists() and mcp.exists(), "installed wheel must create both console entrypoints")
    _, installation = run([str(python), "-c",
                           "import json, pathlib, vqs; print(json.dumps({'path': str(pathlib.Path(vqs.__file__).resolve()), 'version': vqs.__version__}))"],
                          private, env)
    installed = json.loads(installation)
    require(installed["version"] == EXPECTED_VERSION,
            f"installed code must be version {EXPECTED_VERSION}")
    require(Path(installed["path"]).is_relative_to(venv_dir.resolve()),
            "runtime is importing source checkout rather than installed wheel")
    _, doctor = json_command([str(vqs), "doctor"], private, env, timeout=55)
    preflight = doctor["checks"]["authoring_preflight"]
    require(preflight["status"] == "pass",
            f"pinned Microsoft authoring preflight failed: {preflight}")
    require(preflight["assurance"] == "microsoft_structural_only",
            "real Microsoft-backed authoring assurance required")
    require(preflight["skill"]["snapshot"]["file_count"] == 88,
            "attested skill file count mismatched")
    require(preflight["skill"]["snapshot"]["sha256"] ==
            "82a19935d88def4600522430fa61cbdcee689f9d3e76db2a57b1eea0983b1eda",
            "attested Microsoft skill bytes differ")
    require("2026-07-28" in doctor["checks"]["mcp_protocols"],
            "modern protocol unavailable")

    fixture = repo / "examples" / "contoso-retail-verified"
    pbip_file = "Contoso Retail.pbip"
    report_subpath = Path("Contoso Retail.Report")
    visual_subpath = (report_subpath / "definition" / "pages" /
                      "Executive_overview" / "visuals" / "card-b8ef7dc2" / "visual.json")
    clean = private / "clean contoso project"
    shutil.copytree(fixture, clean)
    clean_digest = fingerprint(clean)
    _, result = json_command(
        [str(vqs), "fix", str(clean / pbip_file),
         "--run-root", str(private / "runs"), "--run-id", "clean-no-candidate"],
        private, env, allowed=(2,), timeout=110)
    require(result["verdict"] == "blocked" and result["candidate"] is None,
            f"source-ambiguous report must block without speculative candidate: {result}")
    require(len(result["needs_review"]) >= 2,
            f"expected owner-evidence design decisions, got {result}")
    require(fingerprint(clean) == clean_digest, "negative control modified original project")

    seeded = private / "seeded overlap project"
    shutil.copytree(fixture, seeded)
    visual = seeded / visual_subpath
    source = json.loads(visual.read_text(encoding="utf-8"))
    require(source["position"]["x"] == 336, "upstream fixture changed; revisit seeded proof")
    source["position"]["x"] = 314  # 6 px geometric overlap.
    visual.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    seeded_before = fingerprint(seeded)
    full_path = evidence / "seeded-full-envelope.json"
    exit_code, fixed = json_command(
        [str(vqs), "fix", str(seeded / pbip_file),
         "--run-root", str(private / "runs"), "--run-id", "seeded-positive",
         "--report-out", str(full_path)],
        private, env, allowed=(1,), timeout=160)
    require(exit_code == 1 and fixed["verdict"] == "fail"
            and fixed["outcome"] == "improved_not_accepted",
            f"expected proven improvement with still-open unrelated findings: {fixed}")
    require("layout.no_visual_overlap" in fixed["fixed"], "overlap was not auto-repaired")
    require(fixed["regressions"] == [], f"new regression detected: {fixed}")
    require(fixed["candidate_status"] == "verified" and fixed["candidate"],
            f"verified candidate missing: {fixed}")
    require(fixed["promotion_performed"] is False and fixed["acceptance"] is False,
            "candidate was improperly promoted or report certified")
    require(fingerprint(seeded) == seeded_before,
            "auto-repair mutated original project!")
    candidate = Path(fixed["candidate"])
    require(candidate.is_dir() and candidate != seeded / report_subpath,
            "candidate missing or overlaps original")
    candidate_visual = json.loads(
        (candidate / visual_subpath.relative_to(report_subpath)).read_text(encoding="utf-8"))
    require(candidate_visual["position"]["x"] >= 320,
            "automatic correction did not eliminate seeded overlap")
    full = json.loads(full_path.read_text(encoding="utf-8"))
    stages = {stage["stage"]: stage["status"] for stage in full["stages"]}
    require(all(stages.get(stage) == "pass" for stage in
                ("inspect", "review", "propose", "repair", "verify", "remeasure")),
            f"not every required static repair gate passed: {stages}")
    require(len(json.dumps(fixed).encode("utf-8")) < 6000,
            "compact CLI output grew beyond the agent context budget")
    # v0.1.2: the owner-decision, gate and explicit-adoption chain, on the
    # installed wheel and on its own disposable copy of the fictional report.
    decisions_project = private / "owner decisions project"
    shutil.copytree(fixture, decisions_project)
    decisions_proof = owner_decisions_and_gate(
        vqs, decisions_project, pbip_file, report_subpath, private, env)

    # The result contract supports advanced full run output without losing evidence.
    _, reviewed = json_command(
        [str(vqs), "run", str(clean / pbip_file), "--mode", "review",
         "--scope", "static", "--summary", "--run-root", str(private / "runs"),
         "--run-id", "review-only"],
        private, env, allowed=(0, 1, 2), timeout=90)
    require(reviewed["verdict"] in {"pass", "fail", "blocked"},
            "review must expose machine-readable verdict")

    malformed = private / "ambiguous-project"
    malformed.mkdir()
    (malformed / "A.Report").mkdir()
    (malformed / "B.Report").mkdir()
    _, negative = json_command(
        [str(vqs), "fix", str(malformed), "--run-root", str(private / "runs")],
        private, env, allowed=(2,), timeout=30)
    require(negative["verdict"] == "blocked"
            and "2 report folders" in " ".join(negative["blocked_reasons"]),
            "ambiguous project must be refused")

    modern_meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "gh-runner-e2e", "version": "1.0"},
    }
    def modern(ident: int, method: str, **params: object) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "method": method,
                "params": {"_meta": modern_meta, **params}}

    theme_candidate = private / "theme candidate"
    modern_results = mcp_exchange(mcp, [
        modern(1, "server/discover"),
        modern(2, "tools/list"),
        modern(3, "tools/call", name="vqs_theme",
               arguments={"action": "presets"}),
        modern(4, "tools/call", name="vqs_theme",
               arguments={"action": "preview",
                          "report_dir": str(clean / pbip_file),
                          "mode": "dark", "palette_preset": "executive-blue"}),
        modern(5, "tools/call", name="vqs_theme",
               arguments={"action": "apply",
                          "report_dir": str(clean / pbip_file),
                          "mode": "dark", "palette_preset": "executive-blue"}),
        modern(6, "tools/call", name="vqs_theme",
               arguments={"action": "apply",
                          "report_dir": str(clean / pbip_file),
                          "candidate_root": str(theme_candidate),
                          "mode": "dark", "palette_preset": "executive-blue"}),
        modern(7, "tools/call", name="vqs_theme",
               arguments={"action": "audit",
                          "report_dir": str(theme_candidate)}),
    ], private, env)
    require(modern_results[0]["result"]["resultType"] == "complete",
            "stateless discover missing")
    tools_list = modern_results[1]["result"]["tools"]
    require(len(tools_list) == 10
            and all("outputSchema" in tool for tool in tools_list),
            "modern tool schemas missing")
    presets = modern_results[2]["result"]["structuredContent"]
    require(presets["status"] == "pass" and "executive-blue" in presets["presets"],
            "modern theme presets broken")
    preview = modern_results[3]["result"]["structuredContent"]
    require(preview.get("status") != "blocked",
            f"modern theme preview failed: {preview}")
    denied = modern_results[4]["result"]["structuredContent"]
    require(denied.get("verdict") == "blocked",
            "MCP theme apply without separate candidate path must block")
    applied = modern_results[5]["result"]["structuredContent"]
    require(applied.get("status") not in ("blocked", "fail"),
            f"modern theme apply failed: {applied}")
    require(theme_candidate.exists(), "theme candidate folder not generated")
    audited = modern_results[6]["result"]["structuredContent"]
    require(audited.get("status") == "pass",
            f"independently audited theme candidate was not clean: {audited}")
    require(fingerprint(clean) == clean_digest,
            "MCP theme preview/apply modified original")

    legacy_results = mcp_exchange(mcp, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "legacy-e2e", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "vqs_run_status",
                    "arguments": {"run_root": str(private / "runs"),
                                  "run_id": "nonexistent"}}}
    ], private, env)
    require(legacy_results[0]["result"]["protocolVersion"] == "2024-11-05",
            "legacy handshake changed")
    require(len(legacy_results[1]["result"]["tools"]) == 10,
            "legacy tool listing regressed")
    old = legacy_results[2]["result"]
    require("structuredContent" not in old
            and json.loads(old["content"][0]["text"])["verdict"] == "blocked",
            "legacy text-envelope behavior changed")

    report = {
        "scope": "wheel-installed source-only E2E, not Power BI Desktop",
        "python": sys.version.split()[0],
        "os": sys.platform,
        "installed": installed,
        "package": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "sdist_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "official_authoring_skill_sha256": preflight["skill"]["snapshot"]["sha256"],
        "authoring_assurance": preflight["assurance"],
        "negative_no_candidate": result["verdict"],
        "seeded_repair": {
            "verdict": fixed["verdict"],
            "outcome": fixed["outcome"],
            "resolved": fixed["fixed"],
            "regressions": fixed["regressions"],
            "candidate_x": candidate_visual["position"]["x"],
            "stages": stages},
        "owner_decisions_gate_adoption": decisions_proof,
        "modern_mcp": "discovery/list/presets/preview/denial/apply/audit PASS",
        "legacy_mcp": "initialize/list/full text envelope PASS",
        "source_unchanged": True,
        "native_desktop_acceptance": "NOT RUN",
        "result": "PASS",
    }
    (evidence / "runner-e2e-result.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write("## Installed-wheel source-only E2E: PASS\n"
                       f"- OS/Python: {sys.platform} / {sys.version.split()[0]}\n"
                       "- Official Microsoft authoring preflight: PASS (pinned)\n"
                       "- Seeded geometry: x=314 to x>=320, no new regressions\n"
                       "- Original project: unchanged; no promotion\n"
                       "- MCP modern + legacy + theme apply/audit: PASS\n"
                       "- Owner decisions -> changes -> adoption, gate/SARIF: PASS\n"
                       "- Stale answers, bogus answers, forged owner proof: BLOCKED\n"
                       "- Native Desktop acceptance: NOT RUN\n")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
