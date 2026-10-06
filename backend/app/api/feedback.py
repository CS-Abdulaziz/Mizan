"""POST /api/v1/feedback (SPEC §9, API_CONTRACT.md). Stores no message text."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.pipeline import orchestrator

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")


class FeedbackRequest(BaseModel):
    check_id: str
    claim_index: int = Field(ge=0, le=50)
    issue: Literal["wrong_verdict", "wrong_source", "other"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/feedback")
async def feedback(body: FeedbackRequest) -> dict[str, bool]:
    result = await orchestrator.load_result(body.check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.claim_index >= max(1, len(result.claims)):
        raise HTTPException(status_code=422, detail="claim_index_out_of_range")
    from app.db import queries

    try:
        await queries.insert_feedback(body.check_id, body.claim_index, body.issue, body.note)
    except Exception as e:  # noqa: BLE001
        log.warning("feedback_persist_failed", extra={"error": type(e).__name__})
        raise HTTPException(status_code=503, detail="service_unavailable") from None
    log.info("feedback", extra={"issue": body.issue, "claim_index": body.claim_index})
    return {"ok": True}
