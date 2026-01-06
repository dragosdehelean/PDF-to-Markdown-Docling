"""@fileoverview Unit tests for audit spacing helpers."""

from __future__ import annotations

import unittest

from audit_utils import (
    is_multi_space_text,
    is_spaced_text,
    needs_spacing_fix,
    needs_table_spacing_fix,
)


class AuditUtilsTests(unittest.TestCase):
    def test_detects_multi_space_between_tokens(self) -> None:
        # Arrange
        value = "foo  bar"

        # Act
        result = is_multi_space_text(value)

        # Assert
        self.assertTrue(result)

    def test_multi_space_is_not_spacing_fix_by_default(self) -> None:
        # Arrange
        value = "foo  bar"

        # Act
        result = needs_spacing_fix(value)

        # Assert
        self.assertFalse(result)

    def test_single_letter_word_is_not_spaced_text(self) -> None:
        # Arrange
        value = "Group a inregistrat rezultate"

        # Act
        result = is_spaced_text(value)

        # Assert
        self.assertFalse(result)

    def test_split_word_is_spaced_text(self) -> None:
        # Arrange
        value = "finan c iar"

        # Act
        result = is_spaced_text(value)

        # Assert
        self.assertTrue(result)

    def test_digit_middle_token_is_not_spaced_text(self) -> None:
        # Arrange
        value = "la 1 martie"

        # Act
        result = is_spaced_text(value)

        # Assert
        self.assertFalse(result)

    def test_table_spacing_ignores_sold_suffix(self) -> None:
        # Arrange
        value = "Sold C"

        # Act
        result = needs_table_spacing_fix(value)

        # Assert
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
