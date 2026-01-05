"""@fileoverview Integration tests for table spacing fixes in Markdown output."""

from __future__ import annotations

from pathlib import Path

from audit_utils import needs_table_spacing_fix
from conversion_utils import convert_pdf_to_markdown
from docling_core.types.doc.base import ImageRefMode


ROOT_DIR = Path(__file__).resolve().parents[2]


def _first_cell_rows(markdown: str) -> list[str]:
    rows = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if parts:
            rows.append(parts[0])
    return rows


def test_table_headers_are_not_split(tmp_path: Path) -> None:
    """Validate that key table labels are not rendered as split words.

    WHY: Table headers are high-value signals for RAG and must be clean.
    Pre-conditions: long_report.pdf is present in the repository root.
    """
    pdf_path = ROOT_DIR / "long_report.pdf"
    if not pdf_path.exists():
        # WHY: Integration test depends on the sample report shipped with the repo.
        return

    output_path = tmp_path / "snippet.md"
    convert_pdf_to_markdown(
        input_path=pdf_path,
        output_path=output_path,
        image_mode=ImageRefMode.PLACEHOLDER,
        images_dir=None,
        max_pages=None,
        page_range=(2, 6),
        ocr_mode="off",
        ocr_engine="tesseract",
        ocr_lang="eng",
        force_full_page_ocr=False,
        spacing_fix="pymupdf",
        device="cpu",
        pdf_backend="docling-parse-v4",
        quiet=True,
    )

    markdown = output_path.read_text(encoding="utf-8")
    first_cells = _first_cell_rows(markdown)

    cifra = next((cell for cell in first_cells if "CIFRA DE AFACERI" in cell), "")
    produs = next((cell for cell in first_cells if "Produc" in cell), "")

    assert cifra, "Expected CIFRA DE AFACERI row not found in Markdown table."
    assert produs, "Expected Producția row not found in Markdown table."
    assert needs_table_spacing_fix(cifra) is False
    assert needs_table_spacing_fix(produs) is False
