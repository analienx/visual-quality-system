"""Explicit product/component release scopes.

Power BI is the primary VQS component.  DOCX/Word is an optional,
independently gated component.  The legacy combined profile remains
strictly backward-compatible for existing acceptance records.

These profiles specify *required evidence*, not a way to bypass the
independent reviewer, producer capability or owner promotion checks.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseScope:
    name: str
    min_pbip: int
    min_docx: int
    allowed_kinds: frozenset[str]
    coverage_pairs: frozenset[tuple[str, str]]
    required_negatives: frozenset[str]


_PBI_NEGATIVES = frozenset({
    "stale_image", "wrong_pid", "blank_first_open", "partial_canvas",
    "empty_model", "hallucinated_defect", "hidden_fifth_bar",
    "broken_slicer", "false_agent_approval",
})
_WORD_NEGATIVES = frozenset({
    "stale_image", "missing_word_font", "narrative_mismatch",
    "false_agent_approval",
})

POWERBI_CORE = ReleaseScope(
    name="powerbi-core",
    min_pbip=2,
    min_docx=0,
    allowed_kinds=frozenset({"pbip"}),
    coverage_pairs=frozenset({
        ("G0", "pbip"), ("G1", "pbip"), ("G2", "pbip"),
        ("G3", "pbip"), ("G4", "pbip"),
    }),
    required_negatives=_PBI_NEGATIVES,
)

WORD_DOCX = ReleaseScope(
    name="word-docx",
    min_pbip=0,
    min_docx=1,
    allowed_kinds=frozenset({"docx"}),
    coverage_pairs=frozenset({
        ("G0", "docx"), ("G1", "docx"), ("G5", "docx"),
    }),
    required_negatives=_WORD_NEGATIVES,
)

COMBINED_LEGACY = ReleaseScope(
    name="combined",
    min_pbip=2,
    min_docx=1,
    allowed_kinds=frozenset({"pbip", "docx"}),
    coverage_pairs=POWERBI_CORE.coverage_pairs | WORD_DOCX.coverage_pairs,
    required_negatives=_PBI_NEGATIVES | _WORD_NEGATIVES,
)

RELEASE_SCOPES = {
    scope.name: scope for scope in (POWERBI_CORE, WORD_DOCX, COMBINED_LEGACY)
}


def suite_subject_digest(subjects: list[dict[str, str]],
                         scope: ReleaseScope) -> object:
    """Return a canonical domain-separated digest input.

    The legacy combined release intentionally retains its historical
    subject-only digest. Scoped suites bind the scope name so a Word
    reviewer receipt cannot be replayed as Power BI release evidence.
    """
    ordered = sorted(subjects, key=lambda subject: subject["id"])
    if scope.name == "combined":
        return ordered
    return {"release_scope": scope.name, "subjects": ordered}
