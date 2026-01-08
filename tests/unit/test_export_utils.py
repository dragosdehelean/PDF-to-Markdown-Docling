"""@fileoverview Unit tests for Markdown page marker helpers."""

from __future__ import annotations

import unittest

from pdf_to_markdown_docling.export_utils import (
    add_visible_page_markers,
    reduce_markdown_noise,
    normalize_kpi_blocks,
    remove_axis_like_lines,
    remove_orphan_headings,
)


PAGE_BREAK = "<!-- page break -->"


class ExportUtilsTests(unittest.TestCase):
    def test_single_page_marker_added(self) -> None:
        # Arrange
        markdown = "Hello world"

        # Act
        result = add_visible_page_markers(markdown, PAGE_BREAK)

        # Assert
        self.assertIn("**[Page 1]**", result)

    def test_multi_page_marker_added(self) -> None:
        # Arrange
        markdown = f"First\n\n{PAGE_BREAK}\n\nSecond"

        # Act
        result = add_visible_page_markers(markdown, PAGE_BREAK)

        # Assert
        self.assertIn("**[Page 2]**", result)

    def test_page_break_placeholder_preserved(self) -> None:
        # Arrange
        markdown = f"First\n\n{PAGE_BREAK}\n\nSecond"

        # Act
        result = add_visible_page_markers(markdown, PAGE_BREAK)

        # Assert
        self.assertIn(PAGE_BREAK, result)

    def test_no_double_markers_when_present(self) -> None:
        # Arrange
        markdown = "<!-- page: 1 -->\n\n**[Page 1]**\n\nHello"

        # Act
        result = add_visible_page_markers(markdown, PAGE_BREAK)

        # Assert
        self.assertNotIn("<!-- page: 1 -->", result)
        self.assertIn("**[Page 1]**", result)

    def test_reduce_markdown_noise_removes_image_placeholders(self) -> None:
        # Arrange
        markdown = "[//]: # (page: 1)\n\n<!-- image -->\n\nContent"

        # Act
        result = reduce_markdown_noise(
            markdown, PAGE_BREAK, remove_image_placeholders=True
        )

        # Assert
        self.assertNotIn("<!-- image -->", result)
        self.assertIn("Content", result)

    def test_reduce_markdown_noise_dedupes_repeated_heading(self) -> None:
        # Arrange
        markdown = (
            "[//]: # (page: 1)\n\n## Analiza rezultatelor financiare\n\n## Unic 1\n\n"
            f"{PAGE_BREAK}\n\n"
            "[//]: # (page: 2)\n\n## Analiza rezultatelor financiare\n\n## Unic 2\n\n"
            f"{PAGE_BREAK}\n\n"
            "[//]: # (page: 3)\n\n## Analiza rezultatelor financiare\n\n## Unic 3\n\n"
        )

        # Act
        result = reduce_markdown_noise(markdown, PAGE_BREAK)

        # Assert
        self.assertEqual(result.count("Analiza rezultatelor financiare"), 1)
        self.assertIn("## Unic 2", result)
        self.assertIn("## Unic 3", result)

    def test_normalize_kpi_blocks_merges_label_and_values(self) -> None:
        markdown = (
            "ACTIVE CIRCULANTE\n\n"
            "RON 132,07 MIL. (EUR 25,99 MIL.)\n\n"
            "+14,07% vs 31.12.2024"
        )
        result = normalize_kpi_blocks(markdown, PAGE_BREAK)
        self.assertEqual(
            result,
            "ACTIVE CIRCULANTE RON 132,07 MIL. (EUR 25,99 MIL.) +14,07% vs 31.12.2024",
        )

    def test_remove_orphan_headings_drops_trailing_heading(self) -> None:
        markdown = "Text\n\n## Profit din exploatare\n\n"
        result = remove_orphan_headings(markdown, PAGE_BREAK)
        self.assertEqual(result.strip(), "Text")

    def test_remove_orphan_headings_preserves_heading_with_next_content(self) -> None:
        markdown = (
            "Text\n\n## Profit din exploatare\n\n"
            f"{PAGE_BREAK}\n\n"
            "Continuare text\n\n"
        )
        result = remove_orphan_headings(markdown, PAGE_BREAK)
        self.assertIn("## Profit din exploatare", result)

    def test_remove_orphan_headings_drops_when_next_heading_same_level(self) -> None:
        markdown = (
            "Text\n\n## Profit din exploatare\n\n"
            f"{PAGE_BREAK}\n\n"
            "## Alte sectiuni\n\n"
            "Content\n"
        )
        result = remove_orphan_headings(markdown, PAGE_BREAK)
        self.assertNotIn("## Profit din exploatare", result)

    def test_remove_orphan_headings_skips_page_marker_on_next_page(self) -> None:
        markdown = (
            "Text\n\n## Profit din exploatare\n\n"
            f"{PAGE_BREAK}\n\n"
            "**[Page 2]**\n\n"
            "## Alte sectiuni\n\n"
            "Content\n"
        )
        result = remove_orphan_headings(markdown, PAGE_BREAK)
        self.assertNotIn("## Profit din exploatare", result)

    def test_remove_orphan_headings_drops_on_heading_like_next_line(self) -> None:
        markdown = (
            "Text\n\n## Profit din exploatare\n\n"
            f"{PAGE_BREAK}\n\n"
            "Analiza contului de profit si pierdere la nivel consolidat\n\n"
            "Continuare text.\n"
        )
        result = remove_orphan_headings(markdown, PAGE_BREAK)
        self.assertNotIn("## Profit din exploatare", result)

    def test_remove_axis_like_lines_drops_chart_ticks(self) -> None:
        markdown = (
            "Text\n\n"
            "74% 9L 2025\n\n"
            f"{PAGE_BREAK}\n\n"
            "More text\n"
        )
        result = remove_axis_like_lines(markdown, PAGE_BREAK)
        self.assertNotIn("74% 9L 2025", result)


if __name__ == "__main__":
    unittest.main()
