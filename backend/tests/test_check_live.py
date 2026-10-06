"""Live smoke (TASKS B16): 3 example messages through the real pipeline, each under 12 s. Run with --live."""

from __future__ import annotations

import importlib.util
import sys
import time

import pytest

from app.core.config import REPO_ROOT, get_settings
from app.pipeline import hadith_retrieve, orchestrator, quran_match

pytestmark = pytest.mark.live

spec = importlib.util.spec_from_file_location("try_check", REPO_ROOT / "scripts" / "try_check.py")
try_check = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["try_check"] = try_check
spec.loader.exec_module(try_check)  # type: ignore[union-attr]


async def test_three_live_messages_under_12s() -> None:
    if not (get_settings().llm_api_key and quran_match.QURAN_JSON.exists()):
        pytest.skip("LLM key or data/quran.json missing")
    index = await quran_match.load_index()
    await quran_match.load_translations(index)
    await hadith_retrieve.load_hadeeth_index()
    orchestrator._cache.clear()
    timings = []
    for label, msg in try_check.demo_messages(index):
        t0 = time.perf_counter()
        res = await orchestrator.run_check(msg, "api")
        dt = time.perf_counter() - t0
        timings.append((label, round(dt, 1), res.status, [c.verdict for c in res.claims]))
    print("\n", timings)
    await hadith_retrieve.close_dorar()
    assert [t[2] for t in timings] == ["ok", "ok", "no_claims"]
    assert all(t[1] < 12 for t in timings), timings
