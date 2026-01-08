"""Compatibility shim for the CLI; delegates to the package entrypoint."""

from __future__ import annotations

import sys
from pathlib import Path


def _add_src_to_path() -> None:
    root = Path(__file__).resolve().parent
    src_dir = root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> None:
    _add_src_to_path()
    from pdf_to_markdown_docling.cli import main as package_main

    package_main()


if __name__ == "__main__":
    main()
