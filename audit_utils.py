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


@dataclass(frozen=True)
class PageAudit:
    page_no: int
    token_coverage: float
    numeric_recall: float
    date_recall: float
    pdf_text_length: int
    md_text_length: int


_SPACED_TEXT_PATTERN = re.compile(r"(?:\b[\wĂÂÎȘȚăâîșț]\b\s+){4,}")
_SPACED_DIGIT_PATTERN = re.compile(r"(?:\b\d\b\s+){3,}\b\d\b")
_SPLIT_WORD_PATTERN = re.compile(r"\b\w{2,}\s+\w\s+\w{2,}\b", flags=re.UNICODE)
_SPACED_NUMBER_PATTERN = re.compile(r"\d\s+[.,/]?\s*\d")


def is_spaced_text(text: str) -> bool:
    if len(text) < 6:
        return False
    if _SPACED_TEXT_PATTERN.search(text):
        return True
    if _SPACED_DIGIT_PATTERN.search(text):
        return True
    if _SPLIT_WORD_PATTERN.search(text):
        return True
    if _SPACED_NUMBER_PATTERN.search(text):
        return True

    tokens = [tok for tok in text.split() if tok]
    if len(tokens) < 6:
        return False
    single_tokens = [tok for tok in tokens if len(tok) == 1]
    return (len(single_tokens) / len(tokens)) >= 0.6


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
            tables.append(item)
    cell_count = sum(table.data.num_rows * table.data.num_cols for table in tables)
    return len(tables), cell_count


def _docling_heading_count(doc: DoclingDocument) -> int:
    heading_labels = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
    count = 0
    for item, _level in doc.iterate_items():
        if getattr(item, "label", None) in heading_labels:
            count += 1
    return count


def audit_doc_vs_markdown(doc: DoclingDocument, markdown: str) -> AuditMetrics:
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
    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            for cell in item.data.table_cells:
                total_cells += 1
                if is_spaced_text(cell.text):
                    spaced_cells += 1

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
    )


def split_markdown_pages(
    markdown: str, page_break_placeholder: str = "<!-- page break -->"
) -> list[str]:
    if page_break_placeholder not in markdown:
        return [markdown]
    parts = markdown.split(page_break_placeholder)
    return [part.strip() for part in parts if part.strip()]


def audit_doc_vs_markdown_per_page(
    doc: DoclingDocument,
    markdown: str,
    page_break_placeholder: str = "<!-- page break -->",
) -> list[PageAudit]:
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
    return (
        f"token_coverage={metrics.token_coverage:.2%}, "
        f"numeric_recall={metrics.numeric_recall:.2%}, "
        f"date_recall={metrics.date_recall:.2%}, "
        f"tables_pdf={metrics.table_count_pdf}, tables_md={metrics.table_count_md}, "
        f"table_cells_pdf={metrics.table_cells_pdf}, "
        f"headings_pdf={metrics.heading_count_pdf}, headings_md={metrics.heading_count_md}, "
        f"pdf_text_len={metrics.pdf_text_length}, md_text_len={metrics.md_text_length}, "
        f"spaced_cells={metrics.spaced_table_cells}/{metrics.total_table_cells}"
    )
