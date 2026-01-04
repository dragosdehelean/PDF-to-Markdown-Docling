PDF to Markdown (Docling)

Simple CLI that converts a financial report PDF into Markdown ready for RAG ingestion.

Requirements
- Python 3.12+
- `uv`

Setup
```powershell
uv sync
```

Convert a PDF
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf"
```

Pick output path and extract images
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf" -o "D:\\rag\\financial_report.md" --image-mode referenced --images-dir "D:\\rag\\financial_report_assets"
```

Options
- `--page-range 1:10` to process a subset of pages
- `--max-pages 30` to cap the number of processed pages
- `--quiet` to reduce Docling logs

Notes
- Default image mode is `placeholder` for clean RAG text. Use `referenced` to keep chart/table images.
