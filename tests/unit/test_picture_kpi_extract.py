"""@fileoverview Unit tests for KPI text detection."""

from __future__ import annotations

import unittest

from picture_kpi_extract import _is_axis_like, _is_kpi_text, _normalize_kpi_caption


class PictureKpiExtractTests(unittest.TestCase):
    def test_kpi_text_with_currency(self) -> None:
        # Arrange
        value = "Cifra de afaceri neta 158.065.856 RON"

        # Act
        result = _is_kpi_text(value)

        # Assert
        self.assertTrue(result)

    def test_kpi_text_with_keyword_and_number(self) -> None:
        # Arrange
        value = "Profit net 43.000.000"

        # Act
        result = _is_kpi_text(value)

        # Assert
        self.assertTrue(result)

    def test_non_kpi_text_without_numbers(self) -> None:
        # Arrange
        value = "Q&A cu CEO"

        # Act
        result = _is_kpi_text(value)

        # Assert
        self.assertFalse(result)

    def test_non_kpi_text_without_currency_or_keyword(self) -> None:
        # Arrange
        value = "Grafic 0 10 20 30 40 50"

        # Act
        result = _is_kpi_text(value)

        # Assert
        self.assertFalse(result)

    def test_non_kpi_text_with_many_numbers(self) -> None:
        # Arrange
        value = "1 2 3 4 5 6 7 8 9 10 11 12 13"

        # Act
        result = _is_kpi_text(value)

        # Assert
        self.assertFalse(result)

    def test_axis_like_chart_is_rejected(self) -> None:
        value = "20 0 40 60 80 9L 2024 9L 2025 mil. RON"
        self.assertTrue(_is_axis_like(value))
        self.assertFalse(_is_kpi_text(value))

    def test_normalize_caption_single_line(self) -> None:
        value = "PROFIT\nNET\nRON\n42,92 MIL.\n(EUR 8,45 MIL.)\n+103,61%\nvs\n9L 2024"
        normalized = _normalize_kpi_caption(value)
        self.assertEqual(
            normalized,
            "PROFIT NET RON 42,92 MIL. (EUR 8,45 MIL.) +103,61% vs 9L 2024",
        )


if __name__ == "__main__":
    unittest.main()
