"""Hadith retriever (SPEC §7.4, D-8, D-19).

Three paths in parallel, merged into one candidate list keyed by source id:
- A. Dorar: each Arabic query in turn (up to 3), stopping early once a result has token_set_ratio >= 90
  with the query. Results sharing a matn (token_set_ratio >= 92) are grouped into one candidate that carries
  every grading of the group.
- B. Vector: `match_hadith` over embedded HadeethEnc texts (optional; skipped when embeddings / DB fail).
- C. Local: rapidfuzz over HadeethEnc Arabic texts (Arabic queries) and over the approved HadeethEnc
  translations in the quote's language (the quote itself). HadeethEnc's search endpoint is unusable (D-8).

A Dorar failure sets `source_status = "source_unavailable"`; paths B and C still run.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from app.core import thresholds as T
from app.core.config import DATA_DIR
from app.core.logging import get_logger
from app.pipeline.normalize import normalize_ar
from app.sources import SourceUnavailable
from app.sources.dorar import DorarClient, DorarResult
from app.sources.hadeethenc import hadith_url

log = get_logger(__name__)

BULK_LOAD_TIMEOUT_S = 120  # one-off startup loads of whole tables from a remote DB


@dataclass
class HadithCandidate:
    id: str  # dorar:<12 hex> (group representative) | he:<HadeethEnc id>
    source: str  # dorar | hadeethenc
    text_ar: str
    text_clean: str
    score: float  # 0-100 similarity to the quote / queries (ranking only)
    url: str
    translation: str | None = None  # approved HadeethEnc translation in the quote language
    attribution: str | None = None  # HadeethEnc
    grade: str | None = None  # HadeethEnc, as given
    members: list[DorarResult] = field(default_factory=list)  # Dorar group: every chain / book of this matn
    via: set[str] = field(default_factory=set)


@dataclass
class RetrievalResult:
    candidates: list[HadithCandidate]
    source_status: str = "ok"  # ok | source_unavailable
    dorar_queries: int = 0
    embed_tokens: int = 0


# --------------------------------------------------------------------------- local HadeethEnc index


@dataclass
class HadeethIndex:
    ids: list[int]
    text_ar: list[str]
    text_clean: list[str]
    attribution: list[str | None]
    grade: list[str | None]
    translations: dict[str, dict[int, str]]  # lang -> id -> text
    trans_clean: dict[str, tuple[list[int], list[str]]]  # lang -> (ids, normalized texts) for lexical search


_hindex: HadeethIndex | None = None


def _build(rows: list[dict[str, Any]], trs: list[tuple[int, str, str]]) -> HadeethIndex:
    from app.pipeline.quran_match import normalize_translation

    rows = sorted(rows, key=lambda r: r["id"])
    translations: dict[str, dict[int, str]] = {}
    for hid, lang, text in trs:
        translations.setdefault(lang, {})[hid] = text
    trans_clean = {
        lang: (list(d), [normalize_translation(t) for t in d.values()]) for lang, d in translations.items() if lang != "ar"
    }
    return HadeethIndex(
        ids=[r["id"] for r in rows], text_ar=[r["text_ar"] for r in rows],
        text_clean=[r["text_ar_clean"] for r in rows], attribution=[r.get("attribution") for r in rows],
        grade=[r.get("grade") for r in rows], translations=translations, trans_clean=trans_clean,
    )


async def load_hadeeth_index() -> HadeethIndex | None:
    """From the DB (hadiths + hadith_translations), else the local HadeethEnc cache. Never raises."""
    global _hindex
    rows: list[dict[str, Any]] = []
    trs: list[tuple[int, str, str]] = []
    try:
        from app.db.session import get_pool

        pool = await get_pool()
        rows = [dict(r) for r in await pool.fetch("select id, text_ar, text_ar_clean, attribution, grade from hadiths", timeout=BULK_LOAD_TIMEOUT_S)]
        trs = [(r["hadith_id"], r["lang"], r["text"])
               for r in await pool.fetch("select hadith_id, lang, text from hadith_translations", timeout=BULK_LOAD_TIMEOUT_S)]
    except Exception as e:  # noqa: BLE001
        log.warning("hadeeth_index_db_unavailable", extra={"error": type(e).__name__})
    if not rows:
        cache = DATA_DIR / "raw" / "hadeethenc"
        for f in sorted(cache.glob("*_ar.json")) if cache.exists() else []:
            h = json.loads(f.read_text(encoding="utf-8"))
            if not h.get("text"):
                continue
            rows.append({"id": h["id"], "text_ar": h["text"], "text_ar_clean": normalize_ar(h["text"]),
                         "attribution": h.get("attribution"), "grade": h.get("grade")})
            trs.append((h["id"], "ar", h["text"]))
            for lang in ("en", "ur"):
                g = cache / f"{h['id']}_{lang}.json"
                if g.exists():
                    trs.append((h["id"], lang, json.loads(g.read_text(encoding="utf-8"))["text"]))
    if not rows:
        log.warning("hadeeth_index_unavailable")
        return None
    _hindex = _build(rows, trs)
    log.info("hadeeth_index_loaded", extra={"hadiths": len(_hindex.ids)})
    return _hindex


def get_hadeeth_index() -> HadeethIndex | None:
    return _hindex


def set_hadeeth_index(index: HadeethIndex | None) -> None:
    global _hindex
    _hindex = index


def _he_candidate(ix: HadeethIndex, pos: int, score: float, lang: str, via: str) -> HadithCandidate:
    hid = ix.ids[pos]
    return HadithCandidate(
        id=f"he:{hid}", source="hadeethenc", text_ar=ix.text_ar[pos], text_clean=ix.text_clean[pos], score=score,
        url=hadith_url(hid, lang if lang in ("ar", "en", "ur") else "ar"),
        translation=ix.translations.get(lang, {}).get(hid) if lang != "ar" else None,
        attribution=ix.attribution[pos], grade=ix.grade[pos], via={via},
    )


def path_c_local(ar_queries: list[str], span: str, lang: str) -> list[HadithCandidate]:
    ix = _hindex
    if ix is None:
        return []
    best: dict[int, float] = {}
    for q in ar_queries:
        qc = normalize_ar(q)
        if len(qc.split()) < 2:
            continue
        for _, sc, pos in process.extract(qc, ix.text_clean, scorer=fuzz.partial_ratio, limit=T.HADITH_LOCAL_TOP_K):
            best[pos] = max(best.get(pos, 0.0), sc)
    if lang not in ("ar", "") and lang in ix.trans_clean:
        from app.pipeline.quran_match import normalize_translation

        ids, texts = ix.trans_clean[lang]
        qn = normalize_translation(span)
        pos_of = {hid: i for i, hid in enumerate(ix.ids)}
        if len(qn.split()) >= 3:
            for scorer in (fuzz.token_set_ratio, fuzz.partial_ratio):
                for _, sc, j in process.extract(qn, texts, scorer=scorer, limit=T.HADITH_LOCAL_TOP_K):
                    p = pos_of.get(ids[j])
                    if p is not None:
                        best[p] = max(best.get(p, 0.0), sc)
    ranked = sorted(best.items(), key=lambda kv: -kv[1])[: T.HADITH_LOCAL_TOP_K]
    return [_he_candidate(ix, p, sc, lang, "local") for p, sc in ranked]


async def path_b_vector(span: str, lang: str) -> tuple[list[HadithCandidate], int]:
    ix = _hindex
    if ix is None:
        return [], 0
    try:
        from app.db.session import get_pool
        from app.llm.embeddings import get_embedding_client

        res = await get_embedding_client().embed_with_usage([span], input_type="query")
        pool = await get_pool()
        rows = await pool.fetch("select hadith_id, score from match_hadith($1, $2, $3)", res.vectors[0], lang,
                                T.HADITH_VECTOR_TOP_K)
    except Exception as e:  # noqa: BLE001 - optional path (D-19)
        log.info("hadith_vector_path_skipped", extra={"error": type(e).__name__})
        return [], 0
    pos_of = {hid: i for i, hid in enumerate(ix.ids)}
    out: dict[int, float] = {}
    for r in rows:
        p = pos_of.get(r["hadith_id"])
        if p is not None:
            out[p] = max(out.get(p, 0.0), float(r["score"]) * 100)
    return [_he_candidate(ix, p, sc, lang, "vector") for p, sc in out.items()], res.tokens


# --------------------------------------------------------------------------- Dorar


_dorar: DorarClient | None = None


def get_dorar() -> DorarClient:
    global _dorar
    if _dorar is None:
        _dorar = DorarClient()
    return _dorar


async def close_dorar() -> None:
    global _dorar
    if _dorar is not None:
        await _dorar.aclose()
        _dorar = None


def group_by_matn(results: list[DorarResult], queries_clean: list[str]) -> list[HadithCandidate]:
    groups: list[list[DorarResult]] = []
    for r in results:
        for g in groups:
            if fuzz.token_set_ratio(r.text_clean, g[0].text_clean) >= T.MATN_GROUP_RATIO:
                g.append(r)
                break
        else:
            groups.append([r])
    out: list[HadithCandidate] = []
    for g in groups:
        rep = max(g, key=lambda r: len(r.text_clean))  # the fullest wording represents the group
        score = max((fuzz.partial_ratio(q, r.text_clean) for q in queries_clean for r in g), default=0.0)
        out.append(HadithCandidate(
            id=rep.id, source="dorar", text_ar=rep.text, text_clean=rep.text_clean, score=score, url=rep.url,
            members=g, via={"dorar"},
        ))
    return out


async def path_a_dorar(ar_queries: list[str], client: DorarClient | None = None) -> tuple[list[HadithCandidate], int]:
    """Raises SourceUnavailable only if every query failed."""
    client = client or get_dorar()
    results: list[DorarResult] = []
    seen: set[str] = set()
    calls, failures = 0, 0
    queries = [q for q in ar_queries if normalize_ar(q)][:3]
    for q in queries:
        calls += 1
        try:
            found = await client.search(q)
        except SourceUnavailable:
            failures += 1
            continue
        qc = normalize_ar(q)
        for r in found:
            if r.id not in seen:
                seen.add(r.id)
                results.append(r)
        if any(fuzz.token_set_ratio(qc, r.text_clean) >= T.DORAR_EARLY_STOP for r in found):
            break
    if queries and failures == calls:
        raise SourceUnavailable("dorar", "all queries failed")
    return group_by_matn(results, [normalize_ar(q) for q in queries]), calls


# --------------------------------------------------------------------------- merge


async def retrieve(span: str, lang: str, ar_queries: list[str], *, dorar: DorarClient | None = None,
                   use_vectors: bool = True) -> RetrievalResult:
    a_task = asyncio.create_task(path_a_dorar(ar_queries, dorar)) if ar_queries else None
    b_task = asyncio.create_task(path_b_vector(span, lang)) if use_vectors else None
    c = path_c_local(ar_queries, span, lang)
    status, calls, a = "ok", 0, []
    if a_task is not None:
        try:
            a, calls = await a_task
        except SourceUnavailable:
            status = "source_unavailable"
            log.warning("dorar_unavailable")
    b, embed_tokens = await b_task if b_task is not None else ([], 0)

    merged: dict[str, HadithCandidate] = {}
    for cand in [*a, *b, *c]:
        m = merged.get(cand.id)
        if m is None:
            merged[cand.id] = cand
        else:
            m.score = max(m.score, cand.score)
            m.via |= cand.via
    ranked = sorted(merged.values(), key=lambda x: (-x.score, -len(x.via)))
    # neither source may crowd the other out: up to half the slots are reserved for each
    half = T.HADITH_VERIFIER_TOP // 2
    top = [x for x in ranked if x.source == "dorar"][:half] + [x for x in ranked if x.source != "dorar"][:half]
    top += [x for x in ranked if x not in top][: T.HADITH_VERIFIER_TOP - len(top)]
    top.sort(key=lambda x: (-x.score, -len(x.via)))
    return RetrievalResult(top, status, calls, embed_tokens)


HE_LINK_MIN_RATIO = 92.0  # a Dorar matn found inside a HadeethEnc text at this similarity is the same hadith
HE_LINK_MIN_WORDS = 5


def hadeethenc_for_matn(text_clean: str, lang: str) -> HadithCandidate | None:
    """Deterministically link a matched Dorar matn to the HadeethEnc entry with the same wording (if any),
    so the card can show the approved translation and HadeethEnc's own link."""
    ix = _hindex
    if ix is None or len(text_clean.split()) < HE_LINK_MIN_WORDS:
        return None
    hit = process.extractOne(text_clean, ix.text_clean, scorer=fuzz.partial_ratio, score_cutoff=HE_LINK_MIN_RATIO)
    if not hit:
        return None
    _, score, pos = hit
    return _he_candidate(ix, pos, score, lang, "linked")
