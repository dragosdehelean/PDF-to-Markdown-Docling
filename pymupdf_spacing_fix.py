"""@fileoverview Spacing repair using PyMuPDF glyph positions (OCR-free)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import re
import statistics

import fitz

from docling_core.types.doc import TableItem
from docling_core.types.doc.base import BoundingBox, CoordOrigin

from audit_utils import needs_spacing_fix, needs_table_spacing_fix, is_spaced_text


TEXT_FLAGS = fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
_RUNON_LETTERS = re.compile(r"(?:[^\W\d_]{20,})", flags=re.UNICODE)
_MERGED_ALNUM = re.compile(
    r"(?:[^\W\d_]{6,}\d{2,}[^\W\d_]{2,}|\d{2,}[^\W\d_]{6,})", flags=re.UNICODE
)
_NUMERIC_ONLY = re.compile(r"[0-9\s.,/%()-]+")
_SUSPICIOUS_NUMERIC = re.compile(r"^[.,]?\d[.,]?$")
_TRAILING_ALPHA = re.compile(r"[A-Za-zĂÂÎăâîșșțȚȘ]$", flags=re.UNICODE)
_ALPHA_TOKEN = re.compile(r"[A-Za-zĂÂÎăâîșșțȚȘ]+", flags=re.UNICODE)
_VOWELS = set("aeiouAEIOUăâîĂÂÎ")


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
    # WHY: Clustering gaps separates intra-word kerning from actual word breaks.
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


def _bbox_to_top_left(bbox: BoundingBox, page_height: float) -> BoundingBox:
    if bbox.coord_origin is CoordOrigin.TOPLEFT:
        return bbox
    return bbox.to_top_left_origin(page_height)


def _clip_rect(page: fitz.Page, bbox: BoundingBox, pad: float) -> Optional[fitz.Rect]:
    rect = fitz.Rect(bbox.l, bbox.t, bbox.r, bbox.b)
    rect = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
    rect = rect & page.rect
    if rect.is_empty:
        return None
    return rect


def _extract_words(page: fitz.Page, rect: fitz.Rect) -> list[tuple[str, int, int, int]]:
    words = page.get_text("words", clip=rect, flags=TEXT_FLAGS)
    out: list[tuple[str, int, int, int]] = []
    for word in words:
        if len(word) < 8:
            continue
        _x0, _y0, _x1, _y1, text, block_no, line_no, word_no = word
        if not text:
            continue
        out.append((text, block_no, line_no, word_no))
    return out


def _extract_chars(page: fitz.Page, rect: fitz.Rect) -> list[tuple[str, fitz.Rect]]:
    raw = page.get_text("rawdict", clip=rect, flags=TEXT_FLAGS)
    chars: list[tuple[str, fitz.Rect]] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    text = ch.get("c")
                    bbox = ch.get("bbox")
                    if not text or not bbox or len(bbox) != 4:
                        continue
                    chars.append((text, fitz.Rect(bbox)))
    return chars


def _reconstruct_from_words(words: list[tuple[str, int, int, int]]) -> str:
    if not words:
        return ""

    lines: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for text, block_no, line_no, word_no in words:
        lines.setdefault((block_no, line_no), []).append((word_no, text))

    out_lines: list[str] = []
    for key in sorted(lines.keys()):
        items = sorted(lines[key], key=lambda item: item[0])
        line_text = " ".join(word for _idx, word in items).strip()
        if line_text:
            out_lines.append(line_text)
    return " ".join(out_lines).strip()


def _reconstruct_from_chars(
    chars: list[tuple[str, fitz.Rect]],
    *,
    gap_ratio: float,
    line_ratio: float,
    space_width_ratio: float,
) -> str:
    if not chars:
        return ""

    heights = [bbox.height for _text, bbox in chars]
    line_tol = _median(heights) * line_ratio

    chars.sort(key=lambda item: ((item[1].y0 + item[1].y1) / 2, item[1].x0))

    lines: list[dict[str, object]] = []
    for text, bbox in chars:
        y_center = (bbox.y0 + bbox.y1) / 2
        if not lines or abs(y_center - lines[-1]["y"]) > line_tol:
            lines.append({"y": y_center, "chars": []})
        lines[-1]["chars"].append((bbox.x0, text, bbox))

    line_texts: list[str] = []
    for line in lines:
        items = sorted(line["chars"], key=lambda item: item[0])
        non_space_widths = [bbox.width for _x, text, bbox in items if not text.isspace()]
        median_char_width = _median(non_space_widths)
        gaps = []
        for idx in range(1, len(items)):
            gap = items[idx][2].x0 - items[idx - 1][2].x1
            if gap >= 0:
                gaps.append(gap)
        gap_threshold = _gap_threshold(
            gaps,
            median_char_width=median_char_width,
            fallback_ratio=gap_ratio,
        )

        out = ""
        prev_bbox: Optional[fitz.Rect] = None
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
                gap = bbox.x0 - prev_bbox.x1
                if gap > gap_threshold:
                    out += " "
            out += text
            prev_bbox = bbox

        if out.strip():
            line_texts.append(out.strip())

    return " ".join(line_texts).strip()


def _spacing_badness(text: str) -> float:
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    if not tokens:
        return 0.0
    avg_len = sum(len(t) for t in tokens) / len(tokens)
    long_tokens = sum(1 for t in tokens if len(t) >= 18)
    badness = max(0.0, avg_len - 6.0)
    badness += long_tokens * 1.5
    if _RUNON_LETTERS.search(text):
        badness += 4.0
    if _MERGED_ALNUM.search(text):
        badness += 3.0
    if is_spaced_text(text):
        badness += 4.0
    return badness


def _expand_suffix_with_pad(
    page: fitz.Page,
    bbox: BoundingBox,
    *,
    pad: float,
    gap_ratio: float,
    line_ratio: float,
    space_width_ratio: float,
    base_text: str,
) -> str:
    if not _needs_suffix_completion(base_text):
        return base_text
    clip = _clip_rect(page, bbox, pad * 3.0)
    if clip is None:
        return base_text
    words = _extract_words(page, clip)
    reconstructed = _compact_numeric_spacing(_reconstruct_from_words(words))
    if reconstructed and _should_replace_text(base_text, reconstructed, table_mode=True):
        return reconstructed
    chars = _extract_chars(page, clip)
    reconstructed = _compact_numeric_spacing(
        _reconstruct_from_chars(
            chars,
            gap_ratio=gap_ratio,
            line_ratio=line_ratio,
            space_width_ratio=space_width_ratio,
        )
    )
    if reconstructed and _should_replace_text(base_text, reconstructed, table_mode=True):
        return reconstructed
    return base_text


def _numeric_only(text: str) -> bool:
    return bool(_NUMERIC_ONLY.fullmatch(text.strip()))


def _needs_numeric_repair(text: str) -> bool:
    if not _numeric_only(text):
        return False
    stripped = text.strip()
    if not stripped:
        return True
    digits = re.sub(r"\D", "", stripped)
    if not digits:
        return True
    if len(digits) <= 2:
        return True
    if _SUSPICIOUS_NUMERIC.fullmatch(stripped):
        return True
    if stripped.startswith((".", ",")) and len(digits) <= 4:
        return True
    return False


def _needs_short_text_repair(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return stripped.isalpha() and len(stripped) <= 2


def _needs_suffix_completion(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 6:
        return False
    tokens = _ALPHA_TOKEN.findall(stripped)
    if not tokens:
        return False
    last_token = tokens[-1]
    if len(last_token) < 6:
        return False
    if not _TRAILING_ALPHA.search(last_token):
        return False
    return last_token[-1] not in _VOWELS


def _needs_table_cell_repair(text: str) -> bool:
    return (
        needs_table_spacing_fix(text)
        or _needs_numeric_repair(text)
        or _needs_short_text_repair(text)
        or _needs_suffix_completion(text)
    )


def _compact_numeric_spacing(text: str) -> str:
    if not _numeric_only(text):
        return text
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\s+(?=[.,/%])", "", text)
    text = re.sub(r"(?<=[.,/%])\s+(?=\d)", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _should_replace_text(old: str, new: str, *, table_mode: bool = False) -> bool:
    if not new or new == old:
        return False
    if not old.strip():
        return True
    if new.startswith(old) and 0 < (len(new) - len(old)) <= 3:
        return True
    old_tokens = re.findall(r"\w+", old, flags=re.UNICODE)
    new_tokens = re.findall(r"\w+", new, flags=re.UNICODE)
    if table_mode and needs_table_spacing_fix(old) and old_tokens:
        if len(new_tokens) <= max(1, int(len(old_tokens) * 0.6)):
            return True
    if _needs_numeric_repair(old) and _numeric_only(new):
        old_digits = len(re.sub(r"\D", "", old))
        new_digits = len(re.sub(r"\D", "", new))
        if new_digits > old_digits:
            return True
    if _needs_short_text_repair(old) and len(new) > len(old):
        return True
    if old.isalpha() and new.isalpha():
        if new.startswith(old) and 0 < (len(new) - len(old)) <= 3:
            return True
    if len(new) < max(8, int(len(old) * 0.4)):
        if not (is_spaced_text(old) or _NUMERIC_ONLY.fullmatch(old)):
            return False
    old_tokens = re.findall(r"\w+", old, flags=re.UNICODE)
    new_tokens = re.findall(r"\w+", new, flags=re.UNICODE)
    if old_tokens and len(new_tokens) < max(1, int(len(old_tokens) * 0.6)):
        if not (
            is_spaced_text(old)
            or _NUMERIC_ONLY.fullmatch(old)
            or (table_mode and needs_table_spacing_fix(old))
        ):
            return False
    if needs_spacing_fix(old) and not needs_spacing_fix(new):
        return True
    if table_mode and needs_table_spacing_fix(old) and not needs_table_spacing_fix(new):
        return True
    return _spacing_badness(new) + 0.5 < _spacing_badness(old)


def fix_spaced_items_with_pymupdf_glyphs(
    doc,
    pdf_path: Path,
    *,
    pages_to_fix: Optional[set[int]] = None,
    pad: float = 1.0,
    gap_ratio: float = 0.35,
    line_ratio: float = 0.6,
    space_width_ratio: float = 0.6,
) -> SpacingFixReport:
    """Repair spaced table/text items using PyMuPDF glyph reconstruction."""
    if pages_to_fix is not None and not pages_to_fix:
        return SpacingFixReport(0, 0, 0)

    table_replaced = 0
    text_replaced = 0

    with fitz.open(pdf_path) as pdf:
        def get_page(page_no: int) -> Optional[fitz.Page]:
            if page_no < 1 or page_no > pdf.page_count:
                return None
            return pdf.load_page(page_no - 1)

        for item, _level in doc.iterate_items():
            if isinstance(item, TableItem):
                page_no = item.prov[0].page_no if item.prov else None
                if page_no is None or (pages_to_fix and page_no not in pages_to_fix):
                    continue
                page = get_page(page_no)
                if page is None:
                    continue
                for cell in item.data.table_cells:
                    if cell.bbox is None or not _needs_table_cell_repair(cell.text):
                        continue
                    bbox = _bbox_to_top_left(cell.bbox, page.rect.height)
                    original_text = cell.text
                    replaced = False

                    clip = _clip_rect(page, bbox, pad)
                    if clip is None:
                        continue
                    words = _extract_words(page, clip)
                    reconstructed = _compact_numeric_spacing(
                        _reconstruct_from_words(words)
                    )
                    if reconstructed and not needs_spacing_fix(reconstructed):
                        reconstructed = _expand_suffix_with_pad(
                            page,
                            bbox,
                            pad=pad,
                            gap_ratio=gap_ratio,
                            line_ratio=line_ratio,
                            space_width_ratio=space_width_ratio,
                            base_text=reconstructed,
                        )
                        if _should_replace_text(original_text, reconstructed, table_mode=True):
                            cell.text = reconstructed
                            table_replaced += 1
                            replaced = True
                        else:
                            reconstructed = ""
                    if not replaced:
                        chars = _extract_chars(page, clip)
                        reconstructed = _compact_numeric_spacing(
                            _reconstruct_from_chars(
                                chars,
                                gap_ratio=gap_ratio,
                                line_ratio=line_ratio,
                                space_width_ratio=space_width_ratio,
                            )
                        )
                        if reconstructed:
                            reconstructed = _expand_suffix_with_pad(
                                page,
                                bbox,
                                pad=pad,
                                gap_ratio=gap_ratio,
                                line_ratio=line_ratio,
                                space_width_ratio=space_width_ratio,
                                base_text=reconstructed,
                            )
                        if reconstructed and _should_replace_text(
                            original_text, reconstructed, table_mode=True
                        ):
                            cell.text = reconstructed
                            table_replaced += 1
                            replaced = True

                    if not replaced and _needs_suffix_completion(original_text):
                        # WHY: Expand bbox padding to capture trailing glyphs for clipped words.
                        reconstructed = _expand_suffix_with_pad(
                            page,
                            bbox,
                            pad=pad,
                            gap_ratio=gap_ratio,
                            line_ratio=line_ratio,
                            space_width_ratio=space_width_ratio,
                            base_text=original_text,
                        )
                        if reconstructed and _should_replace_text(
                            original_text, reconstructed, table_mode=True
                        ):
                            cell.text = reconstructed
                            table_replaced += 1
            else:
                text = getattr(item, "text", None)
                if not text or not needs_spacing_fix(text):
                    continue
                if not getattr(item, "prov", None):
                    continue
                page_no = item.prov[0].page_no
                if page_no is None or (pages_to_fix and page_no not in pages_to_fix):
                    continue
                bbox = item.prov[0].bbox
                if bbox is None:
                    continue
                page = get_page(page_no)
                if page is None:
                    continue
                bbox = _bbox_to_top_left(bbox, page.rect.height)
                clip = _clip_rect(page, bbox, pad)
                if clip is None:
                    continue
                words = _extract_words(page, clip)
                reconstructed = _compact_numeric_spacing(_reconstruct_from_words(words))
                if reconstructed and not needs_spacing_fix(reconstructed):
                    if _should_replace_text(text, reconstructed):
                        item.text = reconstructed
                        text_replaced += 1
                    continue
                chars = _extract_chars(page, clip)
                reconstructed = _compact_numeric_spacing(
                    _reconstruct_from_chars(
                        chars,
                        gap_ratio=gap_ratio,
                        line_ratio=line_ratio,
                        space_width_ratio=space_width_ratio,
                    )
                )
                if reconstructed and _should_replace_text(text, reconstructed):
                    item.text = reconstructed
                    text_replaced += 1

    pages_processed = 0 if pages_to_fix is None else len(pages_to_fix)
    return SpacingFixReport(
        table_cells=table_replaced,
        text_items=text_replaced,
        pages_processed=pages_processed,
    )
