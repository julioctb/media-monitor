"""Keyword matching engine: accent- and case-insensitive word-boundary match.

Works for Spanish and English alike by folding both keyword and haystack:
unicode NFD decomposition -> drop combining marks -> casefold. A keyword
matches only on word boundaries, so "BUAP" does not match inside
"BUAPatito" and "oxxo" does not match "foxxo".
"""

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache


def fold_text(text: str) -> str:
    """Normalize text for matching: strip accents (NFD) and casefold."""
    decomposed = unicodedata.normalize("NFD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.casefold()


@lru_cache(maxsize=1024)
def keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Compiled word-boundary regex for a folded keyword.

    Multi-word keywords allow any whitespace run between words. The
    lookarounds (instead of \\b) keep boundaries correct for keywords that
    start or end with non-word characters.
    """
    folded = fold_text(keyword.strip())
    parts = [re.escape(part) for part in folded.split() if part]
    if not parts:
        # Blank keyword: compile a never-matching pattern.
        return re.compile(r"(?!)")
    body = r"\s+".join(parts)
    return re.compile(rf"(?<!\w){body}(?!\w)")


def matches_keyword(text: str, keyword: str) -> bool:
    """True if `keyword` appears in `text` as a whole word, accent-blind."""
    return keyword_pattern(keyword).search(fold_text(text)) is not None


def find_matching_keyword(text: str, keywords: Iterable[str]) -> str | None:
    """First keyword (in given order) matching `text`, or None."""
    folded = fold_text(text)
    for keyword in keywords:
        if keyword_pattern(keyword).search(folded):
            return keyword
    return None
