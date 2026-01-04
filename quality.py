from __future__ import annotations

from dataclasses import dataclass
from collections import Counter


@dataclass(frozen=True)
class QualityReport:
    score: int
    short_line_count: int
    repeated_line_count: int
    control_char_count: int


def score_markdown(text: str) -> QualityReport:
    lines = [line.strip() for line in text.splitlines()]

    def is_noise_line(line: str) -> bool:
        if not line:
            return True
        if line.startswith("<!-- image"):
            return True
        if line.startswith("<!-- page break"):
            return True
        if line.startswith("#"):
            return True
        return False

    short_lines = [
        line
        for line in lines
        if line
        and len(line.replace(" ", "")) <= 4
        and any(ch.isalpha() for ch in line)
    ]

    counts = Counter(
        line.lower() for line in lines if len(line) >= 6 and not is_noise_line(line)
    )
    repeated_lines = [line for line, count in counts.items() if count >= 3]

    control_chars = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\t")

    score = 100 - (5 * len(short_lines)) - (2 * len(repeated_lines)) - control_chars
    return QualityReport(
        score=max(score, 0),
        short_line_count=len(short_lines),
        repeated_line_count=len(repeated_lines),
        control_char_count=control_chars,
    )


def format_report(report: QualityReport) -> str:
    return (
        "score="
        f"{report.score} short_lines={report.short_line_count} "
        f"repeated_lines={report.repeated_line_count} "
        f"control_chars={report.control_char_count}"
    )
