"""F23 RED: malformed observation types must block, never crash.

check_observations hashes unvalidated observation IDs and tests
unvalidated statuses in sets; list/dict fields raise TypeError out of
public adjudication. Hostile JSON must return structured blocked (CLI:
exit 2, no traceback) and retain a failed attempt when a run began.

M3 covers the CLI exit-2/run-retention half; these controls pin the
no-crash contract at the adjudication boundary.
"""
import json

from vqs.policy import POLICY_VERSION, REQUIRED
from vqs.review import adjudicate_bundle

SOURCE = "c" * 64
REASON = "All labels legible at the target size on the fresh full-canvas render."


def _observations(status="pass"):
    return [{"id": check, "criterion": check, "status": status,
             "reason": REASON, "severity": None, "region": None,
             "visual_id": "page", "proposed_fix": ""}
            for check in REQUIRED["report"]]


def _bundle(**overrides):
    base = {
        "source_sha256": SOURCE,
        "surface": "report",
        "reviewer": {"id": "reviewer-1", "role": "independent_visual_reviewer"},
        "fixer_id": "executor-1",
        "image_capability": {"available": True, "provider": "synthetic-test"},
        "calibration": {"canvas_width": 500, "canvas_height": 500, "scale": 1,
                        "viewport": "500x500@1x", "method": "bridge-screenshot-all"},
        "data_readiness": {"populated": True, "method": "scoped-dax-probe",
                           "checked_at": "2026-10-03T00:00:00Z"},
        "pages": [{
            "id": "page-1",
            "image_sha256": "d" * 64,
            "image_source_sha256": SOURCE,
            "pixels": [500, 500],
            "observations": _observations(),
        }],
    }
    base.update(overrides)
    return base


def test_f23_unhashable_observation_id_blocks() -> None:
    """RED: list observation id must block, not raise TypeError."""
    bundle = _bundle()
    bundle["pages"][0]["observations"][0]["id"] = ["text_legibility"]
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"


def test_f23_mapping_observation_id_blocks() -> None:
    """RED: dict observation id must block, not raise TypeError."""
    bundle = _bundle()
    bundle["pages"][0]["observations"][0]["id"] = {"id": "text_legibility"}
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"


def test_f23_unhashable_status_blocks() -> None:
    """RED: list status must block, not raise TypeError."""
    bundle = _bundle()
    for answer in bundle["pages"][0]["observations"]:
        answer["status"] = ["pass"]
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"

def test_f23_unhashable_fail_fields_block() -> None:
    """Unhashable severity/visual_id on a fail must block, not raise."""
    bundle = _bundle()
    first = bundle["pages"][0]["observations"][0]
    first["status"] = "fail"
    first["severity"] = ["high"]
    first["visual_id"] = {"id": "page"}
    assert adjudicate_bundle(bundle)["verdict"] == "blocked"


def test_f23_hostile_visual_inventory_ignored_without_raise() -> None:
    """Malformed visual inventory is skipped safely, never crashes.

    S10: static adjudication never passes, so the no-crash property
    lands on the image-review block, not on a pass.
    """
    bundle = _bundle(schema=1, policy_version=POLICY_VERSION)
    bundle["pages"][0]["visual_inventory"] = None
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"
    assert "image_review_required" in {row.get("rule") for row in result["findings"]}
    bundle = _bundle(schema=1, policy_version=POLICY_VERSION)
    bundle["pages"][0]["visual_inventory"] = [{"id": ["x"]}]
    result = adjudicate_bundle(bundle)
    assert result["verdict"] == "blocked"
    assert "image_review_required" in {row.get("rule") for row in result["findings"]}


def test_f23_hostile_bundle_cli_blocks_and_retains_run(tmp_path, capsys) -> None:
    """CLI: hostile bundle exits 2 with no traceback; the run is retained sealed."""
    from vqs.cli import main as vqs_main

    bundle = _bundle()
    bundle["pages"][0]["observations"][0]["id"] = ["text_legibility"]
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    code = vqs_main(["adjudicate-bundle", str(bundle_path),
                   "--run-root", str(tmp_path / "runs"),
                   "--run-id", "hostile-1"])
    assert code == 2
    assert "Traceback" not in capsys.readouterr().err
    manifest = json.loads((tmp_path / "runs" / "hostile-1" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sealed"] is True
    assert manifest["status"] == "blocked"
