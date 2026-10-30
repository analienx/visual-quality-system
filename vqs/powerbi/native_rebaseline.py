"""Read-only audit of an observed Desktop Save followed by a strict rebaseline.

First Save never receives retrospective approval. A second, separate Desktop
session must prove the new exact source is stable before any G4 review.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vqs.powerbi.desktop_native_provenance import snapshot, verify


def _hash_size(rows: Mapping[str, Any]) -> dict[str, tuple[str, int]]:
    out = {}
    for rel, info in rows.items():
        if not isinstance(rel, str) or not isinstance(info, Mapping):
            raise TypeError("malformed source inventory")
        digest, size = info.get("sha256"), info.get("size")
        if not isinstance(digest, str) or len(digest) != 64 or (
                any(c not in "0123456789abcdef" for c in digest)
                or type(size) is not int or size < 0):
            raise ValueError("invalid source file fingerprint")
        out[rel] = (digest, size)
    return out


def _change_kind(path: str) -> str:
    if path.endswith("/mobile.json"):
        return "mobile_layout_requires_review"
    if path.endswith("/pages.json"):
        return "active_page_requires_review"
    if path.endswith((".pbip", "/definition.pbir")):
        return "schema_or_reference_requires_review"
    if path.endswith("/visual.json"):
        return "visual_requires_review"
    return "other_source_requires_review"


def evaluate(first: Path, first_receipt: Mapping[str, Any],
             stabilized: Path, second_receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Prove source continuity, never report acceptance or first-Save equivalence."""
    result: dict[str, Any] = {
        "schema": "vqs.native-source-rebaseline/1",
        "status": "blocked",
        "first_save_semantically_accepted": False,
        "formal_g2_g4_g6": "blocked",
    }
    try:
        first = first.resolve(strict=True)
        stabilized = stabilized.resolve(strict=True)
        if first == stabilized or first in stabilized.parents or (
                stabilized in first.parents):
            raise ValueError("first and stabilized projects must be separate")
        for project, receipt in ((first, first_receipt),
                                 (stabilized, second_receipt)):
            if receipt.get("schema") != "vqs.native-desktop-saved-source/1":
                raise ValueError("invalid native Save receipt schema")
            control = receipt.get("native_save_control")
            if not isinstance(control, Mapping) or (
                    control.get("method") != "InvokePattern"
                    or control.get("automation_id") != "save"
                    or control.get("button") != "Save"
                    or control.get("pid") != receipt.get("desktop_pid")):
                raise ValueError("native Save UIA action unverified")
            if receipt.get("unsaved_before") is not True or (
                    receipt.get("unsaved_after") is not False):
                raise ValueError("saved-state transition not proved")
            if receipt.get("pbip") != str(project / Path(str(
                    receipt.get("pbip"))).name):
                raise ValueError("receipt path differs from project")
        if first_receipt.get("native_saved_source_verified") is not False:
            raise ValueError("first Save must be an explicitly blocked source transition")
        if second_receipt.get("native_saved_source_verified") is not True:
            raise ValueError("second Save was not strictly attested")
        one_before = first_receipt["manifest_before"]
        one_after = first_receipt["manifest_after"]
        two_before = second_receipt["manifest_before"]
        two_after = second_receipt["manifest_after"]
        if not all(isinstance(x, Mapping) for x in (
                one_before, one_after, two_before, two_after)):
            raise ValueError("missing source snapshot")
        if _hash_size(one_after) != _hash_size(snapshot(first)):
            raise ValueError("first source drifted after native Save")
        if _hash_size(two_after) != _hash_size(snapshot(stabilized)):
            raise ValueError("stabilized source drifted after native Save")
        if _hash_size(one_after) != _hash_size(two_before):
            raise ValueError("new candidate not an exact copy of first saved revision")
        if set(one_before) != set(one_after):
            raise ValueError("first Save source file set changed")
        changed = sorted(k for k in one_before if (
            _hash_size({k: one_before[k]}) != _hash_size({k: one_after[k]})))
        if not changed:
            raise ValueError("first Save did not change source")
        if _hash_size(two_before) != _hash_size(two_after):
            raise ValueError("second Save still changes source bytes")
        valid, reason, _ = verify(
            stabilized, second_receipt["desktop_pid"],
            second_receipt["process_created"], second_receipt)
        if not valid:
            raise ValueError("second native Save verifier: " + reason)
        result.update({
            "status": "stabilized_candidate_needs_independent_acceptance",
            "new_exact_source_verified": True,
            "first_save_changes": [
                {"relative_path": rel, "classification": _change_kind(rel)}
                for rel in changed
            ],
            "second_save_changes": [],
            "source_file_count": len(two_after),
            "next_step": (
                "Review first source diffs; bind new exact source; rerun native "
                "DAX, all-page G2 and bounded G4; obtain authorized approvals."
            ),
        })
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["reason"] = str(exc)
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_project", type=Path)
    parser.add_argument("first_receipt", type=Path)
    parser.add_argument("stabilized_project", type=Path)
    parser.add_argument("stabilized_receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("refusing to overwrite existing evidence")
    data = evaluate(
        args.first_project, json.loads(args.first_receipt.read_text("utf8")),
        args.stabilized_project, json.loads(args.stabilized_receipt.read_text("utf8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    print(json.dumps({
        "status": data["status"],
        "changed_files": len(data.get("first_save_changes", [])),
        "reason": data.get("reason"), "output": str(args.output),
    }))
    return 0 if data["status"] == "stabilized_candidate_needs_independent_acceptance" else 2


if __name__ == "__main__":
    raise SystemExit(main())
