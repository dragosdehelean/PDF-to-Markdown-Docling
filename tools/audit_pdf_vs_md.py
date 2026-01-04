from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from audit_utils import audit_doc_vs_markdown, format_audit
from conversion_utils import convert_pdf_to_doc
from docling_core.types.doc.base import ImageRefMode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit PDF vs Markdown conversion fidelity."
    )
    parser.add_argument("pdf", help="Path to the input PDF.")
    parser.add_argument("md", help="Path to the Markdown output.")
    parser.add_argument(
        "--pdf-backend",
        choices=("auto", "pypdfium2", "docling-parse-v4"),
        default="auto",
        help="PDF backend to use for audit extraction.",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="Accelerator device for Docling (default: cuda).",
    )
    parser.add_argument(
        "--ocr",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable OCR for audit extraction if needed.",
    )
    parser.add_argument(
        "--ocr-mode",
        choices=("off", "on", "auto"),
        default="off",
        help="OCR mode for audit extraction.",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=("auto", "tesseract", "rapidocr", "easyocr"),
        default="tesseract",
        help="OCR engine if OCR is enabled.",
    )
    parser.add_argument(
        "--ocr-lang",
        default="eng",
        help="OCR languages (e.g. 'eng' or 'ron+eng').",
    )
    parser.add_argument(
        "--force-full-page-ocr",
        action="store_true",
        help="Force full-page OCR when OCR is enabled.",
    )
    parser.add_argument(
        "--fix-spaced-tables",
        action="store_true",
        help="Hybrid fix for spaced-out table text using OCR just for tables.",
    )
    parser.add_argument(
        "--per-page",
        action="store_true",
        help="Print per-page audit summary.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Show top N worst pages by token coverage (default: 5).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    md_path = Path(args.md).expanduser().resolve()

    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if not md_path.exists():
        raise SystemExit(f"Markdown not found: {md_path}")

    markdown = md_path.read_text(encoding="utf-8")
    ocr_mode = args.ocr_mode
    if args.ocr:
        ocr_mode = "on"

    result, backend_name, _labels = convert_pdf_to_doc(
        input_path=pdf_path,
        image_mode=ImageRefMode.PLACEHOLDER,
        max_pages=None,
        page_range=None,
        ocr_mode=ocr_mode,
        ocr_engine=args.ocr_engine,
        ocr_lang=args.ocr_lang,
        force_full_page_ocr=args.force_full_page_ocr,
        fix_spaced_tables=args.fix_spaced_tables,
        device=args.device,
        pdf_backend=args.pdf_backend,
        quiet=True,
    )

    metrics = audit_doc_vs_markdown(result.document, markdown)
    print(f"Backend used: {backend_name}")
    print(format_audit(metrics))

    if args.per_page:
        from audit_utils import audit_doc_vs_markdown_per_page

        page_audits = audit_doc_vs_markdown_per_page(result.document, markdown)
        page_audits.sort(key=lambda p: p.token_coverage)
        print(f"Top {min(args.top, len(page_audits))} pages by lowest token coverage:")
        for audit in page_audits[: args.top]:
            print(
                f"  page {audit.page_no}: "
                f"token_coverage={audit.token_coverage:.2%}, "
                f"numeric_recall={audit.numeric_recall:.2%}, "
                f"date_recall={audit.date_recall:.2%}, "
                f"pdf_len={audit.pdf_text_length}, md_len={audit.md_text_length}"
            )


if __name__ == "__main__":
    main()
