"""Non-Arabic verse path (TASKS B12, D-19). Approved translations come from the QuranEnc cache / DB."""

from __future__ import annotations

import asyncio

import pytest

from app.pipeline import quran_match as qm

pytestmark = pytest.mark.skipif(not qm.QURAN_JSON.exists(), reason="data/quran.json missing")

REFS = [(2, 255), (112, 1), (55, 13)]  # selected by reference


@pytest.fixture(scope="module")
def ti():
    index = qm.load_from_json()
    qm._index = index
    t = asyncio.run(qm.load_translations(index))
    if t is None or not {"en", "ur"} <= set(t.texts):
        pytest.skip("approved translations unavailable (run scripts/ingest_quranenc.py)")
    return index, t


@pytest.mark.parametrize("lang", ["en", "ur"])
@pytest.mark.parametrize("ref", REFS)
async def test_approved_translation_finds_verse_in_top6(ti, lang: str, ref: tuple[int, int]) -> None:
    index, t = ti
    vi = index.by_ref[ref]
    span = t.texts[lang][vi]
    cands = await qm.match_translation(span, lang, [], index, use_vectors=False)
    assert vi in [c.verses[0] for c in cands], (ref, lang)
    assert len(cands) <= 6


async def test_partial_translation_still_found(ti) -> None:
    index, t = ti
    vi = index.by_ref[(2, 255)]
    words = t.texts["en"][vi].split()
    span = " ".join(words[5:25])
    cands = await qm.match_translation(span, "en", [], index, use_vectors=False)
    assert cands[0].verses == (vi,)


async def test_arabic_queries_add_candidates(ti) -> None:
    index, _ = ti
    vi = index.by_ref[(2, 255)]
    q = " ".join(index.verses[vi].imlaei_clean.split()[:6])
    cands = await qm.match_translation("unrelated words here", "en", [q], index, use_vectors=False)
    assert any(vi in c.verses and "arabic" in c.via for c in cands)
