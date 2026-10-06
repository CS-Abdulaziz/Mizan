"""Authentic alternative (SPEC §8.5, P1): only for `not_established` hadith claims.

Dorar's own "authentic alternative" is not exposed by the official API (B02), so this is a vector search over
HadeethEnc: the top result is offered only if its similarity >= 0.75, and it is always labelled as a *different
hadith on a related meaning*, never as the correct version of the quote. With no embeddings available (free-tier
quota, D-19) there is simply no alternative: no lexical guess.
"""

from __future__ import annotations

from app.core import thresholds as T
from app.core.logging import get_logger
from app.models.result import Alternative

log = get_logger(__name__)


async def vector_hits(span: str, k: int = 5) -> list[tuple[int, float]]:
    """(HadeethEnc id, cosine similarity) over embedded translations and Arabic texts."""
    from app.db.session import get_pool
    from app.llm.embeddings import embed

    vec = (await embed([span], input_type="query"))[0]
    pool = await get_pool()
    rows = await pool.fetch(
        "select hadith_id, score from hadith_translations, lateral (select 1 - (embedding <=> $1) as score) s "
        "where embedding is not null order by embedding <=> $1 limit $2", vec, k)
    return [(r["hadith_id"], float(r["score"])) for r in rows]


async def find_alternative(span: str, lang: str, exclude_ids: set[int] | None = None) -> Alternative | None:
    from app.pipeline.hadith_retrieve import get_hadeeth_index
    from app.sources.hadeethenc import hadith_url

    ix = get_hadeeth_index()
    if ix is None:
        return None
    try:
        hits = await vector_hits(span)
    except Exception as e:  # noqa: BLE001 - optional feature
        log.info("alternative_skipped", extra={"error": type(e).__name__})
        return None
    pos_of = {hid: i for i, hid in enumerate(ix.ids)}
    for hid, score in hits:
        if exclude_ids and hid in exclude_ids:
            continue
        if score < T.ALTERNATIVE_MIN_SIMILARITY:
            return None
        p = pos_of.get(hid)
        if p is None:
            continue
        return Alternative(
            source="hadeethenc", id=hid, text_arabic=ix.text_ar[p],
            translation=ix.translations.get(lang, {}).get(hid) if lang in ("en", "ur") else None,
            attribution=ix.attribution[p], url=hadith_url(hid, lang if lang in ("ar", "en", "ur") else "ar"),
        )
    return None
