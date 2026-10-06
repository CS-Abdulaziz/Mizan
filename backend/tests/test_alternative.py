"""Authentic alternative (TASKS B22)."""

from __future__ import annotations

import pytest

from app.pipeline import alternative as alt
from app.pipeline import hadith_retrieve as hr


@pytest.fixture(autouse=True)
def index():
    hr.set_hadeeth_index(hr._build(
        [{"id": 7, "text_ar": "نص عربي", "text_ar_clean": "نص عربي", "attribution": "رواه مسلم", "grade": "صحيح"}],
        [(7, "ar", "نص عربي"), (7, "en", "english text")]))
    yield
    hr.set_hadeeth_index(None)


def hits(values):
    async def _h(span, k=5):
        return values
    return _h


async def test_above_threshold_offered_and_labelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alt, "vector_hits", hits([(7, 0.81)]))
    a = await alt.find_alternative("q", "en")
    assert a and a.id == 7 and a.label == "different_hadith_related_meaning" and a.translation == "english text"
    assert a.url.startswith("https://hadeethenc.com/en/")


async def test_below_threshold_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alt, "vector_hits", hits([(7, 0.74)]))
    assert await alt.find_alternative("q", "en") is None


async def test_no_embeddings_no_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(span, k=5):
        raise RuntimeError("quota")
    monkeypatch.setattr(alt, "vector_hits", boom)
    assert await alt.find_alternative("q", "ar") is None


async def test_matched_hadith_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alt, "vector_hits", hits([(7, 0.9)]))
    assert await alt.find_alternative("q", "en", exclude_ids={7}) is None


def test_only_for_not_established() -> None:
    import inspect

    from app.pipeline import orchestrator

    src = inspect.getsource(orchestrator.decide_hadith)
    assert 'if verdict == "not_established"' in src and "find_alternative" in src
