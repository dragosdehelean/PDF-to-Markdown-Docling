"""@fileoverview Targeted text normalization for encoding artifacts."""

from __future__ import annotations

_ROMANIAN_DIACRITICS = set("ăâîșțĂÂÎȘȚ")
_ALLOWED_LATIN1 = set("âîÂÎ")
_LIGATURE_MAP = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}


def _mojibake_score(text: str) -> int:
    score = 0
    for ch in text:
        code = ord(ch)
        if 0x80 <= code <= 0x9F:
            score += 3
            continue
        if 0x00C0 <= code <= 0x00FF and ch not in _ALLOWED_LATIN1:
            score += 1
    score += text.count("�") * 4
    return score


def _romanian_diacritic_count(text: str) -> int:
    return sum(1 for ch in text if ch in _ROMANIAN_DIACRITICS)


def normalize_mojibake_text(text: str) -> str:
    """Fix common UTF-8 mojibake by round-tripping Latin-1/CP1252."""
    if not text or len(text) < 4:
        return text

    base_score = _mojibake_score(text)
    if base_score == 0:
        return text

    base_diacritics = _romanian_diacritic_count(text)
    best = text
    best_score = base_score

    for encoding in ("cp1252", "latin1"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if candidate == text:
            continue
        cand_score = _mojibake_score(candidate)
        if cand_score >= best_score:
            continue
        cand_diacritics = _romanian_diacritic_count(candidate)
        if cand_diacritics < base_diacritics + 1 and cand_score >= 2:
            continue
        if len(candidate) < max(4, int(len(text) * 0.9)):
            continue
        best = candidate
        best_score = cand_score

    return best


def normalize_ligatures(text: str) -> str:
    """Replace common typographic ligatures with ASCII equivalents."""
    if not text:
        return text
    for key, value in _LIGATURE_MAP.items():
        if key in text:
            text = text.replace(key, value)
    return text
