"""POST /api/v1/check, GET /api/v1/check/{check_id} (SPEC §9, API_CONTRACT.md)."""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.ratelimit import KeyedLimiter
from app.models.result import CheckRequest, CheckResult
from app.pipeline import orchestrator

router = APIRouter(prefix="/api/v1")
limiter = KeyedLimiter(20, 60.0)  # 20 requests / minute per IP (SPEC §9)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/check", response_model=CheckResult)
async def check(body: CheckRequest, request: Request) -> CheckResult | JSONResponse:
    wait = limiter.hit(client_ip(request))
    if wait > 0:
        return JSONResponse({"detail": "rate_limited"}, status_code=429,
                            headers={"Retry-After": str(max(1, math.ceil(wait)))})
    try:
        return await orchestrator.run_check(body.text, body.channel, body.lang_hint)
    except orchestrator.InputTooLong:
        raise HTTPException(status_code=413, detail="text_too_long") from None
    except orchestrator.ServiceUnavailable:
        raise HTTPException(status_code=503, detail="service_unavailable") from None


@router.get("/check/{check_id}", response_model=CheckResult)
async def get_check(check_id: str) -> CheckResult:
    if not (len(check_id) == 32 and all(ch in "0123456789abcdef" for ch in check_id)):
        raise HTTPException(status_code=404, detail="not_found")
    result = await orchestrator.load_result(check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    return result
