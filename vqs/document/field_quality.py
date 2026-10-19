"""P21: bounded English Word field-error text triage; no raw text disclosure.

Word can export a structurally complete PDF whose visible field results are
broken. Return only stable rule IDs and counts. Other languages, outlined
glyphs and documents discussing these phrases require human interpretation.
"""
from __future__ import annotations

import re
import unicodedata

FIELD_ERRORS = {
    "word_bookmark_not_defined": re.compile(r"\berror\s*!\s*bookmark\s+not\s+defined\b"),
    "word_reference_source_not_found": re.compile(
        r"\berror\s*!\s*reference\s+source\s+not\s+found\b"),
    "word_toc_entries_not_found": re.compile(
        r"\berror\s*!\s*no\s+table\s+of\s+contents\s+entries\s+found\b"),
}

PLACEHOLDERS = {
    "unconfirmed_owner_or_value": re.compile(r"\[\s*to\s+be\s+confirmed\s*\]"),
    "document_owner_placeholder": re.compile(r"\[\s*document\s+owner\s*\]"),
    "organization_logo_placeholder": re.compile(r"\borg\s+logo\b"),
}


def scan_text(text: str) -> dict:
    """Find known Word field render faults and reviewable placeholders.

    A nonempty 'errors' is objective visible broken-field text, **not** an
    independent adjudication of the entire document. Placeholders are only
    review candidates, never automatically a semantic contradiction.
    """
    if not isinstance(text, str):
        raise TypeError("rendered PDF text must be a string")
    if len(text) > 4_000_000:
        raise ValueError("page text exceeds bounded field-quality scan")
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {
        "errors": {key: len(pattern.findall(normalized))
                   for key, pattern in FIELD_ERRORS.items()
                   if pattern.search(normalized)},
        "placeholders": {key: len(pattern.findall(normalized))
                         for key, pattern in PLACEHOLDERS.items()
                         if pattern.search(normalized)},
    }
