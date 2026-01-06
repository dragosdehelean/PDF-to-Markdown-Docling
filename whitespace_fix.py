"""@fileoverview Normalize excessive whitespace in extracted text items."""

from __future__ import annotations

import re

from docling_core.types.doc import TableItem

from text_normalize import normalize_ligatures, normalize_mojibake_text

_MULTI_SPACE_BETWEEN_TOKENS = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")


def normalize_text_whitespace(text: str) -> str:
    """Collapse repeated spaces/tabs between non-whitespace tokens."""
    return _MULTI_SPACE_BETWEEN_TOKENS.sub(" ", text)


def normalize_document_text_whitespace(doc) -> int:
    """Normalize extra whitespace for non-table text items in a document."""
    updated = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            continue
        text = getattr(item, "text", None)
        if not text:
            continue
        normalized = normalize_text_whitespace(text)
        normalized = normalize_mojibake_text(normalized)
        normalized = normalize_ligatures(normalized)
        if normalized != text:
            item.text = normalized
            updated += 1
    return updated
