from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from quality import format_report, score_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a lightweight quality report for a Markdown file."
    )
    parser.add_argument("input", help="Path to the Markdown file to analyze.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    report = score_markdown(text)
    print(f"{input_path.name}: {format_report(report)}")


if __name__ == "__main__":
    main()
