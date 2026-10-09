"""Measured rules must fail on actual violations, not guessed inputs."""
from vqs.design_rules import (
    axis_display_distinctness,
    category_axis_space,
    cross_page_metric_units,
    format_declaration_consistency,
    palette_semantic_consistency,
    text_contrast,
)


def test_repeated_percent_labels_do_not_pass() -> None:
    finding = axis_display_distinctness([0.096, 0.104], ["10%", "10%"])
    assert finding["status"] == "fail" and finding["evidence"]["collisions"]
    assert axis_display_distinctness([0.096, 0.104], ["9.6%", "10.4%"])["status"] == "pass"
    assert axis_display_distinctness(None, ["10%", "10%"])["status"] == "unknown"
    assert axis_display_distinctness([0.1, 0.2], None)["status"] == "unknown"


def test_contrast_is_measured_not_inferred() -> None:
    assert text_contrast("#000000", "#FFFFFF")["status"] == "pass"
    assert text_contrast("#888888", "#FFFFFF")["status"] == "fail"
    assert text_contrast("#777777", None)["status"] == "unknown"
    assert text_contrast("rgba(0,0,0,0.5)", "#FFFFFF")["status"] == "unknown"
    assert text_contrast("#777777", "#FFFFFF", large_text=True)["status"] == "pass"


def test_f14_unresolvable_pairs_are_explicit() -> None:
    finding = text_contrast(readings=[
        {"foreground": "#000000", "background": "#FFFFFF",
         "page": "P1", "role": "title", "count": 1},
        {"foreground": "RED", "background": "#FFFFFF",
         "page": "P1", "role": "title", "count": 1}])
    assert finding["status"] == "unknown"
    unresolved = finding["evidence"]["unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0]["page"] == "P1"
    assert unresolved[0]["role"] == "title"
    assert "RED" in unresolved[0].get("foreground", "")


def test_label_density_uses_actual_dimensions() -> None:
    assert category_axis_space([70, 70, 70], 300)["status"] == "pass"
    assert category_axis_space([70, 70, 70], 150)["status"] == "fail"
    assert category_axis_space(None, 300)["status"] == "unknown"
    assert category_axis_space([70, 70], None)["status"] == "unknown"


def test_undeclared_recoloring_fails_and_overrides_pass() -> None:
    rows = [
        {"state": "good", "color": "#00AA00", "page": "A"},
        {"state": "good", "color": "#CC0000", "page": "B"},
    ]
    failed = palette_semantic_consistency(rows)
    assert failed["status"] == "fail" and len(failed["evidence"]["conflicts"]) == 1
    assert palette_semantic_consistency(rows, declared_overrides=["good"])["status"] == "pass"
    assert palette_semantic_consistency([
        {"state": "good", "color": "#00AA00", "page": "A"},
        {"state": "good", "color": "#00AA00", "page": "B"},
    ])["status"] == "pass"
    assert palette_semantic_consistency(None)["status"] == "unknown"
    assert palette_semantic_consistency([{"state": "good"}])["status"] == "unknown"


def test_changed_units_fail_and_stable_units_pass() -> None:
    failed = cross_page_metric_units([
        {"measure": "Revenue", "unit": "USD", "page": "A"},
        {"measure": "Revenue", "unit": "% of total", "page": "B"},
    ])
    assert failed["status"] == "fail"
    assert failed["evidence"]["conflicts"][0]["measure"] == "Revenue"
    assert cross_page_metric_units([
        {"measure": "Revenue", "unit": "USD", "page": "A"},
        {"measure": "Revenue", "unit": "USD", "page": "B"},
    ])["status"] == "pass"
    assert cross_page_metric_units(None)["status"] == "unknown"


def test_mixed_without_proof_is_unknown_not_fail() -> None:
    """U7: mixed explicit/inherited with unknown effective needs render evidence."""
    mixed = [
        {"cohort": "slicer/header.textSize", "visual": "a", "page": "P1", "value": None},
        {"cohort": "slicer/header.textSize", "visual": "b", "page": "P2", "value": 11},
    ]
    result = format_declaration_consistency(mixed)
    assert result["status"] == "unknown"
    assert "needs_render_evidence" in result["evidence"]["reason"]
    assert result["evidence"]["pending"][0]["kind"] == "mixed_declaration"
    assert result["evidence"]["conflicts"] == []


def test_divergent_declarations_fail() -> None:
    divergent = [
        {"cohort": "card/label.fontSize", "visual": "a", "page": "P1", "value": 10},
        {"cohort": "card/label.fontSize", "visual": "b", "page": "P1", "value": 12},
    ]
    failed = format_declaration_consistency(divergent)
    assert failed["status"] == "fail"
    assert failed["evidence"]["conflicts"][0]["kind"] == "divergent_values"
    assert format_declaration_consistency([
        {"cohort": "slicer/header.textSize", "visual": "a", "page": "P1", "value": 10},
        {"cohort": "slicer/header.textSize", "visual": "b", "page": "P2", "value": 10},
    ])["status"] == "pass"
    assert format_declaration_consistency([
        {"cohort": "slicer/header.textSize", "visual": "a", "page": "P1", "value": None},
        {"cohort": "slicer/header.textSize", "visual": "b", "page": "P2", "value": None},
    ])["status"] == "pass"
    assert format_declaration_consistency(None)["status"] == "unknown"
    assert format_declaration_consistency([])["status"] == "unknown"
    assert format_declaration_consistency([{"cohort": "x"}])["status"] == "unknown"
    assert format_declaration_consistency([
        {"cohort": "x", "visual": "a", "page": "P1", "value": {"nested": 1}},
    ])["status"] == "unknown"
