"""@fileoverview Unit tests for PyMuPDF spacing repair helpers."""

from __future__ import annotations

from pymupdf_spacing_fix import _compact_numeric_spacing, _should_replace_text


def test_compact_numeric_spacing() -> None:
    """Ensure numeric spacing is compacted without touching non-numeric text."""
    assert _compact_numeric_spacing("1 58 . 0 6 5 . 85 6") == "158.065.856"
    assert _compact_numeric_spacing("RON 1 2 3") == "RON 1 2 3"


def test_should_replace_table_text_when_spacing_fixed() -> None:
    """Confirm table-mode replacement allows token contraction for split words."""
    old = "1.  Produ cț ia  vâ ndu tă"
    new = "1. Producția vândută"
    assert _should_replace_text(old, new, table_mode=True) is True
