"""Extraction (SPEC §7.2, AMENDMENT 3, 7): one LLM call + the rule detector, merged and validated.

- The message is wrapped in <message> tags (data, not instructions); a literal "</message" inside the
  user text is defused before rendering.
- Post-validation: a claim whose span is not a substring of the message (after whitespace normalization)
  is dropped and logged as a hallucination. Offsets (`span_start`/`span_end`) come from the message.
- `ar_queries` not written in Arabic script are dropped (D-18). For an Arabic span the span itself is
  always available as a query.
- Rule-detected spans that overlap no LLM claim are added (type from the trigger).
- At most MAX_CLAIMS claims.
- If the LLM fails, extraction falls back to the rules alone (`llm_ok = False`).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.thresholds import MAX_CLAIMS
from app.llm.client import LLMError, LLMUsage, complete_json
from app.models.extraction import Extraction
from app.pipeline import rules_detect
from app.pipeline.normalize import normalize_ar

log = get_logger(__name__)

_ARABIC_LETTER = re.compile(r"[ء-ي]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
# Letters used in Urdu but not in Arabic: ٹ ڈ ڑ ں ہ ھ ے ی ۓ ک گ پ چ ژ
_URDU_LETTER = re.compile(r"[ٹڈڑںہھےیۓکگپچژ]")


@dataclass
class ExtractedClaim:
    type: str  # quran | hadith | attributed_saying
    span: str
    span_start: int
    span_end: int
    lang: str
    claimed_source: str | None
    ar_queries: list[str]
    origin: str = "llm"  # llm | rules


@dataclass
class ExtractionResult:
    intent: str
    personal_ruling_request: bool
    claims: list[ExtractedClaim] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    llm_ok: bool = True
    hallucinated_spans: int = 0


def script_lang(s: str) -> str:
    """'ur' if the text uses Urdu-only letters, 'ar' if mostly Arabic script, else 'en'."""
    ar, la = len(_ARABIC_LETTER.findall(s)), len(_LATIN_LETTER.findall(s))
    if ar == 0 or ar < la:
        return "en"
    return "ur" if len(_URDU_LETTER.findall(s)) >= 2 else "ar"


def is_arabic(s: str) -> bool:
    return script_lang(s) == "ar"


def find_span(text: str, span: str) -> tuple[int, int] | None:
    """Locate `span` in `text`, tolerating whitespace differences. Returns (start, end) or None."""
    span = span.strip()
    if not span:
        return None
    i = text.find(span)
    if i != -1:
        return i, i + len(span)
    parts = span.split()
    m = re.search(r"\s+".join(re.escape(p) for p in parts), text)
    return (m.start(), m.end()) if m else None


def tighten_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Drop a lead-in such as "قال الله تعالى:" and keep the inside of quotation marks when the span has them,
    so the matchers see only the quoted words (bench dev finding, D-23)."""
    seg = text[start:end]
    for o, c in rules_detect.QUOTE_PAIRS.items():
        i = seg.find(o)
        j = seg.find(c, i + 1) if i != -1 else -1
        if i != -1 and j != -1 and len(seg[i + 1 : j].split()) >= 2:
            return rules_detect._strip(text, start + i + 1, start + j)
    for pattern, _ in rules_detect.TRIGGERS:
        m = pattern.match(seg.lstrip())
        if m:
            lead = len(seg) - len(seg.lstrip()) + m.end()
            s2, e2 = rules_detect._strip(text, start + lead, end)
            if len(text[s2:e2].split()) >= 2:
                return s2, e2
    return rules_detect._strip(text, start, end)


def _trigger_type(text: str, start: int, end: int) -> str | None:
    """Type implied by an explicit trigger right before / at the start of the span ("Allah says" -> quran)."""
    window = text[max(0, start - 60) : min(end, start + 60)]
    for pattern, ctype in rules_detect.TRIGGERS:
        if ctype in ("quran", "hadith") and pattern.search(window) and pattern.pattern not in ("حدیث|حديث",):
            return ctype
    return None


def _claim_lang(span: str, llm_lang: str) -> str:
    detected = script_lang(span)
    if detected in ("ar", "ur"):
        return detected
    return (llm_lang or "en").lower()[:2] if (llm_lang or "en").lower()[:2] not in ("ar", "ur") else "en"


def _defuse(text: str) -> str:
    return re.sub(r"</\s*message", "</ message", text, flags=re.I)


def _clean_queries(queries: list[str], span: str) -> list[str]:
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and is_arabic(q) and normalize_ar(q) and q not in out:
            out.append(q)
    if not out and is_arabic(span):
        out.append(span)
    return out[:3]


async def _llm_extract(text: str) -> tuple[Extraction, LLMUsage]:
    s = get_settings()
    return await complete_json("extract", {"text": _defuse(text)}, Extraction, s.llm_model_extract)


async def extract(text: str) -> ExtractionResult:
    llm_task = asyncio.create_task(_llm_extract(text))
    rule_spans = rules_detect.detect(text)
    res = ExtractionResult(intent="no_claims", personal_ruling_request=False)
    try:
        ext, res.usage = await llm_task
    except LLMError as e:
        log.warning("extract_llm_failed", extra={"error": type(e).__name__})
        ext = None
        res.llm_ok = False

    if ext is not None:
        res.intent, res.personal_ruling_request = ext.intent, ext.personal_ruling_request
        for c in ext.claims:
            pos = find_span(text, c.span)
            if pos is None:
                res.hallucinated_spans += 1
                log.warning("hallucination_span_dropped", extra={"claim_type": c.type})
                continue
            raw_start = pos[0]
            pos = tighten_span(text, *pos)
            span = text[pos[0]:pos[1]]
            ctype = c.type
            if ctype == "attributed_saying":
                ctype = _trigger_type(text, raw_start, pos[1]) or ctype
            res.claims.append(
                ExtractedClaim(
                    type=ctype, span=span, span_start=pos[0], span_end=pos[1],
                    lang=_claim_lang(span, c.lang),
                    claimed_source=c.claimed_source, ar_queries=_clean_queries(c.ar_queries, span),
                )
            )

    for r in rule_spans:
        if any(not (r.end <= c.span_start or r.start >= c.span_end) for c in res.claims):
            continue
        res.claims.append(
            ExtractedClaim(
                type=r.type, span=r.text, span_start=r.start, span_end=r.end,
                lang=script_lang(r.text),
                claimed_source=None, ar_queries=[r.text] if is_arabic(r.text) else [], origin="rules",
            )
        )
        log.info("rules_added_claim", extra={"claim_type": r.type})

    res.claims.sort(key=lambda c: c.span_start)
    res.claims = res.claims[:MAX_CLAIMS]
    if res.claims and res.intent == "no_claims":
        res.intent = "claims"
    return res
