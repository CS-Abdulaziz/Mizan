"""asyncpg connection pool (Supabase session pooler or direct URL, DECISIONS D-7)."""

from __future__ import annotations

import asyncio
import json

import asyncpg
from pgvector.asyncpg import register_vector

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

POOL_CREATE_TIMEOUT_S = 20.0  # TLS + auth to a remote pooler can take several seconds

_pool: asyncpg.Pool | None = None
_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None


class DatabaseUnavailable(Exception):
    pass


async def register_vector_any(conn: asyncpg.Connection) -> None:
    """Register the pgvector codec wherever the extension lives (Supabase installs it in `extensions`)."""
    schema = await conn.fetchval(
        "select n.nspname from pg_type t join pg_namespace n on n.oid = t.typnamespace where t.typname = 'vector' limit 1"
    )
    await register_vector(conn, schema=schema or "public")


async def _init_conn(conn: asyncpg.Connection) -> None:
    await register_vector_any(conn)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    """Create the pool on first use. Raises DatabaseUnavailable if DATABASE_URL is unset or unreachable."""
    global _pool, _lock, _lock_loop
    if _pool is not None:
        return _pool
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:  # a Lock is bound to the loop that first uses it
        _lock, _lock_loop = asyncio.Lock(), loop
    async with _lock:
        if _pool is not None:
            return _pool
        dsn = get_settings().database_url
        if not dsn:
            raise DatabaseUnavailable("DATABASE_URL is not set")
        try:
            _pool = await asyncio.wait_for(
                asyncpg.create_pool(dsn, min_size=1, max_size=10, init=_init_conn, command_timeout=10),
                timeout=POOL_CREATE_TIMEOUT_S,
            )
        except (OSError, asyncio.TimeoutError, asyncpg.PostgresError) as e:
            raise DatabaseUnavailable(type(e).__name__) from e
    return _pool


async def ping(timeout_s: float = 5.0) -> bool:
    """`select 1` against the DB (SPEC §14, AMENDMENT 8). Never raises."""

    try:
        pool = await get_pool()  # creation has its own timeout; the ping timeout covers the query only

        async def _ping() -> bool:
            async with pool.acquire() as conn:
                return await conn.fetchval("select 1") == 1

        return await asyncio.wait_for(_ping(), timeout=timeout_s)
    except Exception as e:  # noqa: BLE001 - health check must not raise
        log.warning("db_ping_failed", extra={"error": type(e).__name__})
        return False


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
