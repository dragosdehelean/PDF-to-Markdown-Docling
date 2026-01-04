from __future__ import annotations

import argparse
import logging
from pathlib import Path

from docling.datamodel.document import ConversionStatus
from docling_core.types.doc.base import ImageRefMode

from conversion_utils import convert_pdf_to_markdown


def parse_page_range(value: str) -> tuple[int, int]:
    try:
        start_str, end_str = value.split(":")
        start = int(start_str)
        end = int(end_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Page range must look like 1:10.") from exc

    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("Page range must be 1-based and end >= start.")

    return start, end


def resolve_output_path(input_path: Path, output_arg: str | None) -> Path:
    if output_arg is None:
        return input_path.with_suffix(".md")

    if output_arg.endswith(("/", "\\")):
        return Path(output_arg) / f"{input_path.stem}.md"

    output_path = Path(output_arg)
    if output_path.exists() and output_path.is_dir():
        return output_path / f"{input_path.stem}.md"

    return output_path


def resolve_export_path(input_path: Path, export_arg: str) -> Path:
    if export_arg.endswith(("/", "\\")):
        return Path(export_arg) / f"{input_path.stem}.docling.json"

    export_path = Path(export_arg)
    if export_path.exists() and export_path.is_dir():
        return export_path / f"{input_path.stem}.docling.json"

    return export_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF financial report into Markdown using Docling."
    )
    parser.add_argument("input", help="Path to the input PDF.")
    parser.add_argument(
        "-o",
        "--output",
        help="Output Markdown file (default: <input>.md).",
    )
    parser.add_argument(
        "--image-mode",
        choices=("placeholder", "embedded", "referenced"),
        default="placeholder",
        help="How to represent images in Markdown (default: placeholder).",
    )
    parser.add_argument(
        "--images-dir",
        help="Directory for extracted images when using referenced mode.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to process.",
    )
    parser.add_argument(
        "--page-range",
        type=parse_page_range,
        help="Page range to process, 1-based and inclusive (e.g., 1:10).",
    )
    parser.add_argument(
        "--ocr",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable OCR for scanned PDFs (default: off for digital PDFs).",
    )
    parser.add_argument(
        "--ocr-mode",
        choices=("off", "on", "auto"),
        default="off",
        help="OCR mode: off, on, or auto (default: off).",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=("auto", "tesseract", "rapidocr", "easyocr"),
        default="tesseract",
        help="OCR engine when OCR is enabled (default: tesseract).",
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
        "--pdf-backend",
        choices=("auto", "pypdfium2", "docling-parse-v4"),
        default="auto",
        help="PDF text backend to use (default: auto).",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="Accelerator device: auto, cpu, mps, cuda, or cuda:N (default: cuda).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce logging noise from Docling.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run a PDF-to-Markdown audit after conversion.",
    )
    parser.add_argument(
        "--export-json",
        help="Save Docling JSON (lossless) to a file or directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    log_level = logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    output_path = resolve_output_path(input_path, args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    images_dir = None
    if args.images_dir:
        images_dir = Path(args.images_dir).expanduser().resolve()
        images_dir.mkdir(parents=True, exist_ok=True)

    image_mode_map = {
        "placeholder": ImageRefMode.PLACEHOLDER,
        "embedded": ImageRefMode.EMBEDDED,
        "referenced": ImageRefMode.REFERENCED,
    }
    image_mode = image_mode_map[args.image_mode]

    if image_mode is ImageRefMode.REFERENCED and images_dir is None:
        images_dir = output_path.parent / f"{output_path.stem}_assets"
        images_dir.mkdir(parents=True, exist_ok=True)

    ocr_mode = args.ocr_mode
    if args.ocr:
        ocr_mode = "on"

    result, backend_name = convert_pdf_to_markdown(
        input_path=input_path,
        output_path=output_path,
        image_mode=image_mode,
        images_dir=images_dir,
        max_pages=args.max_pages,
        page_range=args.page_range,
        ocr_mode=ocr_mode,
        ocr_engine=args.ocr_engine,
        ocr_lang=args.ocr_lang,
        force_full_page_ocr=args.force_full_page_ocr,
        device=args.device,
        pdf_backend=args.pdf_backend,
        quiet=args.quiet,
    )
    if result.status in {ConversionStatus.FAILURE, ConversionStatus.SKIPPED}:
        raise SystemExit(f"Conversion failed with status: {result.status}")

    if result.status is ConversionStatus.PARTIAL_SUCCESS:
        logging.warning("Conversion completed with partial success.")

    print(f"Wrote Markdown to {output_path}")
    if args.pdf_backend == "auto":
        print(f"Used PDF backend: {backend_name}")

    if args.audit:
        from audit_utils import (
            audit_doc_vs_markdown,
            audit_doc_vs_markdown_per_page,
            format_audit,
        )

        markdown_text = output_path.read_text(encoding="utf-8")
        metrics = audit_doc_vs_markdown(result.document, markdown_text)
        print("Audit:", format_audit(metrics))

        page_audits = audit_doc_vs_markdown_per_page(result.document, markdown_text)
        page_audits.sort(key=lambda p: p.token_coverage)
        worst = page_audits[:5]
        if worst:
            print("Worst pages by token coverage:")
            for audit in worst:
                print(
                    f"  page {audit.page_no}: "
                    f"token_coverage={audit.token_coverage:.2%}, "
                    f"numeric_recall={audit.numeric_recall:.2%}, "
                    f"date_recall={audit.date_recall:.2%}, "
                    f"pdf_len={audit.pdf_text_length}, md_len={audit.md_text_length}"
                )

    if args.export_json:
        from export_utils import save_docling_json

        export_path = resolve_export_path(input_path, args.export_json).resolve()
        save_docling_json(result.document, export_path)
        print(f"Wrote Docling JSON to {export_path}")
    if images_dir and image_mode is ImageRefMode.REFERENCED:
        print(f"Saved images to {images_dir}")


if __name__ == "__main__":
    main()
