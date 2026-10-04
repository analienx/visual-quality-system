"""Read-only PBIR source inventory and identity. No Desktop, query, or image needed.

:func:`read_report_files` is the single unified reader for report folders:
every other emitter consumes it instead of walking PBIR itself. It returns
parsed documents plus explicit per-file issues (unreadable JSON, malformed
shape, missing required metadata) and a full file inventory with digests —
including files VQS cannot parse, whose bytes repair rules must preserve.

:func:`source_inventory` resolves the report's own definition.pbir dataset
reference to exactly one sibling model: unrelated sibling models never
affect identity. Registered static resources (themes, images) are
rendering-affecting source and are hashed; user-local ``.pbi`` settings
and runtime caches are excluded. Field scope follows the reference
validator: queryState, sortDefinition, filterConfig, objects.*, selector
metadata. Bookmark snapshots (name, targets, active section, filter
entities, groups) and per-page visual interactions are exposed as
static facts for repair invariants; dynamic interaction *effects*
still need a live host.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SOURCE_EXTENSIONS = frozenset({".json", ".tmdl", ".pbism", ".pbir"})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp",
                              ".webp"})
KNOWN_SCHEMA_MAJORS = {"report": 1, "page": 2, "visualcontainer": 2,
                         "pagesmetadata": 1}


def _schema_major(schema: object) -> tuple[str, int | None]:
    """Parse a Fabric $schema URL into (entity, major version)."""
    if not isinstance(schema, str):
        return "", None
    marker = "/definition/"
    if marker not in schema:
        return "", None
    entity = schema.split(marker, 1)[1].split("/", 1)[0].casefold()
    version = schema.rsplit("/", 2)[-2] if schema.count("/") >= 2 else ""
    major, _, _ = version.partition(".")
    return entity, int(major) if major.isdigit() else None


def _read_json_file(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return None, f"unreadable: {exc}"
    except ValueError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "expected a JSON object"
    return data, None


def _read_index_file(path: Path) -> tuple[list[str] | None, list[dict[str, Any]]]:
    """Read one page-order index file; (ids, issues), ids None when absent.

    A present file must be a JSON object whose ``pageOrder`` is a list
    of strings; anything else is ``pages_index_invalid`` (blocking).
    """
    rel = path.as_posix()
    if not path.is_file():
        return None, []
    data, error = _read_json_file(path)
    if error is not None:
        return None, [{"rule": "pages_index_invalid", "path": rel,
                       "detail": error}]
    order = data.get("pageOrder")
    if not isinstance(order, list) or not all(isinstance(p, str) for p in order):
        return None, [{"rule": "pages_index_invalid", "path": rel,
                       "detail": "pageOrder must be a list of strings"}]
    entity, major = _schema_major(data.get("$schema"))
    if entity and entity in KNOWN_SCHEMA_MAJORS and major != KNOWN_SCHEMA_MAJORS[entity]:
        return None, [{"rule": "unsupported_schema", "path": rel,
                       "schema": data.get("$schema")}]
    return list(order), []


def _display_name(pages: dict[str, dict[str, Any]], page_id: str) -> str:
    name = pages.get(page_id, {}).get("displayName")
    return name if isinstance(name, str) else page_id


def _select_page_index(root: Path
                       ) -> tuple[list[str], str, list[dict[str, Any]]]:
    """Listed ids from the winning index file (dangling included).

    Shared by the resolvable-order loader and the raw declared-order
    reader so identity comparison sees exactly what the index
    declares, including entries with no directory behind them.
    """
    canonical, issues = _read_index_file(
        root / "definition" / "pages" / "pages.json")
    if canonical is not None or issues:
        return list(canonical or []), "canonical", issues
    legacy, legacy_issues = _read_index_file(
        root / "definition" / "pages.json")
    issues = list(legacy_issues)
    if legacy is not None or legacy_issues:
        issues.append({"rule": "legacy_pages_index",
                       "path": "definition/pages.json"})
        return list(legacy or []), "legacy", issues
    return [], "unindexed", []


def listed_page_order(report_dir: str | Path) -> list[str]:
    """Raw declared page ids from the winning index (dangling included)."""
    listed, _origin, _issues = _select_page_index(Path(report_dir))
    return listed


def load_page_index(report_dir: str | Path, pages: dict[str, dict[str, Any]]
                    ) -> tuple[list[str], str, list[dict[str, Any]]]:
    """Order page ids from the canonical index, legacy index, or names.

    Returns ``(order, origin, issues)`` with origin one of
    ``canonical``/``legacy``/``unindexed``. The canonical
    ``definition/pages/pages.json`` wins when present; the legacy
    ``definition/pages.json`` is honored with a non-blocking
    ``legacy_pages_index`` notice; with neither, physical pages order
    by display name (no issue: the index is optional per the PBIR
    spec). Unlisted physical pages append in display-name order, so a
    defective unlisted page can never be silently omitted (R02);
    listed-but-missing pages are ``page_order_dangling`` (blocking) —
    the inventory cannot vouch for a page with no directory;
    duplicated order ids are ``page_order_duplicate`` (blocking);
    listed ids that cannot become evidence filenames are
    ``page_order_unsafe`` (blocking, same predicate as
    capture._safe_page_id).
    """
    listed, origin, issues = _select_page_index(Path(report_dir))
    seen: set[str] = set()
    for page_id in listed:
        if page_id in seen:
            issues.append({"rule": "page_order_duplicate", "page": page_id})
        seen.add(page_id)
        if (not isinstance(page_id, str) or not page_id
                or page_id != page_id.strip() or page_id.startswith(".")
                or "/" in page_id or "\\" in page_id or ":" in page_id):
            issues.append({"rule": "page_order_unsafe", "page": page_id})
    order = [page_id for page_id in listed if page_id in pages]
    for page_id in listed:
        if page_id not in pages:
            issues.append({"rule": "page_order_dangling", "page": page_id})
    unlisted = sorted((page_id for page_id in pages if page_id not in seen),
                      key=lambda page_id: _display_name(pages, page_id))
    return order + unlisted, origin, issues


def read_report_files(report_dir: str | Path) -> dict[str, Any]:
    """Parse a report folder once; malformed files become issues, never raise.

    Returns ``report``/``pages``/``visuals`` documents keyed by id,
    ``bookmarks`` (bookmark docs keyed by file id) and ``bookmark_groups``
    (raw group entries), ``files`` (every file with its digest or null
    when unreadable), and ``issues`` (unreadable JSON, wrong shapes,
    missing required metadata, unsupported schema majors). Page order
    follows the canonical ``definition/pages/pages.json`` index when
    present, else the legacy ``definition/pages.json`` index (flagged),
    else display-name order; see :func:`load_page_index`.
    """
    root = Path(report_dir)
    files: dict[str, str | None] = {}
    issues: list[dict[str, Any]] = []
    pages: dict[str, dict[str, Any]] = {}
    visuals: dict[tuple[str, str], dict[str, Any]] = {}
    report_doc: dict[str, Any] | None = None
    order: list[str] = []
    bookmarks: dict[str, dict[str, Any]] = {}
    bookmark_groups: list[dict[str, Any]] = []
    try:
        paths = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    except OSError as exc:
        return {"report": None, "pages": {}, "visuals": {}, "order": [],
                "bookmarks": {}, "bookmark_groups": [],
                "files": {}, "issues": [{"rule": "report_unreadable",
                                         "detail": str(exc)}]}
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            files[rel] = None
    version_path = root / "definition" / "version.json"
    version_doc: dict[str, Any] | None = None
    if version_path.is_file():
        data, error = _read_json_file(version_path)
        if error is not None:
            issues.append({"rule": "version_unreadable",
                           "path": "definition/version.json", "detail": error})
        else:
            version_doc = data
    else:
        issues.append({"rule": "version_missing",
                       "path": "definition/version.json"})
    report_path = root / "definition" / "report.json"
    if report_path.is_file():
        data, error = _read_json_file(report_path)
        if error is not None:
            issues.append({"rule": "report_doc_unreadable", "detail": error})
        else:
            missing = [key for key in ("$schema", "layoutOptimization",
                                       "themeCollection")
                       if key not in data]
            mistyped = [key for key, kind in
                        (("$schema", str), ("layoutOptimization", str),
                         ("themeCollection", dict))
                        if key in data and not isinstance(data[key], kind)]
            if missing or mistyped:
                issues.append({"rule": "report_doc_invalid",
                               "path": "definition/report.json",
                               "missing": missing, "mistyped": mistyped})
            if isinstance(data, dict):
                # Flagged but still readable: validation issues must
                # never silently drop report content (filters, config).
                report_doc = data
            if not missing and not mistyped:
                entity, major = _schema_major(data.get("$schema"))
                if (entity and entity in KNOWN_SCHEMA_MAJORS
                        and major != KNOWN_SCHEMA_MAJORS[entity]):
                    issues.append({"rule": "unsupported_schema",
                                   "path": "definition/report.json",
                                   "schema": data.get("$schema")})
    else:
        issues.append({"rule": "report_doc_missing",
                       "path": "definition/report.json"})
    bookmarks_root = root / "definition" / "bookmarks"
    if bookmarks_root.is_dir():
        index_path = bookmarks_root / "bookmarks.json"
        if index_path.is_file():
            data, error = _read_json_file(index_path)
            if error is not None:
                issues.append({"rule": "bookmark_index_unreadable",
                               "path": "definition/bookmarks/bookmarks.json",
                               "detail": error})
            elif not isinstance(data.get("groups"), list):
                issues.append({"rule": "bookmark_index_invalid",
                               "path": "definition/bookmarks/bookmarks.json"})
            else:
                bookmark_groups = [entry for entry in data["groups"]
                                   if isinstance(entry, dict)]
        for bookmark_path in sorted(bookmarks_root.glob("*.bookmark.json")):
            rel = bookmark_path.relative_to(root).as_posix()
            key = bookmark_path.name.removesuffix(".bookmark.json")
            data, error = _read_json_file(bookmark_path)
            if error is not None:
                issues.append({"rule": "bookmark_doc_unreadable", "path": rel,
                               "detail": error})
                continue
            if not isinstance(data.get("name"), str):
                issues.append({"rule": "bookmark_metadata_incomplete",
                               "path": rel, "missing": "name"})
            if not isinstance(data.get("displayName"), str):
                issues.append({"rule": "bookmark_metadata_incomplete",
                               "path": rel, "missing": "displayName"})
            bookmarks[key] = data
    pages_root = root / "definition" / "pages"
    page_dirs = sorted(p.name for p in pages_root.iterdir()
                       if p.is_dir() and not p.is_symlink()) if pages_root.is_dir() else []
    for page_id in page_dirs:
        page_path = pages_root / page_id / "page.json"
        if not page_path.is_file():
            issues.append({"rule": "page_doc_missing", "page": page_id})
            continue
        page, error = _read_json_file(page_path)
        if error is not None:
            issues.append({"rule": "page_doc_unreadable", "page": page_id, "detail": error})
            continue
        if not isinstance(page.get("displayName"), str):
            issues.append({"rule": "page_metadata_incomplete", "page": page_id,
                           "missing": "displayName"})
        if (not isinstance(page.get("width"), (int, float))
                or not isinstance(page.get("height"), (int, float))):
            issues.append({"rule": "page_metadata_incomplete", "page": page_id,
                           "missing": "width/height"})
        entity, major = _schema_major(page.get("$schema"))
        if entity and entity in KNOWN_SCHEMA_MAJORS and major != KNOWN_SCHEMA_MAJORS[entity]:
            issues.append({"rule": "unsupported_schema", "page": page_id,
                           "schema": page.get("$schema")})
        pages[page_id] = page
        visuals_root = pages_root / page_id / "visuals"
        if not visuals_root.is_dir():
            continue
        for visual_dir in sorted(p for p in visuals_root.iterdir()
                                 if p.is_dir() and not p.is_symlink()):
            visual_path = visual_dir / "visual.json"
            key = (page_id, visual_dir.name)
            if not visual_path.is_file():
                issues.append({"rule": "visual_doc_missing", "page": page_id,
                               "visual": visual_dir.name})
                continue
            visual, error = _read_json_file(visual_path)
            if error is not None:
                issues.append({"rule": "visual_doc_unreadable", "page": page_id,
                               "visual": visual_dir.name, "detail": error})
                continue
            if not isinstance(visual.get("name"), str):
                issues.append({"rule": "visual_metadata_incomplete", "page": page_id,
                               "visual": visual_dir.name, "missing": "name"})
            if not isinstance(visual.get("position"), dict):
                issues.append({"rule": "visual_metadata_incomplete", "page": page_id,
                               "visual": visual_dir.name, "missing": "position"})
            if not isinstance(visual.get("visual"), dict):
                issues.append({"rule": "visual_metadata_incomplete", "page": page_id,
                               "visual": visual_dir.name, "missing": "visual"})
            entity, major = _schema_major(visual.get("$schema"))
            if entity and entity in KNOWN_SCHEMA_MAJORS and major != KNOWN_SCHEMA_MAJORS[entity]:
                issues.append({"rule": "unsupported_schema", "page": page_id,
                               "visual": visual_dir.name, "schema": visual.get("$schema")})
            visuals[key] = visual
    order, _origin, index_issues = load_page_index(root, pages)
    issues.extend(index_issues)
    return {"report": report_doc, "version": version_doc, "pages": pages,
            "visuals": visuals, "order": order, "bookmarks": bookmarks,
            "bookmark_groups": bookmark_groups, "files": files,
            "issues": issues}


def resolve_model_dir(report: str | Path) -> str | None:
    """Model dir named by the report dataset reference, else None.

    F09/D1: the report source is the single authority for its model.
    """
    model_dir, _rule, _detail = _resolve_model_dir(Path(report))
    return str(model_dir) if model_dir is not None else None


def _hash_model_dir(model_dir: Path) -> str | None:
    """Hash sorted TMDL bytes under a model dir; None when absent/empty.

    Same walk as :func:`vqs.pipeline._model_digest` (kept separate to
    avoid a pipeline import cycle); the two must agree byte for byte.
    """
    try:
        files = sorted(p for p in model_dir.rglob("*.tmdl") if p.is_file()
                       and not p.is_symlink())
    except OSError:
        return None
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        try:
            content = path.read_bytes()
        except OSError:
            return None
        digest.update(path.relative_to(model_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def resolved_model_digest(report: str | Path) -> tuple[str | None, str | None, str | None]:
    """Resolve the report model and digest it; (digest, rule, detail).

    Returns the model TMDL digest, or (None, rule, detail) with the
    :func:`_resolve_model_dir` miss rule (absent/unresolved/remote).
    Relocation guards compare this digest across original and
    candidate instead of trusting directory names.
    """
    model_dir, rule, detail = _resolve_model_dir(Path(report))
    if model_dir is None:
        return None, rule, detail
    digest = _hash_model_dir(model_dir)
    if digest is None:
        return None, "model_reference_unresolved", (
            f"referenced model has no readable TMDL: {model_dir}")
    return digest, None, None


def _resolve_model_dir(report: Path) -> tuple[Path | None, str | None, str | None]:
    """Resolve definition.pbir byPath; (dir, rule, detail) with a null dir on miss.

    A missing PBIR is absence of a claim (model_reference_absent);
    an unreadable or dangling reference is unresolved (blocking).
    """
    pbir_path = report / "definition.pbir"
    if not pbir_path.is_file():
        return (None, "model_reference_absent",
                "definition.pbir missing: model source excluded from identity")
    try:
        data = json.loads(pbir_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, "model_reference_unresolved", f"definition.pbir unreadable: {exc}"
    dataset_ref = data.get("datasetReference", {}) or {}
    ref = dataset_ref.get("byPath", {}) or {}
    target = ref.get("path", "")
    if not isinstance(target, str) or not target:
        if isinstance(dataset_ref.get("byConnection"), dict):
            return (None, "model_reference_remote",
                    ("definition.pbir uses datasetReference.byConnection: "
                     "remote models stay outside static identity"))
        return (None, "model_reference_unresolved",
                "definition.pbir has no datasetReference.byPath")
    candidate = (report / target).resolve()
    definition = candidate / "definition"
    model_root = definition if definition.is_dir() else candidate
    if not model_root.is_dir() or not any(model_root.rglob("*.tmdl")):
        return (None, "model_reference_unresolved",
                f"referenced model has no TMDL: {target}")
    return model_root, None, None


def source_inventory(report: str | Path) -> dict[str, Any]:
    """Fingerprint report + referenced-model source; unrelated siblings excluded.

    Returns ``digest`` (report JSON/PBIR, registered images, referenced-model
    TMDL/JSON), ``model_dir`` (resolved path or null), ``report_files`` and
    ``model_files`` (relative paths hashed), and ``issues`` (unresolved
    model reference, unreadable files). ``.pbi`` user settings never count.
    """
    report_path = Path(report).resolve()
    model_dir, model_rule, model_detail = _resolve_model_dir(report_path)
    issues: list[dict[str, Any]] = []
    if model_rule is not None:
        issues.append({"rule": model_rule, "detail": model_detail})
    digest = hashlib.sha256()
    report_files: list[str] = []
    for path in sorted(report_path.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(report_path)
        if ".pbi" in rel.parts:
            continue
        suffix = path.suffix.lower()
        in_resources = "StaticResources" in rel.parts
        if suffix in SOURCE_EXTENSIONS or (in_resources and suffix in IMAGE_EXTENSIONS):
            report_files.append(rel.as_posix())
            try:
                content = path.read_bytes()
            except OSError as exc:
                issues.append({"rule": "source_file_unreadable",
                               "path": rel.as_posix(), "detail": str(exc)})
                continue
            digest.update(rel.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
    model_files: list[str] = []
    if model_dir is not None:
        for path in sorted(model_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(model_dir)
            if ".pbi" in rel.parts or path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            model_files.append(rel.as_posix())
            try:
                content = path.read_bytes()
            except OSError as exc:
                issues.append({"rule": "source_file_unreadable",
                               "path": rel.as_posix(), "detail": str(exc)})
                continue
            digest.update(b"model\0")
            digest.update(rel.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
    return {"digest": digest.hexdigest(),
            "model_dir": str(model_dir) if model_dir else None,
            "report_files": report_files, "model_files": model_files,
            "issues": issues}


def source_digest(report: Path) -> str:
    """Fingerprint report plus referenced-model source (see source_inventory)."""
    return str(source_inventory(report)["digest"])


def _literals(node: object, prefix: str = "", limit: int = 50) -> list[dict]:
    result: list[dict] = []
    def walk(value: object, key: str, depth: int) -> None:
        if len(result) >= limit or depth > 16:
            return
        if isinstance(value, dict):
            literal = value.get("Literal")
            if isinstance(literal, dict) and "Value" in literal:
                text = str(literal["Value"])
                if len(text) <= 180:
                    result.append({"path": key + ".Literal.Value", "value": text})
                return
            for name, child in value.items():
                walk(child, f"{key}.{name}" if key else name, depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{key}[{index}]", depth + 1)
    walk(node, prefix, 0)
    return result


def visual_context(item: dict) -> dict:
    visual = item.get("visual", {})
    roles = visual.get("query", {}).get("queryState", {})
    bindings = {
        name: [{"query_ref": projection.get("queryRef", ""), "field": projection.get("field", {}),
                "active": projection.get("active", True)} for projection in spec.get("projections", [])]
        for name, spec in roles.items()
    }
    return {"visual_id": item["name"], "visual_type": visual.get("visualType", ""),
            "position": item["position"], "field_bindings": bindings,
            "sort_definition": visual.get("query", {}).get("sortDefinition"),
            "configured_visual_properties": _literals(visual.get("objects", {}), "visual.objects"),
            "configured_container_properties": _literals(
                visual.get("visualContainerObjects", {}), "visual.visualContainerObjects"),
            "evidence_limits": {"pixel_readability": "requires a fresh rendered image",
                                "data_values": "requires an authorized semantic-model query",
                                "missing_property": "may be inherited from theme or Desktop defaults"}}


def report_context(report: Path, *,
                   allow_unresolved_model: bool = False) -> dict:
    """Read native PBIR page/visual inventory without asserting design approval.

    Raises ValueError listing every metadata problem instead of KeyError on
    the first missing field; callers map it to blocked, never to approval.

    ``allow_unresolved_model`` is only for relocated repair
    candidates whose byPath model stays pinned at the original
    location (the sealed repair records the original model digest
    and sealed verify re-checks it): the candidate copy cannot
    resolve a model that was never relocated with it, and that
    must not block a visual-only repair whose identity basis is
    the pin rather than candidate-side resolution.
    """
    model_rules = ("model_reference_remote", "model_reference_unresolved")
    found = read_report_files(report)
    _model_dir, model_rule, model_detail = _resolve_model_dir(Path(report))
    if model_rule in model_rules:
        found["issues"].append({"rule": model_rule, "detail": model_detail})
    fatal = [issue for issue in found["issues"]
             if issue["rule"] in ("report_unreadable", "report_doc_unreadable",
                                  "report_doc_missing", "report_doc_invalid",
                                  "pages_index_invalid", "page_order_duplicate",
                                  "page_order_dangling", "page_order_unsafe",
                                  "page_doc_unreadable",
                                  "page_metadata_incomplete",
                                  "visual_doc_unreadable",
                                  "visual_metadata_incomplete",
                                  "page_doc_missing",
                                  "visual_doc_missing", "unsupported_schema",
                                  "version_missing", "version_unreadable",
                                  "model_reference_remote",
                                  "model_reference_unresolved")
             and not (allow_unresolved_model
                      and issue["rule"] in model_rules)]
    if fatal:
        detail = "; ".join(sorted({f'{i["rule"]}:{i.get("page", "?")}/{i.get("visual", "")}'
                                   for i in fatal}))
        order = ", ".join(found["order"])
        raise ValueError(
            f"Report metadata invalid: {detail} "
            f"(declared page order: {order})")
    pages = []
    for page_id in found["order"]:
        page = found["pages"].get(page_id)
        if page is None:
            continue
        items = [(vid, found["visuals"][(page_id, vid)])
                 for (pid, vid) in sorted(found["visuals"]) if pid == page_id]
        pages.append({"id": page_id, "display_name": page["displayName"],
                      "canvas": [page["width"], page["height"]],
                      "visuals": [visual_context(item) for _, item in items]})
    return {"schema": 1, "kind": "PBIR source metadata, not visual or data approval",
            "source_sha256": source_digest(Path(report)), "pages": pages}
