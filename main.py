from __future__ import annotations

import argparse
import logging
from pathlib import Path

from docling.datamodel.document import ConversionStatus
from docling.document_converter import DocumentConverter
from docling_core.types.doc.base import ImageRefMode


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
        "--quiet",
        action="store_true",
        help="Reduce logging noise from Docling.",
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

    converter = DocumentConverter()
    convert_kwargs: dict[str, object] = {}
    if args.max_pages is not None:
        convert_kwargs["max_num_pages"] = args.max_pages
    if args.page_range is not None:
        convert_kwargs["page_range"] = args.page_range

    result = converter.convert(input_path, **convert_kwargs)
    if result.status in {ConversionStatus.FAILURE, ConversionStatus.SKIPPED}:
        raise SystemExit(f"Conversion failed with status: {result.status}")

    if result.status is ConversionStatus.PARTIAL_SUCCESS:
        logging.warning("Conversion completed with partial success.")

    result.document.save_as_markdown(
        output_path,
        artifacts_dir=images_dir,
        image_mode=image_mode,
    )

    print(f"Wrote Markdown to {output_path}")
    if images_dir and image_mode is ImageRefMode.REFERENCED:
        print(f"Saved images to {images_dir}")


if __name__ == "__main__":
    main()
