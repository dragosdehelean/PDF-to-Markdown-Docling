"""@fileoverview Unit tests for Markdown page marker helpers."""

from __future__ import annotations

import unittest

from export_utils import add_visible_page_markers, reduce_markdown_noise


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


if __name__ == "__main__":
    unittest.main()
