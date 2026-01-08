"""@fileoverview Extract KPI-like text from picture regions."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import fitz

from docling_core.types.doc.base import BoundingBox, CoordOrigin
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from docling_core.types.doc import PictureItem

from pdf_to_markdown_docling.text_normalize import normalize_ligatures, normalize_mojibake_text


_TEXT_FLAGS = fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE
_NUM_TOKEN = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_CURRENCY_TOKEN = re.compile(r"\b(?:RON|EUR|USD|LEI)\b", flags=re.IGNORECASE)
_PERCENT_TOKEN = re.compile(r"%")
_AXIS_UNIT_TOKEN = re.compile(r"\b(?:mil\.?|mii|milioane?)\b", flags=re.IGNORECASE)
_KEYWORD_TOKEN = re.compile(
    r"\b(?:profit\w*|cifr\w*|venit\w*|active\w*|ebitda\w*|marj\w*|rezultat\w*|capital\w*)\b",
    flags=re.IGNORECASE,
)
_TESS_LANG_CACHE: Optional[str] = None


def _bbox_to_top_left(bbox: BoundingBox, page_height: Optional[float]) -> BoundingBox:
    if bbox.coord_origin is CoordOrigin.TOPLEFT or page_height is None:
        return bbox
    return bbox.to_top_left_origin(page_height)


def _clip_rect(page: fitz.Page, bbox: BoundingBox, pad: float) -> Optional[fitz.Rect]:
    rect = fitz.Rect(bbox.l, bbox.t, bbox.r, bbox.b)
    rect = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
    rect = rect & page.rect
    if rect.is_empty:
        return None
    return rect


def _extract_picture_text(page: fitz.Page, bbox: BoundingBox) -> str:
    clip = _clip_rect(page, bbox, pad=2.0)
    if clip is None:
        return ""
    words = page.get_text("words", clip=clip, flags=_TEXT_FLAGS)
    if not words:
        return ""
    lines: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for word in words:
        _x0, _y0, _x1, _y1, text, block_no, line_no, word_no = word
        if not text:
            continue
        lines.setdefault((block_no, line_no), []).append((word_no, text))

    out_lines: list[str] = []
    for key in sorted(lines.keys()):
        items = sorted(lines[key], key=lambda item: item[0])
        line_text = " ".join(word for _idx, word in items).strip()
        if line_text:
            out_lines.append(line_text)
    return "\n".join(out_lines).strip()


def _available_tesseract_lang() -> Optional[str]:
    global _TESS_LANG_CACHE
    if _TESS_LANG_CACHE is not None:
        return _TESS_LANG_CACHE
    if shutil.which("tesseract") is None:
        _TESS_LANG_CACHE = ""
        return None
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        _TESS_LANG_CACHE = ""
        return None
    langs = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if "ron" in langs and "eng" in langs:
        _TESS_LANG_CACHE = "ron+eng"
    elif "ron" in langs:
        _TESS_LANG_CACHE = "ron"
    elif "eng" in langs:
        _TESS_LANG_CACHE = "eng"
    else:
        _TESS_LANG_CACHE = ""
    return _TESS_LANG_CACHE or None


def _ocr_picture_text(page: fitz.Page, bbox: BoundingBox) -> str:
    lang = _available_tesseract_lang()
    if not lang:
        return ""
    clip = _clip_rect(page, bbox, pad=2.0)
    if clip is None:
        return ""
    pix = page.get_pixmap(clip=clip, dpi=300)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "kpi.png"
        pix.save(str(temp_path))
        result = subprocess.run(
            ["tesseract", str(temp_path), "stdout", "-l", lang, "--psm", "6"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()


def _normalize_kpi_caption(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    joined = " ".join(lines)
    joined = re.sub(r"\s+", " ", joined).strip()
    joined = re.sub(r"\s+([,.;:%])", r"\1", joined)
    joined = re.sub(r"\(\s+", "(", joined)
    joined = re.sub(r"\s+\)", ")", joined)
    joined = re.sub(
        r"(?i)(\b\d[\d.,]*\s*mil\.?)\s+ron\b", r"RON \1", joined
    )
    return joined


def _is_axis_like(text: str) -> bool:
    numbers = _NUM_TOKEN.findall(text)
    if len(numbers) < 4:
        return False
    has_decimal = any("." in num or "," in num for num in numbers)
    if has_decimal:
        return False
    small_ticks = 0
    large_non_year = False
    for num in numbers:
        cleaned = num.replace(".", "").replace(",", "")
        if not cleaned.isdigit():
            continue
        value = int(cleaned)
        if value <= 200:
            small_ticks += 1
        if value >= 1000 and not (1900 <= value <= 2100):
            large_non_year = True
    if large_non_year:
        return False
    if small_ticks < 4:
        return False
    if not (_AXIS_UNIT_TOKEN.search(text) or _CURRENCY_TOKEN.search(text)):
        return False
    return True


def _is_kpi_text(text: str) -> bool:
    if not text or len(text) < 8:
        return False
    num_tokens = _NUM_TOKEN.findall(text)
    if not num_tokens:
        return False
    if len(num_tokens) > 12:
        return False
    has_currency = bool(_CURRENCY_TOKEN.search(text))
    has_percent = bool(_PERCENT_TOKEN.search(text))
    has_keyword = bool(_KEYWORD_TOKEN.search(text))
    alpha_tokens = [tok for tok in re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)]
    if not alpha_tokens:
        return False
    non_currency = [
        tok
        for tok in alpha_tokens
        if tok.casefold() not in {"ron", "eur", "usd", "lei"}
    ]
    if not non_currency:
        return False
    if _is_axis_like(text):
        return False
    if not (has_currency or has_percent or has_keyword):
        return False
    if len(text) > 300:
        return False
    if text.count("\n") > 8:
        return False
    return True


def add_picture_kpi_captions(
    doc: DoclingDocument,
    pdf_path: Path,
    *,
    max_added: int = 30,
) -> int:
    """Extract KPI-like text from picture areas and attach as captions."""
    if max_added <= 0:
        return 0
    doc_text = doc.export_to_text().casefold()
    added = 0

    with fitz.open(pdf_path) as pdf:
        for item, _level in doc.iterate_items():
            if not isinstance(item, PictureItem):
                continue
            if item.captions:
                continue
            if not item.prov:
                continue
            prov = item.prov[0]
            if prov.page_no is None or prov.bbox is None:
                continue
            if prov.page_no < 1 or prov.page_no > pdf.page_count:
                continue
            page = pdf.load_page(prov.page_no - 1)
            page_height = doc.pages[prov.page_no].size.height if prov.page_no in doc.pages and doc.pages[prov.page_no].size else None
            bbox = _bbox_to_top_left(prov.bbox, page_height)
            raw = _extract_picture_text(page, bbox)
            if raw:
                raw = normalize_ligatures(normalize_mojibake_text(raw))
                raw = _normalize_kpi_caption(raw)
            if not raw or not _is_kpi_text(raw):
                ocr_raw = _ocr_picture_text(page, bbox)
                if not ocr_raw:
                    continue
                ocr_raw = normalize_ligatures(normalize_mojibake_text(ocr_raw))
                ocr_raw = _normalize_kpi_caption(ocr_raw)
                if not _is_kpi_text(ocr_raw):
                    continue
                raw = ocr_raw
            normalized = raw.casefold()
            if normalized and normalized in doc_text:
                continue
            caption = doc.add_text(
                label=DocItemLabel.CAPTION,
                text=raw,
                parent=item,
            )
            item.captions.append(caption.get_ref())
            added += 1
            if added >= max_added:
                break

    return added
