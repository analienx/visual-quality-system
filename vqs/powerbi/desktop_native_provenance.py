"""Conservative native-Save provenance for a *disposable*, local PBIP.

This is distinct from the default read-only, pre-open source-age gate.
A trusted native-save witness must be revalidated against live files, OS
process and Desktop Bridge state at every subsequent strict DAX/UIA call.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from vqs.powerbi.desktop_source import local_semantic_model, project_artifacts

SCHEMA = "vqs.native-desktop-saved-source/1"


def source_files(project: Path) -> list[Path]:
    wrapper, report = project_artifacts(project)
    model, reference = local_semantic_model(project, report, wrapper)
    if reference != "byPath_source_checked" or model is None:
        raise ValueError("native saved-source requires declared local byPath model")
    files = [wrapper]
    for root in (report, model):
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("symlink inside native source")
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if ".pbi" in relative.parts:
                continue  # Microsoft volatile state and ABF cache, not PBIR/TMDL source.
            if root == model and path.name == ".platform":
                continue
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(project).as_posix())


def snapshot(project: Path) -> dict[str, dict[str, int | str]]:
    result: dict[str, dict[str, int | str]] = {}
    for path in source_files(project):
        data = path.read_bytes()
        info = path.stat()
        result[path.relative_to(project).as_posix()] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "mtime_ns": info.st_mtime_ns,
        }
    return result


def _metadata_pair(project: Path) -> list[Path]:
    wrapper, report = project_artifacts(project)
    return [wrapper, report / "definition.pbir"]


def metadata_source(project: Path) -> dict[str, str]:
    return {
        path.relative_to(project).as_posix(): path.read_bytes().decode("utf-8")
        for path in _metadata_pair(project)
    }


def _equivalent_json(before: str, after: str) -> bool:
    original = json.loads(before)
    saved = json.loads(after)
    if not isinstance(original, dict) or not isinstance(saved, dict):
        return False
    original.pop("$schema", None)
    saved.pop("$schema", None)
    return original == saved


def _is_native_visual_json(rel: str) -> bool:
    """Limit semantic-equivalence exceptions to native PBIR visual definitions."""
    parts = Path(rel).parts
    return (len(parts) == 7 and parts[0].endswith(".Report")
            and parts[1:3] == ("definition", "pages")
            and parts[4] == "visuals" and parts[-1] == "visual.json"
            and parts[3] not in ("", ".", "..")
            and parts[5] not in ("", ".", ".."))


def _strict_json_semantics(source: str) -> str:
    """Prevent duplicate-key/NaN JSON from faking semantic equivalence."""
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key in PBIR source")
            out[key] = value
        return out

    def reject_constant(value: str) -> None:
        raise ValueError("non-JSON constant " + value)

    obj = json.loads(source, object_pairs_hook=unique,
                     parse_constant=reject_constant)
    if not isinstance(obj, dict):
        raise TypeError("visual definition is not a JSON object")
    if not isinstance(obj.get("visual"), dict):
        raise TypeError("PBIR visual object absent")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def verify(
    project: Path, pid: int, created: float,
    witness: Mapping[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """Fail closed on stale files, different PIDs, substantive Save changes."""
    details: dict[str, Any] = {}
    try:
        wrapper, report = project_artifacts(project)
        model, reference = local_semantic_model(project, report, wrapper)
        if reference != "byPath_source_checked" or model is None:
            raise ValueError("local byPath semantic model not verified")
        if witness.get("schema") != SCHEMA:
            raise ValueError("missing native-save receipt schema")
        if witness.get("desktop_pid") != pid:
            raise ValueError("native-save witness PID differs")
        if (witness.get("pbip") != str(wrapper.resolve()) or
                witness.get("report") != str(report.resolve()) or
                witness.get("model") != str(model.resolve())):
            raise ValueError("native-save witness path/model differs")
        if type(witness.get("process_created")) not in (float, int) or (
                abs(witness["process_created"] - created) > .2):
            raise ValueError("native-save witness process start differs")
        control = witness.get("native_save_control")
        if (not isinstance(control, Mapping) or
                control.get("method") != "InvokePattern" or
                control.get("automation_id") != "save" or
                control.get("button") != "Save" or
                control.get("pid") != pid or
                control.get("window") != wrapper.stem):
            raise ValueError("native Save UIA control not corroborated")
        started = witness.get("save_start_epoch")
        ended = witness.get("saved_observed_epoch")
        if type(started) not in (float, int) or type(ended) not in (float, int):
            raise ValueError("native-save action epoch invalid")
        start_epoch = float(cast(float, started))
        end_epoch = float(cast(float, ended))
        if not created <= start_epoch <= end_epoch:
            raise ValueError("native-save action chronology invalid")
        if witness.get("unsaved_before") is not True or (
                witness.get("unsaved_after") is not False):
            raise ValueError("native-save state transition is not proved")
        before = witness.get("manifest_before")
        after = witness.get("manifest_after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise TypeError("missing complete source inventories")
        current = snapshot(project)
        if dict(after) != current or set(before) != set(current):
            raise ValueError("source hashes, timestamps or file set drifted since Save")
        for rel, old in before.items():
            if not isinstance(old, Mapping) or set(old) != {
                    "sha256", "size", "mtime_ns"}:
                raise ValueError("native-save before inventory malformed")
            if type(old["mtime_ns"]) is not int or (
                    old["mtime_ns"] / 1e9 > created + 1):
                raise ValueError("source changed after launch before native Save")
        metadata_pre = witness.get("metadata_before")
        metadata_post = witness.get("metadata_after")
        current_metadata = metadata_source(project)
        expected_metadata = {p.relative_to(project).as_posix()
                             for p in _metadata_pair(project)}
        if (not isinstance(metadata_pre, Mapping) or
                not isinstance(metadata_post, Mapping) or
                set(metadata_pre) != expected_metadata or
                set(metadata_post) != expected_metadata or
                dict(metadata_post) != current_metadata):
            raise ValueError("native Save metadata files/contents changed")
        for rel in expected_metadata:
            if (not isinstance(metadata_pre[rel], str) or
                    not isinstance(metadata_post[rel], str) or
                    hashlib.sha256(metadata_pre[rel].encode("utf-8")).hexdigest()
                    != before[rel]["sha256"] or
                    hashlib.sha256(metadata_post[rel].encode("utf-8")).hexdigest()
                    != after[rel]["sha256"]):
                raise ValueError("native Save metadata fingerprints inconsistent")
        visual_before = witness.get("visual_json_before", {})
        if not isinstance(visual_before, Mapping) or (
                any(not isinstance(k, str) or not _is_native_visual_json(k)
                    or k not in current or not isinstance(v, str)
                    for k, v in visual_before.items())):
            raise ValueError("invalid pre-Save native PBIR visual snapshots")
        changed = []
        semantically_identical_visuals = []
        for rel, info in current.items():
            prior = before[rel]
            if prior["sha256"] != info["sha256"]:
                if rel in expected_metadata:
                    if not _equivalent_json(metadata_pre[rel], metadata_post[rel]):
                        raise ValueError("native Save modified metadata semantics")
                    changed.append(rel)
                elif _is_native_visual_json(rel):
                    snapshot_before = visual_before.get(rel)
                    if not isinstance(snapshot_before, str):
                        raise ValueError("changed visual missing pre-Save bytes")
                    raw_before = snapshot_before.encode("utf-8")
                    if (hashlib.sha256(raw_before).hexdigest() != prior["sha256"]
                            or len(raw_before) != prior["size"]):
                        raise ValueError("pre-Save visual text does not match prior content hash")
                    if _strict_json_semantics(snapshot_before) != _strict_json_semantics(
                            (project / rel).read_bytes().decode("utf-8")):
                        raise ValueError("native Save changed visual JSON meaning")
                    semantically_identical_visuals.append(rel)
                else:
                    raise ValueError("native Save changed report/model source content")
            mtime = float(info["mtime_ns"]) / 1e9
            if mtime > created + 1 and not (
                    start_epoch - 2 <= mtime <= end_epoch + 2):
                raise ValueError("source changed outside witnessed native Save interval")
        details = {
            "native_save_witness_verified": True,
            "saved_source_file_count": len(current),
            "saved_metadata_only_byte_changes": changed,
            "saved_semantically_equivalent_visual_changes": semantically_identical_visuals,
            "local_model_reference": reference,
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, str(exc), {}
    return True, ("native UIA Save, Bridge clean state, unchanged semantic model "
                  "and byte- or strictly semantic-equivalent PBIR source bound"), details
