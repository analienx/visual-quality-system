"""Source-bound report/Word page evidence, ported from PBIPDocumenter VQS.

A passed JSON checklist is not proof that the reviewer actually inspected pixels.
The separate rule/data/render stages must also pass before release approval.

This module additionally owns the trusted evidence-store abstraction used by
release acceptance: a SHA-256 digest only becomes evidence when a trusted
store resolves it to bytes, recomputes the digest, and returns the envelope
for source/environment/scope binding. Caller-supplied mappings are never a
store. :class:`TestEvidenceStore` is an explicitly untrusted unit-test double.
"""
from __future__ import annotations

import hashlib
import json
import struct
import zlib
from fractions import Fraction
from pathlib import Path
from typing import Any

from .policy import (
    CRITERIA,
    OPTIONAL,
    POLICY_VERSION,
    REQUIRED,
    SEVERITIES,
    STATUSES,
    required_criteria,
)
from .run_store import _resolve_artifact

REVIEWER_ROLE = "independent_visual_reviewer"


def digest(path: Path) -> str:
    """SHA-256 over a file, enforcing the encoded-size cap first.

    T08: the file size is capped before any bulk read and the hash
    streams in chunks, so oversized inputs are refused before
    unbounded allocation. Raises ValueError when over the cap.
    """
    try:
        if path.stat().st_size > _PNG_FILE_CAP:
            raise ValueError(f"Evidence file exceeds size cap: {path}")
    except OSError:
        pass  # the read below surfaces missing files exactly as before
    digestor = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > _PNG_FILE_CAP:
                raise ValueError(f"Evidence file exceeds size cap: {path}")
            digestor.update(chunk)
    return digestor.hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    """Check PNG signature, chunk bounds, CRCs and final IEND, not only the header."""
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Invalid PNG signature: {path}")
        size = None
        data_seen = end_seen = False
        for _ in range(100000):
            header = stream.read(8)
            if len(header) != 8:
                break
            length, tag = struct.unpack(">I4s", header)
            if length > 100_000_000:
                raise ValueError(f"Oversized PNG chunk: {path}")
            payload, check = stream.read(length), stream.read(4)
            if len(payload) != length or len(check) != 4:
                raise ValueError(f"Truncated PNG chunk: {path}")
            if zlib.crc32(tag + payload) != struct.unpack(">I", check)[0]:
                raise ValueError(f"Corrupt PNG chunk: {path}")
            if tag == b"IHDR":
                if size is not None or length != 13:
                    raise ValueError(f"Invalid PNG header: {path}")
                size = struct.unpack(">II", payload[:8])
            elif tag == b"IDAT":
                data_seen = True
            elif tag == b"IEND":
                end_seen = True
                break
        if size is None or not data_seen or not end_seen or not all(1 <= x <= 20000 for x in size):
            raise ValueError(f"Incomplete PNG image: {path}")
        return size


_PNG_PIXEL_CAP = 256 * 1024 * 1024
_PNG_BLOB_CAP = 64 * 1024 * 1024
_PNG_FILE_CAP = 80 * 1024 * 1024


def _decode_png(path: Path) -> tuple[int, int, int, bytes]:
    """Walk chunks, inflate IDAT and check filters; ValueError when undecodable.

    S12: the file size is capped before any read (the running IDAT
    total plus header/ancillary headroom), the IHDR-declared type
    and dimensions gate every later allocation — a hostile size
    claim fails before any IDAT body is kept — and inflation is
    incremental against the exact declared pixel count, so neither
    a burst of chunks nor a lying stream can exhaust memory.
    Only 8-bit non-interlaced grayscale/truecolor/truecolor+alpha
    are supported; every scanline filter byte must be 0-4.
    """
    try:
        if path.stat().st_size > _PNG_FILE_CAP:
            raise ValueError(f"PNG file exceeds decode cap: {path}")
    except OSError:
        pass  # the read below surfaces missing files exactly as before
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Invalid PNG signature: {path}")
    position = 8
    dims: tuple[int, int, int] | None = None
    parts: list[bytes] = []
    total = 0
    end = len(raw)
    while True:
        if position + 8 > end:
            raise ValueError(f"Truncated PNG chunk table: {path}")
        length, tag = struct.unpack(">I4s", raw[position:position + 8])
        if length > 100_000_000:
            raise ValueError(f"Oversized PNG chunk: {path}")
        body = raw[position + 8:position + 8 + length]
        check = raw[position + 8 + length:position + 12 + length]
        if len(body) != length or len(check) != 4:
            raise ValueError(f"Truncated PNG chunk: {path}")
        if zlib.crc32(tag + body) != struct.unpack(">I", check)[0]:
            raise ValueError(f"Corrupt PNG chunk: {path}")
        position += 12 + length
        if tag == b"IHDR":
            if dims is not None or length != 13:
                raise ValueError(f"Invalid PNG header: {path}")
            width, height, depth, color, _comp, _filter, interlace = struct.unpack(
                ">IIBBBBB", body)
            if depth != 8 or color not in (0, 2, 6) or interlace != 0:
                raise ValueError(f"Unsupported PNG image type "
                                 f"(depth={depth} color={color} interlace={interlace}): {path}")
            if not 1 <= width <= 20000 or not 1 <= height <= 20000:
                raise ValueError(f"Implausible PNG dimensions {width}x{height}: {path}")
            bpp = {0: 1, 2: 3, 6: 4}[color]
            if height * (1 + width * bpp) > _PNG_PIXEL_CAP:
                raise ValueError(f"PNG pixel content exceeds decode cap: {path}")
            dims = (width, height, bpp)
        elif tag == b"IDAT":
            if dims is None:
                raise ValueError(f"IDAT before IHDR: {path}")
            total += length
            if total > _PNG_BLOB_CAP:
                raise ValueError(f"PNG stream exceeds decode cap: {path}")
            parts.append(body)
        elif tag == b"IEND":
            break
    if dims is None or not parts:
        raise ValueError(f"Incomplete PNG image: {path}")
    width, height, bpp = dims
    expected = height * (1 + width * bpp)
    decompressor = zlib.decompressobj()
    chunks: list[bytes] = []
    produced = 0
    try:
        for part in parts:
            out = decompressor.decompress(part, expected - produced + 1)
            produced += len(out)
            chunks.append(out)
            if produced > expected:
                raise ValueError(
                    f"IDAT pixels exceed expected {expected}: {path}")
        tail = decompressor.flush()
        if tail:
            produced += len(tail)
            chunks.append(tail)
    except zlib.error as exc:
        raise ValueError(f"IDAT stream undecodable: {exc}") from exc
    if produced > expected:
        raise ValueError(f"IDAT pixels exceed expected {expected}: {path}")
    if not decompressor.eof or decompressor.unused_data:
        raise ValueError(f"IDAT stream has trailing data: {path}")
    pixels = b"".join(chunks)
    if len(pixels) != expected:
        raise ValueError(f"IDAT pixels {len(pixels)} != expected {expected}: {path}")
    stride = 1 + width * bpp
    for row in range(height):
        filter_type = pixels[row * stride]
        if filter_type > 4:
            raise ValueError(f"Unknown PNG filter type {filter_type} "
                             f"on row {row}: {path}")
    return width, height, bpp, pixels


def decode_png_pixels(path: Path) -> tuple[int, int]:
    """Decode PNG IDAT pixels with bounded work; ValueError when undecodable.

    R13: a CRC-correct container can still carry a non-zlib IDAT, a
    cut-short stream, or unknown filter types, and no consumer may
    approve pixels it never decoded. S12: 8-bit non-interlaced
    grayscale/truecolor/truecolor+alpha are honored with IHDR-first
    bounds and a capped running compressed total.
    """
    width, height, _bpp, _pixels = _decode_png(path)
    return width, height


def _unfilter_scanlines(width: int, channels: int, pixels: bytes) -> bytes:
    """Reconstruct original samples; raise on unknown filter types."""
    stride = width * channels
    out = bytearray()
    previous = bytearray(stride)
    offset = 0
    rows = len(pixels) // (stride + 1)
    for _ in range(rows):
        kind = pixels[offset]
        offset += 1
        row = bytearray(pixels[offset:offset + stride])
        offset += stride
        if kind == 1:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                row[index] = (row[index] + left) & 0xFF
        elif kind == 2:
            for index in range(stride):
                row[index] = (row[index] + previous[index]) & 0xFF
        elif kind == 3:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                row[index] = (row[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif kind == 4:
            for index in range(stride):
                left = row[index - channels] if index >= channels else 0
                up = previous[index]
                upper = previous[index - channels] if index >= channels else 0
                pick = left + up - upper
                dist_left = abs(pick - left)
                dist_up = abs(pick - up)
                dist_corner = abs(pick - upper)
                if dist_left <= dist_up and dist_left <= dist_corner:
                    row[index] = (row[index] + left) & 0xFF
                elif dist_up <= dist_corner:
                    row[index] = (row[index] + up) & 0xFF
                else:
                    row[index] = (row[index] + upper) & 0xFF
        elif kind != 0:
            raise ValueError(f"Unknown PNG filter type {kind}")
        out += row
        previous = row
    return bytes(out)


def pixel_digest(path: Path) -> str:
    """Canonical sha256 over decoded pixel content (S12).

    Scanlines are unfiltered and samples expanded to RGBA (grayscale
    and truecolor gain opaque alpha), prefixed by dimensions, so the
    same visual content hashes identically across grayscale, RGB and
    opaque-RGBA encodings. Translucent alpha stays distinct from any
    RGB encoding: it looks different.
    """
    width, height, bpp, pixels = _decode_png(path)
    raw = _unfilter_scanlines(width, bpp, pixels)
    expanded = bytearray()
    if bpp == 1:
        for sample in raw:
            expanded += bytes((sample, sample, sample, 255))
    elif bpp == 3:
        for index in range(0, len(raw), 3):
            expanded += raw[index:index + 3] + b"\xff"
    else:
        expanded += raw
    return hashlib.sha256(struct.pack(">II", width, height)
                          + bytes(expanded)).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def canonical_json_sha256(payload: object) -> str:
    """SHA256 over canonical JSON bytes (R6-DEC-03/06 shared digest).

    ``sort_keys`` + compact separators + UTF-8, no ``default=str``:
    inputs must be JSON-native so every producer/consumer/test
    computes identical bytes. Used by the acceptance suite digest
    and the review-bundle identity.
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def safe_render_name(name: object) -> str | None:
    """Accept plain basenames only; reject traversal and absolute paths."""
    if not isinstance(name, str) or not name or name.startswith((".", "/")):
        return None
    if "/" in name or "\\" in name or ":" in name:
        return None
    if Path(name).name != name:
        return None
    return name


class EvidenceStore:
    """Resolve evidence digests to sealed envelopes; base type, untrusted."""

    TRUSTED = False

    def resolve(self, sha256: str) -> dict[str, Any]:
        """Return the envelope for a digest; raise when unresolvable."""
        raise NotImplementedError


class SealedEvidenceStore(EvidenceStore):
    """Production store: content-addressed sealed files under ``root/objects``.

    ``resolve`` reads ``objects/<sha256>``, refuses symlinks and escapes
    through linked ancestors (S15), recomputes the digest over the raw
    bytes, and parses the envelope as a JSON object.
    Missing digests raise :class:`LookupError`; tampered or malformed
    envelopes raise :class:`ValueError`.
    """

    TRUSTED = True

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def resolve(self, sha256: str) -> dict[str, Any]:
        digest_ok = (
            isinstance(sha256, str)
            and len(sha256) == 64
            and all(c in "0123456789abcdefABCDEF" for c in sha256)
        )
        if not digest_ok:
            raise ValueError(f"Evidence digest is not hex64: {sha256!r}")
        if _resolve_artifact(self.root, "objects/" + sha256) is None:
            raise ValueError(f"Evidence path escapes the trusted root: {sha256}")
        path = self.root / "objects" / sha256
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise LookupError(f"Evidence not materialized: {sha256}") from exc
        if hashlib.sha256(raw).hexdigest() != sha256.lower():
            raise ValueError(f"Evidence bytes do not match digest: {sha256}")
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"Evidence envelope is not JSON: {sha256}") from exc
        envelope_ok = isinstance(envelope, dict)
        if not envelope_ok:
            raise ValueError(f"Evidence envelope is not an object: {sha256}")
        return envelope


class TestEvidenceStore(EvidenceStore):
    """Explicit unit-test double; NEVER trusted production evidence.

    ``TRUSTED`` is ``False`` so release acceptance always blocks on it.
    Production callers must wire :class:`SealedEvidenceStore`.
    """

    TRUSTED = False
    __test__ = False

    def __init__(self, envelopes: dict[str, dict[str, Any]]) -> None:
        self._envelopes = dict(envelopes)

    def resolve(self, sha256: str) -> dict[str, Any]:
        try:
            envelope = self._envelopes[sha256]
        except KeyError as exc:
            raise LookupError(f"Evidence not materialized: {sha256}") from exc
        envelope_ok = isinstance(envelope, dict)
        if not envelope_ok:
            raise ValueError(f"Evidence envelope is not an object: {sha256}")
        return dict(envelope)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _parse_effective_scale(value: object) -> Fraction | None:
    """Parse a recorded measured scale (``"5/2"``, ``"2"``, ``2``); None when unproven."""
    try:
        if isinstance(value, bool):
            return None
        ratio = Fraction(value) if not isinstance(value, Fraction) else value
    except (ValueError, ZeroDivisionError, TypeError):
        return None
    if ratio <= 0:
        return None
    return ratio


def calibration_expected_pixels(calibration: dict[str, Any]) -> list[int] | None:
    """Expected full-canvas PNG pixels from recorded calibration (pure).

    U3 measured calibration: when the producer recorded a Bridge-proven
    ``effective_scale`` (host-DPI transforms the requested scale cannot
    describe), the expectation follows the measurement, not the request.
    Otherwise the requested ``scale`` governs exactly as before. Returns
    None when the calibration shape is invalid or the measured product
    is non-integral — unproven, never rounded into a pass.
    Geometry-blocked records (render identity without a proven
    pixel transform) carry no expectation: always None.
    """
    if calibration.get("geometry_calibration") == "blocked":
        return None
    width = calibration.get("canvas_width")
    height = calibration.get("canvas_height")
    if not _is_positive_int(width) or not _is_positive_int(height):
        return None
    raw = calibration.get("effective_scale", calibration.get("scale"))
    ratio = _parse_effective_scale(raw)
    if ratio is None:
        return None
    expected_w, expected_h = width * ratio, height * ratio
    if expected_w.denominator != 1 or expected_h.denominator != 1:
        return None
    return [int(expected_w), int(expected_h)]


def check_calibration(calibration: object,
                      pixels: tuple[int, int] | list[int] | None = None
                      ) -> list[dict[str, Any]]:
    """Validate full-canvas calibration evidence, optionally against pixels.

    Two evidence levels: a ``geometry_calibration == "blocked"`` record
    binds render identity (exact PID/path/page/source PNG for whole-page
    perceptual review) with no pixel transform to check, so observed
    pixels never mismatch — coordinate-dependent claims stay unproven
    by construction. Anything else must prove the transform.
    """
    if not isinstance(calibration, dict):
        return [{"rule": "calibration_missing", "verdict": "blocked"}]
    width = calibration.get("canvas_width")
    height = calibration.get("canvas_height")
    scale = calibration.get("scale")
    viewport = calibration.get("viewport")
    method = calibration.get("method")
    if (not _is_positive_int(width) or not _is_positive_int(height)
            or isinstance(scale, bool) or scale not in (1, 2)
            or not isinstance(method, str) or not method.strip()):
        return [{"rule": "calibration_invalid", "verdict": "blocked"}]
    if calibration.get("geometry_calibration") == "blocked":
        reason = calibration.get("geometry_reason")
        if not isinstance(reason, str) or not reason.strip():
            return [{"rule": "calibration_invalid", "verdict": "blocked"}]
        return []
    if (not isinstance(viewport, str) or not viewport.strip()):
        return [{"rule": "calibration_invalid", "verdict": "blocked"}]
    if "effective_scale" in calibration and calibration_expected_pixels(calibration) is None:
        return [{"rule": "calibration_invalid", "verdict": "blocked"}]
    if pixels is None:
        return []
    expected = calibration_expected_pixels(calibration)
    actual = tuple(pixels) if isinstance(pixels, (list, tuple)) else None
    if expected is None or actual != (expected[0], expected[1]):
        return [{"rule": "calibration_mismatch", "verdict": "blocked",
                 "expected": expected,
                 "actual": list(actual) if actual is not None else pixels}]
    return []


def check_data_readiness(readiness: object) -> list[dict[str, Any]]:
    """Validate scoped data-readiness evidence; unproven data never passes."""
    if not isinstance(readiness, dict):
        return [{"rule": "data_readiness_missing", "verdict": "blocked"}]
    if readiness.get("populated") is not True:
        return [{"rule": "data_unpopulated", "verdict": "blocked"}]
    method = readiness.get("method")
    if not isinstance(method, str) or not method.strip():
        return [{"rule": "data_readiness_invalid", "verdict": "blocked"}]
    scope = readiness.get("scope")
    if scope is not None and not isinstance(scope, dict):
        return [{"rule": "data_readiness_invalid", "verdict": "blocked"}]
    return []


def check_policy_binding(doc: object, kind: str, source_sha: str) -> list[dict[str, Any]]:
    """Canonical schema/policy/surface/source binding for review entries (F21)."""
    if not isinstance(doc, dict):
        return [{"rule": "review_policy_or_source_mismatch", "verdict": "blocked"}]
    if (doc.get("schema") != 1 or doc.get("policy_version") != POLICY_VERSION or
            doc.get("surface") != kind or doc.get("source_sha256") != source_sha):
        return [{"rule": "review_policy_or_source_mismatch", "verdict": "blocked"}]
    return []


def check_reviewer(reviewer: object, fixer_id: str) -> list[dict[str, Any]]:
    """Canonical reviewer check: independent identity, never the fixer.

    Identity compares on the normalized form (case/padding aliases of
    the fixer fail); the sealed record keeps the verbatim claimed id.
    """
    from .contracts.types import normalize_identity

    if not isinstance(reviewer, dict):
        return [{"rule": "independent_reviewer_required", "verdict": "blocked"}]
    reviewer_id = reviewer.get("id", "")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        return [{"rule": "independent_reviewer_required", "verdict": "blocked"}]
    if not isinstance(fixer_id, str) or not fixer_id.strip():
        return [{"rule": "fixer_identity_required", "verdict": "blocked"}]
    if normalize_identity(reviewer_id) == normalize_identity(fixer_id):
        return [{"rule": "own_review_forbidden", "verdict": "fail"}]
    if reviewer.get("role") != REVIEWER_ROLE:
        return [{"rule": "independent_reviewer_required", "verdict": "blocked"}]
    return []


def check_observations(kind: str, observations: object,
                       valid_visual_ids: set[str],
                       page_id: str = "?") -> list[dict[str, Any]]:
    """Canonical observation check shared by verify_review and adjudication."""
    if kind not in REQUIRED:
        return [{"rule": "review_surface_unknown", "verdict": "blocked",
                 "page": page_id}]
    if not isinstance(observations, list):
        return [{"rule": "review_observations_invalid", "verdict": "blocked",
                 "page": page_id}]
    answers = [answer for answer in observations if isinstance(answer, dict)]
    if any(not isinstance(answer.get("id"), str) for answer in answers):
        return [{"rule": "review_observations_invalid", "verdict": "blocked",
                 "page": page_id}]
    by_id = {answer.get("id"): answer for answer in answers}
    expected = set(REQUIRED[kind])
    if len(answers) != len(observations) or len(by_id) != len(answers) or set(by_id) != expected:
        return [{"rule": "review_observations_incomplete", "verdict": "blocked",
                 "page": page_id}]
    findings: list[dict[str, Any]] = []
    for check in expected:
        answer = by_id[check]
        status, reason = answer.get("status"), answer.get("reason")
        if (not isinstance(status, str) or status not in STATUSES
                or not isinstance(reason, str) or len(reason.strip()) < 32):
            findings.append({"rule": "observation_unsubstantiated",
                             "verdict": "blocked", "page": page_id, "check": check})
        elif status == "not_applicable" and check not in OPTIONAL[kind]:
            findings.append({"rule": "mandatory_observation_skipped",
                             "verdict": "blocked", "page": page_id, "check": check})
        elif status == "fail":
            region = answer.get("region")
            located = (isinstance(region, list) and len(region) == 4 and
                       all(isinstance(x, (int, float)) and not isinstance(x, bool)
                           and 0 <= x <= 1 for x in region) and
                       region[0] < region[2] and region[1] < region[3])
            severity = answer.get("severity")
            visual_id = answer.get("visual_id")
            if (not isinstance(severity, str) or severity not in SEVERITIES
                    or not located or not isinstance(visual_id, str)
                    or visual_id not in valid_visual_ids
                    or len(str(answer.get("proposed_fix", "")).strip()) < 12):
                findings.append({"rule": "issue_lacks_location_or_repair",
                                 "verdict": "blocked", "page": page_id, "check": check})
            else:
                findings.append({"rule": "visual_defect", "verdict": "fail",
                                 "page": page_id, "check": check,
                                 "severity": answer["severity"], "region": region,
                                 "visual_id": answer["visual_id"],
                                 "detail": reason, "proposed_fix": answer["proposed_fix"]})
    return findings


def image_evidence(images: Path, source_sha: str, page_ids: list[str],
                   canvases: dict[str, Any] | None = None) -> tuple[list[dict], list[dict]]:
    """Validate rendered page PNGs against a source-linked capture manifest."""
    manifest_path = images / "capture-manifest.json"
    if not manifest_path.is_file():
        return [], [{"rule": "render_manifest_missing", "path": str(manifest_path)}]
    try:
        manifest = load(manifest_path)
    except (OSError, ValueError, TypeError) as error:
        return [], [{"rule": "render_manifest_invalid", "detail": str(error)}]
    issues: list[dict] = []
    if manifest.get("source_sha256") != source_sha:
        issues.append({"rule": "render_source_stale"})
    files = manifest.get("files")
    mapping = manifest.get("page_images")
    if not isinstance(files, dict) or not isinstance(mapping, dict):
        return [], issues + [{"rule": "render_manifest_invalid"}]
    calibration = manifest.get("calibration")
    readiness = manifest.get("data_readiness")
    shape_issues = check_calibration(calibration)
    issues.extend(shape_issues)
    issues.extend(check_data_readiness(readiness))
    pages = []
    for page_id in page_ids:
        fallback = page_id if page_id.lower().endswith(".png") else page_id + ".png"
        name = safe_render_name(mapping.get(page_id, fallback))
        if name is None:
            issues.append({"rule": "page_render_invalid", "page": page_id,
                           "detail": "unsafe render filename in manifest"})
            continue
        path = images / name
        if not path.is_file():
            issues.append({"rule": "page_render_missing", "page": page_id})
            continue
        try:
            dimensions = png_size(path)
            if min(dimensions) < 450:
                raise ValueError("Image too small to review")
            sha = digest(path)
        except (ValueError, OSError) as error:
            issues.append({"rule": "page_render_invalid", "page": page_id, "detail": str(error)})
            continue
        if files.get(name) != sha:
            issues.append({"rule": "page_render_unbound", "page": page_id})
        try:
            decode_png_pixels(path)
        except (ValueError, OSError) as error:
            issues.append({"rule": "page_render_undecodable", "verdict": "blocked",
                           "page": page_id, "detail": str(error)})
            continue
        inventory = manifest.get("visuals")
        if inventory is not None:
            entry = inventory.get(page_id) if isinstance(inventory, dict) else None
            if not isinstance(entry, list):
                issues.append({"rule": "unknown_visual_context", "verdict": "blocked",
                               "page": page_id})
                continue
            if canvases is None:
                issues.append({"rule": "render_canvas_missing", "verdict": "blocked",
                               "page": page_id,
                               "detail": "authoritative canvases required "
                                         "for inventoried renders"})
                continue
        if not shape_issues:
            for row in check_calibration(calibration, dimensions):
                issues.append({**row, "page": page_id})
            if canvases is not None:
                canvas = canvases.get(page_id)
                calib = calibration if isinstance(calibration, dict) else {}
                if (not isinstance(canvas, (list, tuple)) or len(canvas) != 2
                        or [calib.get("canvas_width"), calib.get("canvas_height")] != [canvas[0], canvas[1]]):
                    issues.append({"rule": "render_canvas_mismatch", "verdict": "blocked",
                                   "page": page_id,
                                   "source_canvas": list(canvas) if isinstance(canvas, (list, tuple)) and len(canvas) == 2 else None,
                                   "calibration_canvas": [calib.get("canvas_width"), calib.get("canvas_height")]})
        pages.append({"id": page_id, "image": name, "sha256": sha, "pixels": dimensions})
    return pages, issues


def review_template(kind: str, source_sha: str, pages: list[dict], fixer_id: str,
                    *, calibration: dict[str, Any],
                    data_readiness: dict[str, Any],
                    source_pages: list[str]) -> dict:
    """Create an unapproved review form; pending observations never imply approval.

    T09: ``source_pages`` is the authoritative whole-source page
    inventory from the producer (report_context page ids), required
    so the completed form binds completeness instead of letting a
    caller-edited list certify it.
    """
    required_criteria(kind)
    if not source_sha or not fixer_id or not fixer_id.strip():
        raise ValueError("Template needs a source hash and a fixer id")
    if (not isinstance(source_pages, list) or not source_pages
            or any(not isinstance(entry, str) or not entry
                   for entry in source_pages)):
        raise ValueError("Template needs the authoritative source_pages inventory")
    calibration_issues = check_calibration(calibration)
    if calibration_issues:
        raise ValueError("Template needs valid calibration evidence: "
                         f"{calibration_issues[0]['rule']}")
    readiness_issues = check_data_readiness(data_readiness)
    if readiness_issues:
        raise ValueError("Template needs valid data_readiness evidence: "
                         f"{readiness_issues[0]['rule']}")
    return {"schema": 1, "policy_version": POLICY_VERSION, "surface": kind,
            "source_sha256": source_sha, "fixer_id": fixer_id,
            "source_pages": list(source_pages),
            "calibration": calibration, "data_readiness": data_readiness,
            "reviewer": {"id": "", "role": "independent_visual_reviewer"},
            "pages": [{"id": page["id"], "image": page["image"], "image_sha256": page["sha256"],
                       "image_source_sha256": source_sha,
                       "visual_inventory": page.get("visual_inventory", []),
                       "observations": [{"id": check, "criterion": CRITERIA[check], "status": "pending", "reason": "",
                                         "severity": None, "region": None, "visual_id": "page", "proposed_fix": ""}
                                        for check in REQUIRED[kind]]} for page in pages]}


def verify_review(kind: str, source_sha: str, pages: list[dict], review: dict, fixer_id: str) -> list[dict]:
    """Reject missing checks, stale images, self-approval and unlocated failures."""
    required_criteria(kind)
    findings: list[dict] = []
    mismatch = check_policy_binding(review, kind, source_sha)
    if mismatch:
        return mismatch
    calibration = review.get("calibration")
    readiness = review.get("data_readiness")
    shape_issues = check_calibration(calibration)
    findings.extend(shape_issues)
    findings.extend(check_data_readiness(readiness))
    findings.extend(check_reviewer(review.get("reviewer", {}), fixer_id))
    rows = review.get("pages", [])
    if not isinstance(rows, list) or len(rows) != len(pages):
        return findings + [{"rule": "review_page_inventory_mismatch"}]
    observed = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if len(observed) != len(pages):
        return findings + [{"rule": "review_duplicate_page"}]
    for page in pages:
        item = observed.get(page["id"])
        if not item or item.get("image_sha256") != page["sha256"]:
            findings.append({"rule": "review_image_stale", "page": page["id"]})
            continue
        if not shape_issues and page.get("pixels") is not None:
            for row in check_calibration(calibration, page["pixels"]):
                findings.append({**row, "page": page["id"]})
        valid_ids = {"page"} | {v["id"] for v in page.get("visual_inventory", [])
                                if isinstance(v, dict) and v.get("id")}
        findings.extend(check_observations(kind, item.get("observations"),
                                           valid_ids, page["id"]))
    return findings
