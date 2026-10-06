"""POST /api/v1/reply (SPEC §9, §7.6; API_CONTRACT.md)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.cache import TTLCache
from app.core.logging import get_logger
from app.pipeline import orchestrator
from app.pipeline.reply import LANG_NAMES, make_reply

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")
_replies: TTLCache[dict] = TTLCache(1024, 24 * 3600)


class ReplyRequest(BaseModel):
    check_id: str
    lang: str | None = None


class ReplyResponse(BaseModel):
    check_id: str
    lang: str
    reply: str | None
    reply_error: str | None


@router.post("/reply", response_model=ReplyResponse)
async def reply(body: ReplyRequest) -> ReplyResponse:
    result = await orchestrator.load_result(body.check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    lang = body.lang if body.lang in LANG_NAMES else (result.lang if result.lang in LANG_NAMES else "ar")
    if not result.claims:
        return ReplyResponse(check_id=body.check_id, lang=lang, reply=None, reply_error="no_claims")
    key = f"{body.check_id}:{lang}"
    cached = _replies.get(key)
    if cached is None:
        from app.db import queries

        try:
            cached = await queries.get_reply(body.check_id, lang)
        except Exception:  # noqa: BLE001
            cached = None
    if cached is None or cached.get("reply_error") == "llm_unavailable":
        text, err = await make_reply(result, lang)
        cached = {"reply": text, "reply_error": err}
        _replies.put(key, cached)
        if err != "llm_unavailable":
            from app.db import queries

            try:
                await queries.save_reply(body.check_id, lang, cached)
            except Exception as e:  # noqa: BLE001
                log.warning("reply_persist_failed", extra={"error": type(e).__name__})
    return ReplyResponse(check_id=body.check_id, lang=lang, reply=cached.get("reply"),
                         reply_error=cached.get("reply_error"))
