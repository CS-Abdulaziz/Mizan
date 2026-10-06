from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import session

router = APIRouter()


@router.get("/health/dorar")
async def health_dorar() -> JSONResponse:
    """One fixed Dorar search from this server (no user input, no cache): status, content type, latency.
    Diagnoses whether the host can reach Dorar (e.g. a Cloudflare block on datacenter IPs)."""
    import time

    import httpx

    from app.core.config import get_settings
    from app.sources import USER_AGENT

    url = get_settings().dorar_base_url.rstrip("/") + "/dorar_api.json"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=12) as c:
            r = await c.get(url, params={"skey": "الصلاة"})
        ctype = r.headers.get("content-type", "")
        ok = r.status_code == 200 and "json" in ctype and '"ahadith"' in r.text[:200]
        body = {"ok": ok, "status": r.status_code, "content_type": ctype, "cf_ray": r.headers.get("cf-ray"),
                "server": r.headers.get("server"), "challenge": "Attention Required" in r.text or "cf-chl" in r.text,
                "latency_ms": int((time.perf_counter() - t0) * 1000), "base_url": url}
    except Exception as e:  # noqa: BLE001
        body = {"ok": False, "error": type(e).__name__, "latency_ms": int((time.perf_counter() - t0) * 1000),
                "base_url": url}
    return JSONResponse(body)


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness; queries the DB so the uptime pinger also keeps Supabase awake (SPEC §14, AMENDMENT 8)."""
    db_ok = await session.ping()
    return JSONResponse({"ok": db_ok, "db": db_ok}, status_code=200 if db_ok else 503)
