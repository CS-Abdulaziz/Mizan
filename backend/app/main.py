"""FastAPI application: routes, CORS, lifespan."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import check, feedback, file_report, health, reply, sources, telegram
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db import queries, session
from app.pipeline import hadith_retrieve, quran_match

log = get_logger(__name__)

CLEANUP_INTERVAL_S = 3600


async def cleanup_expired_results_forever() -> None:
    """Delete expired check_results at startup and every hour (SPEC §5, §13 privacy)."""
    while True:
        try:
            n = await queries.delete_expired_results()
            log.info("cleanup_expired_results", extra={"deleted": n})
        except Exception as e:  # noqa: BLE001 - keep the loop alive; DB may be down
            log.warning("cleanup_failed", extra={"error": type(e).__name__})
        await asyncio.sleep(CLEANUP_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("startup")
    try:
        await session.get_pool()  # connect once at startup (remote pooler handshake is slow)
    except session.DatabaseUnavailable as e:
        log.warning("db_unavailable_at_startup", extra={"error": str(e)})
    await quran_match.load_index()
    await quran_match.load_translations()
    await hadith_retrieve.load_hadeeth_index()
    cleanup = asyncio.create_task(cleanup_expired_results_forever())
    try:
        await telegram.start_bot()
    except Exception as e:  # noqa: BLE001 - the API must start even if the bot cannot
        log.warning("telegram_bot_start_failed", extra={"error": type(e).__name__})
    try:
        yield
    finally:
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup
        await telegram.stop_bot()
        await hadith_retrieve.close_dorar()
        await session.close_pool()
        log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Mizan API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(check.router)
    app.include_router(sources.router)
    app.include_router(reply.router)
    app.include_router(feedback.router)
    app.include_router(telegram.router)
    app.include_router(file_report.router)
    return app


app = create_app()
