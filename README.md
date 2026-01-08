PDF to Markdown (Docling)

Simple CLI that converts a financial report PDF into Markdown ready for RAG ingestion.

Requirements
- Python 3.12+
- `uv`
- NVIDIA GPU with CUDA 12.8 drivers if you want GPU acceleration

Setup
```powershell
uv sync
```

Convert a PDF
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf"
```

Convert using .env (auto-loaded) — omit the positional arg if `FIN_REPORT_PDF` is set in `.env` or your shell:
```powershell
uv run python main.py
```

Preferred module form
```powershell
uv run python -m pdf_to_markdown_docling.cli --help
```

Convert + audit
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf" --audit
```

Pick output path and extract images
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf" -o "D:\\rag\\financial_report.md" --image-mode referenced --images-dir "D:\\rag\\financial_report_assets"
```

Options
- `--page-range 1:10` to process a subset of pages
- `--max-pages 30` to cap the number of processed pages
- `--ocr-mode off|on|auto` to control OCR (default off, auto retries only if extraction is poor)
- `--ocr` shorthand to force OCR on
- `--ocr-engine tesseract` to select the OCR engine
- `--ocr-lang ron+eng` to set OCR languages (if installed)
- `--force-full-page-ocr` to OCR the full page instead of detected regions
- `--spacing-fix pymupdf|docling|ocr` to repair spacing issues (default is OCR-free glyph reconstruction via PyMuPDF)
- `--fix-spaced-tables` deprecated alias for `--spacing-fix ocr`
- `--pdf-backend auto` to auto-select the cleaner backend (default is auto)
- `--device cuda` to run on GPU (use `auto` or `cpu` if CUDA is unavailable)
- `--audit` to run a PDF↔MD fidelity audit
- `--export-json` to save Docling JSON (lossless)
- `--quiet` to reduce Docling logs

Environment overrides (auto-loaded from `.env` in repo root if present)
- `FIN_REPORT_PDF=<path>` lets you omit the positional `input` argument.
- `KPI_OCR=0` to disable KPI extraction from image regions (skips the OCR-heavy pass).

Notes
- Default image mode is `placeholder` for clean RAG text. Use `referenced` to keep chart/table images.
- PDF conversion uses a high-accuracy layout model, accurate table extraction, and filters page headers/footers.
- Tables with header-spanned columns (e.g., currency + value pairs) are collapsed into single columns.
- Page breaks are marked with `<!-- page break -->`, and pages are annotated with `**[Page N]**`.
- Excess whitespace between words is normalized in non-table text.
- CUDA builds of `torch` and `torchvision` are pinned via `pyproject.toml` using the PyTorch cu128 index.

Quality check
```powershell
uv run python scripts\\quality_report.py "D:\\rag\\financial_report.md"
```

Audit PDF vs MD (standalone)
```powershell
uv run python scripts\\audit_pdf_vs_md.py "D:\\reports\\financial_report.pdf" "D:\\rag\\financial_report.md"
```

Integration tests
- Set `FIN_REPORT_PDF` in your environment or add it to a local `.env` file in the repo root.
- The integration test uses `page_range=(1, 8)` instead of `max_pages` because Docling marks inputs invalid when `max_pages` is lower than the PDF's actual page count.
