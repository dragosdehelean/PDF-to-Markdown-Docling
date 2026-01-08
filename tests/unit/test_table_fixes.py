"""@fileoverview Unit tests for table column-group collapsing helpers."""

from __future__ import annotations

import unittest

from docling_core.types.doc.document import TableCell, TableData, TableItem

from pdf_to_markdown_docling.table_fixes import (
    collapse_table_header_groups,
    normalize_table_header_text,
    normalize_table_currency_columns,
    _clean_table_cell_text,
    _is_suspect_currency_cell,
    _should_replace_numeric_cell,
)


def _build_sample_table() -> TableItem:
    cells = [
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            text="Indicatori",
            column_header=True,
        ),
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=1,
            end_col_offset_idx=3,
            text="30/09/2025",
            column_header=True,
            col_span=2,
        ),
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=3,
            end_col_offset_idx=5,
            text="30/09/2024",
            column_header=True,
            col_span=2,
        ),
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=5,
            end_col_offset_idx=7,
            text="30/09/2025",
            column_header=True,
            col_span=2,
        ),
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=7,
            end_col_offset_idx=9,
            text="30/09/2024",
            column_header=True,
            col_span=2,
        ),
        TableCell(
            start_row_offset_idx=0,
            end_row_offset_idx=1,
            start_col_offset_idx=9,
            end_col_offset_idx=10,
            text="Delta%",
            column_header=True,
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=0,
            end_col_offset_idx=1,
            text="CIFRA",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=1,
            end_col_offset_idx=2,
            text="RON",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=2,
            end_col_offset_idx=3,
            text="158.065.856",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=3,
            end_col_offset_idx=4,
            text="RON",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=4,
            end_col_offset_idx=5,
            text="126.792.531",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=5,
            end_col_offset_idx=6,
            text="EUR",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=6,
            end_col_offset_idx=7,
            text="36.549.554",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=7,
            end_col_offset_idx=8,
            text="EUR",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=8,
            end_col_offset_idx=9,
            text="29.318.226",
        ),
        TableCell(
            start_row_offset_idx=1,
            end_row_offset_idx=2,
            start_col_offset_idx=9,
            end_col_offset_idx=10,
            text="24,66%",
        ),
    ]

    data = TableData(table_cells=cells, num_rows=2, num_cols=10)
    return TableItem(self_ref="#/tables/1", data=data)


def _cell_text(table: TableItem, row: int, col: int) -> str:
    for cell in table.data.table_cells:
        if (
            cell.start_row_offset_idx == row
            and cell.start_col_offset_idx == col
            and cell.end_row_offset_idx == row + 1
        ):
            return cell.text
    return ""


class TableFixesTests(unittest.TestCase):
    def test_collapse_reports_change(self) -> None:
        # Arrange
        table = _build_sample_table()

        # Act
        changed = collapse_table_header_groups(table)

        # Assert
        self.assertTrue(changed)

    def test_collapse_reduces_column_count(self) -> None:
        # Arrange
        table = _build_sample_table()

        # Act
        collapse_table_header_groups(table)

        # Assert
        self.assertEqual(table.data.num_cols, 6)

    def test_collapse_merges_currency_value(self) -> None:
        # Arrange
        table = _build_sample_table()

        # Act
        collapse_table_header_groups(table)

        # Assert
        self.assertEqual(_cell_text(table, 1, 1), "RON 158.065.856")

    def test_collapse_preserves_first_column(self) -> None:
        # Arrange
        table = _build_sample_table()

        # Act
        collapse_table_header_groups(table)

        # Assert
        self.assertEqual(_cell_text(table, 1, 0), "CIFRA")

    def test_header_normalization_deduplicates_words(self) -> None:
        # Arrange
        table = _build_sample_table()
        table.data.table_cells[0].text = "Indicatori Indicatori"

        # Act
        normalize_table_header_text(table)

        # Assert
        self.assertEqual(table.data.table_cells[0].text, "Indicatori")

    def test_header_normalization_keeps_last_date(self) -> None:
        # Arrange
        table = _build_sample_table()
        table.data.table_cells[1].text = "31.12.202230/09/2024"

        # Act
        normalize_table_header_text(table)

        # Assert
        self.assertEqual(table.data.table_cells[1].text, "30/09/2024")

    def test_header_normalization_strips_leading_digits(self) -> None:
        # Arrange
        table = _build_sample_table()
        table.data.table_cells[1].text = "3130/09/2025"
        table.data.table_cells[2].text = "202231/12/2024"
        table.data.table_cells[3].text = "31.12.230/09/2025"
        table.data.table_cells[4].text = "02131/12/2024"

        # Act
        normalize_table_header_text(table)

        # Assert
        self.assertEqual(table.data.table_cells[1].text, "30/09/2025")
        self.assertEqual(table.data.table_cells[2].text, "31/12/2024")
        self.assertEqual(table.data.table_cells[3].text, "30/09/2025")
        self.assertEqual(table.data.table_cells[4].text, "31/12/2024")

    def test_clean_table_cell_text_dedup_percent(self) -> None:
        # Arrange
        value = "84 % 84 %"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "84%")

    def test_clean_table_cell_text_removes_duplicate_group(self) -> None:
        # Arrange
        value = "42 42.916.476"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "42.916.476")

    def test_clean_table_cell_text_merges_leading_group(self) -> None:
        # Arrange
        value = "1 234.567"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "1.234.567")

    def test_clean_table_cell_text_normalizes_delta_percent(self) -> None:
        # Arrange
        value = "ƒ^+%"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "Δ%")

    def test_clean_table_cell_text_strips_currency_prefix_dup(self) -> None:
        # Arrange
        value = "78. RON 78.947.449"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 78.947.449")

    def test_clean_table_cell_text_strips_currency_prefix_dup_with_decimals(self) -> None:
        # Arrange
        value = "15.53 EUR 15.537.472"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "EUR 15.537.472")

    def test_clean_table_cell_text_strips_trailing_currency_fragment(self) -> None:
        # Arrange
        value = "16. EUR 16.559.155 R"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "EUR 16.559.155")

    def test_clean_table_cell_text_strips_trailing_currency_fragment_n(self) -> None:
        # Arrange
        value = "RON 418.244.920 N"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 418.244.920")

    def test_clean_table_cell_text_normalizes_currency_suffix(self) -> None:
        # Arrange
        value = "168.506.901 RON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 168.506.901")

    def test_clean_table_cell_text_fixes_missing_currency_letter(self) -> None:
        # Arrange
        value = "168.506.901 ON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 168.506.901")

    def test_clean_table_cell_text_removes_internal_number_spaces(self) -> None:
        # Arrange
        value = "139.369. 058"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "139.369.058")

    def test_clean_table_cell_text_dedupes_repeated_currency_value(self) -> None:
        # Arrange
        value = "153.689.723 RON 153.689.723 RON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 153.689.723")

    def test_clean_table_cell_text_strips_extra_prefix_value(self) -> None:
        # Arrange
        value = "16 RON 164.980.067 RON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 164.980.067")

    def test_clean_table_cell_text_strips_trailing_on_fragment(self) -> None:
        # Arrange
        value = "RON 78.947.449 ON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 78.947.449")

    def test_clean_table_cell_text_strips_duplicate_currency_suffix(self) -> None:
        # Arrange
        value = "RON 139.369. 058 RON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 139.369.058")

    def test_clean_table_cell_text_fixes_on_middle_pattern(self) -> None:
        # Arrange
        value = "126.39 ON 126.397.863 RON"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 126.397.863")

    def test_clean_table_cell_text_fixes_negative_space(self) -> None:
        # Arrange
        value = "- 45,40%"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "-45,40%")

    def test_clean_table_cell_text_fixes_ro_currency_token(self) -> None:
        # Arrange
        value = "7 RO 133.339.798 R"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "RON 133.339.798")

    def test_clean_table_cell_text_compacts_paren_spacing(self) -> None:
        # Arrange
        value = "EUR ( 420 )"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "EUR (420)")

    def test_clean_table_cell_text_dedupes_dates(self) -> None:
        # Arrange
        value = "31/12/20 31/12/2024"

        # Act
        result = _clean_table_cell_text(value)

        # Assert
        self.assertEqual(result, "31/12/2024")

    def test_clean_table_cell_text_strips_square_brackets(self) -> None:
        value = "RON 471.371]"
        result = _clean_table_cell_text(value)
        self.assertEqual(result, "RON 471.371")

    def test_clean_table_cell_text_strips_currency_trailing_short_token(self) -> None:
        value = "115.784.991 RON 7"
        result = _clean_table_cell_text(value)
        self.assertEqual(result, "RON 115.784.991")

    def test_normalize_table_currency_columns_aligns_mismatch(self) -> None:
        table = _build_sample_table()
        # Add extra data rows to build a dominant currency per column.
        base_row = [
            ("ALT RAND", 0),
            ("RON", 1),
            ("1.000.000", 2),
            ("RON", 3),
            ("900.000", 4),
            ("EUR", 5),
            ("200.000", 6),
            ("EUR", 7),
            ("180.000", 8),
            ("10,00%", 9),
        ]
        for row_idx in (2, 3, 4):
            for text, col in base_row:
                table.data.table_cells.append(
                    TableCell(
                        start_row_offset_idx=row_idx,
                        end_row_offset_idx=row_idx + 1,
                        start_col_offset_idx=col,
                        end_col_offset_idx=col + 1,
                        text=text,
                    )
                )
        table.data.num_rows = 5
        collapse_table_header_groups(table)
        # Flip one cell currency in the first numeric column after collapse.
        for cell in table.data.table_cells:
            if cell.start_row_offset_idx == 1 and cell.start_col_offset_idx == 1:
                cell.text = "EUR 158.065.856"
                break
        changed = normalize_table_currency_columns(table)
        self.assertGreater(changed, 0)
        self.assertEqual(_cell_text(table, 1, 1), "RON 158.065.856")

    def test_suspect_currency_cell_detects_leading_dot(self) -> None:
        self.assertTrue(_is_suspect_currency_cell("EUR .961.31"))

    def test_suspect_currency_cell_accepts_grouped_number(self) -> None:
        self.assertFalse(_is_suspect_currency_cell("EUR 6.961.310"))

    def test_should_replace_numeric_cell_adds_leading_digit(self) -> None:
        base = "RON 71.371"
        ocr = "RON 471.371"
        self.assertTrue(_should_replace_numeric_cell(base, ocr))

    def test_should_replace_numeric_cell_rejects_mismatch(self) -> None:
        base = "RON 71.371"
        ocr = "RON 1.371.000"
        self.assertFalse(_should_replace_numeric_cell(base, ocr))

    def test_should_replace_numeric_cell_replaces_invalid_group(self) -> None:
        base = "EUR .961.31"
        ocr = "EUR 6.961.310"
        self.assertTrue(_should_replace_numeric_cell(base, ocr))

    def test_should_replace_numeric_cell_numeric_only(self) -> None:
        base = ".961.31"
        ocr = "6.961.310"
        self.assertTrue(_should_replace_numeric_cell(base, ocr))


if __name__ == "__main__":
    unittest.main()
