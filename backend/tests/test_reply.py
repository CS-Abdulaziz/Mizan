"""Ready reply (TASKS B21): URL validation, one regeneration, then reply null."""

from __future__ import annotations

import pytest

from app.llm.client import LLMUsage
from app.models.result import CheckResult, ClaimResult, Evidence
from app.pipeline import reply as rp


def result() -> CheckResult:
    return CheckResult(
        check_id="a" * 32, status="ok", lang="en", disclaimer="d", expires_at="2026-10-07T00:00:00Z",
        claims=[ClaimResult(index=0, type="hadith", span="quoted words", span_start=0, span_end=12, lang="en",
                            verdict="not_established",
                            evidence=Evidence(source="dorar", text_arabic="نص", url="https://dorar.net/hadith/search?q=x"))],
    )


def fake(replies: list[str], calls: list[dict]):
    async def _f(prompt_name, variables, schema, model):
        calls.append(variables)
        return rp.ReplyOut(reply=replies.pop(0)), LLMUsage()

    return _f


async def test_foreign_url_regenerated_then_null(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(rp, "complete_json", fake(["See https://evil.example/x", "Also https://other.example"], calls))
    text, err = await rp.make_reply(result(), "en")
    assert text is None and err == "validation_failed" and len(calls) == 2


async def test_regeneration_can_fix_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    ok = "Gently: this is not established. Source: https://dorar.net/hadith/search?q=x"
    monkeypatch.setattr(rp, "complete_json", fake(["bad https://evil.example", ok], calls))
    text, err = await rp.make_reply(result(), "en")
    assert text == ok and err is None and len(calls) == 2


async def test_prompt_gets_facts_language_and_disclaimer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(rp, "complete_json", fake(["fine, no links"], calls))
    await rp.make_reply(result(), "ur")
    v = calls[0]
    assert v["lang"] == "Urdu" and "not_established" in v["verdicts"] and v["disclaimer"]
    assert "https://dorar.net/hadith/search?q=x" in v["verdicts"]


@pytest.mark.live
@pytest.mark.parametrize("lang", ["en", "ur"])
async def test_live_reply(lang: str) -> None:
    from app.core.config import get_settings

    if not get_settings().llm_api_key:
        pytest.skip("LLM not configured")
    text, err = await rp.make_reply(result(), lang)
    print(f"\n[{lang}] {text}")
    assert err is None and text and len(text.split()) <= 200
