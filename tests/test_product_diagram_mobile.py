"""Keep the repository's product-direction diagram readable on narrow GitHub screens.

The main and roadmap READMEs deliberately use a fixed-aspect, vertical SVG
rather than Mermaid: GitHub Mermaid's fit-to-screen canvas was illegible on
320-390px mobile screens. The SVG is vector and stays editable in Git.
"""

import pathlib
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[1]
SVG = ROOT / "docs" / "diagrams" / "vqs-product-loop-mobile.svg"


def test_product_diagram_is_mobile_first_and_valid_svg() -> None:
    root = ET.parse(SVG).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    width, height = (int(part) for part in root.attrib["viewBox"].split()[2:])
    assert width <= 720, "Keep the designed viewBox narrow enough for 320px screens"
    assert height <= 1500, "Avoid a needlessly tall mobile diagram"
    assert int(root.attrib["width"]) == width
    assert int(root.attrib["height"]) == height

    tags = [el.tag.rsplit("}", 1)[-1] for el in root.iter()]
    assert "title" in tags and "desc" in tags, "Provide accessible diagram alternatives"
    assert not {"script", "foreignObject", "image"}.intersection(tags)

    labels = [element for element in root.iter() if element.tag.endswith("}text")]
    assert len(labels) >= 14
    assert min(int(label.attrib["font-size"]) for label in labels) >= 27
    # Conservative layout guard against the original cut-off/overflow problem.
    for label in labels:
        x = float(label.attrib["x"])
        size = float(label.attrib["font-size"])
        rendered = "".join(label.itertext())
        assert 0 <= x <= width
        if label.attrib.get("text-anchor") != "middle":
            assert x + len(rendered) * size * 0.55 < width, rendered


def test_public_entry_points_use_the_mobile_diagram_not_mermaid() -> None:
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "roadmap" / "README.md").read_text(encoding="utf-8")
    assert 'src="docs/diagrams/vqs-product-loop-mobile.svg"' in root_readme
    assert 'src="../docs/diagrams/vqs-product-loop-mobile.svg"' in roadmap
    assert "```mermaid" not in root_readme.split("## Product direction", 1)[1].split("## Install", 1)[0]
    assert "```mermaid" not in roadmap.split("## Product direction", 1)[1].split("## Release path", 1)[0]
