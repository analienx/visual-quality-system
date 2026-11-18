"""Work-package ledger validation and reporting (WP-02, WP-12 packaging).

Pure stdlib logic over an already-loaded ledger dict; no I/O, no GitHub API,
and it never modifies the ledger. Both the installed ``vqs status`` command
and ``scripts/roadmap_report.py`` share this module so the packaged entry
point works without the source checkout on ``sys.path``.
"""
from __future__ import annotations

import re

SCHEMA_VERSION = "1.0.0"
VALID_STATES = {"planned", "ready", "active", "review", "blocked", "failed", "verified", "deferred"}
VALID_VERIFICATION = {"not_run", "partial", "failed", "blocked", "verified"}


def validate(data: dict) -> list[str]:
    """Validate IDs, graph, states and proof requirements; do not infer proof."""
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        return ["unsupported or missing roadmap schema_version"]
    packages = data.get("packages")
    if not isinstance(packages, list) or not packages:
        return ["packages must be a non-empty list"]
    by_id: dict[str, dict] = {}
    issues: set[int] = set()
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            errors.append(f"package[{index}] is not an object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"WP-\d{2,}", identifier):
            errors.append(f"package[{index}] has invalid id")
            continue
        if identifier in by_id:
            errors.append(f"duplicate work package {identifier}")
        by_id[identifier] = item
        issue = item.get("issue")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            errors.append(f"{identifier}: missing issue number")
        elif issue in issues:
            errors.append(f"{identifier}: duplicate issue number {issue}")
        issues.add(issue)
        state, verification = item.get("state"), item.get("verification")
        if state not in VALID_STATES:
            errors.append(f"{identifier}: invalid state {state!r}")
        if verification not in VALID_VERIFICATION:
            errors.append(f"{identifier}: invalid verification {verification!r}")
        if not isinstance(item.get("depends_on"), list) or any(
            not isinstance(dep, str) for dep in item.get("depends_on", [])
        ):
            errors.append(f"{identifier}: depends_on must be a list of IDs")
        if state == "verified" and (
            verification != "verified" or not item.get("verified_commit")
            or not item.get("evidence_uri") or not item.get("pull_request")
        ):
            errors.append(f"{identifier}: verified claim lacks independent evidence/merged commit/PR")
        if state == "deferred" and verification == "verified":
            errors.append(f"{identifier}: deferred cannot claim verified")
        if state == "blocked" and not item.get("blocker"):
            errors.append(f"{identifier}: blocked must include a blocker")
        if state in {"ready", "active", "review"} and verification == "verified":
            errors.append(f"{identifier}: workflow state contradicts verified evidence")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            errors.append(f"dependency cycle includes {identifier}")
            return
        if identifier in visited:
            return
        visiting.add(identifier)
        for dep in by_id[identifier].get("depends_on", []):
            if dep == identifier:
                errors.append(f"{identifier}: self dependency")
            elif dep not in by_id:
                errors.append(f"{identifier}: missing dependency {dep}")
            else:
                visit(dep)
                if by_id[identifier].get("state") in {"ready", "active", "review", "verified"} and (
                    by_id[dep].get("state") != "verified" or by_id[dep].get("verification") != "verified"
                ):
                    errors.append(f"{identifier}: prerequisite {dep} not independently verified")
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in by_id:
        visit(identifier)
    if data.get("first_ready_package") not in by_id:
        errors.append("first_ready_package does not exist")
    return sorted(set(errors))


def summarize(data: dict) -> dict:
    """Summarize verification counts and dependency-ready packages."""
    packages = data["packages"]
    non_deferred = [item for item in packages if item["state"] != "deferred"]
    # The historical initial program covers S0-S8. Later product milestones
    # belong in the same DAG but must not inflate the initial-release count.
    initial = [item for item in non_deferred
               if isinstance(item.get("stage"), str)
               and re.fullmatch(r"S[0-8](?:[A-Z]|-S[0-8])?", item["stage"])]
    verified = [item for item in initial if item["state"] == "verified" and item["verification"] == "verified"]
    by_id = {item["id"]: item for item in packages}
    runnable = [item["id"] for item in non_deferred if item["state"] in {"planned", "ready"} and all(
        by_id[dep]["state"] == "verified" and by_id[dep]["verification"] == "verified"
        for dep in item["depends_on"]
    )]
    return {"snapshot_utc": data.get("snapshot_utc"), "independently_verified": len(verified),
            "initial_release_packages": len(initial), "deferred": len(packages) - len(non_deferred),
            "next_runnable": runnable, "packages": [
                {"id": item["id"], "issue": item["issue"], "stage": item["stage"],
                 "state": item["state"], "verification": item["verification"],
                 "depends_on": item["depends_on"], "evidence_uri": item.get("evidence_uri")}
                for item in packages]}
