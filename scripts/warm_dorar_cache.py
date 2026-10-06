"""Fill the shared dorar_cache (Supabase) from a machine that can reach Dorar (D-32).

For every Arabic quote in the demo examples, the bench items and any extra texts, runs the same deterministic
Dorar query the server uses first (`hadith_retrieve.span_query`), through the cache. Needs DATABASE_URL.

    python scripts/warm_dorar_cache.py [--extra "text" ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.examples import build_examples  # noqa: E402
from app.pipeline import hadith_retrieve, quran_match, rules_detect  # noqa: E402
from app.pipeline.extract import is_arabic  # noqa: E402
from app.sources import SourceUnavailable  # noqa: E402
from app.sources.dorar import DorarClient, cache_key  # noqa: E402


def arabic_spans(text: str) -> list[str]:
    spans = [s.text for s in rules_detect.detect(text) if is_arabic(s.text)]
    return spans or ([text] if is_arabic(text) else [])


async def main_async(extra: list[str]) -> int:
    from app.db import queries

    index = await quran_match.load_index()
    await quran_match.load_translations(index)
    await hadith_retrieve.load_hadeeth_index()
    texts = [e["text"] for e in build_examples()] + list(extra)
    items = ROOT / "bench" / "items.jsonl"
    texts += [json.loads(x)["text"] for x in items.read_text(encoding="utf-8").splitlines() if x.strip()]
    qs = []
    for t in texts:
        for sp in arabic_spans(t):
            q = hadith_retrieve.span_query(sp)
            if q and q not in qs:
                qs.append(q)
    client = DorarClient()
    hit = fetched = failed = 0
    try:
        for q in qs:
            if await queries.dorar_cache_get(cache_key(q)) is not None:
                hit += 1
                continue
            try:
                await client.search(q)
                fetched += 1
            except SourceUnavailable as e:
                failed += 1
                print("failed:", e.reason)
            await asyncio.sleep(0.5)
    finally:
        await client.aclose()
    print(f"queries {len(qs)}: already cached {hit}, fetched {fetched}, failed {failed}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", nargs="*", default=[])
    return asyncio.run(main_async(ap.parse_args().extra))


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
