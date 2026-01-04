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

Pick output path and extract images
```powershell
uv run python main.py "D:\\reports\\financial_report.pdf" -o "D:\\rag\\financial_report.md" --image-mode referenced --images-dir "D:\\rag\\financial_report_assets"
```

Options
- `--page-range 1:10` to process a subset of pages
- `--max-pages 30` to cap the number of processed pages
- `--ocr` to force OCR for scanned PDFs (default is off for digital PDFs)
- `--pdf-backend auto` to auto-select the cleaner backend (default is auto)
- `--device cuda` to run on GPU (use `auto` or `cpu` if CUDA is unavailable)
- `--quiet` to reduce Docling logs

Notes
- Default image mode is `placeholder` for clean RAG text. Use `referenced` to keep chart/table images.
- PDF conversion uses a high-accuracy layout model, accurate table extraction, and filters page headers/footers.
- Page breaks are marked with `<!-- page break -->` to help chunking for RAG.
- CUDA builds of `torch` and `torchvision` are pinned via `pyproject.toml` using the PyTorch cu128 index.

Quality check
```powershell
uv run python tools\\quality_report.py "D:\\rag\\financial_report.md"
```
