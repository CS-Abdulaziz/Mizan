"""POST /api/v1/check/file (SPEC §9, P2; TASKS B27): TXT / DOCX / PDF up to 5 MB -> paragraphs -> checks -> report.

Paragraphs are packed into chunks of at most MAX_INPUT_CHARS and checked one after another (free-tier quotas);
at most MAX_CHUNKS chunks per file. The response aggregates verdict counts and lists every quote with its chunk's
check_id (each check is stored 24 h like any other).
"""

from __future__ import annotations

import io
from collections import Counter

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.api.check import client_ip, limiter
from app.core.config import get_settings
from app.core.logging import get_logger
from app.pipeline import orchestrator

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1")

MAX_BYTES = 5 * 1024 * 1024
MAX_CHUNKS = 10


def extract_text(name: str, data: bytes) -> str:
    low = name.lower()
    if low.endswith(".txt"):
        return data.decode("utf-8-sig", errors="replace")
    if low.endswith(".docx"):
        import docx

        return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)
    raise HTTPException(status_code=415, detail="unsupported_file_type")


def chunk_paragraphs(text: str, max_chars: int) -> list[str]:
    paras = [p.strip() for p in text.replace("\r", "").split("\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        p = p[:max_chars]
        if cur and len(cur) + 1 + len(p) > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


@router.post("/check/file")
async def check_file(file: UploadFile, request: Request) -> dict:
    if limiter.hit(client_ip(request)) > 0:
        raise HTTPException(status_code=429, detail="rate_limited")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="file_too_large")
    text = extract_text(file.filename or "", data)
    chunks = chunk_paragraphs(text, get_settings().max_input_chars)
    if not chunks:
        raise HTTPException(status_code=422, detail="empty_file")
    truncated = len(chunks) > MAX_CHUNKS
    claims, checks = [], []
    for i, ch in enumerate(chunks[:MAX_CHUNKS]):
        try:
            res = await orchestrator.run_check(ch, "api")
        except orchestrator.ServiceUnavailable:
            raise HTTPException(status_code=503, detail="service_unavailable") from None
        checks.append({"chunk": i, "check_id": res.check_id, "status": res.status})
        for c in res.claims:
            claims.append({"chunk": i, "check_id": res.check_id, **c.model_dump(mode="json")})
    return {
        "filename": file.filename, "chunks": len(chunks), "checked_chunks": len(checks), "truncated": truncated,
        "summary": dict(Counter(c["verdict"] for c in claims)), "checks": checks, "claims": claims,
    }
