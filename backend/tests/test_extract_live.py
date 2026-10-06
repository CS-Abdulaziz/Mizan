"""One live extraction call against the configured LLM (run with --live; needs LLM_* in .env).

The message is built from saved source fixtures (no scripture typed by hand): an approved English
translation of a hadith (HadeethEnc) and an approved English translation of a verse (QuranEnc).
"""

from __future__ import annotations

import json
import re
import time

import pytest

from app.core.config import FIXTURES_DIR, get_settings
from app.llm.client import LLMClient
from app.models.extraction import Extraction

pytestmark = pytest.mark.live


def build_message() -> tuple[str, str, str]:
    hadith = json.loads(next((FIXTURES_DIR / "hadeethenc").glob("one_*_en.json")).read_text(encoding="utf-8"))
    sura = json.loads((FIXTURES_DIR / "quranenc" / "sura_english_rwwad_1.json").read_text(encoding="utf-8"))
    verse = sura["result"][1]  # 1:2, selected by reference
    # the Prophet's words only: the text inside the inner quotation marks of the source translation
    hadith_text = re.findall(r'"([^"]+)"', hadith["hadeeth"])[-1].strip()
    verse_text = re.sub(r"\[\d+\]", "", verse["translation"]).strip(" ,")  # drop footnote markers
    msg = (
        f"Someone forwarded this to our group. The Prophet (peace be upon him) said: \"{hadith_text}\" "
        f"And Allah says in Surah Al-Fatihah: \"{verse_text}\". Is this correct?"
    )
    return msg, hadith_text, verse_text


async def test_live_extraction_finds_both_quotes() -> None:
    s = get_settings()
    if not (s.llm_provider and s.llm_api_key and s.llm_model_extract):
        pytest.skip("LLM_PROVIDER / LLM_API_KEY / LLM_MODEL_EXTRACT not set")
    msg, _, _ = build_message()
    t0 = time.perf_counter()
    out, usage = await LLMClient(s).complete_json("extract", {"text": msg}, Extraction, s.llm_model_extract)
    latency = time.perf_counter() - t0
    print(f"\nlatency {latency:.1f} s, providers {usage.providers}, tokens {usage.input_tokens}/{usage.output_tokens}")
    print(out.model_dump_json(indent=1))
    assert out.intent == "claims"
    types = sorted(c.type for c in out.claims)
    assert types == ["hadith", "quran"]
    for c in out.claims:
        assert c.lang == "en" and c.ar_queries


def three_messages() -> list[tuple[str, str]]:
    """(lang, message) built from fixtures: en (hadith + verse), ar (hadith), ur (verse)."""
    en, _, _ = build_message()
    ar_body = json.loads(next((FIXTURES_DIR / "hadeethenc").glob("one_*_ar.json")).read_text(encoding="utf-8"))
    ar_h = max(re.findall(r"[«\"]([^«»\"]+)[»\"]", ar_body["hadeeth"]), key=len).strip()
    ar = f"أرسل لي أحدهم: قال رسول الله صلى الله عليه وسلم: «{ar_h}» هل هذا صحيح؟"
    ur_body = json.loads((FIXTURES_DIR / "quranenc" / "aya_urdu_junagarhi_2_255.json").read_text(encoding="utf-8"))
    ur_v = re.sub(r"\[\d+\]", "", ur_body["result"]["translation"]).split("۔")[0].strip()
    ur = f"اللہ تعالیٰ فرماتا ہے: {ur_v}۔ کیا یہ درست ہے؟"
    return [("en", en), ("ar", ar), ("ur", ur)]


async def test_live_pipeline_extract_three_messages() -> None:
    from app.pipeline import extract as ex

    s = get_settings()
    if not (s.llm_provider and s.llm_api_key and s.llm_model_extract):
        pytest.skip("LLM not configured")
    for lang, msg in three_messages():
        res = await ex.extract(msg)
        print(f"\n{lang}: intent={res.intent} providers={res.usage.providers} "
              f"claims={[(c.type, c.origin, c.lang, c.ar_queries[:1]) for c in res.claims]}")
        assert res.intent == "claims" and res.claims, lang
        for c in res.claims:
            assert all(ex.is_arabic(q) for q in c.ar_queries)
