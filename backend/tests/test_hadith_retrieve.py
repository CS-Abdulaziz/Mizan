"""Hadith retriever (TASKS B13) against saved Dorar / HadeethEnc fixtures."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.core.config import FIXTURES_DIR
from app.pipeline import hadith_retrieve as hr
from app.pipeline.normalize import normalize_ar
from app.sources.dorar import DorarClient, parse_results

DORAR_URL = "https://dorar.net/dorar_api.json"


def dorar_fixture() -> tuple[str, str]:
    raw = (FIXTURES_DIR / "dorar" / "api_plain.json").read_text(encoding="utf-8")
    query = json.loads((FIXTURES_DIR / "dorar" / "api_plain.meta.json").read_text(encoding="utf-8"))["params"]["skey"]
    return raw, query


@pytest.fixture(autouse=True)
def local_index():
    """A tiny HadeethEnc index built from the saved fixtures (ar/en/ur of one hadith)."""
    rows, trs = [], []
    for lang in ("ar", "en", "ur"):
        path = next((FIXTURES_DIR / "hadeethenc").glob(f"one_*_{lang}.json"))
        body = json.loads(path.read_text(encoding="utf-8"))
        hid = int(body["id"])
        if lang == "ar":
            rows.append({"id": hid, "text_ar": body["hadeeth"], "text_ar_clean": normalize_ar(body["hadeeth"]),
                         "attribution": body["attribution"], "grade": body["grade"]})
        trs.append((hid, lang, body["hadeeth"]))
    hr.set_hadeeth_index(hr._build(rows, trs))
    yield
    hr.set_hadeeth_index(None)


def test_group_by_matn_collects_all_chains_of_one_matn() -> None:
    raw, query = dorar_fixture()
    results = parse_results(json.loads(raw)["ahadith"]["result"], query)
    groups = hr.group_by_matn(results, [normalize_ar(query)])
    assert len(groups) < len(results)  # several chains collapsed
    biggest = max(groups, key=lambda g: len(g.members))
    assert len(biggest.members) >= 3
    books = {m.book for m in biggest.members}
    assert len(books) >= 2  # gradings from several books travel together
    assert {m.id for g in groups for m in g.members} == {r.id for r in results}  # nothing lost


@respx.mock
async def test_retrieve_merges_dorar_and_local() -> None:
    raw, query = dorar_fixture()
    respx.get(DORAR_URL).mock(return_value=httpx.Response(200, text=raw, headers={"content-type": "application/json"}))
    client = DorarClient(cache_get=None, cache_put=None)
    res = await hr.retrieve(query, "ar", [query], dorar=client, use_vectors=False)
    assert res.source_status == "ok" and res.dorar_queries == 1  # early stop after a strong hit
    sources = {c.source for c in res.candidates}
    assert sources == {"dorar", "hadeethenc"} and len(res.candidates) <= 6
    he = next(c for c in res.candidates if c.source == "hadeethenc")
    assert he.id.startswith("he:") and he.grade and he.url.startswith("https://hadeethenc.com/")


@respx.mock
async def test_dorar_down_sets_source_unavailable_and_local_still_runs() -> None:
    _, query = dorar_fixture()
    respx.get(DORAR_URL).mock(side_effect=httpx.ConnectTimeout("down"))
    client = DorarClient(cache_get=None, cache_put=None)
    res = await hr.retrieve(query, "ar", [query], dorar=client, use_vectors=False)
    assert res.source_status == "source_unavailable"
    assert res.candidates and all(c.source == "hadeethenc" for c in res.candidates)


async def test_english_quote_found_through_approved_translation() -> None:
    body = json.loads(next((FIXTURES_DIR / "hadeethenc").glob("one_*_en.json")).read_text(encoding="utf-8"))
    span = body["hadeeth"][:200]
    res = await hr.retrieve(span, "en", [], use_vectors=False)
    assert res.candidates and res.candidates[0].id == f"he:{body['id']}"
    assert res.candidates[0].translation  # approved translation in the quote language
