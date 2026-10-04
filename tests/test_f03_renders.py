"""F03 RED: render verification must inspect materialized evidence.

verify_renders currently counts keys in page_images, so maps-only
manifests pass without PNG bytes, hashes, calibration, or readiness.
Every test below must block; each currently passes (RED).

M2 note: the fix routes verification through the production
image/capture verifier (evidence.image_evidence semantics) against
materialized renders dirs. That reshapes this entry point; when it
lands, rewrite _verify to the new signature and keep every adverse
control below green through the new path.
"""
from vqs.repair.regress import verify_renders


def _verify(pages, manifests, digest):
    """Current entry-point shape; rewritten with the M2 fix."""
    return verify_renders(pages, manifests, digest)


def test_f03_null_filename_blocks() -> None:
    manifest = {"source_sha256": "d", "page_images": {"P1": None}}
    verdict = _verify(["P1"], [manifest], "d")
    assert verdict["verdict"] == "blocked"


def test_f03_maps_only_manifest_blocks() -> None:
    manifest = {"source_sha256": "cand-digest",
                "page_images": {"P1": "p1.png", "P2": "p2.png"}}
    verdict = _verify(["P1", "P2"], [manifest], "cand-digest")
    assert verdict["verdict"] == "blocked"


def test_f03_missing_files_map_blocks() -> None:
    manifest = {"source_sha256": "d", "page_images": {"P1": "P1.png"},
                "calibration": {"canvas_width": 1280, "canvas_height": 720,
                                "scale": 1, "viewport": "native",
                                "method": "bridge"},
                "data_readiness": {"populated": True,
                                   "method": "modeling-mcp:repeat-query"}}
    verdict = _verify(["P1"], [manifest], "d")
    assert verdict["verdict"] == "blocked"


def test_f03_unknown_calibration_blocks() -> None:
    manifest = {"source_sha256": "d", "page_images": {"P1": "P1.png"},
                "files": {"P1.png": "abc123"},
                "data_readiness": {"populated": True,
                                   "method": "modeling-mcp:repeat-query"}}
    verdict = _verify(["P1"], [manifest], "d")
    assert verdict["verdict"] == "blocked"


def test_f03_unknown_readiness_blocks() -> None:
    manifest = {"source_sha256": "d", "page_images": {"P1": "P1.png"},
                "files": {"P1.png": "abc123"},
                "calibration": {"canvas_width": 1280, "canvas_height": 720,
                                "scale": 1, "viewport": "native",
                                "method": "bridge"}}
    verdict = _verify(["P1"], [manifest], "d")
    assert verdict["verdict"] == "blocked"
