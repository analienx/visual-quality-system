"""A genuine complete PBIP must fingerprint identically on Windows and Linux."""
from __future__ import annotations

import zipfile
from pathlib import Path

from vqs.pbir import source_inventory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "contoso-retail-complete-p7.zip"
# Verified on both hosted Ubuntu and hosted Windows against the exact same ZIP with host-independent ordering. Historical P7 fingerprints used native OS path ordering and are intentionally different.
CONTOSO_PORTABLE_SHA256 = (
    "d8714ab77ee3aa9225c9656ea10c093156fcbcd3dd77a25c0226015d2c0a31f0"
)


def test_complete_contoso_source_digest_is_host_independent(tmp_path):
    with zipfile.ZipFile(FIXTURE) as archive:
        archive.extractall(tmp_path)
    report = tmp_path / "Contoso Retail.Report"
    evidence = source_inventory(report)
    assert evidence["issues"] == []
    assert len(evidence["report_files"]) >= 60
    assert len(evidence["model_files"]) == 16
    assert evidence["digest"] == CONTOSO_PORTABLE_SHA256


def test_mixed_case_relative_names_have_stable_hash_order(tmp_path):
    report = tmp_path / "Example.Report"
    report.mkdir()
    for name, value in (
        ("Zeta.json", "Z"), ("alpha.json", "a"),
        ("BETA.json", "B"), ("charlie.tmdl", "c"),
    ):
        (report / name).write_text(value, encoding="utf-8")
    evidence = source_inventory(report)
    assert evidence["report_files"] == [
        "alpha.json", "BETA.json", "charlie.tmdl", "Zeta.json",
    ]
