"""Fetch official Microsoft Analysis Services ADOMD.NET client for GH runner.

NuGet package version fixed for experimental local Desktop DAX. No tenant
credentials, no private data, no system-wide DLL installation. Unpack
only net472 DLLs into the runner's temporary directory; persist manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

VERSION = "19.117.0"
PACKAGE = "microsoft.analysisservices.adomdclient"
URL = (f"https://api.nuget.org/v3-flatcontainer/{PACKAGE}/{VERSION}/"
       f"{PACKAGE}.{VERSION}.nupkg")
MAX_BYTES = 25_000_000


def run(out: Path) -> dict[str, object]:
    if out.exists():
        raise RuntimeError("refuse evidence overwrite")
    root = Path(os.environ.get("RUNNER_TEMP", ".")) / "vqs-adomd-net472"
    if root.exists():
        raise RuntimeError("refuse reused ADOMD installation")
    record: dict[str, object] = {
        "contract": "vqs.github-hosted-official-adomd-nuget/1",
        "package": PACKAGE,
        "version": VERSION,
        "source": "api.nuget.org",
        "runtime_target": "net472",
        "assembly_verified": False,
    }
    try:
        req = urllib.request.Request(
            URL, headers={"User-Agent": "VQS-Hosted-DAX-Private-Model-Probe"})
        with urllib.request.urlopen(req, timeout=60) as response:
            if not response.geturl().startswith(
                "https://api.nuget.org/v3-flatcontainer/"
            ):
                raise RuntimeError("NuGet package redirected unexpectedly")
            raw = response.read(MAX_BYTES + 1)
        if not 100_000 < len(raw) < MAX_BYTES:
            raise RuntimeError("NuGet package size outside safety bound")
        import io

        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            candidates = [
                name for name in names
                if name.lower().endswith("/microsoft.analysisservices.adomdclient.dll")
            ]
            if not candidates:
                record["available_lib_paths"] = sorted(
                    name for name in names if name.startswith("lib/")
                )[:45]
                raise RuntimeError("official ADOMD binary absent; see available_lib_paths")
            frameworks = ("net472", "net48", "net462", "net461", "netstandard2.0")
            selected = next(
                (candidate for framework in frameworks for candidate in candidates
                 if candidate.lower().startswith("lib/" + framework + "/")),
                None,
            )
            if selected is None:
                record["available_assembly_paths"] = sorted(candidates)
                raise RuntimeError("ADOMD assembly has no supported framework")
            prefix = selected.rsplit("/", 1)[0] + "/"
            record["runtime_target"] = prefix.split("/")[1]
            included = [
                name for name in names
                if name.startswith(prefix) and name.lower().endswith(".dll")
            ]
            if len(included) > 25:
                raise RuntimeError("unexpected ADOMD library count")
            root.mkdir(parents=True, exist_ok=False)
            for item in included:
                binary = archive.read(item)
                if len(binary) > 20_000_000:
                    raise RuntimeError("unexpected DLL size")
                dst = root / Path(item).name
                if dst.exists():
                    raise RuntimeError("duplicate ADOMD basename")
                dst.write_bytes(binary)
        assembly = root / "Microsoft.AnalysisServices.AdomdClient.dll"
        record["package_sha256"] = hashlib.sha256(raw).hexdigest()
        record["package_size"] = len(raw)
        record["assembly_sha256"] = hashlib.sha256(assembly.read_bytes()).hexdigest()
        record["assembly_bytes"] = assembly.stat().st_size
        record["dll_count"] = len(included)
        record["assembly_verified"] = True
        record["status"] = "installed_to_ephemeral_runner"
    except Exception as exc:  # noqa: BLE001 - external download evidence must persist
        record["status"] = "blocked"
        record["error_class"] = type(exc).__name__
        record["error"] = str(exc)[:200]
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.out)
