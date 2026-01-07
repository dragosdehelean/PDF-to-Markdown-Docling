"""@fileoverview Audit helpers for PDF-vs-Markdown fidelity and spacing issues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from docling_core.types.doc import TableItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel


_NUMBER_PATTERN = re.compile(
    r"(?<!\w)[+-]?(?:\d{1,3}(?:[ .]\d{3})+|\d+)(?:[.,]\d+)?%?"
)
_DATE_PATTERN = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")


@dataclass(frozen=True)
class AuditMetrics:
    token_coverage: float
    numeric_recall: float
    date_recall: float
    table_count_pdf: int
    table_count_md: int
    table_cells_pdf: int
    heading_count_pdf: int
    heading_count_md: int
    pdf_text_length: int
    md_text_length: int
    spaced_table_cells: int
    total_table_cells: int
    spaced_text_items: int
    multi_space_text_items: int
    total_text_items: int


@dataclass(frozen=True)
class PageAudit:
    page_no: int
    token_coverage: float
    numeric_recall: float
    date_recall: float
    pdf_text_length: int
    md_text_length: int


_SPACED_TEXT_PATTERN = re.compile(r"(?:\b\w\b\s+){1,}\b\w\b", flags=re.UNICODE)
_SPACED_DIGIT_PATTERN = re.compile(r"(?:\b\d\b\s+){3,}\b\d\b")
_SPLIT_WORD_PATTERN = re.compile(r"\b(\w{2,})\s+(\w)\s+(\w{2,})\b", flags=re.UNICODE)
_SPACED_NUMBER_PATTERN = re.compile(r"\d[.,/]\s+\d|\d\s+[.,/]\s*\d")
_RUNON_LETTERS_PATTERN = re.compile(r"(?:[^\W\d_]{20,})", flags=re.UNICODE)
_RUNON_MERGED_ALNUM_PATTERN = re.compile(
    r"(?:[^\W\d_]{6,}\d{2,}[^\W\d_]{2,}|\d{2,}[^\W\d_]{6,})",
    flags=re.UNICODE,
)
_MULTI_SPACE_PATTERN = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")
_COMMON_SINGLE_LETTER_WORDS = {"a", "A", "I", "i", "o", "O"}
_LETTER_CHARS = r"A-Za-zĂÂÎȘȚăâîșț"
_SHORT_ALPHA_SEQ_PATTERN = re.compile(
    rf"(?:\b[{_LETTER_CHARS}]{{1,2}}\b\s+){{2,}}\b[{_LETTER_CHARS}]{{1,2}}\b",
    flags=re.UNICODE,
)
_TRAILING_SINGLE_ALPHA_PATTERN = re.compile(
    rf"\b[{_LETTER_CHARS}]{{2,}}\s+[{_LETTER_CHARS}]{{1}}\b",
    flags=re.UNICODE,
)
_SOLD_SUFFIX_PATTERN = re.compile(r"\bSOLD\s+[CD]\b", flags=re.IGNORECASE)


def is_spaced_text(text: str) -> bool:
    """Detect obvious spacing artifacts (split letters or digits) in extracted text."""
    if _SPACED_DIGIT_PATTERN.search(text):
        return True
    if _SPACED_NUMBER_PATTERN.search(text):
        return True
    spaced_text_matches = list(_SPACED_TEXT_PATTERN.finditer(text))
    if spaced_text_matches:
        for match in spaced_text_matches:
            tokens = [tok for tok in match.group(0).split() if tok]
            uncommon = [
                tok
                for tok in tokens
                if tok.isalpha() and tok not in _COMMON_SINGLE_LETTER_WORDS
            ]
            if uncommon:
                return True
    if len(text) < 6:
        return False

    split_matches = list(_SPLIT_WORD_PATTERN.finditer(text))
    if split_matches:
        for match in split_matches:
            middle = match.group(2)
            if not middle.isalpha():
                continue
            if middle not in _COMMON_SINGLE_LETTER_WORDS:
                return True

    tokens = [tok for tok in text.split() if tok]
    if len(tokens) < 4:
        return False
    single_tokens = [tok for tok in tokens if len(tok) == 1 and tok.isalnum()]
    if (len(single_tokens) / len(tokens)) >= 0.5:
        return True

    if split_matches:
        rare_single_tokens = [
            tok
            for tok in single_tokens
            if tok.isalpha() and tok not in _COMMON_SINGLE_LETTER_WORDS
        ]
        if len(rare_single_tokens) >= 2:
            return True
        if single_tokens and (len(rare_single_tokens) / len(single_tokens)) >= 0.5:
            return True

    return False


def is_multi_space_text(text: str) -> bool:
    """Detect multiple spaces/tabs between tokens without other spacing artifacts."""
    return bool(_MULTI_SPACE_PATTERN.search(text))

def is_collapsed_text(text: str) -> bool:
    """Detect run-on text where spaces are likely missing between words."""
    if _RUNON_LETTERS_PATTERN.search(text):
        return True
    if _RUNON_MERGED_ALNUM_PATTERN.search(text):
        return True
    if len(text) < 60:
        return False
    tokens = [tok for tok in re.findall(r"\w+", text, flags=re.UNICODE) if tok]
    if len(tokens) < 8:
        return False
    avg_len = sum(len(tok) for tok in tokens) / len(tokens)
    long_tokens = sum(1 for tok in tokens if len(tok) >= 18)
    space_ratio = text.count(" ") / max(len(text), 1)

    if avg_len >= 9.0:
        return True
    if long_tokens >= 2:
        return True
    if len(text) > 120 and space_ratio < 0.05:
        return True
    return False


def needs_spacing_fix(text: str) -> bool:
    """Decide if generic text should be routed through spacing repair."""
    return is_spaced_text(text) or is_collapsed_text(text)


def needs_table_spacing_fix(text: str) -> bool:
    """Decide if table cells need spacing repair (captures short letter splits)."""
    if needs_spacing_fix(text):
        return True
    if not text:
        return False
    has_digit = any(ch.isdigit() for ch in text)
    has_letter = any(ch.isalpha() for ch in text)
    if has_digit and not has_letter:
        return False
    if _SHORT_ALPHA_SEQ_PATTERN.search(text):
        return True
    if _TRAILING_SINGLE_ALPHA_PATTERN.search(text):
        if _SOLD_SUFFIX_PATTERN.search(text):
            return False
        return True
    return False

def _normalize_token(token: str) -> str:
    return token.casefold().strip("_")


def _tokenize(text: str) -> list[str]:
    return [_normalize_token(tok) for tok in re.findall(r"\w+", text, flags=re.UNICODE)]


def _normalize_number(token: str) -> str:
    token = token.strip()
    percent = "%" if token.endswith("%") else ""
    token = token.rstrip("%")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "")
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
    else:
        if token.count(",") == 1 and token.count(".") == 0:
            token = token.replace(",", ".")
        token = token.replace(" ", "")
    return f"{token}{percent}"


def _extract_numbers(text: str) -> set[str]:
    return {_normalize_number(match.group(0)) for match in _NUMBER_PATTERN.finditer(text)}


def _extract_dates(text: str) -> set[str]:
    return {match.group(0) for match in _DATE_PATTERN.finditer(text)}


def _coverage(reference: Iterable[str], candidate: set[str]) -> float:
    reference_list = list(reference)
    if not reference_list:
        return 1.0
    matched = sum(1 for item in reference_list if item in candidate)
    return matched / len(reference_list)


def _markdown_heading_count(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.lstrip().startswith("#"))


def _markdown_table_count(markdown: str) -> int:
    lines = markdown.splitlines()
    count = 0
    for i in range(1, len(lines)):
        if "|" not in lines[i - 1]:
            continue
        line = lines[i].strip()
        if line.startswith("|") and "---" in line:
            count += 1
    return count


def _docling_table_stats(doc: DoclingDocument) -> tuple[int, int]:
    tables = []
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            if _is_toc_like_table(item):
                continue
            tables.append(item)
    cell_count = sum(table.data.num_rows * table.data.num_cols for table in tables)
    return len(tables), cell_count


def _is_toc_like_table(table: TableItem) -> bool:
    if table.data.num_cols != 2 or table.data.num_rows < 6:
        return False
    texts = [cell.text for cell in table.data.table_cells if cell.text]
    if not texts:
        return False
    digit_count = sum(ch.isdigit() for text in texts for ch in text)
    alpha_count = sum(ch.isalpha() for text in texts for ch in text)
    digit_ratio = digit_count / max(1, digit_count + alpha_count)
    if digit_ratio > 0.25:
        return False
    numbers = _extract_numbers(" ".join(texts))
    if not numbers:
        return False
    small_numbers = [
        num for num in numbers if len(re.sub(r"\D", "", num)) <= 3
    ]
    if len(small_numbers) / len(numbers) < 0.7:
        return False
    return True


def _docling_heading_count(doc: DoclingDocument) -> int:
    heading_labels = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
    count = 0
    for item, _level in doc.iterate_items():
        if getattr(item, "label", None) in heading_labels:
            count += 1
    return count


def audit_doc_vs_markdown(doc: DoclingDocument, markdown: str) -> AuditMetrics:
    """Compare Docling text against Markdown to quantify extraction fidelity."""
    pdf_text = doc.export_to_text()
    pdf_tokens = _tokenize(pdf_text)
    md_tokens = set(_tokenize(markdown))

    numbers_pdf = _extract_numbers(pdf_text)
    numbers_md = _extract_numbers(markdown)

    dates_pdf = _extract_dates(pdf_text)
    dates_md = _extract_dates(markdown)

    table_count_pdf, table_cells_pdf = _docling_table_stats(doc)
    table_count_md = _markdown_table_count(markdown)

    heading_count_pdf = _docling_heading_count(doc)
    heading_count_md = _markdown_heading_count(markdown)

    spaced_cells = 0
    total_cells = 0
    spaced_text_items = 0
    multi_space_text_items = 0
    total_text_items = 0
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            if _is_toc_like_table(item):
                continue
            for cell in item.data.table_cells:
                total_cells += 1
                if is_spaced_text(cell.text):
                    spaced_cells += 1
        else:
            text = getattr(item, "text", None)
            if not text:
                continue
            total_text_items += 1
            if is_multi_space_text(text):
                multi_space_text_items += 1
            if needs_spacing_fix(text) and not (
                is_multi_space_text(text)
                and not is_spaced_text(text)
                and not is_collapsed_text(text)
            ):
                spaced_text_items += 1

    return AuditMetrics(
        token_coverage=_coverage(pdf_tokens, md_tokens),
        numeric_recall=_coverage(numbers_pdf, numbers_md),
        date_recall=_coverage(dates_pdf, dates_md),
        table_count_pdf=table_count_pdf,
        table_count_md=table_count_md,
        table_cells_pdf=table_cells_pdf,
        heading_count_pdf=heading_count_pdf,
        heading_count_md=heading_count_md,
        pdf_text_length=len(pdf_text),
        md_text_length=len(markdown),
        spaced_table_cells=spaced_cells,
        total_table_cells=total_cells,
        spaced_text_items=spaced_text_items,
        multi_space_text_items=multi_space_text_items,
        total_text_items=total_text_items,
    )


def split_markdown_pages(
    markdown: str, page_break_placeholder: str = "<!-- page break -->"
) -> list[str]:
    """Split Markdown into page-sized chunks using Docling page markers."""
    if page_break_placeholder not in markdown:
        return [markdown]
    parts = markdown.split(page_break_placeholder)
    return [part.strip() for part in parts if part.strip()]


def audit_doc_vs_markdown_per_page(
    doc: DoclingDocument,
    markdown: str,
    page_break_placeholder: str = "<!-- page break -->",
) -> list[PageAudit]:
    """Compute per-page audit stats to localize low-fidelity regions."""
    pages = sorted(doc.pages.keys())
    md_pages = split_markdown_pages(markdown, page_break_placeholder=page_break_placeholder)

    audits: list[PageAudit] = []
    for idx, page_no in enumerate(pages):
        page_doc = doc.filter(page_nrs={page_no})
        pdf_text = page_doc.export_to_text()
        md_text = md_pages[idx] if idx < len(md_pages) else ""

        pdf_tokens = _tokenize(pdf_text)
        md_tokens = set(_tokenize(md_text))
        numbers_pdf = _extract_numbers(pdf_text)
        numbers_md = _extract_numbers(md_text)
        dates_pdf = _extract_dates(pdf_text)
        dates_md = _extract_dates(md_text)

        audits.append(
            PageAudit(
                page_no=page_no,
                token_coverage=_coverage(pdf_tokens, md_tokens),
                numeric_recall=_coverage(numbers_pdf, numbers_md),
                date_recall=_coverage(dates_pdf, dates_md),
                pdf_text_length=len(pdf_text),
                md_text_length=len(md_text),
            )
        )

    return audits


def format_audit(metrics: AuditMetrics) -> str:
    """Render audit metrics in a compact, CLI-friendly string."""
    return (
        f"token_coverage={metrics.token_coverage:.2%}, "
        f"numeric_recall={metrics.numeric_recall:.2%}, "
        f"date_recall={metrics.date_recall:.2%}, "
        f"tables_pdf={metrics.table_count_pdf}, tables_md={metrics.table_count_md}, "
        f"table_cells_pdf={metrics.table_cells_pdf}, "
        f"headings_pdf={metrics.heading_count_pdf}, headings_md={metrics.heading_count_md}, "
        f"pdf_text_len={metrics.pdf_text_length}, md_text_len={metrics.md_text_length}, "
        f"spaced_cells={metrics.spaced_table_cells}/{metrics.total_table_cells}, "
        f"spacing_issue_text_items={metrics.spaced_text_items}/{metrics.total_text_items}, "
        f"multi_space_text_items={metrics.multi_space_text_items}/{metrics.total_text_items}"
    )
