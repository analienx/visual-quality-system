"""Atomic candidate application (WP-09 execution half).

Two stages, no shortcuts: the plan validates (allowlist) before anything
is copied, and every operation binds (recipes) before anything is
written. The candidate root must be fresh; the original is never
modified (verified by digest after the run). Any failure restores the
candidate snapshot and blocks with the exact op index and reason.
chart.replace needs a vetted registered template plus identical intent
or an owner approval; nothing else may change a visual's type or query.
Every write lands in a visual.json under the candidate report tree: the
executor physically cannot touch model files, so broader DAX/model
mutation stays a later separately authorized capability even when a plan
carries an owner approval id.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .allowlist import (
    normalize_targets,
    validate_materialized_roots,
    validate_plan,
    within_root,
)
from .recipes import RecipeError, affected_pages, bind_operation
from .templates import TemplateError, get_template, verify_bindings


class RepairError(OSError):
    """Candidate materialization or application failed; nothing applied."""


def _digest_map(entries: list[tuple[str, bytes]]) -> str:
    """Hash (relative path, content) pairs in sorted order.

    Shared by tree digests and pre-copy pins so the two can never
    disagree byte for byte.
    """
    digest = hashlib.sha256()
    for rel, data in sorted(entries):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def tree_digest(report: str | Path) -> str:
    """Fingerprint a report tree relative to its own root.

    Unlike source_digest (which binds the report's parent path and
    sibling models), this compares original and candidate CONTENT across
    different roots: identical trees digest identically wherever they
    live. Any link or hardlink inside refuses instead of hashing
    through it.
    """
    root = Path(report)
    try:
        entries = sorted(root.rglob("*"))
    except OSError as exc:
        raise RepairError(f"cannot walk {root}: {exc}") from exc
    root_real = os.path.normcase(os.path.realpath(root))
    pairs: list[tuple[str, bytes]] = []
    for path in entries:
        if path.is_symlink() or not within_root(root_real, str(path)):
            raise RepairError(f"link inside repair tree: {path}")
        if path.is_file():
            try:
                siblings = path.stat().st_nlink
            except OSError as exc:
                raise RepairError(f"cannot stat {path}: {exc}") from exc
            if siblings > 1:
                raise RepairError(f"hardlink inside repair tree: {path}")
            try:
                pairs.append((path.relative_to(root).as_posix(),
                              path.read_bytes()))
            except OSError as exc:
                raise RepairError(f"cannot read {path}: {exc}") from exc
    return _digest_map(pairs)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RepairError(f"cannot read {path}: {exc}") from exc


def _write_json(path: Path, doc: Any) -> None:
    try:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        raise RepairError(f"cannot write {path}: {exc}") from exc


def _walk_original(original: str) -> tuple[str, list[tuple[str, str]]]:
    """Validated (relative, absolute) original files; refuses links/loops.

    The same walk feeds the pre-copy pin and the copy itself, so the
    pin and the materialized candidate cannot disagree on membership.
    """
    original_real = os.path.normcase(os.path.realpath(original))
    failures: list[OSError] = []

    def _on_error(exc: OSError) -> None:
        failures.append(exc)

    seen: set[str] = {original_real}
    found: list[tuple[str, str]] = []
    walker = os.walk(original, followlinks=False, onerror=_on_error)
    for current, dirs, files in walker:
        for name in list(dirs):
            marker = os.path.normcase(os.path.realpath(
                os.path.join(current, name)))
            if marker in seen:
                raise RepairError("original contains a directory loop: "
                                  f"{os.path.join(current, name)}")
            seen.add(marker)
        for name in files:
            source = os.path.join(current, name)
            if os.path.islink(source):
                raise RepairError(f"original contains a link: {source}")
            if not within_root(original_real, source):
                raise RepairError("original entry escapes its root: "
                                  f"{source}")
            found.append((os.path.relpath(source, original), source))
    if failures:
        raise RepairError(f"original unreadable: {failures[0]}")
    return original_real, found


def _snapshot_original(original: str) -> list[tuple[str, bytes]]:
    """Pin the original content before any copy; R19 pre-copy baseline.

    Relative names use forward slashes so the pin hashes exactly like
    :func:`tree_digest` on every host.
    """
    _real, found = _walk_original(original)
    try:
        return [(rel.replace(os.sep, "/"), Path(source).read_bytes())
                for rel, source in found]
    except OSError as exc:
        raise RepairError(f"original unreadable: {exc}") from exc


def _assert_original_pinned(original: str, before_digest: str,
                            stage: str) -> None:
    """Re-snapshot the original; any drift since the pin refuses (T11).

    Monkeypatch seam: tests wrap this to stage after-copy saves and
    assert the hook ran; the guard logic itself always executes, and
    the original is never written back.
    """
    current = _digest_map(_snapshot_original(original))
    if current != before_digest:
        raise RepairError(f"original changed {stage}; retry with a fresh "
                          "candidate root")


def _assert_model_pinned(original: str, model_pin: dict,
                         stage: str) -> None:
    """Re-resolve the original model identity; drift refuses (T11)."""
    from vqs.pbir import resolved_model_digest

    kind = model_pin.get("kind")
    if kind in (None, "absent"):
        target, connection = bypath_claim(Path(original))
        if target is not None or connection is not None:
            raise RepairError(f"original gained a model claim {stage}")
        return
    if kind == "remote":
        _target, connection = bypath_claim(Path(original))
        if connection != model_pin.get("connection"):
            raise RepairError(f"original remote model claim changed {stage}")
        return
    if kind == "byPath":
        digest, _rule, _detail = resolved_model_digest(original)
        if digest != model_pin.get("digest"):
            raise RepairError(f"original model changed {stage}")
        return
    raise RepairError(f"unknown model pin kind {stage}: {kind!r}")


def bypath_claim(report: Path) -> tuple[str | None, Any]:
    """Original model claim: (byPath target, byConnection doc).

    (None, None) means the report makes no model claim at all; a
    present-but-unusable reference refuses instead of guessing.
    """
    pbir_path = report / "definition.pbir"
    if not pbir_path.is_file():
        return None, None
    try:
        data = json.loads(pbir_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RepairError(f"definition.pbir unreadable: {exc}") from exc
    ref = data.get("datasetReference", {}) or {}
    if not isinstance(ref, dict):
        raise RepairError("definition.pbir datasetReference is not an object")
    by_path = ref.get("byPath", {}) or {}
    target = by_path.get("path", "") if isinstance(by_path, dict) else ""
    if isinstance(target, str) and target:
        return target, None
    connection = ref.get("byConnection")
    if isinstance(connection, dict):
        return None, connection
    raise RepairError("definition.pbir names no datasetReference.byPath "
                      "or byConnection model")


def _model_root_beneath(base: Path, target: str) -> Path:
    """Resolve a byPath target against a report root.

    Mirrors ``vqs.pbir._resolve_model_dir`` (definition/ subdir wins)
    without requiring the candidate to exist yet.
    """
    resolved = (base / target).resolve()
    definition = resolved / "definition"
    return definition if definition.is_dir() else resolved


def check_relocation_model(original: str, candidate_root: str, *,
                           allow_missing: bool = False) -> dict:
    """Refuse a relocation that would lose or switch the byPath model.

    Compares the model the candidate path WOULD resolve against the
    original's pinned model digest — directory names are never trusted.
    Missing candidate-side models refuse unless ``allow_missing`` (the
    sealed pipeline path, which pins the original identity for later
    sealed verify instead); different same-name models always refuse.
    Remote (byConnection) references travel with the copy, so they pin
    the connection document. Returns the model pin for sealed evidence.
    """
    from vqs.pbir import _hash_model_dir, _resolve_model_dir

    original_path = Path(original)
    target, connection = bypath_claim(original_path)
    if connection is not None:
        return {"kind": "remote", "connection": connection}
    if target is None:
        return {"kind": "absent"}
    original_model, rule, detail = _resolve_model_dir(original_path)
    if original_model is None:
        raise RepairError(f"original model unresolvable ({rule}): {detail}")
    original_digest = _hash_model_dir(original_model)
    if original_digest is None:
        raise RepairError(f"original model has no readable TMDL: {original_model}")
    pin: dict = {"kind": "byPath", "path": str(original_model),
                 "digest": original_digest}
    candidate_model = _model_root_beneath(Path(candidate_root), target)
    try:
        has_tmdl = (candidate_model.is_dir()
                    and any(candidate_model.rglob("*.tmdl")))
    except OSError:
        has_tmdl = False
    if not has_tmdl:
        if allow_missing:
            return pin
        raise RepairError(
            "relocated candidate model missing: "
            f"{target!r} from {candidate_root} resolves to "
            f"{candidate_model} with no readable TMDL")
    candidate_digest = _hash_model_dir(candidate_model)
    if candidate_digest != original_digest:
        raise RepairError(
            "relocated candidate model differs from the original model: "
            f"{candidate_model} does not match {original_model}")
    return pin


def _project_dir_for(candidate_root: str) -> Path:
    """Disposable project workspace holding the candidate report."""
    return Path(os.path.abspath(candidate_root)).parent


def _within_dir(parent: Path, path: Path) -> bool:
    """True when realpath ``path`` sits strictly inside ``parent``."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return os.path.realpath(path) != os.path.realpath(parent)


def _model_identity_root(model_dir: Path) -> Path:
    """Identity root for digesting: definition/ when present, else root."""
    definition = model_dir / "definition"
    return definition if definition.is_dir() else model_dir


def _copy_model_tree(source: Path, dest: Path) -> int:
    """Copy a SemanticModel project root, minus ephemeral local state.

    Copies every regular file except the ephemeral ``.pbi`` local
    cache/settings tree (stale user/runtime state is never imported);
    required source/project metadata (.platform, definition.pbism,
    diagramLayout.json, definition/**) travels byte-identically.
    Links, junctions, loops, and escapes refuse; the count of copied
    files is returned for the workspace provenance record.
    """
    from vqs.repair.allowlist import within_root

    source_real = os.path.normcase(os.path.realpath(source))
    failures: list[OSError] = []

    def _on_error(exc: OSError) -> None:
        failures.append(exc)

    seen: set[str] = {source_real}
    count = 0
    walker = os.walk(source, followlinks=False, onerror=_on_error)
    for current, dirs, files in walker:
        for name in list(dirs):
            full = os.path.join(current, name)
            if name == ".pbi":
                dirs.remove(name)
                continue
            marker = os.path.normcase(os.path.realpath(full))
            if marker in seen:
                raise RepairError("model contains a directory loop: "
                                  f"{full}")
            seen.add(marker)
            if (os.path.islink(full)
                    or (getattr(os.path, "isjunction", None)
                        is not None
                        and os.path.isjunction(full))  # type: ignore[attr-defined]
                    or not within_root(source_real, full)):
                raise RepairError("model contains an unsafe entry: "
                                  f"{full}")
        for name in files:
            if ".pbi" in Path(current).relative_to(source).parts:
                continue
            full = os.path.join(current, name)
            if (os.path.islink(full)
                    or not within_root(source_real, full)):
                raise RepairError("model contains an unsafe entry: "
                                  f"{full}")
            rel = os.path.relpath(full, source)
            target = os.path.join(str(dest), rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(full, target)
            count += 1
    if failures:
        raise RepairError(f"model unreadable: {failures[0]}")
    return count


def stage_candidate_workspace(original: str,
                              candidate_root: str) -> dict[str, Any]:
    """Stage the disposable candidate PROJECT around the report candidate.

    Stages a valid SemanticModel project root at the candidate byPath
    target: the exact project directory named by
    datasetReference.byPath is copied (required source/project
    metadata preserved byte-identically, ephemeral ``.pbi`` local
    cache excluded), or a pre-existing identical project root is
    adopted. The candidate then resolves through the normal
    ``_resolve_model_dir`` path with a digest equal to the original —
    a valid project for Desktop, not a flattened TMDL pile. Remote
    (byConnection) and absent references stage nothing. The semantic
    model stays read-only in this report-repair path: only the copy
    is ever read, never a repair target.

    Unsafe layouts refuse before any write: an unresolvable or
    non-directory source, a source outside the original project, a
    destination escaping the disposable project, collision with the
    candidate root or the original tree, and occupied targets holding
    a different model. Returns the workspace provenance record; the
    caller rolls it back on any later failure.
    """
    from vqs.pbir import _hash_model_dir, _resolve_model_dir

    project = _project_dir_for(candidate_root)
    project_real = Path(os.path.realpath(project))
    original_path = Path(original)
    original_real = Path(os.path.realpath(original))
    target, connection = bypath_claim(original_path)
    if connection is not None:
        return {"kind": "remote", "project": str(project),
                "model_copy": None, "model_digest": None,
                "adopted": False, "wrapper": None,
                "connection": connection}
    if target is None:
        return {"kind": "absent", "project": str(project),
                "model_copy": None, "model_digest": None,
                "adopted": False, "wrapper": None}
    source_root = (original_path / target).resolve()
    if not source_root.is_dir():
        raise RepairError(
            f"original model unresolvable (not a directory): {target!r} "
            f"resolves to {source_root}")
    home = original_path.resolve().parent
    estate = home.parent
    if not _within_dir(estate, source_root) and source_root != estate:
        raise RepairError(
            f"original model project outside the original project: "
            f"{target!r} resolves to {source_root}; refusing a source "
            "that cannot be represented safely")
    identity = _model_identity_root(source_root)
    original_digest = _hash_model_dir(identity)
    if original_digest is None:
        raise RepairError(
            f"original model has no readable TMDL: {source_root}")
    dest = (Path(os.path.abspath(candidate_root)) / target).resolve()
    dest_real = Path(os.path.realpath(dest))
    candidate_real_resolved = Path(os.path.realpath(candidate_root))
    if not _within_dir(project_real, dest_real):
        raise RepairError(
            f"candidate model target escapes the disposable project: "
            f"{target!r} resolves to {dest}; refusing traversal")
    if (dest_real == candidate_real_resolved
            or _within_dir(candidate_real_resolved, dest_real)
            or _within_dir(dest_real, candidate_real_resolved)):
        raise RepairError(
            "candidate model target collides with the candidate report "
            f"root: {dest}; refusing a layout that would corrupt the "
            "report evidence digests")
    if (_within_dir(original_real, dest_real)
            or dest_real == original_real
            or _within_dir(dest_real, original_real)):
        raise RepairError(
            f"candidate model target overlaps the original tree: {dest}; "
            "the disposable workspace must not touch the original")
    if os.path.lexists(dest):
        if dest.is_dir():
            staged_digest = _hash_model_dir(_model_identity_root(dest))
            if staged_digest == original_digest:
                return {"kind": "byPath", "project": str(project),
                        "model_copy": os.path.realpath(dest),
                        "model_digest": original_digest, "adopted": True,
                        "wrapper": None}
        raise RepairError(
            f"candidate model target occupied by different content: {dest}; "
            "refusing to overwrite it")
    created_project = not project.is_dir()
    try:
        project.mkdir(parents=True, exist_ok=True)
        copied = _copy_model_tree(source_root, dest)
    except (OSError, RepairError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        if created_project:
            try:
                project.rmdir()
            except OSError:
                pass
        if isinstance(exc, RepairError):
            raise
        raise RepairError(
            f"cannot stage candidate model copy: {exc}") from exc
    staged_digest = _hash_model_dir(_model_identity_root(dest))
    if staged_digest != original_digest:
        shutil.rmtree(dest, ignore_errors=True)
        raise RepairError(
            "staged candidate model differs from the original model "
            "after copy; refusing a switched model")
    return {"kind": "byPath", "project": str(project),
            "model_copy": os.path.realpath(dest),
            "model_digest": staged_digest, "adopted": False,
            "files": copied, "wrapper": None,
            "created_project": created_project}


def write_candidate_wrapper(candidate_root: str) -> dict[str, str]:
    """Write the deterministic PBIP wrapper beside the candidate report.

    The wrapper mirrors the first-party shape (version + report path
    artifact); it is execution scaffolding for Bridge ``open``, never
    a report semantic change, and carries its own digest in the
    workspace provenance. An occupied wrapper path refuses instead of
    overwriting.
    """
    project = _project_dir_for(candidate_root)
    base = os.path.basename(os.path.abspath(candidate_root))
    stem = base
    for suffix in (".Report", ".report"):
        if base.endswith(suffix):
            stem = base[: -len(suffix)]
            break
    wrapper = project / f"{stem}.pbip"
    if os.path.lexists(wrapper):
        raise RepairError(
            f"candidate wrapper path occupied; refusing to overwrite: "
            f"{wrapper}")
    doc = {"version": "1.0", "artifacts": [{"report": {"path": base}}],
           "settings": {"enableAutoRecovery": True}}
    try:
        wrapper.write_text(json.dumps(doc, indent=2) + "\n",
                           encoding="utf-8")
    except OSError as exc:
        raise RepairError(
            f"cannot write candidate wrapper: {exc}") from exc
    digest = hashlib.sha256(
        wrapper.read_bytes()).hexdigest() if wrapper.is_file() else ""
    if not digest:
        raise RepairError("candidate wrapper unreadable after write")
    return {"path": os.path.realpath(wrapper), "digest": digest}


def _rollback_workspace(workspace: dict[str, Any] | None) -> None:
    """Remove staged workspace artifacts; adopted content is never touched."""
    if not isinstance(workspace, dict):
        return
    if not workspace.get("adopted"):
        model_copy = workspace.get("model_copy")
        if isinstance(model_copy, str) and model_copy:
            shutil.rmtree(model_copy, ignore_errors=True)
    wrapper = workspace.get("wrapper")
    if isinstance(wrapper, str) and wrapper:
        try:
            os.remove(wrapper)
        except OSError:
            pass
    if workspace.get("created_project"):
        try:
            Path(str(workspace.get("project", ""))).rmdir()
        except OSError:
            pass


def materialize_candidate(original: str, candidate_root: str,
                          workspace: dict[str, Any] | None = None) -> dict:
    """Copy the original report into a fresh candidate root (links refuse).

    ``workspace`` is the staged candidate-project record: a copy
    failure also rolls back staged model/wrapper artifacts, since the
    workspace only exists to serve this candidate.
    """
    if not os.path.isdir(original):
        raise RepairError(f"original report is not a directory: {original}")
    if os.path.lexists(candidate_root):
        raise RepairError("candidate root exists; use a fresh path: "
                          f"{candidate_root}")
    try:
        os.makedirs(candidate_root)
    except OSError as exc:
        raise RepairError(f"cannot create candidate root: {exc}") from exc
    try:
        root_issues = validate_materialized_roots(original, candidate_root)
        if root_issues:
            raise RepairError(f"repair roots rejected: {root_issues[0]}")
        _real, found = _walk_original(original)
        count = 0
        for rel, source in found:
            target = os.path.join(candidate_root, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
            count += 1
        final = tree_digest(candidate_root)
    except Exception:
        shutil.rmtree(candidate_root, ignore_errors=True)
        _rollback_workspace(workspace)
        raise
    return {"original": os.path.realpath(original),
            "candidate": os.path.realpath(candidate_root), "files": count,
            "digest": final}


def _visual_file(candidate: Path, page: str, visual: str) -> Path:
    return (candidate / "definition" / "pages" / page / "visuals" / visual
            / "visual.json")


def _canvas_of(candidate: Path, page: str) -> tuple[int, int]:
    page_doc = _read_json(candidate / "definition" / "pages" / page
                          / "page.json")
    if not isinstance(page_doc, dict):
        raise RepairError(f"page {page} has no positive integer canvas")
    width, height = page_doc.get("width"), page_doc.get("height")
    if (not isinstance(width, int) or isinstance(width, bool)
            or not isinstance(height, int) or isinstance(height, bool)
            or width <= 0 or height <= 0):
        raise RepairError(f"page {page} has no positive integer canvas")
    return width, height


def _set_path(doc: dict, path: list, value: Any) -> None:
    node = doc
    for step in path[:-1]:
        node = node[step] if isinstance(node, dict) else node[int(step)]
    last = path[-1]
    if isinstance(node, dict):
        node[last] = value
    else:
        node[int(last)] = value


def _del_path(doc: dict, path: list) -> None:
    """Delete one property entry (format.unset_override only).

    The recipe bind proved the entry holds the bound override literal;
    a missing entry at apply time is source drift and blocks.
    """
    node = doc
    for step in path[:-1]:
        if isinstance(node, dict) and step in node or (
                isinstance(node, list) and isinstance(step, int)
                and 0 <= step < len(node)):
            node = node[step]
        else:
            raise RepairError(
                f"precondition failed: path {path!r} missing")
    last = path[-1]
    if isinstance(node, dict):
        if last not in node:
            raise RepairError(
                f"precondition failed: path {path!r} missing")
        del node[last]
    elif (isinstance(node, list) and isinstance(last, int)
            and 0 <= last < len(node)):
        del node[last]
    else:
        raise RepairError(
            f"precondition failed: path {path!r} missing")


def _unified_patch(rel: str, before: bytes, after: bytes) -> str:
    before_lines = before.decode("utf-8-sig").splitlines()
    after_lines = after.decode("utf-8-sig").splitlines()
    return "\n".join(difflib.unified_diff(
        before_lines, after_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}",
        lineterm=""))


def apply_plan(plan: dict, original: str, candidate_root: str,
               approved_semantic_change: str | None = None,
               allow_missing_relocated_model: bool = False) -> dict:
    """Validate, materialize, and apply a plan; blocked restores, never half.

    R18: the relocation guard runs before anything is written — a
    candidate that would lose or switch the byPath model is refused
    while the candidate root still does not exist. R19: the original
    baseline is pinned from a pre-copy snapshot (never re-read after
    the copy), and the copy must match the pin before any op lands.
    T11: the original/model pins are re-verified after the copy and
    after application — a save landing in between refuses instead of
    sealing against a changed original. Remaining race boundary: a
    save landing strictly between the final verification and the
    seal, or an A->B->A flap restoring byte-identical content, is
    undetectable here; callers must quiesce the original, and sealed
    verify re-checks the sealed digests against the current trees.
    """
    plan_issues = validate_plan(plan, original, candidate_root,
                                approved_semantic_change)
    if plan_issues:
        return {"verdict": "blocked", "stage": "validate",
                "issues": plan_issues}
    try:
        workspace = stage_candidate_workspace(original, candidate_root)
    except RepairError as exc:
        return {"verdict": "blocked", "stage": "workspace",
                "reason": str(exc)}

    def _drop_candidate() -> None:
        shutil.rmtree(candidate_root, ignore_errors=True)
        _rollback_workspace(workspace)

    try:
        model_pin = check_relocation_model(
            original, candidate_root,
            allow_missing=allow_missing_relocated_model)
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "relocation",
                "reason": str(exc)}
    try:
        pinned = _snapshot_original(original)
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": str(exc)}
    before_digest = _digest_map(pinned)
    try:
        materialize_candidate(original, candidate_root, workspace)
    except RepairError as exc:
        # F01: a refused candidate root was never owned by this
        # attempt, so it is preserved byte-for-byte
        # (materialize_candidate removes only roots it created
        # itself). Staged workspace artifacts are still ours to drop.
        _rollback_workspace(workspace)
        return {"verdict": "blocked", "stage": "materialize",
                "reason": str(exc)}
    try:
        copied_digest = tree_digest(candidate_root)
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": f"cannot re-read candidate copy: {exc}"}
    if copied_digest != before_digest:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": "original changed during copy; retry with a "
                          "fresh candidate root"}
    try:
        _assert_original_pinned(original, before_digest, "during copy")
        _assert_model_pinned(original, model_pin, "during copy")
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": str(exc)}
    candidate = Path(candidate_root)
    operations = plan.get("operations", [])
    snapshot: dict[str, bytes] = {}
    edits: list[dict[str, Any]] = []
    pages: list[str] = []
    rescan = validate_materialized_roots(original, candidate_root)
    if rescan:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": f"roots rejected after copy: {rescan[0]}"}
    try:
        from vqs.pbir import report_context
        info = report_context(
            candidate,
            allow_unresolved_model=allow_missing_relocated_model)
        all_pages = [page["id"] for page in info["pages"]]
    except Exception as exc:  # noqa: BLE001 - any unreadable shape blocks
        _drop_candidate()
        return {"verdict": "blocked", "stage": "materialize",
                "reason": f"candidate report unreadable: {exc}"}
    covered = set()
    for entry in normalize_targets(plan.get("write_targets")):
        absolute = entry if os.path.isabs(entry) else os.path.join(
            candidate_root, entry)
        covered.add(os.path.realpath(absolute))
    for index, op in enumerate(operations):
        try:
            edits.append(_apply_op(op, candidate, all_pages,
                                   approved_semantic_change, snapshot,
                                   covered,
                                   allow_unresolved_model=(
                                       allow_missing_relocated_model)))
        except (RecipeError, TemplateError, RepairError) as exc:
            _drop_candidate()
            return {"verdict": "blocked", "stage": "apply", "index": index,
                    "reason": f"{type(exc).__name__}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - structural crash blocks
            _drop_candidate()
            return {"verdict": "blocked", "stage": "apply", "index": index,
                    "reason": f"operation crashed: {type(exc).__name__}: {exc}"}
    for edit in edits:
        for page in edit["affected"]["pages"]:
            if page not in pages:
                pages.append(page)
    from vqs.pbir import source_digest

    try:
        _assert_original_pinned(original, before_digest,
                                "during application")
        _assert_model_pinned(original, model_pin, "during application")
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "apply",
                "reason": str(exc)}
    try:
        after_digest = tree_digest(candidate)
        source_sha = source_digest(candidate)
        if before_digest == after_digest:
            raise RepairError("candidate digest unchanged; no edit landed")
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "digest",
                "reason": str(exc)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "digest",
                "reason": f"cannot re-read reports: {exc}"}
    try:
        wrapper = write_candidate_wrapper(candidate_root)
    except RepairError as exc:
        _drop_candidate()
        return {"verdict": "blocked", "stage": "workspace",
                "reason": str(exc)}
    workspace["wrapper"] = wrapper["path"]
    workspace_record = {
        "project": workspace["project"],
        "model": {"kind": workspace["kind"],
                  "copy": workspace["model_copy"],
                  "digest": workspace["model_digest"],
                  "adopted": workspace["adopted"]},
        "wrapper": wrapper}
    patch = {rel: _unified_patch(rel, before,
                                 (candidate / rel).read_bytes())
             for rel, before in snapshot.items()}
    return {"verdict": "applied", "candidate": str(candidate),
            "before": before_digest, "after": after_digest,
            "source_sha256": source_sha, "model": model_pin,
            "workspace": workspace_record,
            "edits": edits, "patch": patch, "affected_pages": pages}


def _apply_op(op: dict, candidate: Path, all_pages: list[str],
              approved: str | None, snapshot: dict[str, bytes],
              covered: set[str],
              allow_unresolved_model: bool = False) -> dict:
    from vqs.pbir import report_context

    selector = op.get("selector", {})
    if not isinstance(selector, dict):
        raise RepairError("op selector must be a {page, visual} object")
    page, visual = selector.get("page", ""), selector.get("visual", "")
    for segment, label in ((page, "page"), (visual, "visual")):
        if (not isinstance(segment, str) or not segment
                or segment != segment.strip() or segment.startswith(".")
                or "/" in segment or "\\" in segment or ":" in segment
                or ".." in segment):
            raise RepairError(f"selector {label} escapes or is empty: "
                              f"{segment!r}")
    if page not in all_pages:
        raise RepairError(f"bound page {page} is not in the page order")
    target_file = _visual_file(candidate, page, visual)
    try:
        rel = target_file.relative_to(candidate).as_posix()
    except ValueError as exc:
        raise RepairError(f"selector escapes the candidate: {page}/{visual}"
                          ) from exc
    if os.path.realpath(target_file) not in covered:
        raise RepairError(f"derived write is not a declared write target: "
                          f"{rel}")
    if not target_file.is_file():
        raise RepairError(f"bound visual file missing: {rel}")
    if rel not in snapshot:
        snapshot[rel] = target_file.read_bytes()
    visual_doc = _read_json(target_file)
    canvas = _canvas_of(candidate, page)
    if op.get("type") == "chart.replace":
        return _apply_replace(op, visual_doc, target_file, rel, candidate,
                              all_pages, approved,
                              allow_unresolved_model=allow_unresolved_model)
    binding = bind_operation(op, visual_doc, canvas)
    if op.get("type") == "format.unset_override":
        _del_path(visual_doc, binding["path"])
    else:
        _set_path(visual_doc, binding["path"], binding["new"])
    _write_json(target_file, visual_doc)
    binding["file"] = rel
    binding["affected"] = affected_pages(op, all_pages)
    info = report_context(
        candidate, allow_unresolved_model=allow_unresolved_model)
    info_pages = {page["id"] for page in info["pages"]}
    if page not in info_pages:
        raise RepairError(f"bound page {page} left the page order")
    return binding


def _apply_replace(op: dict, visual_doc: dict, target_file: Path, rel: str,
                   candidate: Path, all_pages: list[str],
                   approved: str | None,
                   allow_unresolved_model: bool = False) -> dict:
    from vqs.pbir import report_context

    binding = bind_operation(op, None)
    if not (op.get("identical_intent") is True or approved):
        raise RepairError("chart.replace needs identical_intent or an "
                          "owner-approved semantic change id")
    template = get_template(binding["template"], binding["version"])
    query = visual_doc.get("visual", {}).get("query", {})
    roles = query.get("queryState", {}) if isinstance(query, dict) else {}
    bindings = {name: spec.get("projections", [])
                for name, spec in roles.items()
                if isinstance(spec, dict)}
    missing = verify_bindings(template, bindings)
    if missing:
        raise RepairError("template bindings unverified on target visual: "
                          + ", ".join(missing))
    new_visual = dict(visual_doc.get("visual", {}))
    new_visual["visualType"] = template["visual_type"]
    new_visual["objects"] = template["body"]["visual"].get("objects", {})
    visual_doc["visual"] = new_visual
    _write_json(target_file, visual_doc)
    info = report_context(
        candidate, allow_unresolved_model=allow_unresolved_model)
    if binding["page"] not in {page["id"] for page in info["pages"]}:
        raise RepairError("bound page left the page order")
    return {**binding, "file": rel,
            "affected": affected_pages(op, all_pages)}


def rollback_candidate(original: str, candidate_root: str,
                       before_digest: str) -> dict:
    """Rollback an applied candidate by re-materializing from the original.

    The candidate is disposable: rollback removes it and copies the
    original again, then proves the restore with rollback_ok against the
    recorded before digest.
    """
    from .allowlist import rollback_ok

    original_real = os.path.realpath(original)
    candidate_real = os.path.realpath(candidate_root)
    if (original_real == candidate_real
            or original_real.startswith(candidate_real + os.sep)
            or candidate_real.startswith(original_real + os.sep)):
        return {"rule": "rollback_refused", "status": "blocked",
                "reason": "rollback candidate must not overlap the original; "
                          "nothing was touched"}
    shutil.rmtree(candidate_root, ignore_errors=True)
    try:
        staged = materialize_candidate(original, candidate_root)
    except RepairError as exc:
        return {"rule": "rollback_unverifiable", "status": "blocked",
                "reason": str(exc)}
    after = tree_digest(candidate_root)
    verdict = rollback_ok(before_digest, after)
    return {**verdict, "candidate": staged["candidate"]}
