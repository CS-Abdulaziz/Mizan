"""Feedback endpoint (TASKS B23)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.result import CheckResult, ClaimResult
from app.pipeline import orchestrator

CID = "b" * 32


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from app.db import queries
    from app.main import app

    stored: list[tuple] = []

    async def fake_insert(check_id, claim_index, issue, note):
        stored.append((check_id, claim_index, issue, note))

    monkeypatch.setattr(queries, "insert_feedback", fake_insert)
    res = CheckResult(check_id=CID, status="ok", lang="en", disclaimer="d", expires_at="2026-10-07T00:00:00Z",
                      claims=[ClaimResult(index=0, type="hadith", span="s", span_start=0, span_end=1, lang="en",
                                          verdict="not_found")])
    orchestrator._by_id.put(CID, res)
    with TestClient(app) as c:
        yield c, stored


def test_valid_feedback_stored_without_text(client) -> None:
    c, stored = client
    r = c.post("/api/v1/feedback", json={"check_id": CID, "claim_index": 0, "issue": "wrong_verdict", "note": "x"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert stored == [(CID, 0, "wrong_verdict", "x")]  # ids + issue + optional note only, no message text


def test_issue_enum_validated(client) -> None:
    c, _ = client
    r = c.post("/api/v1/feedback", json={"check_id": CID, "claim_index": 0, "issue": "spam"})
    assert r.status_code == 422


def test_unknown_check_id_404(client) -> None:
    c, _ = client
    r = c.post("/api/v1/feedback", json={"check_id": "c" * 32, "claim_index": 0, "issue": "other"})
    assert r.status_code == 404
