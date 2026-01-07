"""@fileoverview Helpers for exporting Docling artifacts to disk."""

from __future__ import annotations

import json
import re
from pathlib import Path

from docling_core.types.doc.document import DoclingDocument

_HTML_PAGE_MARKER_PATTERN = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
_MD_PAGE_MARKER_PATTERN = re.compile(r"\[//\]:\s*#\s*\(\s*page:\s*(\d+)\s*\)")
_VISIBLE_PAGE_MARKER_PATTERN = re.compile(
    r"\*\*\s*\[page(?::)?\s*\d+\]\s*\*\*", re.IGNORECASE
)
_PAGE_MARKER_PATTERN = re.compile(
    rf"(?:{_HTML_PAGE_MARKER_PATTERN.pattern}|{_MD_PAGE_MARKER_PATTERN.pattern}|{_VISIBLE_PAGE_MARKER_PATTERN.pattern})",
    re.IGNORECASE,
)
_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\s*<!--\s*image\s*-->\s*$")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_KPI_UNIT_PATTERN = re.compile(r"\b(?:RON|EUR|USD|LEI|MIL\.?)\b", re.IGNORECASE)
_KPI_VALUE_HINT_PATTERN = re.compile(r"\bvs\b|%|\d", re.IGNORECASE)
_AXIS_ALLOWED_PATTERN = re.compile(r"^[0-9A-Za-z%./+\-\s]+$")
_AXIS_TOKEN_PATTERN = re.compile(
    r"^(?:\d{1,4}(?:[.,]\d+)?%?|[12]\d{3}|Q[1-4]|9L|L9|mil|mil\.|RON|EUR|USD|LEI)$",
    flags=re.IGNORECASE,
)


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


def _is_kpi_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    if _HEADING_PATTERN.match(stripped):
        return False
    words = stripped.split()
    if len(words) > 5:
        return False
    letters = [ch for ch in stripped if ch.isalpha()]
    if not letters:
        return False
    upper = [ch for ch in letters if ch.isupper()]
    return len(upper) / len(letters) >= 0.7


def _is_kpi_value(text: str) -> bool:
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    if not _KPI_VALUE_HINT_PATTERN.search(stripped):
        return False
    if _KPI_UNIT_PATTERN.search(stripped):
        return True
    if "vs" in stripped.lower() or "%" in stripped:
        return True
    return False


def _is_heading_like_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _HEADING_PATTERN.match(stripped):
        return False
    if _PAGE_MARKER_PATTERN.match(stripped):
        return False
    if _IMAGE_PLACEHOLDER_PATTERN.match(stripped):
        return False
    if any(ch.isdigit() for ch in stripped):
        return False
    if len(stripped) > 120:
        return False
    if stripped.endswith((".", "!", "?", ";", ":")):
        return False
    words = stripped.split()
    if len(words) < 3:
        return False
    first_alpha = next((ch for ch in stripped if ch.isalpha()), "")
    if not first_alpha or not first_alpha.isupper():
        return False
    return True


def normalize_kpi_blocks(markdown: str, page_break_placeholder: str) -> str:
    """Join short KPI label/value blocks into a single line."""
    if not markdown.strip():
        return markdown

    has_breaks = page_break_placeholder in markdown
    raw_parts = markdown.split(page_break_placeholder) if has_breaks else [markdown]
    cleaned_parts: list[str] = []

    for part in raw_parts:
        blocks = [block for block in re.split(r"\n{2,}", part) if block.strip()]
        out_blocks: list[str] = []
        i = 0
        while i < len(blocks):
            block = blocks[i].strip()
            if _is_kpi_label(block):
                merged = block
                consumed = 1
                for j in range(i + 1, min(i + 3, len(blocks))):
                    candidate = blocks[j].strip()
                    if _is_kpi_value(candidate):
                        merged = f"{merged} {' '.join(candidate.split())}"
                        consumed += 1
                    else:
                        break
                if consumed > 1:
                    out_blocks.append(merged)
                    i += consumed
                    continue
            out_blocks.append(block)
            i += 1
        cleaned_parts.append("\n\n".join(out_blocks))

    if not has_breaks:
        return cleaned_parts[0]

    separator = f"\n\n{page_break_placeholder}\n\n"
    return separator.join(cleaned_parts)


def _is_axis_like_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return False
    if not _AXIS_ALLOWED_PATTERN.match(stripped):
        return False
    tokens = re.findall(r"[A-Za-z0-9%]+", stripped)
    if not tokens or len(tokens) > 6:
        return False
    numeric_tokens = sum(1 for tok in tokens if any(ch.isdigit() for ch in tok))
    if numeric_tokens == 0:
        return False
    if all(_AXIS_TOKEN_PATTERN.match(tok) for tok in tokens):
        return True
    if numeric_tokens >= len(tokens) - 1 and len(stripped) <= 20:
        return True
    return False


def remove_axis_like_lines(markdown: str, page_break_placeholder: str) -> str:
    """Remove standalone axis-like lines that often come from charts."""
    if not markdown.strip():
        return markdown

    has_breaks = page_break_placeholder in markdown
    raw_parts = markdown.split(page_break_placeholder) if has_breaks else [markdown]
    cleaned_parts: list[str] = []

    for part in raw_parts:
        lines_out: list[str] = []
        for line in part.splitlines():
            stripped = line.strip()
            if not stripped:
                lines_out.append(line)
                continue
            if _PAGE_MARKER_PATTERN.match(stripped):
                lines_out.append(line)
                continue
            if _IMAGE_PLACEHOLDER_PATTERN.match(stripped):
                lines_out.append(line)
                continue
            if _HEADING_PATTERN.match(stripped):
                lines_out.append(line)
                continue
            if "|" in stripped:
                lines_out.append(line)
                continue
            if _is_axis_like_line(stripped):
                continue
            lines_out.append(line)
        cleaned_parts.append("\n".join(lines_out))

    if not has_breaks:
        return cleaned_parts[0]

    separator = f"\n\n{page_break_placeholder}\n\n"
    return separator.join(cleaned_parts)


def remove_orphan_headings(markdown: str, page_break_placeholder: str) -> str:
    """Remove headings that end a page but have no content on the next page."""
    if not markdown.strip():
        return markdown

    has_breaks = page_break_placeholder in markdown
    raw_parts = markdown.split(page_break_placeholder) if has_breaks else [markdown]
    cleaned_parts: list[str] = []

    def _next_meaningful_line(start_index: int) -> str | None:
        for part_index in range(start_index, len(raw_parts)):
            for line in raw_parts[part_index].splitlines():
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                if _PAGE_MARKER_PATTERN.match(stripped_line):
                    continue
                if _IMAGE_PLACEHOLDER_PATTERN.match(stripped_line):
                    continue
                return stripped_line
        return None

    for idx, part in enumerate(raw_parts):
        lines = part.splitlines()
        last_idx = None
        for line_idx in range(len(lines) - 1, -1, -1):
            if lines[line_idx].strip():
                last_idx = line_idx
                break
        if last_idx is None:
            cleaned_parts.append(part)
            continue

        stripped = lines[last_idx].strip()
        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            heading_level = len(heading_match.group(1))
            next_line = _next_meaningful_line(idx + 1)
            if next_line is None:
                lines[last_idx] = ""
                part = "\n".join(lines).rstrip()
            else:
                next_match = _HEADING_PATTERN.match(next_line)
                is_superseding_heading = (
                    next_match is not None
                    and len(next_match.group(1)) <= heading_level
                )
                if is_superseding_heading or _is_heading_like_line(next_line):
                    lines[last_idx] = ""
                    part = "\n".join(lines).rstrip()

        cleaned_parts.append(part)

    if not has_breaks:
        return cleaned_parts[0]

    separator = f"\n\n{page_break_placeholder}\n\n"
    return separator.join(cleaned_parts)
