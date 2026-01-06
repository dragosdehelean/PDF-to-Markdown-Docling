"""@fileoverview Remove stray date-only text inside picture regions."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from docling_core.types.doc import TableItem
from docling_core.types.doc.base import BoundingBox, CoordOrigin
from docling_core.types.doc.document import PictureItem


_DATE_ONLY_PATTERN = re.compile(r"^\d{2}[./-]\d{2}[./-]\d{4}$")


def _bbox_to_top_left(bbox: BoundingBox, page_height: Optional[float]) -> BoundingBox:
    if bbox.coord_origin is CoordOrigin.TOPLEFT or page_height is None:
        return bbox
    return bbox.to_top_left_origin(page_height)


def _bbox_area(bbox: BoundingBox) -> float:
    width = max(0.0, bbox.r - bbox.l)
    height = max(0.0, bbox.b - bbox.t)
    return width * height


def _bbox_intersection_area(a: BoundingBox, b: BoundingBox) -> float:
    left = max(a.l, b.l)
    right = min(a.r, b.r)
    top = max(a.t, b.t)
    bottom = min(a.b, b.b)
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    return width * height


def _overlap_ratio(a: BoundingBox, b: BoundingBox) -> float:
    area_a = _bbox_area(a)
    if area_a <= 0:
        return 0.0
    return _bbox_intersection_area(a, b) / area_a


def _date_only(text: str) -> bool:
    return bool(_DATE_ONLY_PATTERN.match(text.strip()))


def remove_date_only_text_inside_pictures(doc, *, overlap_ratio: float = 0.6) -> int:
    """Remove date-only text items that sit inside picture regions."""
    pictures_by_page: dict[int, list[BoundingBox]] = {}
    for item, _level in doc.iterate_items():
        if not isinstance(item, PictureItem):
            continue
        if not item.prov:
            continue
        page_no = item.prov[0].page_no
        bbox = item.prov[0].bbox
        if page_no is None or bbox is None:
            continue
        pictures_by_page.setdefault(page_no, []).append(bbox)

    if not pictures_by_page:
        return 0

    page_heights = {
        page_no: page.size.height
        for page_no, page in doc.pages.items()
        if page.size is not None
    }

    to_delete = []
    for item, _level in doc.iterate_items():
        if isinstance(item, (TableItem, PictureItem)):
            continue
        text = getattr(item, "text", None)
        if not text or not _date_only(text):
            continue
        if not getattr(item, "prov", None):
            continue
        prov = item.prov[0]
        page_no = prov.page_no
        if page_no is None:
            continue
        picture_boxes = pictures_by_page.get(page_no)
        if not picture_boxes:
            continue
        if prov.bbox is None:
            continue
        page_height = page_heights.get(page_no)
        text_bbox = _bbox_to_top_left(prov.bbox, page_height)
        for pic_bbox in picture_boxes:
            aligned_pic = _bbox_to_top_left(pic_bbox, page_height)
            if _overlap_ratio(text_bbox, aligned_pic) >= overlap_ratio:
                to_delete.append(item)
                break

    if not to_delete:
        return 0

    doc.delete_items(node_items=to_delete)
    return len(to_delete)
