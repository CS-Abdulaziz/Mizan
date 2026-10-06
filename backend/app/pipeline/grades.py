"""Grade classification (SPEC §8.1, AMENDMENT 5). NEEDS SH SIGN-OFF (pending, D-20).

classify(book, grade_text) -> accepted | accepted_isnad | weak | very_weak | unclassified
"""

from __future__ import annotations

import re

from app.core import grade_rules as R
from app.pipeline.normalize import normalize_ar

_BRACKET = re.compile(r"^\s*\[([^\]]+)\]")


def _tok(s: str) -> list[str]:
    return normalize_ar(s).split()


def _has_phrase(text_tokens: list[str], phrase: str) -> bool:
    p = _tok(phrase)
    n = len(p)
    return n > 0 and any(text_tokens[i : i + n] == p for i in range(len(text_tokens) - n + 1))


def _any(text_tokens: list[str], phrases: list[str]) -> bool:
    return any(_has_phrase(text_tokens, p) for p in phrases)


def classify_text(grade_text: str) -> str:
    """Rules 3-7 on a grading text."""
    t = _tok(grade_text)
    if _any(t, R.VERY_WEAK):
        return "very_weak"
    if _any(t, R.NARRATOR_ONLY):
        return "unclassified"
    if _any(t, R.ISNAD_UNCLASSIFIED) and not _any(t, R.ACCEPTED_ISNAD):
        return "unclassified"
    if _any(t, R.ACCEPTED_ISNAD):
        return "accepted_isnad"
    if _any(t, R.WEAK):
        return "weak"
    if _any(t, R.ACCEPTED):
        return "accepted"
    return "unclassified"


def classify(book: str, grade_text: str) -> str:
    # Rule 1: Sahih al-Bukhari / Sahih Muslim
    if _any(_tok(book), R.SAHIHAYN_BOOKS):
        return "accepted"
    # Rule 2: a leading bracketed verdict is the verdict on the matn; classify that part only
    m = _BRACKET.match(grade_text or "")
    if m:
        return classify_text(m.group(1))
    return classify_text(grade_text or "")


def is_sahihayn(book: str) -> bool:
    return _any(_tok(book), R.SAHIHAYN_BOOKS)
