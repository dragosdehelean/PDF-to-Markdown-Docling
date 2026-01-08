"""@fileoverview Table repair utilities (OCR-based and structural fixes)."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Iterable

from docling_core.types.doc import TableItem
from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.document import TableCell

from pdf_to_markdown_docling.audit_utils import is_spaced_text
from pdf_to_markdown_docling.text_normalize import normalize_ligatures, normalize_mojibake_text

_DATE_PATTERN = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
_DATE_FUZZY_PATTERN = re.compile(r"\d{1,3}[./-]\d{1,2}[./-]\d{2,4}")
_DATE_SEP_PATTERN = re.compile(r"[./-]")
_DUP_PERCENT_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%\s+\1\s*%")
_SPACED_PERCENT_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_DUP_GROUP_PATTERN = re.compile(r"\b(\d{1,3})\s+\1((?:\.\d{3}){1,})\b")
_LEADING_GROUP_PATTERN = re.compile(r"\b(\d{1,2})\s+(\d{3}(?:\.\d{3}){1,})\b")
_DELTA_PERCENT_PATTERN = re.compile(r"^(?:ƒ\^\+%|∆\s*%|Δ\s*%)$")
_CURRENCY_PREFIX_DUP_PATTERN = re.compile(
    r"^(\d{1,3}(?:[.,]\d{1,3})?[.,]?)\s+(RON|EUR)\s+(\d{1,3}(?:\.\d{3}){1,})$"
)
_CURRENCY_SUFFIX_PATTERN = re.compile(
    r"^(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+(RON|EUR)$"
)
_CURRENCY_MISSING_R_PATTERN = re.compile(
    r"^(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+ON$"
)
_CURRENCY_REPEAT_PREFIX_PATTERN = re.compile(
    r"^(RON|EUR)\s+(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+\1\s+\2$"
)
_CURRENCY_REPEAT_SUFFIX_PATTERN = re.compile(
    r"^(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+(RON|EUR)\s+\1\s+\2$"
)
_CURRENCY_EXTRA_PREFIX_PATTERN = re.compile(
    r"^(\d{1,3})\s+(RON|EUR)\s+(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+\2$"
)
_CURRENCY_ON_MIDDLE_PATTERN = re.compile(
    r"^(\d{1,3}(?:[.,]\d+)?)\s+ON\s+(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)\s+(RON|EUR)$"
)
_CURRENCY_PREFIX_ONLY_PATTERN = re.compile(
    r"^(\d{1,2})\s+(RON|EUR)\s+(\d{1,3}(?:\.\d{3}){1,}(?:[.,]\d+)?)$"
)
_CURRENCY_RO_TOKEN_PATTERN = re.compile(r"\bRO\b")
_CURRENCY_TOKEN_PATTERN = re.compile(r"\b(RON|EUR)\b")
_NUMBER_TOKEN_PATTERN = re.compile(r"[+-]?\(?[.,]?\d[\d.,]*\)?")
_CURRENCY_TRAILING_SHORT_PATTERN = re.compile(
    r"^(\d{1,3}(?:\.\d{3}){1,})\s+(RON|EUR)\s+(\d{1,2})$"
)
_PARENS_SPACE_OPEN_PATTERN = re.compile(r"\(\s+(?=\d)")
_PARENS_SPACE_CLOSE_PATTERN = re.compile(r"(?<=\d)\s+\)")
_NEGATIVE_SPACE_PATTERN = re.compile(r"(?<!\w)-\s+(?=\d)")


def _is_numericish(text: str) -> bool:
    return bool(re.fullmatch(r"[0-9\s.,()%+A-Z-]+", text.upper()))


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value)


def _extract_currency_number(text: str) -> tuple[str | None, str] | None:
    normalized = " ".join(text.split())
    currencies = set(_CURRENCY_TOKEN_PATTERN.findall(normalized))
    numbers = _NUMBER_TOKEN_PATTERN.findall(normalized)
    numbers = [num for num in numbers if _digits_only(num)]
    if not numbers:
        return None
    if currencies:
        if len(currencies) != 1 or len(numbers) != 1:
            return None
        return next(iter(currencies)), numbers[0]
    if any(ch.isalpha() for ch in normalized):
        return None
    if len(numbers) != 1:
        return None
    return None, numbers[0]


def _normalize_number_token(token: str) -> str:
    cleaned = token.strip().strip("()")
    cleaned = cleaned.lstrip("+-").replace(" ", "")
    return cleaned


def _number_grouping_is_valid(token: str) -> bool:
    normalized = _normalize_number_token(token)
    if not normalized:
        return False
    if normalized[0] in {".", ","} or normalized[-1] in {".", ","}:
        return False
    if "," in normalized and "." in normalized:
        if normalized.rfind(",") > normalized.rfind("."):
            normalized = normalized.split(",", 1)[0]
        else:
            normalized = normalized.replace(",", "")
    elif "," in normalized:
        if normalized.count(",") == 1:
            normalized = normalized.split(",", 1)[0]
        normalized = normalized.replace(",", "")

    if "." not in normalized:
        return True
    groups = normalized.split(".")
    if not groups[0]:
        return False
    for group in groups[1:]:
        if len(group) != 3:
            return False
    return True


def _is_negative_number_text(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("-"):
        return True
    return "(" in stripped and ")" in stripped


def _is_suspect_currency_cell(text: str) -> bool:
    data = _extract_currency_number(text)
    if not data:
        return False
    _currency, number = data
    normalized = _normalize_number_token(number)
    if not normalized:
        return False
    if normalized[0] in {".", ","} or normalized[-1] in {".", ","}:
        return True
    return not _number_grouping_is_valid(normalized)


def _strip_trailing_currency_fragment(text: str) -> str:
    tokens = text.split()
    if len(tokens) < 3:
        return text
    if tokens[-1] not in {"R", "E", "N", "ON"}:
        return text
    if tokens[-1] == "ON":
        if "RON" not in tokens:
            return text
        if not _digits_only(tokens[-2]):
            return text
        return " ".join(tokens[:-1])
    if "RON" not in tokens and "EUR" not in tokens:
        return text
    if not _digits_only(tokens[-2]):
        return text
    return " ".join(tokens[:-1])


def _strip_currency_prefix_dup(text: str) -> str:
    match = _CURRENCY_PREFIX_DUP_PATTERN.match(text)
    if not match:
        return text
    prefix = _digits_only(match.group(1))
    value = _digits_only(match.group(3))
    if prefix and value.startswith(prefix):
        return f"{match.group(2)} {match.group(3)}"
    return text


def _strip_currency_trailing_short_token(text: str) -> str:
    match = _CURRENCY_TRAILING_SHORT_PATTERN.match(text)
    if not match:
        return text
    return f"{match.group(2)} {match.group(1)}"


def _strip_duplicate_currency_suffix(text: str) -> str:
    tokens = text.split()
    if len(tokens) < 3:
        return text
    if tokens[0] not in {"RON", "EUR"}:
        return text
    if tokens[-1] != tokens[0]:
        return text
    if not any(ch.isdigit() for ch in tokens[1]):
        return text
    return " ".join(tokens[:-1])


def _compact_number_spacing(text: str) -> str:
    if not _is_numericish(text):
        return text
    compacted = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    compacted = re.sub(r"(?<=\d)\s+(?=[.,])", "", compacted)
    compacted = re.sub(r"(?<=[.,])\s+(?=\d)", "", compacted)
    compacted = re.sub(r"\s{2,}", " ", compacted)
    return compacted.strip()


def _normalize_currency_suffix(text: str) -> str:
    match = _CURRENCY_SUFFIX_PATTERN.match(text)
    if not match:
        return text
    return f"{match.group(2)} {match.group(1)}"


def _fix_missing_currency_letter(text: str) -> str:
    match = _CURRENCY_MISSING_R_PATTERN.match(text)
    if not match:
        if _is_numericish(text) and _CURRENCY_RO_TOKEN_PATTERN.search(text) and "RON" not in text:
            return _CURRENCY_RO_TOKEN_PATTERN.sub("RON", text)
        return text
    return f"RON {match.group(1)}"


def _dedupe_repeated_currency_value(text: str) -> str:
    match = _CURRENCY_REPEAT_PREFIX_PATTERN.match(text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    match = _CURRENCY_REPEAT_SUFFIX_PATTERN.match(text)
    if match:
        return f"{match.group(2)} {match.group(1)}"
    match = _CURRENCY_EXTRA_PREFIX_PATTERN.match(text)
    if match:
        return f"{match.group(2)} {match.group(3)}"
    match = _CURRENCY_ON_MIDDLE_PATTERN.match(text)
    if match:
        prefix_digits = _digits_only(match.group(1))
        value_digits = _digits_only(match.group(2))
        if prefix_digits and value_digits.startswith(prefix_digits):
            return f"{match.group(3)} {match.group(2)}"
    match = _CURRENCY_PREFIX_ONLY_PATTERN.match(text)
    if match:
        prefix_digits = _digits_only(match.group(1))
        value_digits = _digits_only(match.group(3))
        if prefix_digits and not value_digits.startswith(prefix_digits):
            return f"{match.group(2)} {match.group(3)}"
    return text


def _dedupe_dates_in_cell(text: str) -> str:
    dates = _DATE_PATTERN.findall(text)
    if len(dates) < 2:
        return text
    if any(ch.isalpha() for ch in text):
        return text
    # Prefer the date with a 4-digit year and longest token.
    scored = []
    for date in dates:
        parts = _DATE_SEP_PATTERN.split(date)
        year_len = len(parts[-1]) if parts else 0
        scored.append((year_len, len(date), date))
    scored.sort()
    best = scored[-1][2]
    return best


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


def _header_column_groups(table: TableItem) -> list[tuple[int, int]] | None:
    header_cells = [
        cell for cell in table.data.table_cells if cell.start_row_offset_idx == 0
    ]
    if not header_cells:
        return None

    header_cells.sort(key=lambda cell: cell.start_col_offset_idx)
    groups: list[tuple[int, int]] = []
    expected_col = 0

    for cell in header_cells:
        if cell.start_col_offset_idx != expected_col:
            return None
        if cell.end_col_offset_idx <= cell.start_col_offset_idx:
            return None
        groups.append((cell.start_col_offset_idx, cell.end_col_offset_idx))
        expected_col = cell.end_col_offset_idx

    if expected_col != table.data.num_cols:
        return None
    if all(end - start == 1 for start, end in groups):
        return None
    return groups


def _merge_bboxes(bboxes: list[BoundingBox]) -> BoundingBox | None:
    if not bboxes:
        return None
    l = min(bbox.l for bbox in bboxes)
    r = max(bbox.r for bbox in bboxes)
    t = min(bbox.t for bbox in bboxes)
    b = max(bbox.b for bbox in bboxes)
    return BoundingBox(l=l, t=t, r=r, b=b, coord_origin=bboxes[0].coord_origin)


def collapse_table_header_groups(table: TableItem) -> bool:
    """Collapse column groups defined by header spans (e.g., currency + value pairs)."""
    groups = _header_column_groups(table)
    if groups is None:
        return False

    col_map: list[int] = [0] * table.data.num_cols
    for new_idx, (start, end) in enumerate(groups):
        for col_idx in range(start, end):
            col_map[col_idx] = new_idx

    merged_cells: dict[tuple[int, int, int, int], list[tuple[TableCell, int]]] = {}
    for cell in table.data.table_cells:
        new_start = col_map[cell.start_col_offset_idx]
        new_end = col_map[cell.end_col_offset_idx - 1] + 1
        key = (
            cell.start_row_offset_idx,
            cell.end_row_offset_idx,
            new_start,
            new_end,
        )
        merged_cells.setdefault(key, []).append((cell, cell.start_col_offset_idx))

    updated_cells: list[TableCell] = []
    for (row_start, row_end, col_start, col_end), cells in merged_cells.items():
        cells.sort(key=lambda pair: pair[1])
        texts = [cell.text.strip() for cell, _ in cells if cell.text and cell.text.strip()]
        merged_text = " ".join(texts).strip()

        merged_bbox = _merge_bboxes([cell.bbox for cell, _ in cells if cell.bbox])
        column_header = any(cell.column_header for cell, _ in cells)
        row_header = any(cell.row_header for cell, _ in cells)
        row_section = any(cell.row_section for cell, _ in cells)
        fillable = any(cell.fillable for cell, _ in cells)

        updated_cells.append(
            TableCell(
                bbox=merged_bbox,
                row_span=row_end - row_start,
                col_span=col_end - col_start,
                start_row_offset_idx=row_start,
                end_row_offset_idx=row_end,
                start_col_offset_idx=col_start,
                end_col_offset_idx=col_end,
                text=merged_text,
                column_header=column_header,
                row_header=row_header,
                row_section=row_section,
                fillable=fillable,
            )
        )

    updated_cells.sort(
        key=lambda cell: (
            cell.start_row_offset_idx,
            cell.start_col_offset_idx,
            cell.end_row_offset_idx,
            cell.end_col_offset_idx,
        )
    )
    table.data.table_cells = updated_cells
    table.data.num_cols = len(groups)
    return True


def collapse_document_table_groups(doc) -> int:
    """Collapse header-driven column groups across all tables in a document."""
    updated = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem) and collapse_table_header_groups(item):
            updated += 1
    return updated


def _choose_date_match(matches: list[re.Match[str]] | list[tuple[int, str]]) -> str:
    candidates: list[tuple[int, int, int, str]] = []
    for match in matches:
        if isinstance(match, tuple):
            start_idx, date_text = match
        else:
            start_idx, date_text = match.start(), match.group(0)
        parts = _DATE_SEP_PATTERN.split(date_text)
        year_len = len(parts[-1]) if parts else 0
        day_len = len(parts[0]) if parts else 0
        candidates.append((start_idx, year_len, day_len, date_text))
    preferred = [item for item in candidates if item[1] == 4]
    if preferred:
        candidates = preferred
    day_preferred = [item for item in candidates if item[2] == 2]
    if day_preferred:
        candidates = day_preferred
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][3]


def _overlapping_date_matches(pattern: re.Pattern[str], text: str) -> list[tuple[int, str]]:
    overlapping = re.compile(rf"(?=({pattern.pattern}))")
    return [(match.start(), match.group(1)) for match in overlapping.finditer(text)]


def _repair_fuzzy_date(date_text: str) -> str:
    sep_match = _DATE_SEP_PATTERN.search(date_text)
    if not sep_match:
        return date_text
    sep = sep_match.group(0)
    parts = _DATE_SEP_PATTERN.split(date_text)
    if len(parts) != 3:
        return date_text
    day, month, year = parts
    if len(day) > 2:
        day = day[-2:]
    if len(month) > 2:
        month = month[-2:]
    return sep.join([day, month, year])


def _clean_header_text(text: str) -> str:
    if not text:
        return text
    normalized = normalize_mojibake_text(text)
    normalized = normalize_ligatures(normalized)
    normalized = " ".join(normalized.split())
    if _DELTA_PERCENT_PATTERN.match(normalized):
        return "Δ%"
    date_matches = list(_DATE_PATTERN.finditer(normalized))
    chosen_year_len = 0
    if date_matches:
        chosen = _choose_date_match(date_matches)
        chosen_year_len = len(_DATE_SEP_PATTERN.split(chosen)[-1])
        has_full_year = any(
            len(_DATE_SEP_PATTERN.split(match.group(0))[-1]) == 4
            for match in date_matches
        )
        if len(date_matches) > 1 and (has_full_year or chosen_year_len == 4):
            return chosen
        if (
            normalized != chosen
            and re.fullmatch(r"[\d\s./-]+", normalized)
            and chosen_year_len == 4
        ):
            return chosen

    if (
        chosen_year_len < 4
        and normalized.count("/") + normalized.count(".") + normalized.count("-") > 2
    ):
        fuzzy_matches = _overlapping_date_matches(_DATE_FUZZY_PATTERN, normalized)
        if fuzzy_matches:
            fuzzy_chosen = _choose_date_match(fuzzy_matches)
            repaired = _repair_fuzzy_date(fuzzy_chosen)
            if normalized != repaired and re.fullmatch(r"[\d\s./-]+", normalized):
                return repaired
    words = normalized.split()
    if len(words) % 2 == 0:
        mid = len(words) // 2
        if words[:mid] == words[mid:]:
            return " ".join(words[:mid])
    return normalized


def _merge_leading_group(match: re.Match[str]) -> str:
    lead = match.group(1)
    tail = match.group(2)
    if tail.count(".") >= 2:
        return tail
    return f"{lead}.{tail}"


def _clean_table_cell_text(text: str) -> str:
    if not text:
        return text
    cleaned = normalize_mojibake_text(text)
    cleaned = normalize_ligatures(cleaned).strip()
    if _DELTA_PERCENT_PATTERN.match(cleaned):
        return "Δ%"
    cleaned = _DUP_PERCENT_PATTERN.sub(r"\1%", cleaned)
    cleaned = _SPACED_PERCENT_PATTERN.sub(r"\1%", cleaned)
    cleaned = _NEGATIVE_SPACE_PATTERN.sub("-", cleaned)
    cleaned = _DUP_GROUP_PATTERN.sub(r"\1\2", cleaned)
    cleaned = _LEADING_GROUP_PATTERN.sub(_merge_leading_group, cleaned)
    cleaned = " ".join(cleaned.split())
    if any(ch.isdigit() for ch in cleaned):
        cleaned = cleaned.strip("[]")
    cleaned = _compact_number_spacing(cleaned)
    if _is_numericish(cleaned):
        cleaned = _PARENS_SPACE_OPEN_PATTERN.sub("(", cleaned)
        cleaned = _PARENS_SPACE_CLOSE_PATTERN.sub(")", cleaned)
    cleaned = _normalize_currency_suffix(cleaned)
    cleaned = _fix_missing_currency_letter(cleaned)
    cleaned = _strip_currency_trailing_short_token(cleaned)
    cleaned = _dedupe_dates_in_cell(cleaned)
    cleaned = _strip_trailing_currency_fragment(cleaned)
    cleaned = _strip_currency_prefix_dup(cleaned)
    cleaned = _strip_duplicate_currency_suffix(cleaned)
    cleaned = _dedupe_repeated_currency_value(cleaned)
    return cleaned


def _should_replace_numeric_cell(base_text: str, ocr_text: str) -> bool:
    if not base_text or not ocr_text:
        return False
    if is_spaced_text(ocr_text):
        return False
    base_clean = _clean_table_cell_text(base_text)
    ocr_clean = _clean_table_cell_text(ocr_text)
    if base_clean == ocr_clean:
        return False
    base_info = _extract_currency_number(base_clean)
    ocr_info = _extract_currency_number(ocr_clean)
    if not base_info or not ocr_info:
        return False
    if (base_info[0] is None) != (ocr_info[0] is None):
        return False
    if base_info[0] is not None and ocr_info[0] is not None and base_info[0] != ocr_info[0]:
        return False
    if _is_negative_number_text(base_clean) != _is_negative_number_text(ocr_clean):
        return False

    base_num = base_info[1]
    ocr_num = ocr_info[1]
    base_digits = _digits_only(base_num)
    ocr_digits = _digits_only(ocr_num)
    if not base_digits or not ocr_digits:
        return False
    if len(ocr_digits) <= len(base_digits):
        return False
    if not _number_grouping_is_valid(ocr_num):
        return False
    if _is_suspect_currency_cell(base_clean):
        return True
    if ocr_digits.endswith(base_digits):
        if len(ocr_digits) - len(base_digits) <= 2:
            return True
    return False


def normalize_table_header_text(table: TableItem) -> int:
    """Normalize duplicated or merged header labels in a table."""
    updated = 0
    for cell in table.data.table_cells:
        if cell.start_row_offset_idx != 0:
            continue
        cleaned = _clean_header_text(cell.text)
        if cleaned != cell.text:
            cell.text = cleaned
            updated += 1
    return updated


def normalize_document_table_headers(doc) -> int:
    """Normalize header labels across all tables in a document."""
    updated = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            updated += normalize_table_header_text(item)
    return updated


def clean_document_table_cells(doc) -> int:
    """Normalize numeric/percent quirks in table cells after repairs."""
    updated = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            for cell in item.data.table_cells:
                cleaned = _clean_table_cell_text(cell.text)
                if cleaned != cell.text:
                    cell.text = cleaned
                    updated += 1
    return updated


def normalize_table_currency_columns(table: TableItem) -> int:
    """Align currency labels within each numeric column to the dominant currency."""
    num_cols = table.data.num_cols
    if num_cols <= 0:
        return 0

    counts: list[dict[str, int]] = [defaultdict(int) for _ in range(num_cols)]
    for cell in table.data.table_cells:
        if cell.start_row_offset_idx == 0:
            continue
        if cell.end_col_offset_idx - cell.start_col_offset_idx != 1:
            continue
        text = cell.text or ""
        match = _CURRENCY_TOKEN_PATTERN.search(text)
        if not match:
            continue
        currency = match.group(1)
        counts[cell.start_col_offset_idx][currency] += 1

    dominant: list[str | None] = [None] * num_cols
    for col, counter in enumerate(counts):
        if not counter:
            continue
        total = sum(counter.values())
        currency, freq = max(counter.items(), key=lambda item: item[1])
        if total >= 2 and (freq / total) >= 0.7:
            dominant[col] = currency

    updated = 0
    for cell in table.data.table_cells:
        if cell.start_row_offset_idx == 0:
            continue
        if cell.end_col_offset_idx - cell.start_col_offset_idx != 1:
            continue
        desired = dominant[cell.start_col_offset_idx]
        if not desired:
            continue
        text = cell.text or ""
        match = _CURRENCY_TOKEN_PATTERN.search(text)
        if not match:
            continue
        if match.group(1) == desired:
            continue
        new_text = _CURRENCY_TOKEN_PATTERN.sub(desired, text)
        if new_text != text:
            cell.text = new_text
            updated += 1

    return updated


def normalize_document_table_currencies(doc) -> int:
    """Normalize currency labels across all tables in a document."""
    updated = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            updated += normalize_table_currency_columns(item)
    return updated


def count_suspect_table_cells(doc) -> int:
    """Count table cells that look like truncated currency values."""
    count = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            for cell in item.data.table_cells:
                if not cell.text:
                    continue
                cleaned = _clean_table_cell_text(cell.text)
                if _is_suspect_currency_cell(cleaned):
                    count += 1
    return count


def merge_suspect_table_cells(base_doc, ocr_doc) -> int:
    """Replace suspect numeric table cells with higher-quality OCR versions."""
    base_tables = [item for item, _ in base_doc.iterate_items() if isinstance(item, TableItem)]
    ocr_tables = [item for item, _ in ocr_doc.iterate_items() if isinstance(item, TableItem)]

    base_by_page = _tables_by_page(base_tables)
    ocr_by_page = _tables_by_page(ocr_tables)

    replaced = 0

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
                if not cell.text:
                    continue
                key = (
                    cell.start_row_offset_idx,
                    cell.end_row_offset_idx,
                    cell.start_col_offset_idx,
                    cell.end_col_offset_idx,
                )
                ocr_text = ocr_cells.get(key, "")
                if not ocr_text:
                    continue
                if _should_replace_numeric_cell(cell.text, ocr_text):
                    cell.text = ocr_text
                    replaced += 1

    ocr_cells_by_page = _collect_cells_by_page(ocr_tables)
    for page_no, base_page_tables in base_by_page.items():
        ocr_cells = ocr_cells_by_page.get(page_no, [])
        if not ocr_cells:
            continue
        for base_table in base_page_tables:
            for cell in base_table.data.table_cells:
                if not cell.text or cell.bbox is None:
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

                if best_text and _should_replace_numeric_cell(cell.text, best_text):
                    cell.text = best_text
                    replaced += 1

    return replaced


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
