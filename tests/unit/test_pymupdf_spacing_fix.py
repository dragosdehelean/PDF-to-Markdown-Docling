"""@fileoverview Unit tests for PyMuPDF spacing heuristics."""

from __future__ import annotations

import unittest

from pdf_to_markdown_docling.pymupdf_spacing_fix import _needs_suffix_completion, _should_replace_text


class PyMuPdfSpacingFixTests(unittest.TestCase):
    def test_suffix_completion_flags_truncated_word(self) -> None:
        # Arrange
        value = "cheltuiel"

        # Act
        result = _needs_suffix_completion(value)

        # Assert
        self.assertTrue(result)

    def test_should_replace_when_new_extends_word(self) -> None:
        # Arrange
        old = "cheltuiel"
        new = "cheltuieli"

        # Act
        result = _should_replace_text(old, new, table_mode=True)

        # Assert
        self.assertTrue(result)

    def test_should_replace_when_new_extends_phrase(self) -> None:
        # Arrange
        old = "11.10. Alte cheltuiel"
        new = "11.10. Alte cheltuieli"

        # Act
        result = _should_replace_text(old, new, table_mode=True)

        # Assert
        self.assertTrue(result)

    def test_suffix_completion_handles_phrase_tokens(self) -> None:
        # Arrange
        value = "11.10. Alte cheltuiel"

        # Act
        result = _needs_suffix_completion(value)

        # Assert
        self.assertTrue(result)

    def test_should_replace_when_tokens_reduce(self) -> None:
        # Arrange
        old = "Vi t e z a de ro t a ț ie a a ct i v e l or"
        new = "Viteza de rotație a activelor"

        # Act
        result = _should_replace_text(old, new, table_mode=True)

        # Assert
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
