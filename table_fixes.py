"""@fileoverview OCR-based table repair utilities."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from docling_core.types.doc import TableItem

from audit_utils import is_spaced_text


def _table_page_no(table: TableItem) -> int | None:
    if not table.prov:
        return None
    return table.prov[0].page_no


def _tables_by_page(items: Iterable[TableItem]) -> dict[int, list[TableItem]]:
    pages: dict[int, list[TableItem]] = defaultdict(list)
    for table in items:
        page_no = _table_page_no(table)
        if page_no is None:
            continue
        pages[page_no].append(table)
    return pages


def _table_cells_by_key(table: TableItem) -> dict[tuple[int, int, int, int], str]:
    mapping: dict[tuple[int, int, int, int], str] = {}
    for cell in table.data.table_cells:
        key = (
            cell.start_row_offset_idx,
            cell.end_row_offset_idx,
            cell.start_col_offset_idx,
            cell.end_col_offset_idx,
        )
        mapping[key] = cell.text
    return mapping


def _bbox_area(bbox) -> float:
    width = max(0.0, bbox.r - bbox.l)
    height = max(0.0, bbox.b - bbox.t)
    return width * height


def _bbox_intersection_area(a, b) -> float:
    left = max(a.l, b.l)
    right = min(a.r, b.r)
    top = max(a.t, b.t)
    bottom = min(a.b, b.b)
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    return width * height


def _collect_cells_by_page(items: Iterable[TableItem]) -> dict[int, list[tuple[object, str]]]:
    pages: dict[int, list[tuple[object, str]]] = defaultdict(list)
    for table in items:
        page_no = _table_page_no(table)
        if page_no is None:
            continue
        for cell in table.data.table_cells:
            if cell.bbox is None:
                continue
            pages[page_no].append((cell.bbox, cell.text))
    return pages


def merge_spaced_table_cells(
    base_doc, ocr_doc, *, ratio_only: bool = False
) -> tuple[int, int]:
    """Replace spaced table cells with OCR counterparts when available."""
    base_tables = [item for item, _ in base_doc.iterate_items() if isinstance(item, TableItem)]
    ocr_tables = [item for item, _ in ocr_doc.iterate_items() if isinstance(item, TableItem)]

    base_by_page = _tables_by_page(base_tables)
    ocr_by_page = _tables_by_page(ocr_tables)

    replaced = 0
    total_spaced = 0

    for base_table in base_tables:
        for cell in base_table.data.table_cells:
            if is_spaced_text(cell.text):
                total_spaced += 1

    if ratio_only:
        return replaced, total_spaced

    for page_no, base_page_tables in base_by_page.items():
        ocr_page_tables = ocr_by_page.get(page_no, [])
        if not ocr_page_tables:
            continue

        used = set()
        for base_table in base_page_tables:
            match_idx = None
            for idx, ocr_table in enumerate(ocr_page_tables):
                if idx in used:
                    continue
                if (
                    base_table.data.num_rows == ocr_table.data.num_rows
                    and base_table.data.num_cols == ocr_table.data.num_cols
                ):
                    match_idx = idx
                    break
            if match_idx is None:
                continue
            used.add(match_idx)
            ocr_table = ocr_page_tables[match_idx]

            ocr_cells = _table_cells_by_key(ocr_table)
            for cell in base_table.data.table_cells:
                if not is_spaced_text(cell.text):
                    continue
                key = (
                    cell.start_row_offset_idx,
                    cell.end_row_offset_idx,
                    cell.start_col_offset_idx,
                    cell.end_col_offset_idx,
                )
                ocr_text = ocr_cells.get(key, "")
                if ocr_text and not is_spaced_text(ocr_text):
                    cell.text = ocr_text
                    replaced += 1

    # WHY: Some OCR tables cannot be matched by shape; use spatial overlap as fallback.
    ocr_cells_by_page = _collect_cells_by_page(ocr_tables)
    for page_no, base_page_tables in base_by_page.items():
        ocr_cells = ocr_cells_by_page.get(page_no, [])
        if not ocr_cells:
            continue
        for base_table in base_page_tables:
            for cell in base_table.data.table_cells:
                if not is_spaced_text(cell.text):
                    continue
                if cell.bbox is None:
                    continue

                base_area = _bbox_area(cell.bbox)
                if base_area <= 0:
                    continue

                best_text = ""
                best_score = 0.0
                for ocr_bbox, ocr_text in ocr_cells:
                    if not ocr_text or is_spaced_text(ocr_text):
                        continue
                    inter_area = _bbox_intersection_area(cell.bbox, ocr_bbox)
                    if inter_area <= 0:
                        continue
                    ocr_area = _bbox_area(ocr_bbox)
                    if ocr_area <= 0:
                        continue
                    base_cover = inter_area / base_area
                    ocr_cover = inter_area / ocr_area
                    if base_cover < 0.5 or ocr_cover < 0.15:
                        continue
                    score = base_cover * 0.7 + ocr_cover * 0.3
                    if score > best_score:
                        best_score = score
                        best_text = ocr_text

                if best_text:
                    cell.text = best_text
                    replaced += 1

    return replaced, total_spaced
