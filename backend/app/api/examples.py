"""GET /api/v1/examples: demo inputs for the web app's example buttons, built on the server from source data
(Mushaf, approved translations, HadeethEnc, bench items from Dorar), so no scripture is typed in the frontend."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter

from app.core.config import FIXTURES_DIR, REPO_ROOT
from app.pipeline import hadith_retrieve, quran_match
from app.pipeline.normalize import tokens

router = APIRouter(prefix="/api/v1")
PLAIN_WORD = "حاسوب"  # a plain modern word, never in the Quran: makes the altered-verse example
_cache: list[dict] | None = None


def build_examples() -> list[dict]:
    out: list[dict] = []
    index = quran_match.get_index()
    fab = None
    items = REPO_ROOT / "bench" / "items.jsonl"
    if items.exists():
        for line in items.read_text(encoding="utf-8").splitlines():
            it = json.loads(line) if line.strip() else None
            if it and it["category"] == "fabricated_hadith" and it["split"] == "dev":
                m = re.search(r"«(.+?)»|:\s*(.+)$", it["text"])
                fab = (m.group(1) or m.group(2)).strip() if m else None
                break
    if index is not None:
        words = tokens(index.verses[index.by_ref[(2, 255)]].imlaei_clean)[:14]
        words[8] = PLAIN_WORD
        text = f"قال الله تعالى: ﴿{' '.join(words)}﴾"
        if fab:
            text += f" وقال رسول الله ﷺ: «{fab}»"
        out.append({"id": "ar", "label": "آية منقولة بخطأ + حديث متداول", "lang": "ar", "text": text})
    en = None
    ix = hadith_retrieve.get_hadeeth_index()
    if ix is not None and 5907 in ix.translations.get("en", {}):
        en = ix.translations["en"][5907]
    else:
        f = next(FIXTURES_DIR.glob("hadeethenc/one_*_en.json"), None)
        en = json.loads(f.read_text(encoding="utf-8"))["hadeeth"] if f else None
    if en:
        q = re.findall(r'"([^"]+)"', en)
        if q:
            out.append({"id": "en", "label": "English example", "lang": "en",
                        "text": f'The Prophet (peace be upon him) said: "{q[-1]}". Is it authentic?'})
    ti = quran_match.get_translations()
    if index is not None and ti is not None and "ur" in ti.texts:
        ur = ti.texts["ur"][index.by_ref[(112, 1)]]
        out.append({"id": "ur", "label": "Urdu example", "lang": "ur", "text": f"اللہ تعالیٰ فرماتا ہے: «{ur}»"})
    return out


@router.get("/examples")
async def examples() -> dict:
    global _cache
    if not _cache:
        _cache = build_examples()
    return {"examples": _cache}
