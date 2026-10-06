"""Cost and latency per check from check_metrics (SPEC §12; TASKS B25).

    python scripts/cost_report.py [--days 7]

Mean tokens per check, latency p50/p95, provider mix (D-15), and cost from bench/prices.json
(0 on the free tiers; fill paid list prices there to estimate a paid deployment).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402


async def main_async(days: int) -> int:
    import asyncpg

    dsn = get_settings().database_url
    if not dsn:
        print("DATABASE_URL not set")
        return 2
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "select channel, status, n_claims, latency_ms, llm_tokens_in, llm_tokens_out, embed_tokens, llm_providers "
            "from check_metrics where created_at > now() - make_interval(days => $1)", days)
    finally:
        await conn.close()
    if not rows:
        print("no checks in the period")
        return 0
    prices = json.loads((ROOT / "bench" / "prices.json").read_text(encoding="utf-8"))["mizan"]
    lat = sorted(r["latency_ms"] for r in rows)
    tin = statistics.mean(r["llm_tokens_in"] or 0 for r in rows)
    tout = statistics.mean(r["llm_tokens_out"] or 0 for r in rows)
    providers: dict[str, int] = {}
    for r in rows:
        p = r["llm_providers"] or {}
        if isinstance(p, str):
            p = json.loads(p)
        for k, v in p.items():
            providers[k] = providers.get(k, 0) + v
    cost = (tin * prices["input_per_mtok"] + tout * prices["output_per_mtok"]) / 1e6
    print(f"checks: {len(rows)} in the last {days} days")
    print(f"mean claims per check: {statistics.mean(r['n_claims'] or 0 for r in rows):.2f}")
    print(f"latency p50 / p95: {lat[len(lat) // 2]} / {lat[min(len(lat) - 1, int(0.95 * len(lat)))]} ms")
    print(f"mean LLM tokens per check: {tin:.0f} in / {tout:.0f} out; embeddings {statistics.mean(r['embed_tokens'] or 0 for r in rows):.0f}")
    print(f"LLM calls by provider: {providers}")
    print(f"mean cost per check: ${cost:.5f} (prices from bench/prices.json)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    return asyncio.run(main_async(ap.parse_args().days))


if __name__ == "__main__":
    sys.exit(main())
