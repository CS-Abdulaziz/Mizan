"""Orchestrator + /api/v1/check (TASKS B16): contract, end-to-end with mocked externals, privacy of logs."""

from __future__ import annotations

import json
import logging
import re

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import FIXTURES_DIR, REPO_ROOT
from app.core.logging import JsonFormatter
from app.llm.client import LLMUsage
from app.models.extraction import Claim, Extraction
from app.models.result import CheckResult
from app.pipeline import extract as ex
from app.pipeline import hadith_retrieve as hr
from app.pipeline import orchestrator, quran_match
from app.pipeline import verify as vf
from app.pipeline.normalize import normalize_ar, tokens
from app.sources.dorar import parse_results

DORAR_URL = "https://dorar.net/dorar_api.json"
needs_quran = pytest.mark.skipif(not quran_match.QURAN_JSON.exists(), reason="data/quran.json missing")


# --------------------------------------------------------------------------- contract


def contract_examples() -> list[dict]:
    md = (REPO_ROOT / "docs" / "API_CONTRACT.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", md, re.S)
    return [json.loads(b) for b in blocks if '"check_id"' in b and '"status"' in b and '"claims"' in b]


def test_contract_examples_validate_against_models() -> None:
    examples = contract_examples()
    assert len(examples) >= 2
    for e in examples:
        CheckResult.model_validate(e)


def _keys(d: dict) -> set[str]:
    return set(d)


# --------------------------------------------------------------------------- end-to-end (mocked)


def dorar_fixture() -> tuple[str, str]:
    raw = (FIXTURES_DIR / "dorar" / "api_plain.json").read_text(encoding="utf-8")
    query = json.loads((FIXTURES_DIR / "dorar" / "api_plain.meta.json").read_text(encoding="utf-8"))["params"]["skey"]
    return raw, query


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch):
    """Mushaf from data/quran.json, empty HadeethEnc index, Dorar from fixture, LLM mocked."""
    index = quran_match.load_from_json()
    quran_match._index = index
    hr.set_hadeeth_index(None)
    orchestrator._cache.clear()
    raw, query = dorar_fixture()
    hadith_text = parse_results(json.loads(raw)["ahadith"]["result"], query)[0].text
    verse = " ".join(tokens(index.verses[index.by_ref[(2, 255)]].imlaei_clean)[:9])
    msg = f"قال الله تعالى: ﴿{verse}﴾ وقال رسول الله ﷺ: «{hadith_text}»"

    async def fake_extract(text: str):
        return Extraction(intent="claims", personal_ruling_request=False, claims=[
            Claim(type="quran", span=verse, lang="ar", claimed_source=None, ar_queries=[verse]),
            Claim(type="hadith", span=hadith_text, lang="ar", claimed_source="مسلم", ar_queries=[query]),
        ]), LLMUsage(input_tokens=100, output_tokens=50, providers={"gemini": 1})

    async def fake_verify(prompt_name, variables, schema, model):
        first = re.search(r'<c id="([^"]+)"', variables["candidates"]).group(1)
        return vf.VerifyOut(match_ids=[first], relation="exact", confidence=0.95), LLMUsage(providers={"gemini": 1})

    monkeypatch.setattr(ex, "_llm_extract", fake_extract)
    monkeypatch.setattr(vf, "complete_json", fake_verify)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(DORAR_URL).mock(return_value=httpx.Response(200, text=raw, headers={"content-type": "application/json"}))
        mock.post(url__regex=r"https://generativelanguage\.googleapis\.com/.*").mock(
            return_value=httpx.Response(429, json={}))  # embeddings unavailable -> vector path skipped (D-19)
        yield msg, verse, hadith_text
    hr.set_hadeeth_index(None)


@needs_quran
async def test_arabic_message_with_verse_and_hadith_gives_two_cards(pipeline) -> None:
    msg, verse, hadith_text = pipeline
    res = await orchestrator.run_check(msg, "web")
    assert res.status == "ok" and len(res.claims) == 2
    q, h = res.claims
    assert q.type == "quran" and q.verdict == "verified" and q.relation == "exact"
    assert [(x.surah, x.ayah) for x in q.evidence.locations] == [(2, 255)]
    assert q.evidence.source == "quran" and q.evidence.text_arabic and q.evidence.locations[0].url.startswith("https://quranenc.com/")
    assert msg[q.span_start:q.span_end] == verse
    assert h.type == "hadith" and h.evidence.source == "dorar" and h.evidence.gradings
    assert h.verdict in ("verified", "misquoted")  # graded from the Dorar fixture (Sahih Muslim present)
    assert all(g.grade_text is not None and g.book for g in h.evidence.gradings)
    assert msg[h.span_start:h.span_end] == hadith_text
    CheckResult.model_validate(res.model_dump(mode="json"))  # contract shape
    assert res.disclaimer and res.expires_at.endswith("Z") and len(res.check_id) == 32
    # same text again -> LRU cache returns the stored result
    assert (await orchestrator.run_check(msg, "web")).check_id == res.check_id


@needs_quran
async def test_logs_contain_no_message_text(pipeline, caplog: pytest.LogCaptureFixture) -> None:
    msg, verse, hadith_text = pipeline
    fmt = JsonFormatter()
    with caplog.at_level(logging.DEBUG):
        await orchestrator.run_check(msg, "web")
    dump = "\n".join(fmt.format(r) for r in caplog.records)
    assert caplog.records
    for fragment in (verse, hadith_text, normalize_ar(verse), msg[:30]):
        assert fragment not in dump


# --------------------------------------------------------------------------- API layer


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from app.api import check as check_api
    from app.main import app

    check_api.limiter._hits.clear()
    with TestClient(app) as c:
        yield c


def test_too_long_is_413(client: TestClient) -> None:
    r = client.post("/api/v1/check", json={"text": "x" * 4001, "channel": "web"})
    assert r.status_code == 413


def test_invalid_body_is_422(client: TestClient) -> None:
    assert client.post("/api/v1/check", json={"channel": "web"}).status_code == 422


def test_rate_limit_429_with_retry_after(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(text, channel, lang_hint):
        raise orchestrator.InputTooLong()

    monkeypatch.setattr(orchestrator, "run_check", fake_run)
    codes = [client.post("/api/v1/check", json={"text": "a"}).status_code for _ in range(21)]
    assert codes[:20] == [413] * 20 and codes[20] == 429


def test_unknown_check_id_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/check/" + "0" * 32).status_code == 404
    assert client.get("/api/v1/check/not-an-id").status_code == 404


def test_extraction_down_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(text, channel, lang_hint):
        raise orchestrator.ServiceUnavailable()

    monkeypatch.setattr(orchestrator, "run_check", fake_run)
    assert client.post("/api/v1/check", json={"text": "hello"}).status_code == 503


def test_sources_endpoint(client: TestClient) -> None:
    body = client.get("/api/v1/sources?lang=en").json()
    assert body["sources"] and "free tier" in body["privacy"] and body["limits"]


@needs_quran
async def test_d23_dropped_word_is_misquoted_even_if_verifier_says_same_meaning(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.pipeline.extract import ExtractedClaim

    index = quran_match.load_from_json()
    quran_match._index = index
    words = tokens(index.verses[index.by_ref[(2, 255)]].imlaei_clean)
    quote = " ".join(words[:12] + words[13:20])  # one word removed from the middle

    async def fake_verify(prompt_name, variables, schema, model):
        first = re.search(r'<c id="([^"]+)"', variables["candidates"]).group(1)
        return vf.VerifyOut(match_ids=[first], relation="same_meaning", confidence=0.98), LLMUsage()

    monkeypatch.setattr(vf, "complete_json", fake_verify)
    c = ExtractedClaim(type="quran", span=quote, span_start=0, span_end=len(quote), lang="ar", claimed_source=None,
                       ar_queries=[quote])
    out = await orchestrator.decide_quran(0, c, "ar", orchestrator.ClaimTrace())
    assert out.verdict == "misquoted" and out.diff.kind == "wording"
    assert any(o.op == "delete" and o.source == words[12] for o in out.diff.ops)


@needs_quran
async def test_d24_one_word_swapped_is_misquoted_even_if_verifier_says_different(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.pipeline.extract import ExtractedClaim

    index = quran_match.load_from_json()
    quran_match._index = index
    words = tokens(index.verses[index.by_ref[(2, 255)]].imlaei_clean)
    q = list(words[:20])
    q[8] = "حاسوب"
    quote = " ".join(q)

    async def fake_verify(prompt_name, variables, schema, model):
        return vf.VerifyOut(match_ids=[], relation="different", confidence=0.9), LLMUsage()

    monkeypatch.setattr(vf, "complete_json", fake_verify)
    c = ExtractedClaim(type="quran", span=quote, span_start=0, span_end=len(quote), lang="ar", claimed_source=None,
                       ar_queries=[quote])
    out = await orchestrator.decide_quran(0, c, "ar", orchestrator.ClaimTrace())
    assert out.verdict == "misquoted" and [(o.op, o.quoted) for o in out.diff.ops] == [("replace", "حاسوب")]
    assert [(x.surah, x.ayah) for x in out.evidence.locations] == [(2, 255)]
