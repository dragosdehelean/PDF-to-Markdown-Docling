"""@fileoverview Unit tests for text whitespace normalization."""

from __future__ import annotations

import unittest

from whitespace_fix import normalize_text_whitespace


class WhitespaceFixTests(unittest.TestCase):
    def test_collapses_double_space_between_words(self) -> None:
        # Arrange
        value = "foo  bar"

        # Act
        result = normalize_text_whitespace(value)

        # Assert
        self.assertEqual(result, "foo bar")

    def test_collapses_tabs_between_words(self) -> None:
        # Arrange
        value = "foo\t\tbar"

        # Act
        result = normalize_text_whitespace(value)

        # Assert
        self.assertEqual(result, "foo bar")

    def test_preserves_leading_spacing(self) -> None:
        # Arrange
        value = "  foo"

        # Act
        result = normalize_text_whitespace(value)

        # Assert
        self.assertEqual(result, "  foo")

    def test_preserves_trailing_spacing(self) -> None:
        # Arrange
        value = "foo  "

        # Act
        result = normalize_text_whitespace(value)

        # Assert
        self.assertEqual(result, "foo  ")


if __name__ == "__main__":
    unittest.main()
