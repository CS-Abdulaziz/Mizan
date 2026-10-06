"""Verifier (SPEC §7.5, AMENDMENT 2, 3): one constrained LLM call per claim.

The model sees the quote and the candidates with their ids only (never gradings). It may return several
`match_ids` when they are all the same text. In code: every returned id must be one that was sent;
unknown ids are dropped and logged as hallucinations; if none remain it is no match. Then the
per-type confidence thresholds decide whether the relation is accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from app.core import thresholds as T
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.client import LLMUsage, complete_json

log = get_logger(__name__)

Relation = Literal["exact", "same_meaning", "altered", "different"]


class VerifyOut(BaseModel):
    match_ids: list[str] = Field(default_factory=list)
    relation: Relation
    altered_details: str | None = None
    confidence: float = 0.0


@dataclass
class VerifyCandidate:
    id: str
    text_ar: str
    translation: str | None = None  # approved translation in the quote language, when the source has one


@dataclass
class VerifyResult:
    match_ids: list[str]
    relation: Relation | None  # None = no accepted match
    raw_relation: Relation | None
    confidence: float
    altered_details: str | None
    hallucinated_ids: list[str] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)

    @property
    def matched(self) -> bool:
        return bool(self.match_ids) and self.relation in ("exact", "same_meaning", "altered")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_candidates(cands: list[VerifyCandidate]) -> str:
    lines = []
    for c in cands:
        body = _esc(c.text_ar) + (f" || {_esc(c.translation)}" if c.translation else "")
        lines.append(f'<c id="{_esc(c.id)}">{body}</c>')
    return "\n".join(lines)


def accept(kind: str, relation: Relation, confidence: float) -> Relation | None:
    """Per-type thresholds (SPEC §7.5). Returns the accepted relation, or None."""
    if relation == "different":
        return None
    if relation == "altered":
        return "altered" if confidence >= T.ALTERED_CONF else None
    if kind == "quran":
        return relation if confidence >= T.VERSE_ACCEPT_CONF else None
    if relation == "exact":
        return "exact" if confidence >= T.HADITH_EXACT_CONF else None
    return "same_meaning" if confidence >= T.HADITH_SAME_MEANING_CONF else None  # AMENDMENT 3


async def verify(span: str, lang: str, kind: str, candidates: list[VerifyCandidate]) -> VerifyResult:
    if not candidates:
        return VerifyResult([], None, None, 0.0, None)
    variables = {
        "lang": re.sub(r"[^a-z]", "", lang.lower())[:3] or "und",
        "span": _esc(span),
        "candidates": render_candidates(candidates),
    }
    out, usage = await complete_json("verify", variables, VerifyOut, get_settings().llm_model_verify)
    sent = {c.id for c in candidates}
    kept = [i for i in dict.fromkeys(out.match_ids) if i in sent]
    hallucinated = [i for i in out.match_ids if i not in sent]
    if hallucinated:
        log.warning("hallucination_ids_dropped", extra={"count": len(hallucinated), "stage": "verify"})
    confidence = max(0.0, min(1.0, out.confidence))
    relation = accept(kind, out.relation, confidence) if kept else None
    return VerifyResult(
        match_ids=kept if relation else [], relation=relation, raw_relation=out.relation, confidence=confidence,
        altered_details=out.altered_details if relation == "altered" else None,
        hallucinated_ids=hallucinated, usage=usage,
    )
