"""Parse a cited Quran location (SPEC §7.3 step 8): '2:255', 'Al-Baqarah 255', 'البقرة 255',
'سورة البقرة، الآية ٢٥٥', 'Surah 2 verse 255', 'Al-Imran 2'. Arabic-Indic and Latin digits.

Surah names come from the Mushaf index (source data), matched fuzzily after folding diacritics and the
article. Returns (surah, ayah or None), or None when nothing parseable is cited.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from rapidfuzz import fuzz, process

from app.pipeline.normalize import normalize_ar

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_REF = re.compile(r"(\d{1,3})\s*[:：/.]\s*(\d{1,3})")
_SURAH_NUM_VERSE = re.compile(
    r"(?:surah|surat|sura|chapter|سورة|سوره)\s*(?:no\.?|number|رقم)?\s*(\d{1,3})\D{0,20}?(?:verse|ayah|aya|ayat|آية|اية|الآية|الاية)\s*(\d{1,3})",
    re.I,
)
_NOISE_WORDS = re.compile(
    r"\b(?:surah|surat|sura|chapter|verse|verses|ayah|aya|ayat|quran|qur'an|koran|the|holy|no|number)\b", re.I
)
_AR_NOISE = re.compile(r"(?:^|\s)(?:سوره|ايه|الايه|ايات|القران|الكريم|رقم|سورت|آیت|سورۃ)(?=\s|$)")
NAME_MIN_SCORE = 85


def _fold_latin(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z]", "", s.lower())
    return re.sub(r"^(?:al|an|ash|as|at|ad|ar|az)(?=[a-z]{3,})", "", s)


def _fold_ar(s: str) -> str:
    s = normalize_ar(s).replace(" ", "")
    return s[2:] if s.startswith("ال") and len(s) > 4 else s


@lru_cache(maxsize=1)
def _name_tables() -> tuple[dict[str, int], dict[str, int]]:
    from app.pipeline.quran_match import get_index, load_from_json

    index = get_index() or load_from_json()
    en: dict[str, int] = {}
    ar: dict[str, int] = {}
    for v in index.verses:
        if v.ayah == 1:
            en[_fold_latin(v.surah_name_en)] = v.surah
            ar[_fold_ar(v.surah_name_ar)] = v.surah
    return en, ar


def _match_name(text: str) -> int | None:
    en, ar = _name_tables()
    latin = _fold_latin(_NOISE_WORDS.sub(" ", text))
    if len(latin) >= 3:
        hit = process.extractOne(latin, list(en), scorer=fuzz.ratio, score_cutoff=NAME_MIN_SCORE)
        if hit:
            return en[hit[0]]
    arabic = _AR_NOISE.sub(" ", normalize_ar(text))
    folded = _fold_ar(arabic)
    if folded in ar:  # exact name first: one- or two-letter names (ص, ق, طه, يس) cannot be fuzzy-matched
        return ar[folded]
    if len(folded) >= 3:
        hit = process.extractOne(folded, list(ar), scorer=fuzz.ratio, score_cutoff=NAME_MIN_SCORE)
        if hit:
            return ar[hit[0]]
    return None


def parse(cited: str | None) -> tuple[int, int | None] | None:
    if not cited or not cited.strip():
        return None
    text = cited.translate(_DIGITS)
    m = _REF.search(text) or _SURAH_NUM_VERSE.search(text)
    if m:
        s, a = int(m.group(1)), int(m.group(2))
        return (s, a) if 1 <= s <= 114 and a >= 1 else None
    nums = [int(n) for n in re.findall(r"\d{1,3}", text)]
    name_part = re.sub(r"\d+", " ", text)
    surah = _match_name(name_part)
    if surah is None:
        return None
    return surah, (nums[-1] if nums and nums[-1] >= 1 else None)
