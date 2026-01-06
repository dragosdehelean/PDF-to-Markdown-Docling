"""@fileoverview Helpers for exporting Docling artifacts to disk."""

from __future__ import annotations

import json
import re
from pathlib import Path

from docling_core.types.doc.document import DoclingDocument

_HTML_PAGE_MARKER_PATTERN = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
_MD_PAGE_MARKER_PATTERN = re.compile(r"\[//\]:\s*#\s*\(\s*page:\s*(\d+)\s*\)")
_VISIBLE_PAGE_MARKER_PATTERN = re.compile(r"\*\*\s*\[page:\s*\d+\]\s*\*\*", re.IGNORECASE)
_PAGE_MARKER_PATTERN = re.compile(
    rf"(?:{_HTML_PAGE_MARKER_PATTERN.pattern}|{_MD_PAGE_MARKER_PATTERN.pattern}|{_VISIBLE_PAGE_MARKER_PATTERN.pattern})"
)
_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\s*<!--\s*image\s*-->\s*$")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def save_docling_json(doc: DoclingDocument, output_path: Path) -> None:
    """Persist the Docling document as JSON for lossless inspection."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = doc.export_to_dict()
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _strip_page_markers(markdown: str) -> str:
    return _PAGE_MARKER_PATTERN.sub("", markdown)


def add_visible_page_markers(markdown: str, page_break_placeholder: str) -> str:
    """Insert visible `[Page N]` markers before each page chunk."""
    markdown = _strip_page_markers(markdown)

    if page_break_placeholder not in markdown:
        if not markdown.strip():
            return markdown
        return f"**[Page 1]**\n\n{markdown.strip()}"

    parts = [part.strip() for part in markdown.split(page_break_placeholder)]
    out: list[str] = []
    page_no = 1
    for part in parts:
        if not part:
            continue
        out.append(f"**[Page {page_no}]**\n\n{part}")
        page_no += 1
    return f"\n\n{page_break_placeholder}\n\n".join(out)


def add_page_markers(markdown: str, page_break_placeholder: str) -> str:
    """Insert `page: N` markers before each page chunk."""
    markdown = _strip_page_markers(markdown)

    if page_break_placeholder not in markdown:
        if not markdown.strip():
            return markdown
        return f"[//]: # (page: 1)\n\n{markdown.strip()}"

    parts = [part.strip() for part in markdown.split(page_break_placeholder)]
    out: list[str] = []
    page_no = 1
    for part in parts:
        if not part:
            continue
        out.append(f"[//]: # (page: {page_no})\n\n{part}")
        page_no += 1
    return f"\n\n{page_break_placeholder}\n\n".join(out)


def _normalize_heading(text: str) -> str:
    return " ".join(text.split()).casefold()


def reduce_markdown_noise(
    markdown: str,
    page_break_placeholder: str,
    *,
    remove_image_placeholders: bool = False,
    repeated_heading_ratio: float = 0.3,
    min_repeated_heading_count: int = 3,
) -> str:
    """Remove noisy image placeholders and repeated top-of-page headings."""
    if not markdown.strip():
        return markdown

    has_breaks = page_break_placeholder in markdown
    raw_parts = markdown.split(page_break_placeholder) if has_breaks else [markdown]

    first_headings: list[str | None] = []
    for part in raw_parts:
        heading = None
        for line in part.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _IMAGE_PLACEHOLDER_PATTERN.match(stripped):
                continue
            if _PAGE_MARKER_PATTERN.match(stripped):
                continue
            match = _HEADING_PATTERN.match(stripped)
            if match:
                heading = match.group(2)
            break
        first_headings.append(heading)

    total_pages = len(raw_parts)
    if total_pages <= 1:
        frequent = set()
    else:
        counts: dict[str, int] = {}
        for heading in first_headings:
            if not heading:
                continue
            key = _normalize_heading(heading)
            counts[key] = counts.get(key, 0) + 1
        threshold = max(
            min_repeated_heading_count,
            int(total_pages * repeated_heading_ratio + 0.999),
        )
        frequent = {key for key, count in counts.items() if count >= threshold}

    kept_once: set[str] = set()
    cleaned_parts: list[str] = []
    for part, heading in zip(raw_parts, first_headings):
        heading_key = _normalize_heading(heading) if heading else None
        lines_out: list[str] = []
        removed_heading = False
        for line in part.splitlines():
            stripped = line.strip()
            if remove_image_placeholders and _IMAGE_PLACEHOLDER_PATTERN.match(stripped):
                continue
            if (
                not removed_heading
                and heading
                and heading_key in frequent
                and stripped
                and _HEADING_PATTERN.match(stripped)
                and _normalize_heading(_HEADING_PATTERN.match(stripped).group(2))
                == heading_key
            ):
                if heading_key in kept_once:
                    removed_heading = True
                    continue
                kept_once.add(heading_key)
            lines_out.append(line)
        cleaned_parts.append("\n".join(lines_out))

    if not has_breaks:
        return cleaned_parts[0]

    separator = f"\n\n{page_break_placeholder}\n\n"
    return separator.join(cleaned_parts)
