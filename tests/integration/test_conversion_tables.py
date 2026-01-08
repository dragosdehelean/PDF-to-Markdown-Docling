"""@fileoverview Integration tests for generic table spacing fixes."""

from __future__ import annotations

import os
from pathlib import Path

from pdf_to_markdown_docling.audit_utils import needs_table_spacing_fix
from pdf_to_markdown_docling.conversion_utils import convert_pdf_to_markdown
from docling_core.types.doc.base import ImageRefMode


ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PDF_PATH = "FIN_REPORT_PDF"
ENV_FILE = ROOT_DIR / ".env"


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    # WHY: Minimal .env parser to avoid adding a dependency just for tests.
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _resolve_pdf_path() -> Path | None:
    value = os.environ.get(ENV_PDF_PATH, "").strip()
    if not value:
        env_values = _load_env_file(ENV_FILE)
        value = env_values.get(ENV_PDF_PATH, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _is_separator_row(parts: list[str]) -> bool:
    if not parts:
        return False
    stripped = [part.strip() for part in parts]
    if not stripped:
        return False
    for part in stripped:
        if not part:
            continue
        if set(part) - set("-:"):
            return False
    return True


def _first_column_cells(markdown: str) -> list[str]:
    rows: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if _is_separator_row(parts):
            continue
        if parts:
            rows.append(parts[0])
    return rows


def _has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _has_digits(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _should_check_cell(text: str) -> bool:
    if not text or len(text) < 6:
        return False
    if not _has_letters(text):
        return False
    if _has_digits(text):
        return False
    return True


def _cells_with_spacing_issues(cells: list[str]) -> list[str]:
    return [cell for cell in cells if needs_table_spacing_fix(cell)]


def test_table_headers_are_not_split(tmp_path: Path) -> None:
    """Validate that table row labels are not rendered as split words.

    WHY: Table headers are high-value signals for RAG and must be clean.
    Pre-conditions: FIN_REPORT_PDF points to a representative financial report.
    """
    pdf_path = _resolve_pdf_path()
    if not pdf_path:
        # WHY: Skip when no representative report is configured.
        return
    if not pdf_path.exists():
        # WHY: Skip when the configured report path is missing.
        return

    output_path = tmp_path / "snippet.md"
    convert_pdf_to_markdown(
        input_path=pdf_path,
        output_path=output_path,
        image_mode=ImageRefMode.PLACEHOLDER,
        images_dir=None,
        max_pages=None,
        page_range=(1, 8),
        ocr_mode="off",
        ocr_engine="tesseract",
        ocr_lang="eng",
        force_full_page_ocr=False,
        spacing_fix="pymupdf",
        device="cuda",
        pdf_backend="docling-parse-v4",
        quiet=True,
    )

    markdown = output_path.read_text(encoding="utf-8")
    first_cells = _first_column_cells(markdown)
    if not first_cells:
        # WHY: Skip if the selected pages contain no tables.
        return

    candidates = [cell for cell in first_cells if _should_check_cell(cell)]
    if not candidates:
        # WHY: Skip if no sufficiently long alphabetic labels are present.
        return

    bad_cells = _cells_with_spacing_issues(candidates)
    assert not bad_cells
