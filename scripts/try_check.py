"""Run the full pipeline on demo messages built from source data (no scripture typed here).

    python scripts/try_check.py            # prints a compact summary per message
    python scripts/try_check.py --json     # full JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import FIXTURES_DIR  # noqa: E402
from app.pipeline import hadith_retrieve, orchestrator, quran_match  # noqa: E402
from app.pipeline.normalize import tokens  # noqa: E402


def demo_messages(index: quran_match.QuranIndex) -> list[tuple[str, str]]:
    v255 = index.verses[index.by_ref[(2, 255)]]
    partial = " ".join(tokens(v255.imlaei_clean)[:9])
    dorar = json.loads((FIXTURES_DIR / "dorar" / "api_plain.json").read_text(encoding="utf-8"))
    from app.sources.dorar import parse_results

    meta = json.loads((FIXTURES_DIR / "dorar" / "api_plain.meta.json").read_text(encoding="utf-8"))
    h = parse_results(dorar["ahadith"]["result"], meta["params"]["skey"])[0].text
    en_h = json.loads(next((FIXTURES_DIR / "hadeethenc").glob("one_*_en.json")).read_text(encoding="utf-8"))
    en_quote = re.findall(r'"([^"]+)"', en_h["hadeeth"])[-1]
    ti = quran_match.get_translations()
    en_verse = ti.texts["en"][index.by_ref[(112, 1)]] if ti else ""
    return [
        ("ar: verse + hadith", f"قال الله تعالى: ﴿{partial}﴾ وقال رسول الله ﷺ: «{h}»"),
        ("en: hadith + verse", f'The Prophet (pbuh) said: "{en_quote}" and Allah says in Surah Al-Ikhlas: "{en_verse}"'),
        ("en: no claims", "Why do Muslims face the Kaaba when they pray?"),
    ]


def video_messages(index: quran_match.QuranIndex) -> list[tuple[str, str]]:
    """The three demo inputs for the video (B26), built from source data only."""
    words = tokens(index.verses[index.by_ref[(2, 255)]].imlaei_clean)[:14]
    words[8] = "حاسوب"  # one word replaced by a plain modern word -> misquoted
    items = [json.loads(x) for x in (ROOT / "bench" / "items.jsonl").read_text(encoding="utf-8").splitlines() if x]
    fabricated = next(i for i in items if i["category"] == "fabricated_hadith" and i["split"] == "dev")
    fab_quote = re.search(r"[«:]\s*(.+?)»?$", fabricated["text"]).group(1).strip("» ")
    en_h = json.loads(next((FIXTURES_DIR / "hadeethenc").glob("one_*_en.json")).read_text(encoding="utf-8"))
    en_quote = re.findall(r'"([^"]+)"', en_h["hadeeth"])[-1]
    ti = quran_match.get_translations()
    ur_verse = ti.texts["ur"][index.by_ref[(112, 1)]] if ti else ""
    return [
        ("ar: altered verse + fabricated hadith",
         f"وصلتني هذه الرسالة: قال الله تعالى: ﴿{' '.join(words)}﴾ وقال رسول الله ﷺ: «{fab_quote}»"),
        ("en: authentic hadith", f'My friend shared this: the Prophet (peace be upon him) said: "{en_quote}". Is it authentic?'),
        ("ur: verse translation", f"اللہ تعالیٰ فرماتا ہے: «{ur_verse}» کیا یہ قرآن کی آیت ہے؟"),
    ]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--video", action="store_true", help="the three video demo inputs (B26)")
    args = ap.parse_args()
    index = await quran_match.load_index()
    await quran_match.load_translations(index)
    await hadith_retrieve.load_hadeeth_index()
    for label, msg in (video_messages(index) if args.video else demo_messages(index)):
        t0 = time.perf_counter()
        res = await orchestrator.run_check(msg, "api")
        dt = time.perf_counter() - t0
        print(f"\n== {label}: status={res.status} ({dt:.1f} s)")
        print(f"   input: {msg}")
        if args.json:
            print(res.model_dump_json(indent=1))
        for c in res.claims:
            locs = [f"{x.surah}:{x.ayah}" for x in c.evidence.locations]
            grades = [g.grade_class for g in c.evidence.gradings][:6]
            print(f"  [{c.index}] {c.type:8s} {c.verdict:15s} rel={c.relation} conf={c.confidence:.2f} "
                  f"src={c.evidence.source} locs={locs} grades={grades} diff={c.diff.kind if c.diff else None} "
                  f"notes={c.notes} status={c.source_status}")
        if res.message:
            print("  message:", res.message[:80])
    await hadith_retrieve.close_dorar()
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(asyncio.run(main()))
