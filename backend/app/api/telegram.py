"""POST /telegram/webhook (SPEC §10): verified with X-Telegram-Bot-Api-Secret-Token."""

from __future__ import annotations

import hmac
import sys

from fastapi import APIRouter, HTTPException, Request

from app.core.config import REPO_ROOT, get_settings
from app.core.logging import get_logger

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))  # bot/ lives at the repo root (SPEC §15)

log = get_logger(__name__)
router = APIRouter()
_app = None


async def start_bot() -> None:
    global _app
    if not get_settings().enable_telegram_bot:
        return  # D-28: disabled; the webhook route answers 404
    from bot.telegram_bot import build_application

    _app = build_application()
    if _app is not None:
        await _app.initialize()
        await _app.start()
        log.info("telegram_bot_started")


async def stop_bot() -> None:
    global _app
    if _app is not None:
        await _app.stop()
        await _app.shutdown()
        _app = None


@router.post("/telegram/webhook")
async def webhook(request: Request) -> dict[str, bool]:
    if not get_settings().enable_telegram_bot:
        raise HTTPException(status_code=404, detail="not_found")
    secret = get_settings().telegram_webhook_secret
    got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or not hmac.compare_digest(got, secret):
        raise HTTPException(status_code=403, detail="forbidden")
    if _app is None:
        raise HTTPException(status_code=503, detail="bot_not_configured")
    from telegram import Update

    update = Update.de_json(await request.json(), _app.bot)
    await _app.process_update(update)
    return {"ok": True}
