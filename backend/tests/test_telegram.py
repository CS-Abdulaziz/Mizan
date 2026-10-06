"""Telegram bot (TASKS B24): escaping, card splitting, webhook secret, user-id hashing."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT
from app.models.result import CheckResult, ClaimResult, Evidence, Grading

sys.path.insert(0, str(REPO_ROOT))
from bot import telegram_bot as tb  # noqa: E402


def claim(i: int, span: str, verdict: str = "not_established") -> ClaimResult:
    return ClaimResult(index=i, type="hadith", span=span, span_start=0, span_end=len(span), lang="ar", verdict=verdict,
                       evidence=Evidence(source="dorar", gradings=[Grading(mohaddith="m", book="كتاب <b>", page="1",
                                                                           grade_text="موضوع & باطل",
                                                                           grade_class="very_weak")]))


def res(claims: list[ClaimResult]) -> CheckResult:
    return CheckResult(check_id="d" * 32, status="ok", lang="ar", claims=claims, disclaimer="أداة <آلية>",
                       reply_available=True, expires_at="2026-10-07T00:00:00Z")


def test_html_is_escaped() -> None:
    out = "\n".join(tb.format_result(res([claim(0, "<script>alert(1)</script> & x")])))
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "&amp; باطل" in out and "كتاب &lt;b&gt;" in out and "&lt;آلية&gt;" in out
    assert "<b>" in out  # our own markup survives


def test_split_on_card_boundaries() -> None:
    claims = [claim(i, ("كلمة " * 12).strip() + f" {i}") for i in range(80)]
    chunks = tb.format_result(res(claims))
    assert len(chunks) > 1 and all(len(c) <= tb.MAX_LEN for c in chunks)
    cards = [tb.card(c, "ar") for c in claims]
    joined = "\n\n".join(chunks)
    for cd in cards:
        assert cd in joined  # no card was cut in the middle


def test_split_cards_never_mid_line() -> None:
    parts = ["a" * 3000, "b" * 3000, "c" * 100]
    chunks = tb.split_cards(parts, limit=4096)
    assert chunks == ["a" * 3000, "b" * 3000 + "\n\n" + "c" * 100]


def test_user_ids_are_hashed() -> None:
    k = tb.user_key(123456789)
    assert "123456789" not in k and len(k) == 24 and k == tb.user_key(123456789)


def test_webhook_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.post("/telegram/webhook", json={}).status_code == 404  # disabled by default (D-28)
    monkeypatch.setenv("ENABLE_TELEGRAM_BOT", "true")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as c:
            assert c.post("/telegram/webhook", json={}).status_code == 403
            r = c.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
            assert r.status_code == 403
            r = c.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"})
            assert r.status_code == 503  # no bot token configured in tests
    finally:
        monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET")
        monkeypatch.delenv("ENABLE_TELEGRAM_BOT")
        get_settings.cache_clear()
