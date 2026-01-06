"""@fileoverview Unit tests for date-only text cleanup near pictures."""

from __future__ import annotations

import unittest

from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
from docling_core.types.doc.labels import DocItemLabel

from date_cleanup import remove_date_only_text_inside_pictures


def _prov(page_no: int, bbox: BoundingBox) -> ProvenanceItem:
    return ProvenanceItem(page_no=page_no, bbox=bbox, charspan=(0, 0))


class DateCleanupTests(unittest.TestCase):
    def test_removes_date_inside_picture(self) -> None:
        doc = DoclingDocument(name="test")
        pic_bbox = BoundingBox(l=0, t=0, r=100, b=100)
        doc.add_picture(prov=_prov(1, pic_bbox))

        inside_bbox = BoundingBox(l=10, t=10, r=20, b=20)
        outside_bbox = BoundingBox(l=200, t=200, r=210, b=210)
        doc.add_text(
            label=DocItemLabel.TEXT,
            text="31.12.2024",
            prov=_prov(1, inside_bbox),
        )
        doc.add_text(
            label=DocItemLabel.TEXT,
            text="30.09.2025",
            prov=_prov(1, outside_bbox),
        )

        removed = remove_date_only_text_inside_pictures(doc)

        self.assertEqual(removed, 1)
        remaining = [item.text for item, _ in doc.iterate_items() if hasattr(item, "text")]
        self.assertIn("30.09.2025", remaining)
        self.assertNotIn("31.12.2024", remaining)

    def test_keeps_date_without_picture(self) -> None:
        doc = DoclingDocument(name="test")
        bbox = BoundingBox(l=10, t=10, r=20, b=20)
        doc.add_text(
            label=DocItemLabel.TEXT,
            text="31.12.2024",
            prov=_prov(1, bbox),
        )

        removed = remove_date_only_text_inside_pictures(doc)

        self.assertEqual(removed, 0)
        remaining = [item.text for item, _ in doc.iterate_items() if hasattr(item, "text")]
        self.assertIn("31.12.2024", remaining)


if __name__ == "__main__":
    unittest.main()
