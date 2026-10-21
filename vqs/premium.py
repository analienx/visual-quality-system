"""Power BI premium-design preflight: source-grounded, advisory, no AI approval.

One report-wide page design contract, a few meaningful measurable checks and
three prioritized remedies. All observations come from the current PBIR;
inherited styles, pixels and intent are *never* inferred as observed facts.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any

from .pbir import report_context
from .triage import _report_input

SCHEMA = "vqs.premium-design/1"
EXCEPTIONS = frozenset({"spacing.peer_gutters", "typography.explicit_title_scale",
                        "density.data_coverage", "hierarchy.focal"})
CARD_TYPES = frozenset({"card", "cardvisual", "kpi", "multirowcard", "newcard"})
NONDATA_TYPES = frozenset({"slicer", "textbox", "shape", "basicshape",
                           "line", "image", "button", "actionbutton"})
TITLE_SIZE = re.compile(r"^(\\d+(?:\\.\\d+)?)D?$")


def contract_template(context: Mapping[str, Any]) -> dict[str, Any]:
    """Draft intent fields are explicit and empty; not inferred user approval."""
    return {"schema": SCHEMA, "source_sha256": context["source_sha256"],
            "pages": [
                {"page_id": page["id"], "archetype": "unspecified",
                 "audience": None, "primary_question": None,
                 "focal_visual_id": None, "max_data_coverage_pct": None,
                 "exceptions": []} for page in context["pages"]]}


def _validate_contract(raw: Mapping[str, Any], context: Mapping[str, Any]) -> dict:
    if (not isinstance(raw, dict) or set(raw) != {"schema", "source_sha256", "pages"}
            or raw.get("schema") != SCHEMA
            or raw.get("source_sha256") != context["source_sha256"]
            or not isinstance(raw.get("pages"), list)):
        raise ValueError("premium design contract absent, malformed or stale to report source")
    actual = {p["id"]: p for p in context["pages"]}
    results = {}
    for entry in raw["pages"]:
        if (not isinstance(entry, dict) or set(entry) != {
                "page_id", "archetype", "audience", "primary_question",
                "focal_visual_id", "max_data_coverage_pct", "exceptions"}):
            raise ValueError("premium design page entry schema invalid")
        pid = entry["page_id"]
        if not isinstance(pid, str) or pid not in actual or pid in results:
            raise ValueError("premium design contract has unknown/duplicate page")
        if entry["archetype"] not in {"unspecified", "executive", "analytical", "operational", "narrative"}:
            raise ValueError("unsupported premium page archetype")
        if any(v is not None and (not isinstance(v, str) or not v.strip())
               for v in (entry["audience"], entry["primary_question"])):
            raise ValueError("premium intent must be nonempty text or null")
        focal = entry["focal_visual_id"]
        if focal is not None and (not isinstance(focal, str)
                                  or focal not in {v["visual_id"] for v in actual[pid]["visuals"]}):
            raise ValueError("contract focal visual is not present in its declared page")
        budget = entry["max_data_coverage_pct"]
        if budget is not None and (type(budget) not in (int, float) or not 10 <= budget <= 95):
            raise ValueError("invalid data coverage budget; expected 10–95 percent")
        exceptions = entry["exceptions"]
        if (not isinstance(exceptions, list) or len(exceptions) != len({
                x for x in exceptions if isinstance(x, str)})
                or any(not isinstance(x, str) or x not in EXCEPTIONS for x in exceptions)):
            raise ValueError("unsupported or duplicate premium rule exception")
        results[pid] = entry
    if set(results) != set(actual):
        raise ValueError("premium design contract must name every current page")
    return results


def _rect(v: Mapping[str, Any], width: int, height: int) -> tuple[float, float, float, float] | None:
    position = v.get("position")
    if not isinstance(position, dict):
        return None
    values = [position.get(k) for k in ("x", "y", "width", "height")]
    if any(type(x) not in (int, float) or not -100000 < x < 100000 for x in values):
        return None
    x, y, w, h = map(float, values)
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
        return None
    return x, y, w, h


def _area_covered(rects: list[tuple[float, float, float, float]]) -> float:
    """Exact rectangle union; avoids double-counting layered visuals."""
    edges = sorted({x for x, _, w, _ in rects for x in (x, x + w)})
    covered = 0.0
    for left, right in pairwise(edges):
        intervals = sorted((y, y + h) for x, y, w, h in rects
                           if x < right and x + w > left)
        end = 0.0
        for start, stop in intervals:
            covered += (right - left) * max(0.0, stop - max(start, end))
            end = max(end, stop)
    return covered


def _explicit_title_size(v: Mapping[str, Any]) -> float | None:
    for prop in v.get("configured_container_properties", []):
        if (prop.get("path") ==
                "visual.visualContainerObjects.title[0].properties.fontSize.expr.Literal.Value"):
            text = str(prop.get("value", ""))
            matched = TITLE_SIZE.fullmatch(text)
            return float(matched.group(1)) if matched else None
    return None


def audit(source: str, *, contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    report, _model = _report_input(source, None)
    context = report_context(Path(report))
    config = (_validate_contract(contract, context) if contract is not None
              else _validate_contract(contract_template(context), context))
    findings: list[dict[str, Any]] = []
    metrics = []
    for page in context["pages"]:
        pid, width, height = page["id"], *page["canvas"]
        policy = config[pid]
        exclusions = set(policy["exceptions"])
        visuals = [(v, _rect(v, width, height)) for v in page["visuals"]]
        visible = [(v, box) for v, box in visuals if box is not None]
        data = [(v, box) for v, box in visible
                if v["visual_type"].casefold() not in NONDATA_TYPES]
        ratio = 100 * _area_covered([box for _, box in data]) / (width * height)
        metrics.append({"page_id": pid, "page_name": page["display_name"],
                        "visuals": len(page["visuals"]),
                        "geometry_measured": len(visible),
                        "data_coverage_pct": round(ratio, 2),
                        "archetype": policy["archetype"]})
        if ("density.data_coverage" not in exclusions
                and policy["max_data_coverage_pct"] is not None
                and ratio > policy["max_data_coverage_pct"]):
            findings.append({"rule": "density.data_coverage", "importance": "medium",
                             "page_id": pid, "visual_ids": [v["visual_id"] for v, _ in data],
                             "evidence": {"measured_pct": round(ratio, 2),
                                          "declared_budget_pct": policy["max_data_coverage_pct"]},
                             "recommendation": "Group or simplify content against the declared page-density budget; do not remove business answers without approval."})
        cards = [(v, box) for v, box in visible
                 if v["visual_type"].casefold() in CARD_TYPES]
        groups = {}
        for v, box in cards:
            groups.setdefault(round(box[1] / 4), []).append((v, box))
        if "spacing.peer_gutters" not in exclusions:
            for peers in groups.values():
                peers.sort(key=lambda r: r[1][0])
                if len(peers) < 3 or max(b[3] for _, b in peers) - min(
                        b[3] for _, b in peers) > 0.08 * height:
                    continue
                gaps = [round(b[0] - (a[0] + a[2]), 3)
                        for (_, a), (_, b) in pairwise(peers)]
                if gaps and min(gaps) >= 0 and max(gaps) - min(gaps) >= max(8, width * 0.012):
                    findings.append({"rule": "spacing.peer_gutters", "importance": "high",
                                     "page_id": pid, "visual_ids": [v["visual_id"] for v, _ in peers],
                                     "evidence": {"gaps_pbir": gaps,
                                                  "spread_pct": round(100 * (max(gaps) - min(gaps)) / width, 2)},
                                     "recommendation": "Align the peer KPI card gutters on a shared layout grid; preserve each visual's query and interactions."})
        if "typography.explicit_title_scale" not in exclusions:
            groups_by_kind: dict[str, list[tuple[str, float]]] = {}
            for v, _box in visible:
                kind = v["visual_type"].casefold()
                if kind in NONDATA_TYPES:
                    continue
                size = _explicit_title_size(v)
                if size is not None:
                    groups_by_kind.setdefault(kind, []).append((v["visual_id"], size))
            for kind, sizes in groups_by_kind.items():
                if (len(sizes) >= 2 and max(s for _, s in sizes) -
                        min(s for _, s in sizes) >= 3):
                    findings.append({"rule": "typography.explicit_title_scale",
                                     "importance": "medium", "page_id": pid,
                                     "visual_ids": [vid for vid, _ in sizes],
                                     "evidence": {"visual_type": kind,
                                                  "declared_pt": {vid: s for vid, s in sizes}},
                                     "recommendation": "Harmonize explicitly declared peer chart-title sizes, unless the difference communicates an intentional focal hierarchy."})
        focal = policy["focal_visual_id"]
        if focal and "hierarchy.focal" not in exclusions:
            focal_box = next((box for v, box in visible if v["visual_id"] == focal), None)
            focal_type = next((v["visual_type"].casefold() for v, _ in visible
                               if v["visual_id"] == focal), None)
            comparable = [b[2] * b[3] for v, b in data
                          if v["visual_id"] != focal
                          and v["visual_type"].casefold() == focal_type]
            if (focal_box is None or (comparable and focal_box[2] * focal_box[3]
                                     < 1.20 * median(comparable))):
                findings.append({"rule": "hierarchy.focal", "importance": "medium",
                                 "page_id": pid, "visual_ids": [focal],
                                 "evidence": {"focal_area": None if focal_box is None
                                              else round(focal_box[2] * focal_box[3], 1),
                                              "peer_median_area": median(comparable) if comparable else None},
                                 "recommendation": "Give the owner-declared focal visual clearer prominence; verify the reading path in a fresh full-page render."})
    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f["importance"]],
                                 f["page_id"], f["rule"], f["visual_ids"]))
    return {"schema": "vqs.premium-preflight/1", "source_sha256": context["source_sha256"],
            "report_dir": report, "status": "findings" if findings else "advisory",
            "pages": metrics, "findings": findings,
            "top_three": findings[:3],
            "known_limits": ["PBIR static geometry and explicitly declared formatting only",
                             "Inherited styles, visible clipping, color harmony and actual reading path require verified Desktop renders",
                             "Neither a clean preflight nor model critique establishes G2/G4/G6 release acceptance"]}


def markdown(result: Mapping[str, Any]) -> str:
    lines = ["# Premium Power BI — design preflight", "",
             f"**Source SHA-256:** `{result['source_sha256']}`",
             f"**Coverage:** {len(result['pages'])} pages; {len(result['findings'])} measured design opportunities",
             f"**Status:** {result['status']} (source only); native render and independent acceptance required", "",
             "## Highest-impact improvements"]
    if not result["top_three"]:
        lines += ["", "No source-proven premium contract violations. This does **not** certify visual beauty."]
    for index, item in enumerate(result["top_three"], 1):
        lines += ["", f"{index}. **{item['rule']}** — page `{item['page_id']}`",
                  f"   - Visuals: {', '.join(item['visual_ids'])}",
                  f"   - Evidence: {json.dumps(item['evidence'], ensure_ascii=False)}",
                  f"   - Action: {item['recommendation']}"]
    lines += ["", "## Page measurements", ""]
    for page in result["pages"]:
        lines.append(f"- {page['page_name']}: {page['visuals']} visuals; "
                     f"{page['data_coverage_pct']}% geometric data coverage")
    lines += ["", "## Evidence still required", ""]
    lines += [f"- {limit}" for limit in result["known_limits"]]
    return "\n".join(lines) + "\n"
