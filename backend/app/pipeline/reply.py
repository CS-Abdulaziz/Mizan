"""Ready reply (SPEC §7.6, AMENDMENT 10): a short, polite reply built only from the verification output.

The model sees only the decided facts (verdicts, source names, locations, gradings as given, links). After
generation every URL in the reply must appear in that input; otherwise it is regenerated once, then dropped
(`reply: null`, `reply_error: "validation_failed"`). Replies are cached per language in check_results.reply.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.core import messages as M
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.client import LLMError, complete_json
from app.models.result import CheckResult

log = get_logger(__name__)

LANG_NAMES = {"ar": "Arabic", "en": "English", "ur": "Urdu"}
_URL = re.compile(r"https?://[^\s\"'<>)\]،؛؟۔«»]+")  # stop at Arabic/Urdu punctuation


class ReplyOut(BaseModel):
    reply: str


def facts(result: CheckResult) -> dict:
    """Only what the reply may use. No message text beyond each claim's own quoted span."""
    claims = []
    for c in result.claims:
        e = c.evidence
        claims.append({
            "quote": c.span, "type": c.type, "verdict": c.verdict, "relation": c.relation,
            "source": e.source, "locations": [f"{loc.surah_name_en} {loc.surah}:{loc.ayah}" for loc in e.locations],
            "authentic_arabic_text": e.text_arabic, "approved_translation": e.translation,
            "gradings": [{"scholar": g.mohaddith, "book": g.book, "grading": g.grade_text} for g in e.gradings[:6]],
            "link": e.url,
            "difference": (c.diff.model_dump() if c.diff else None),
            "authentic_alternative": (c.alternative.model_dump() if c.alternative else None),
            "notes": c.notes, "source_status": c.source_status,
        })
    return {"claims": claims}


def urls_ok(reply: str, allowed: str) -> bool:
    return all(u.rstrip(".,;:!?") in allowed for u in _URL.findall(reply))


async def make_reply(result: CheckResult, lang: str | None = None) -> tuple[str | None, str | None]:
    lang = lang if lang in LANG_NAMES else (result.lang if result.lang in LANG_NAMES else "ar")
    data = json.dumps(facts(result), ensure_ascii=False)
    variables = {"lang": LANG_NAMES[lang], "disclaimer": M.localized(M.DISCLAIMER, lang),
                 "verdicts": data.replace("</verdicts", "</ verdicts")}
    for attempt in range(2):  # generate, then regenerate once if validation fails
        try:
            out, _ = await complete_json("reply", variables, ReplyOut, get_settings().llm_model_reply)
        except LLMError as e:
            log.warning("reply_llm_failed", extra={"error": type(e).__name__})
            return None, "llm_unavailable"
        if urls_ok(out.reply, data):
            return out.reply.strip(), None
        log.warning("reply_foreign_url", extra={"attempt": attempt + 1})
    return None, "validation_failed"
