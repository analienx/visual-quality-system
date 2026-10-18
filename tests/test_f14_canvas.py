"""F14 RED core: page contrast must compose the source canvas.

_page_background reads objects.outspace (wallpaper) and ignores the
explicit canvas background (PBIR page 2.1.0 objects.background with
Background {color, image, transparency}), alpha, and image
composition. White theme + black canvas + black text emits
black-on-white and passes. M2 resolves canvas layers/transparency and
uses unknown for unsupported composition.

Grounding: objects.background/outspace + Background{color,image,
transparency} from the page 2.1.0 schema; color solid-literal and
transparency expr-Literal "ND" shapes from the committed mini fixture
(mirrored for canvas). Unresolvable readings surface through the
readings/evidence.unresolved contract (see test_design_rules).
"""
import json
import shutil
from pathlib import Path

from vqs.design_rules import text_contrast
from vqs.powerbi.measure import measure_report

FIXTURES = Path(__file__).resolve().parent / "powerbi" / "fixtures"
REPORT = str(FIXTURES / "mini_report")


def _canvas(color_value: str, transparency: str | None = None,
            image: dict | None = None) -> dict:
    props: dict = {"color": {"solid": {"color": {
        "expr": {"Literal": {"Value": color_value}}}}}}
    if transparency is not None:
        props["transparency"] = {"expr": {"Literal": {"Value": transparency}}}
    if image is not None:
        props["image"] = image
    return props


def _clone_with_canvas(tmp_path: Path, canvas: dict) -> Path:
    clone = tmp_path / "report"
    shutil.copytree(REPORT, clone)
    page_path = clone / "definition" / "pages" / "P1" / "page.json"
    page = json.loads(page_path.read_text(encoding="utf-8"))
    page.setdefault("objects", {})["background"] = [{"properties": canvas}]
    page_path.write_text(json.dumps(page), encoding="utf-8")
    return clone


def _readings(report: Path) -> list[dict]:
    return measure_report(str(report))["rules"][
        "typography.text_contrast"]["readings"]


def test_f14_canvas_beats_wallpaper(tmp_path: Path) -> None:
    """RED: black canvas + white wallpaper + black text is black-on-black."""
    clone = _clone_with_canvas(tmp_path, _canvas("'#000000'"))
    backgrounds = {reading["background"] for reading in _readings(clone)}
    assert backgrounds == {"#000000"}


def test_f14_opaque_canvas_with_zero_transparency(tmp_path: Path) -> None:
    """RED: transparency 0 keeps the opaque canvas color (not wallpaper)."""
    clone = _clone_with_canvas(tmp_path, _canvas("'#000000'", "0D"))
    backgrounds = {reading["background"] for reading in _readings(clone)}
    assert backgrounds == {"#000000"}


def test_f14_translucent_canvas_is_unknown(tmp_path: Path) -> None:
    """RED: 50% canvas transparency cannot resolve a bg color -> unknown."""
    clone = _clone_with_canvas(tmp_path, _canvas("'#000000'", "50D"))
    finding = text_contrast(readings=_readings(clone))
    assert finding["status"] == "unknown"
    assert finding["evidence"]["unresolved"] != []


def test_f14_canvas_image_is_unknown(tmp_path: Path) -> None:
    """RED: a canvas image cannot resolve a bg color -> unknown."""
    clone = _clone_with_canvas(
        tmp_path, _canvas("'#000000'", "0D", {"name": "bg.png"}))
    finding = text_contrast(readings=_readings(clone))
    assert finding["status"] == "unknown"
    assert finding["evidence"]["unresolved"] != []
