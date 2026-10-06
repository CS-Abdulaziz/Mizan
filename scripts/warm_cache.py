"""Warm the caches before a judging session (SPEC §6, §12; TASKS B25).

Sends every demo example and every bench item through /api/v1/check so dorar_cache holds every Dorar search
they need (and the API's LRU holds the demo results). Rate-limited for the free tiers; safe to re-run.

    python scripts/warm_cache.py --api https://<service>.onrender.com          # demo examples + bench items
    python scripts/warm_cache.py --api http://localhost:8000 --only-demo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def demo_texts() -> list[str]:
    from app.pipeline import quran_match
    from scripts_try_check import demo_messages  # type: ignore[import-not-found]

    index = quran_match.load_from_json()
    quran_match._index = index
    asyncio.run(quran_match.load_translations(index))
    return [m for _, m in demo_messages(index)]


def bench_texts() -> list[str]:
    f = ROOT / "bench" / "items.jsonl"
    return [json.loads(x)["text"] for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True, help="backend base URL")
    ap.add_argument("--only-demo", action="store_true")
    ap.add_argument("--per-minute", type=int, default=6)
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("scripts_try_check", ROOT / "scripts" / "try_check.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["scripts_try_check"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    texts = demo_texts() + ([] if args.only_demo else bench_texts())
    gap = 60.0 / max(1, args.per_minute)
    ok = fail = 0
    with httpx.Client(timeout=60) as c:
        for i, t in enumerate(texts, 1):
            t0 = time.perf_counter()
            r = c.post(args.api.rstrip("/") + "/api/v1/check", json={"text": t, "channel": "api"})
            if r.status_code == 200:
                ok += 1
            else:
                fail += 1
            print(f"[{i}/{len(texts)}] HTTP {r.status_code} {time.perf_counter() - t0:.1f} s", flush=True)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "30")))
            time.sleep(max(0.0, gap - (time.perf_counter() - t0)))
    print(f"done: {ok} ok, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
