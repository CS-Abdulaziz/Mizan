"""Rule-based quote detector (SPEC §7.2): a safety net that runs in parallel with the LLM extractor.

Each trigger phrase (SPEC §7.2 list) points at a quote: the nearest quoted segment right after it
(﴿…﴾, «…», "…", “…”), otherwise the rest of the sentence. The detector only finds spans; it never
judges them. Spans are character offsets into the original message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ClaimType = Literal["quran", "hadith"]

# (pattern, type guessed from the trigger)
TRIGGERS: list[tuple[re.Pattern[str], ClaimType]] = [
    (re.compile(r"قال\s+(?:الله\s+)?تعالى"), "quran"),
    (re.compile(r"قال\s+الله"), "quran"),
    (re.compile(r"قال\s+رسول\s+الله"), "hadith"),
    (re.compile(r"قال\s+النبي"), "hadith"),
    (re.compile(r"عن\s+النبي"), "hadith"),
    (re.compile(r"صلى\s+الله\s+عليه\s+وسلم|ﷺ"), "hadith"),
    (re.compile(r"\bAllah\s+(?:says|said)\b", re.I), "quran"),
    (re.compile(r"\bthe\s+Prophet\s*(?:\((?:ﷺ|pbuh|peace be upon him)\)|ﷺ|pbuh|peace be upon him)?\s*said\b", re.I), "hadith"),
    (re.compile(r"\bQur'?an\s+\d+\s*:\s*\d+", re.I), "quran"),
    (re.compile(r"\bSurah\b", re.I), "quran"),
    (re.compile(r"نبی\s+کریم\s*ﷺ?\s*نے\s+فرمایا"), "hadith"),
    (re.compile(r"اللہ\s+تعالیٰ\s+فرماتا\s+ہے"), "quran"),
    (re.compile(r"حدیث|حديث"), "hadith"),
]

QUOTE_PAIRS = {"﴿": "﴾", "«": "»", '"': '"', "“": "”", "„": "“"}
_OPEN = re.compile("[" + re.escape("".join(QUOTE_PAIRS)) + "]")
_SENTENCE_END = re.compile(r"[.!?؟\n]")
LOOKAHEAD_CHARS = 40  # how far after a trigger a quote may start
MAX_SPAN_CHARS = 400
MIN_SPAN_CHARS = 8


@dataclass(frozen=True)
class RuleSpan:
    type: ClaimType
    start: int
    end: int
    text: str


def _quoted_after(text: str, pos: int) -> tuple[int, int] | None:
    m = _OPEN.search(text, pos, min(len(text), pos + LOOKAHEAD_CHARS))
    if not m:
        return None
    close = QUOTE_PAIRS[m.group()]
    end = text.find(close, m.end())
    if end == -1 or end - m.end() > MAX_SPAN_CHARS:
        return None
    return m.end(), end


def _sentence_after(text: str, pos: int) -> tuple[int, int] | None:
    # skip separators such as ":" or "،" right after the trigger
    while pos < len(text) and text[pos] in " \t:：،,-–—":
        pos += 1
    m = _SENTENCE_END.search(text, pos)
    end = m.start() if m else len(text)
    end = min(end, pos + MAX_SPAN_CHARS)
    return (pos, end) if end > pos else None


def _strip(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in " \t\n\"'«»“”﴿﴾:،,":
        start += 1
    while end > start and text[end - 1] in " \t\n\"'«»“”﴿﴾:،,.":
        end -= 1
    return start, end


def detect(text: str) -> list[RuleSpan]:
    spans: list[RuleSpan] = []
    for pattern, ctype in TRIGGERS:
        for m in pattern.finditer(text):
            rng = _quoted_after(text, m.end()) or _sentence_after(text, m.end())
            if not rng:
                continue
            start, end = _strip(text, *rng)
            if end - start < MIN_SPAN_CHARS:
                continue
            if any(not (end <= s.start or start >= s.end) for s in spans):
                continue  # overlaps a span already found by an earlier trigger
            spans.append(RuleSpan(ctype, start, end, text[start:end]))
    return sorted(spans, key=lambda s: s.start)
