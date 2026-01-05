"""@fileoverview OCR-free spacing repair using Docling word/char cells."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import statistics

from docling_core.types.doc import TableItem
from docling_core.types.doc.base import BoundingBox, CoordOrigin
from docling_core.types.doc.page import TextCellUnit
from docling_parse.pdf_parser import DoclingPdfParser, PdfDocument

from audit_utils import needs_spacing_fix


@dataclass(frozen=True)
class SpacingFixReport:
    table_cells: int
    text_items: int
    pages_processed: int


def _median(values: Iterable[float], default: float = 1.0) -> float:
    values = list(values)
    if not values:
        return default
    return statistics.median(values)


def _gap_threshold(
    gaps: list[float],
    *,
    median_char_width: float,
    fallback_ratio: float,
) -> float:
    if len(gaps) < 2:
        return median_char_width * fallback_ratio

    c1, c2 = min(gaps), max(gaps)
    for _ in range(8):
        cluster1 = [g for g in gaps if abs(g - c1) <= abs(g - c2)]
        cluster2 = [g for g in gaps if abs(g - c1) > abs(g - c2)]
        new_c1 = statistics.mean(cluster1) if cluster1 else c1
        new_c2 = statistics.mean(cluster2) if cluster2 else c2
        if abs(new_c1 - c1) < 1e-3 and abs(new_c2 - c2) < 1e-3:
            break
        c1, c2 = new_c1, new_c2

    if not cluster1 or not cluster2:
        return median_char_width * fallback_ratio

    if abs(c2 - c1) < median_char_width * 0.3:
        return median_char_width * fallback_ratio

    return (c1 + c2) / 2


def _bbox_to_bottom_left(bbox: BoundingBox, page_height: float) -> BoundingBox:
    if bbox.coord_origin is CoordOrigin.BOTTOMLEFT:
        return bbox
    return bbox.to_bottom_left_origin(page_height)


def _collect_words_in_bbox(
    page, bbox_bl: BoundingBox, *, ios: float
) -> list[tuple[str, BoundingBox]]:
    words = page.get_cells_in_bbox(TextCellUnit.WORD, bbox_bl, ios=ios)
    page_height = page.dimension.height
    out: list[tuple[str, BoundingBox]] = []
    for word in words:
        if not word.text:
            continue
        word_bbox = word.rect.to_bounding_box().to_top_left_origin(page_height)
        out.append((word.text, word_bbox))
    return out


def _collect_chars_in_bbox(
    page, bbox_bl: BoundingBox, *, ios: float
) -> list[tuple[str, BoundingBox]]:
    chars = page.get_cells_in_bbox(TextCellUnit.CHAR, bbox_bl, ios=ios)
    page_height = page.dimension.height
    out: list[tuple[str, BoundingBox]] = []
    for ch in chars:
        if not ch.text:
            continue
        ch_bbox = ch.rect.to_bounding_box().to_top_left_origin(page_height)
        out.append((ch.text, ch_bbox))
    return out


def _reconstruct_from_words(
    words: list[tuple[str, BoundingBox]],
    *,
    gap_ratio: float,
    line_ratio: float,
) -> str:
    if not words:
        return ""

    heights = [bbox.height for _text, bbox in words]
    line_tol = _median(heights) * line_ratio

    words.sort(key=lambda item: ((item[1].t + item[1].b) / 2, item[1].l))

    lines: list[dict[str, object]] = []
    for text, bbox in words:
        y_center = (bbox.t + bbox.b) / 2
        if not lines or abs(y_center - lines[-1]["y"]) > line_tol:
            lines.append({"y": y_center, "words": []})
        lines[-1]["words"].append((bbox.l, text, bbox))

    line_texts: list[str] = []
    for line in lines:
        items = sorted(line["words"], key=lambda item: item[0])
        char_widths = [bbox.width / max(len(text), 1) for _x, text, bbox in items]
        median_char_width = _median(char_widths)
        gaps = []
        for idx in range(1, len(items)):
            gap = items[idx][2].l - items[idx - 1][2].r
            if gap >= 0:
                gaps.append(gap)
        gap_threshold = _gap_threshold(
            gaps,
            median_char_width=median_char_width,
            fallback_ratio=gap_ratio,
        )
        out = ""
        prev_bbox: Optional[BoundingBox] = None
        for _x, text, bbox in items:
            if prev_bbox is None:
                out += text
            else:
                gap = bbox.l - prev_bbox.r
                if gap > gap_threshold:
                    out += " " + text
                else:
                    out += text
            prev_bbox = bbox
        if out.strip():
            line_texts.append(out.strip())

    return " ".join(line_texts).strip()


def _reconstruct_from_chars(
    chars: list[tuple[str, BoundingBox]],
    *,
    gap_ratio: float,
    line_ratio: float,
    space_width_ratio: float,
) -> str:
    if not chars:
        return ""

    heights = [bbox.height for _text, bbox in chars]
    line_tol = _median(heights) * line_ratio

    chars.sort(key=lambda item: ((item[1].t + item[1].b) / 2, item[1].l))

    lines: list[dict[str, object]] = []
    for text, bbox in chars:
        y_center = (bbox.t + bbox.b) / 2
        if not lines or abs(y_center - lines[-1]["y"]) > line_tol:
            lines.append({"y": y_center, "chars": []})
        lines[-1]["chars"].append((bbox.l, text, bbox))

    line_texts: list[str] = []
    for line in lines:
        items = sorted(line["chars"], key=lambda item: item[0])
        non_space_widths = [bbox.width for _x, text, bbox in items if not text.isspace()]
        median_char_width = _median(non_space_widths)
        gaps = []
        for idx in range(1, len(items)):
            gap = items[idx][2].l - items[idx - 1][2].r
            if gap >= 0:
                gaps.append(gap)
        gap_threshold = _gap_threshold(
            gaps,
            median_char_width=median_char_width,
            fallback_ratio=gap_ratio,
        )

        out = ""
        prev_bbox: Optional[BoundingBox] = None
        pending_space = False
        pending_space_width = 0.0
        for _x, text, bbox in items:
            if text.isspace():
                pending_space = True
                pending_space_width = max(pending_space_width, bbox.width)
                continue
            if prev_bbox is None:
                if pending_space and pending_space_width >= median_char_width * space_width_ratio:
                    out += " "
                pending_space = False
                pending_space_width = 0.0
                out += text
                prev_bbox = bbox
                continue
            if pending_space:
                if pending_space_width >= median_char_width * space_width_ratio:
                    out += " "
                pending_space = False
                pending_space_width = 0.0
            else:
                gap = bbox.l - prev_bbox.r
                if gap > gap_threshold:
                    out += " "
            out += text
            prev_bbox = bbox

        if out.strip():
            line_texts.append(out.strip())

    return " ".join(line_texts).strip()


def fix_spaced_items_with_word_cells(
    doc,
    pdf_path: Path,
    *,
    pages_to_fix: Optional[set[int]] = None,
    ios: float = 0.2,
    gap_ratio: float = 0.35,
    line_ratio: float = 0.6,
    space_width_ratio: float = 0.6,
) -> SpacingFixReport:
    """Repair spaced-out text using Docling word/char cells within item bounds."""
    if pages_to_fix is not None and not pages_to_fix:
        return SpacingFixReport(0, 0, 0)

    parser = DoclingPdfParser(loglevel="fatal")
    dp_doc: PdfDocument = parser.load(path_or_stream=str(pdf_path))

    if pages_to_fix is None:
        pages_to_fix = set(doc.pages.keys())

    page_cache: dict[int, object] = {}

    def get_page(page_no: int):
        if page_no not in page_cache:
            page_cache[page_no] = dp_doc.get_page(page_no)
        return page_cache[page_no]

    table_replaced = 0
    text_replaced = 0

    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            page_no = item.prov[0].page_no if item.prov else None
            if page_no is None or page_no not in pages_to_fix:
                continue
            page = get_page(page_no)
            for cell in item.data.table_cells:
                if cell.bbox is None or not needs_spacing_fix(cell.text):
                    continue
                bbox_bl = _bbox_to_bottom_left(cell.bbox, page.dimension.height)
                words = _collect_words_in_bbox(page, bbox_bl, ios=ios)
                reconstructed = _reconstruct_from_words(
                    words, gap_ratio=gap_ratio, line_ratio=line_ratio
                )
                if reconstructed and not needs_spacing_fix(reconstructed):
                    cell.text = reconstructed
                    table_replaced += 1
                    continue

                chars = _collect_chars_in_bbox(page, bbox_bl, ios=ios)
                reconstructed = _reconstruct_from_chars(
                    chars,
                    gap_ratio=gap_ratio,
                    line_ratio=line_ratio,
                    space_width_ratio=space_width_ratio,
                )
                if reconstructed and not needs_spacing_fix(reconstructed):
                    cell.text = reconstructed
                    table_replaced += 1
        else:
            text = getattr(item, "text", None)
            if not text or not needs_spacing_fix(text):
                continue
            if not getattr(item, "prov", None):
                continue
            page_no = item.prov[0].page_no
            if page_no is None or page_no not in pages_to_fix:
                continue
            page = get_page(page_no)
            bbox = item.prov[0].bbox
            if bbox is None:
                continue
            bbox_bl = _bbox_to_bottom_left(bbox, page.dimension.height)
            chars = _collect_chars_in_bbox(page, bbox_bl, ios=ios)
            reconstructed = _reconstruct_from_chars(
                chars,
                gap_ratio=gap_ratio,
                line_ratio=line_ratio,
                space_width_ratio=space_width_ratio,
            )
            if reconstructed and not needs_spacing_fix(reconstructed):
                item.text = reconstructed
                text_replaced += 1

    return SpacingFixReport(
        table_cells=table_replaced,
        text_items=text_replaced,
        pages_processed=len(pages_to_fix),
    )
