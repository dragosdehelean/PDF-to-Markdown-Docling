"""@fileoverview Unit tests for text normalization helpers."""

from __future__ import annotations

import unittest

from pdf_to_markdown_docling.text_normalize import normalize_ligatures, normalize_mojibake_text


class TextNormalizeTests(unittest.TestCase):
    def test_normalize_mojibake_text_repairs_romanian(self) -> None:
        # Arrange: "Subvenții" mis-decoded as CP1252/Latin-1.
        value = "SubvenÈ›ii pentru investiÈ›ii"

        # Act
        result = normalize_mojibake_text(value)

        # Assert
        self.assertEqual(result, "Subvenții pentru investiții")

    def test_normalize_mojibake_text_keeps_clean_text(self) -> None:
        # Arrange
        value = "Analiza rezultatelor financiare"

        # Act
        result = normalize_mojibake_text(value)

        # Assert
        self.assertEqual(result, value)

    def test_normalize_ligatures_replaces_fi(self) -> None:
        # Arrange
        value = "Proﬁtul și ﬁnanciare"

        # Act
        result = normalize_ligatures(value)

        # Assert
        self.assertEqual(result, "Profitul și financiare")


if __name__ == "__main__":
    unittest.main()
