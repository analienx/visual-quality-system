"""Versioned visual observation policy, ported from PBIPDocumenter PR #12.

These questions are a *review contract*, not an executable design-rule engine.
The independently measured design rules are a separate, future stage.
"""

POLICY_VERSION = "1.0.0"
SURFACES = ("report", "document")
COMMON = (
    "information_hierarchy", "purpose_and_story", "typography_hierarchy",
    "text_legibility", "color_contrast", "palette_consistency", "color_semantics",
    "spacing_and_padding", "alignment_and_grid", "whitespace_balance",
    "density_and_clutter", "clipping_and_overflow", "accessibility",
)
REPORT = COMMON + (
    "chart_type_suitability", "visual_encoding", "axis_tick_density",
    "axis_precision", "axis_title_necessity", "category_label_density",
    "visual_size_for_content", "scrollbars_in_key_visuals", "table_fit",
    "metric_format_and_units", "slicer_usability", "rendered_data_integrity",
)
DOCUMENT = COMMON + (
    "page_margins", "paragraph_spacing", "heading_navigation",
    "table_pagination_and_fit", "figure_size_and_fidelity",
    "figure_caption_and_reference", "page_breaks_and_orphans",
    "header_footer_consistency", "page_numbering", "document_report_consistency",
)
REQUIRED = {"report": REPORT, "document": DOCUMENT}
OPTIONAL = {
    "report": {"axis_tick_density", "axis_precision", "axis_title_necessity",
               "category_label_density", "scrollbars_in_key_visuals", "table_fit",
               "slicer_usability"},
    "document": {"table_pagination_and_fit", "figure_size_and_fidelity",
                 "figure_caption_and_reference", "document_report_consistency"},
}
STATUSES = {"pass", "fail", "not_applicable"}
SEVERITIES = {"critical", "high", "medium", "low"}
CRITERIA = {
    "information_hierarchy": "Can a reader identify the main message, metrics and next action in five seconds?",
    "purpose_and_story": "Does every major graphic answer a distinct business question without contradicting adjacent graphics?",
    "typography_hierarchy": "Are title, section, visual title, label, axis and footnote font sizes consistently differentiated?",
    "text_legibility": "Can all labels and numbers be read at the target viewing size without zoom or truncated text?",
    "color_contrast": "Is foreground/background contrast sufficient for small labels, marks and tables, including pale fills?",
    "palette_consistency": "Does the page use a restrained palette consistent with other pages and the chosen theme?",
    "color_semantics": "Are colors assigned consistently to categories and states; is meaning available without color alone?",
    "spacing_and_padding": "Are inner chart padding, tick-to-title space, card padding and outer gutters sufficient?",
    "alignment_and_grid": "Do peer panels, edges, baselines and card contents align deliberately?",
    "whitespace_balance": "Is empty space intentional rather than caused by unnecessarily tall tables or small charts?",
    "density_and_clutter": "Does data, decoration, legend, gridline and annotation density fit available space?",
    "clipping_and_overflow": "Are any marks, headings, labels, tables, legends or annotations cropped or obscured?",
    "accessibility": "Are labels meaningful and readable, with redundant encoding for states and graphics?",
    "chart_type_suitability": "Does the chosen chart encode its analytical task and actual data distribution?",
    "visual_encoding": "Are comparisons, magnitudes, zero baselines, percentages and color assignments semantically correct?",
    "axis_tick_density": "Are tick counts appropriate to plot width, with distinguishable nonoverlapping labels?",
    "axis_precision": "Do different ticks render distinct values with sensible precision, avoiding repeated 10% or 33.863%?",
    "axis_title_necessity": "Is each axis title useful and short, preserving indispensable units and meaning?",
    "category_label_density": "Are categories legible without unnecessary scrolling or truncated legends?",
    "visual_size_for_content": "Are panels proportionate to actual data, with marks large enough to interpret?",
    "scrollbars_in_key_visuals": "Can essential chart categories and time periods be seen without scrolling?",
    "table_fit": "Do visible table columns, rows, captions and panel width agree without unjustified whitespace?",
    "metric_format_and_units": "Are currencies, percentage points, percentages, abbreviations and decimals correct?",
    "slicer_usability": "Can the viewer understand filters and current selections without a cluttered header?",
    "rendered_data_integrity": "Does each visual display actual data rather than blanks or an error/loading state?",
    "page_margins": "Is content inside consistent printable margins for each page orientation?",
    "paragraph_spacing": "Do line height, paragraph spacing and keep-with-next form readable text blocks?",
    "heading_navigation": "Are heading levels, numbering and section titles consistent across page breaks?",
    "table_pagination_and_fit": "Are tables legible, with aligned columns, no split headers and repeating headings?",
    "figure_size_and_fidelity": "Are report captures, diagrams, M/DAX and schema figures readable at Word page size?",
    "figure_caption_and_reference": "Do figures have accurate captions, numbering and references near their first mention?",
    "page_breaks_and_orphans": "Are headings, captions and content free from orphans or clipped breaks?",
    "header_footer_consistency": "Are repeated headers/footers within bounds, aligned and free of collisions?",
    "page_numbering": "Are page numbers present, correctly ordered and consistent across sections?",
    "document_report_consistency": "Do embedded figures and inventories describe the same report revision and fields?",
}
assert set(REPORT + DOCUMENT) == set(CRITERIA), "Each observation needs a criterion"


def required_criteria(kind: str) -> tuple[str, ...]:
    """Return the complete criterion set for a surface; reject unknown kinds."""
    if kind not in REQUIRED:
        raise ValueError(f"Unsupported review surface: {kind}")
    return REQUIRED[kind]
