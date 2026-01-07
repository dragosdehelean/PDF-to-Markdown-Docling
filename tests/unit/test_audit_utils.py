"""@fileoverview Unit tests for audit spacing helpers."""

from __future__ import annotations

import unittest

from audit_utils import (
    _is_toc_like_table,
    is_multi_space_text,
    is_spaced_text,
    needs_spacing_fix,
    needs_table_spacing_fix,
)
from docling_core.types.doc.document import TableCell, TableData, TableItem


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

    def test_spaced_number_in_label_is_not_spaced_text(self) -> None:
        # Arrange
        value = "T1 2025 rezultate"

        # Act
        result = is_spaced_text(value)

        # Assert
        self.assertFalse(result)

    def test_common_single_letter_sequence_is_not_spaced_text(self) -> None:
        # Arrange
        value = "Într-o a doua etapă"

        # Act
        result = is_spaced_text(value)

        # Assert
        self.assertFalse(result)

    def test_detects_toc_like_table(self) -> None:
        # Arrange
        cells = []
        for row_idx in range(6):
            cells.append(
                TableCell(
                    start_row_offset_idx=row_idx,
                    end_row_offset_idx=row_idx + 1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text=f"Section {row_idx + 1}",
                )
            )
            cells.append(
                TableCell(
                    start_row_offset_idx=row_idx,
                    end_row_offset_idx=row_idx + 1,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text=str(row_idx + 1),
                )
            )
        table = TableItem(self_ref="#/tables/1", data=TableData(table_cells=cells, num_rows=6, num_cols=2))

        # Act
        result = _is_toc_like_table(table)

        # Assert
        self.assertTrue(result)

    def test_non_toc_two_column_table_is_not_toc(self) -> None:
        # Arrange
        cells = [
            TableCell(
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=0,
                end_col_offset_idx=1,
                text="Total active",
            ),
            TableCell(
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=1,
                end_col_offset_idx=2,
                text="RON 418.244.920",
            ),
        ]
        table = TableItem(self_ref="#/tables/2", data=TableData(table_cells=cells, num_rows=1, num_cols=2))

        # Act
        result = _is_toc_like_table(table)

        # Assert
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
