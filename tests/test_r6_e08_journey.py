"""R6-E08: documented installed journey on two unrelated projects.

Oracle A08: the exact commands in docs/JOURNEY.md (modulo paths) run
through the installed CLI surface on two independently built
synthetic projects. Project A walks inspect -> measure/check ->
typed repair -> verified bundle review to the static ceiling
(static_conformance pass, image_review_required blocked). Project B
exercises negative paths: a missing queryRef blocks the check, a
model-target plan fails closed without touching the filesystem, and
a tampered transport is refused. Synthetic renders and readiness
are labeled synthetic throughout; nothing claims Desktop capture
or live data. Each project produces its own effects through the
real pipeline; no helper lends producer outputs across projects.
"""
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

from vqs.cli import main as vqs_main
from vqs.pbir import source_digest
from vqs.review.adjudicate import adjudicate_bundle
from vqs.review.bundle import verify as verify_bundle

VQS_BIN = shutil.which("vqs")
needs_vqs = pytest.mark.skipif(VQS_BIN is None,
                               reason="installed vqs entry point not on PATH")

FAIR = "https://developer.microsoft.com/json-schemas/fabric/item/"
SYNTH = "synthetic-journey-standin"
LEAF = ["visual", "objects", "categoryAxis", 0, "properties",
        "labelPrecision", "expr", "Literal", "Value"]
TICK_FORMAT = "definition/pages/P1/visuals/v1/visual.json"
HONEST_REASON = ("Synthetic journey stand-in: static shape verified; "
                 "pixel review not performed.")


def _write_png(path: Path, width: int = 500, height: int = 500) -> None:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x20\x60\xc0" * width
                   for _ in range(height))
    comp = zlib.compress(raw)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def _page_shell(report: Path, pages: tuple[str, ...]) -> None:
    definition = report / "definition"
    for page_id in pages:
        page_dir = definition / "pages" / page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "page.json").write_text(json.dumps(
            {"displayName": page_id, "width": 500, "height": 500}),
            encoding="utf-8")
    (definition / "pages" / "pages.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/pagesMetadata/1.1.0/schema.json",
         "pageOrder": list(pages)}), encoding="utf-8")
    (definition / "pages.json").write_text(
        json.dumps({"pageOrder": list(pages)}), encoding="utf-8")
    (definition / "version.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/versionMetadata/1.0.0/schema.json",
         "version": "2.0.0"}), encoding="utf-8")
    (definition / "report.json").write_text(json.dumps(
        {"$schema": FAIR + "report/definition/report/3.3.0/schema.json",
         "layoutOptimization": "None", "themeCollection": {}}),
        encoding="utf-8")


def _measure_projection(entity: str, prop: str,
                        query_ref: str | None) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "active": True,
        "field": {"Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop}},
        "nativeQueryRef": prop}
    if query_ref is not None:
        projection["queryRef"] = query_ref
    return projection


def _visual_doc(name: str, visual_type: str,
                projections: list[dict[str, Any]],
                tick_value: str | None = None) -> dict[str, Any]:
    visual: dict[str, Any] = {
        "visualType": visual_type,
        "query": {"queryState": {"Values": {"projections": projections}}}}
    if tick_value is not None:
        visual["objects"] = {"categoryAxis": [{"properties": {
            "labelPrecision": {"expr": {"Literal": {
                "Value": tick_value}}}}}]}
    return {
        "name": name,
        "position": {"x": 0, "y": 0, "width": 100, "height": 100, "z": 1},
        "visual": visual}


def _build_sales(root: Path) -> tuple[Path, Path]:
    """Independent project A: Revenue reused in a bar and a card."""
    report = root / "sales.Report"
    _page_shell(report, ("P1", "P2"))
    visuals = report / "definition" / "pages"
    v1 = visuals / "P1" / "visuals" / "v1"
    v1.mkdir(parents=True)
    (v1 / "visual.json").write_text(json.dumps(_visual_doc(
        "v1", "barChart",
        [_measure_projection("Sales", "Revenue", "Sales.Revenue")],
        tick_value="2")), encoding="utf-8")
    v2 = visuals / "P2" / "visuals" / "v2"
    v2.mkdir(parents=True)
    (v2 / "visual.json").write_text(json.dumps(_visual_doc(
        "v2", "card",
        [_measure_projection("Sales", "Revenue", "Sales.Revenue")])),
        encoding="utf-8")
    model = root / "sales.SemanticModel"
    tables = model / "tables"
    tables.mkdir(parents=True)
    (tables / "Sales.tmdl").write_text(
        "table Sales\n\n\tmeasure Revenue = 1\n\n\tmeasure Orders = 2\n",
        encoding="utf-8")
    return report, model


def _build_inventory(root: Path) -> tuple[Path, Path]:
    """Independent project B: one bound visual, one missing queryRef."""
    report = root / "inventory.Report"
    _page_shell(report, ("Overview", "Detail"))
    visuals = report / "definition" / "pages"
    w1 = visuals / "Overview" / "visuals" / "w1"
    w1.mkdir(parents=True)
    (w1 / "visual.json").write_text(json.dumps(_visual_doc(
        "w1", "lineChart",
        [_measure_projection("Inventory", "StockOnHand",
                             "Inventory.StockOnHand")])),
        encoding="utf-8")
    w2 = visuals / "Detail" / "visuals" / "w2"
    w2.mkdir(parents=True)
    (w2 / "visual.json").write_text(json.dumps(_visual_doc(
        "w2", "card",
        [_measure_projection("Inventory", "StockOnHand", None)])),
        encoding="utf-8")
    model = root / "inventory.SemanticModel"
    tables = model / "tables"
    tables.mkdir(parents=True)
    (tables / "Inventory.tmdl").write_text(
        "table Inventory\n\n\tmeasure StockOnHand = 3\n", encoding="utf-8")
    return report, model


def _renders(report: Path, root: Path, name: str,
              pages: tuple[str, ...]) -> Path:
    renders = root / name
    renders.mkdir(exist_ok=True)
    mapping, files = {}, {}
    for page_id in pages:
        _write_png(renders / f"{page_id}.png")
        files[f"{page_id}.png"] = hashlib.sha256(
            (renders / f"{page_id}.png").read_bytes()).hexdigest()
        mapping[page_id] = f"{page_id}.png"
    (renders / "capture-manifest.json").write_text(json.dumps(
        {"source_sha256": source_digest(report), "page_images": mapping,
         "files": files,
         "calibration": {"canvas_width": 500, "canvas_height": 500,
                         "scale": 1, "viewport": "500x500@1x",
                         "method": SYNTH},
         "data_readiness": {"populated": True, "method": SYNTH,
                            "checked_at": "2026-10-05T00:00:00Z"}}),
        encoding="utf-8")
    return renders


def _complete_form(template: dict[str, Any]) -> dict[str, Any]:
    form = json.loads(json.dumps(template))
    form["reviewer"]["id"] = "reviewer-1"
    form["image_capability"] = {"available": True, "provider": SYNTH}
    for page in form["pages"]:
        page["pixels"] = [500, 500]
        for answer in page["observations"]:
            answer.update(status="pass", reason=HONEST_REASON)
    return form


def test_sales_journey_to_static_ceiling(tmp_path: Path,
                                         capsys: Any) -> None:
    """Project A: documented commands reach the static ceiling."""
    report, model = _build_sales(tmp_path)
    runs = tmp_path / "runs"
    assert vqs_main(["inspect", str(report), "--model", str(model),
                     "--out", str(tmp_path / "inspect.json")]) == 0
    inspected = json.loads((tmp_path / "inspect.json").read_text(
        encoding="utf-8"))
    assert inspected["verdict"] == "pass"
    assert vqs_main(["measure", str(report), "--model", str(model),
                     "--out", str(tmp_path / "facts.json")]) == 0
    facts = json.loads((tmp_path / "facts.json").read_text(
        encoding="utf-8"))
    reused = [entry for entry in facts["models"][0]["bindings"]
              if entry["query_ref"] == "Sales.Revenue"]
    assert len(reused) == 2
    assert {(entry["page"], entry["visual"]) for entry in reused} == {
        ("P1", "v1"), ("P2", "v2")}
    assert vqs_main(["check", str(tmp_path / "facts.json"),
                     "--run-root", str(runs),
                     "--run-id", "sales1"]) == 0
    manifest = json.loads((runs / "sales1" / "manifest.json").read_text(
        encoding="utf-8"))
    assert manifest["artifacts"]["observation"]["gate"] == "G0"
    assert manifest["artifacts"]["gate"] == "G0"
    assert manifest["artifacts"]["status"] == "pass"
    plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "P1", "visual": "v1"},
        "target": "visual", "path": list(LEAF), "value": "3",
        "writes": [TICK_FORMAT]}],
        "rollback": "re-materialize from original",
        "write_targets": [TICK_FORMAT]}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    candidate = tmp_path / "candidate-sales.Report"
    assert vqs_main(["validate-plan", str(tmp_path / "plan.json"),
                     "--original", str(report),
                     "--candidate-root", str(candidate),
                     "--run-root", str(runs),
                     "--run-id", "vp1"]) == 0
    capsys.readouterr()
    assert vqs_main(["repair", str(tmp_path / "plan.json"),
                     "--original", str(report),
                     "--candidate-root", str(candidate),
                     "--run-root", str(runs), "--run-id", "repair1",
                     "--authoring-backend", "direct"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["authoring"]["backend"] == "direct"
    patched = json.loads((candidate / TICK_FORMAT).read_text(
        encoding="utf-8"))
    node: Any = patched
    for step in LEAF[:-1]:
        node = node[step] if isinstance(node, dict) else node[int(step)]
    assert node[LEAF[-1]] == "3"
    assert vqs_main(["request-review", str(candidate),
                     str(_renders(candidate, tmp_path, "renders",
                                  ("P1", "P2"))),
                     "--fixer-id", "fixer-1"]) == 0
    template = json.loads(capsys.readouterr().out)
    form_path = tmp_path / "form.json"
    form_path.write_text(json.dumps(_complete_form(template)),
                         encoding="utf-8")
    assert vqs_main(["bundle", "pack", str(candidate),
                     str(tmp_path / "renders"),
                     str(tmp_path / "bundle-you"),
                     "--fixer-id", "fixer-1"]) == 0
    capsys.readouterr()
    assert vqs_main(["bundle", "verify",
                     str(tmp_path / "bundle-you")]) == 0
    capsys.readouterr()
    assert vqs_main(["adjudicate-bundle", str(form_path),
                     "--transport-bundle", str(tmp_path / "bundle-you"),
                     "--report", str(candidate),
                     "--run-root", str(runs),
                     "--run-id", "adj1"]) == 2
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["verdict"] == "blocked"
    checks = {row["check"]: row["status"] for row in sealed["findings"]}
    assert checks.get("image_review_required") == "blocked"
    assert "source_pages_unbound" not in checks
    assert not any(status == "fail" for status in checks.values())
    # Static ceiling through the real verify authority (same
    # transport the CLI just bound): conformant yet never passing.
    form = json.loads(form_path.read_text(encoding="utf-8"))
    decided = adjudicate_bundle(
        form, verify_bundle(str(tmp_path / "bundle-you"), str(candidate)))
    assert decided["static_conformance"] == "pass"
    assert decided["verdict"] == "blocked"


def test_inventory_negative_paths(tmp_path: Path, capsys: Any) -> None:
    """Project B: unknown bindings, model plans, and tamper fail closed."""
    report, model = _build_inventory(tmp_path)
    runs = tmp_path / "runs"
    assert vqs_main(["measure", str(report), "--model", str(model),
                     "--out", str(tmp_path / "facts-b.json")]) == 0
    assert vqs_main(["check", str(tmp_path / "facts-b.json"),
                     "--run-root", str(runs),
                     "--run-id", "inv1"]) == 2
    measured = json.loads((tmp_path / "facts-b.json").read_text(
        encoding="utf-8"))
    orphans = [entry for entry in measured["models"][0]["bindings"]
               if entry.get("query_ref_missing")]
    assert len(orphans) == 1
    assert (orphans[0]["page"], orphans[0]["visual"]) == ("Detail", "w2")
    findings = (runs / "inv1" / "findings.json").read_text(encoding="utf-8")
    assert "binding_projection_unidentified" in findings
    bad_plan = {"operations": [{
        "type": "axis.tick_format",
        "selector": {"page": "Overview", "visual": "w1"},
        "target": "model", "path": list(LEAF), "value": "3",
        "writes": [TICK_FORMAT]}],
        "rollback": "re-materialize from original",
        "write_targets": [TICK_FORMAT]}
    (tmp_path / "model-plan.json").write_text(json.dumps(bad_plan),
                                              encoding="utf-8")
    assert vqs_main(["validate-plan", str(tmp_path / "model-plan.json"),
                     "--original", str(report),
                     "--candidate-root",
                     str(tmp_path / "candidate-bad"),
                     "--run-root", str(runs),
                     "--run-id", "vp-bad"]) == 1
    assert vqs_main(["repair", str(tmp_path / "model-plan.json"),
                     "--original", str(report),
                     "--candidate-root", str(tmp_path / "candidate-bad"),
                     "--run-root", str(runs),
                     "--run-id", "repair-bad"]) == 1
    assert not (tmp_path / "candidate-bad").exists()
    renders = _renders(report, tmp_path, "renders-b",
                       ("Overview", "Detail"))
    assert vqs_main(["bundle", "pack", str(report), str(renders),
                     str(tmp_path / "bundle-b"),
                     "--fixer-id", "fixer-1"]) == 0
    capsys.readouterr()
    (tmp_path / "bundle-b" / "Overview.png").write_bytes(b"tampered")
    form_path = tmp_path / "form-b.json"
    form_path.write_text(json.dumps({"source_sha256": source_digest(report),
                                     "source_pages": ["Overview", "Detail"],
                                     "pages": []}),
                         encoding="utf-8")
    assert vqs_main(["adjudicate-bundle", str(form_path),
                     "--transport-bundle", str(tmp_path / "bundle-b"),
                     "--run-root", str(runs),
                     "--run-id", "adj-bad"]) == 2
    assert "Transport invalid" in capsys.readouterr().out


@needs_vqs
def test_installed_measure_matches_documented_command(
        tmp_path: Path) -> None:
    """Installed entry point runs the documented measure command."""
    report, model = _build_sales(tmp_path)
    out = tmp_path / "installed-facts.json"
    proc = subprocess.run(
        [VQS_BIN, "measure", str(report), "--model", str(model),
         "--out", str(out)],
        capture_output=True, text=True, timeout=180, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    facts = json.loads(out.read_text(encoding="utf-8"))
    assert facts["models"][0]["model_dir"] == str(model)
