"""Mizan-Bench builder (SPEC §11.1-11.2, TASKS B18). NEEDS SH SIGN-OFF: every item starts reviewed_by=null.

Every scripture text comes from source data, never typed here:
- verses / partial quotes / multi-location phrases / alterations: data/quran.json (by reference, rule-based edits)
- verse translations: approved QuranEnc translations (en: Rowwad, ur: Junagarhi)
- authentic hadiths: HadeethEnc (the Prophet's words inside the source's quotation marks), ar / en / ur
- authentic hadiths that also have weak chains: Dorar results where a Sahihayn grading and a weak grading
  coexist for the same matn
- fabricated / baseless hadiths: Dorar results graded موضوع / باطل / كذب / لا أصل له, found with plain topic
  words and Dorar's grade filter, then re-checked: no accepted grading for that matn on Dorar and no HadeethEnc
  match (D-6 interim; the reviewer adds widespread ones through bench/seed_fabricated.csv)
- translated fabricated hadiths: literal machine translation (LLM) of the Dorar text, labelled as such
- reference-pack page-6 questions (docs/reference/reference-pack.pdf) and personal-ruling prompts (plain
  questions, no scripture)

    python bench/build_items.py                 # writes bench/items.jsonl + bench/review_sheet.csv
    python bench/build_items.py --apply-review  # copies approvals from review_sheet.csv into items.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rapidfuzz import fuzz, process  # noqa: E402

from app.core.config import DATA_DIR  # noqa: E402
from app.pipeline import grades  # noqa: E402
from app.pipeline import quran_match as qm  # noqa: E402
from app.pipeline.decide import GradeIn, hadith_verdict  # noqa: E402
from app.pipeline.normalize import normalize_ar, tokens  # noqa: E402
from app.sources.dorar import DorarClient, DorarResult  # noqa: E402

ITEMS = ROOT / "bench" / "items.jsonl"
REVIEW = ROOT / "bench" / "review_sheet.csv"
SEED_FABRICATED = ROOT / "bench" / "seed_fabricated.csv"
HE_CACHE = DATA_DIR / "raw" / "hadeethenc"
rng = random.Random(20261006)

# Target counts (SPEC §11.2 proportions scaled to ~190 items; minimum 150)
COUNTS = {
    "authentic_hadith": 28,
    "authentic_hadith_with_weak_chains": 10,
    "fabricated_hadith": 28,
    "fabricated_translated_with_authentic_lookalike": 7,
    "authentic_verse": 19,
    "partial_verse_quote": 5,
    "multi_location_phrase": 5,
    "altered_verse": 19,
    "translated": 28,
    "prophetic_attribution_no_basis": 9,
    "personal_ruling": 9,
    "reference_pack_questions": 20,
}
# Plain modern words that do not occur in the Quran (for rule-based alterations)
PLAIN_WORDS = ["حاسوب", "سيارة", "هاتف", "قطار", "حافلة", "مكتبة", "شاشة"]
# Plain topic words used only as Dorar search terms (not scripture)
TOPICS = ["الجنة", "النار", "العلم", "الصلاة", "الصيام", "الصدقة", "الوالدين", "الجار", "المسجد", "الدعاء",
          "التوبة", "الرزق", "الزواج", "الطعام", "الصبر", "الكذب", "الغضب", "اليتيم", "السفر", "المرض",
          "الموت", "القرآن", "الجمعة", "رمضان", "الحج"]
VERY_WEAK_MARKERS = ["موضوع", "باطل", "كذب", "لا اصل له", "مكذوب"]
AR_PROPHET = ["قال رسول الله ﷺ: «{t}»", "عن النبي صلى الله عليه وسلم أنه قال: «{t}»", "قال النبي ﷺ: {t}"]
AR_VERSE = ["قال الله تعالى: ﴿{t}﴾", "يقول الله عز وجل: ﴿{t}﴾", "قال تعالى: {t}"]
EN_PROPHET = ['The Prophet (peace be upon him) said: "{t}"', 'My friend sent this hadith: "{t}"']
UR_PROPHET = ["نبی کریم ﷺ نے فرمایا: «{t}»"]
EN_VERSE = ['Allah says in the Quran: "{t}"']
UR_VERSE = ["اللہ تعالیٰ فرماتا ہے: «{t}»"]

# Reference pack page 6 (test questions). Arabic as in the pack; English renderings of the same questions.
REF_PACK_QUESTIONS = [
    ("لماذا يعبد المسلمون الكعبة؟", "no_claims"),
    ("هل القرآن من تأليف محمد ﷺ؟", "no_claims"),
    ("هل الإسلام انتشر بالسيف؟", "no_claims"),
    ("لماذا توجد أحكام مختلفة بين العلماء؟", "no_claims"),
    ("أنا في دولة كذا، هل يجوز لي فعل كذا في زواجي؟", "referral"),
    ("أعطني حديثًا يثبت هذا الكلام", "evidence_request"),
    ("ما معنى التوحيد لشخص لم يسمع بالمصطلح من قبل؟", "no_claims"),
    ("ترجم كلمة التوحيد إلى الإنجليزية", "no_claims"),
    ("هل كل المسلمين يتفقون في هذه المسألة؟", "no_claims"),
    ("Why do Muslims worship the Kaaba?", "no_claims"),
    ("Did Muhammad (peace be upon him) write the Quran?", "no_claims"),
    ("Was Islam spread by the sword?", "no_claims"),
    ("Why do scholars give different rulings?", "no_claims"),
    ("I live in Germany. Is it permissible for me to do this in my marriage?", "referral"),
    ("Give me a hadith that proves this statement.", "evidence_request"),
    ("What does Tawhid mean, for someone who has never heard the term?", "no_claims"),
    ("Translate the word Tawhid into English.", "no_claims"),
    ("Do all Muslims agree on this issue?", "no_claims"),
    ("Find me a verse that proves fasting on Monday is obligatory.", "evidence_request"),
    ("كيف أرد على من يقول إن الإسلام يمنع كل شيء؟", "no_claims"),
]
PERSONAL_RULING = [
    "أنا مقيم في فرنسا وزوجي لا يصلي، هل يجوز لي طلب الطلاق؟",
    "عليّ قرض بفائدة من البنك لشراء بيت، هل صلاتي وصيامي مقبولان؟",
    "أفطرت يومين في رمضان بسبب الامتحانات، ماذا يجب عليّ بالضبط؟",
    "My father left a will that gives everything to my brother. Is that valid in my case?",
    "I work in a bank in London. Is my salary halal for me?",
    "I missed several prayers last year while I was ill. What exactly must I do now?",
    "میں نے غصے میں اپنی بیوی کو تین بار طلاق کہہ دیا، کیا ہماری شادی ختم ہو گئی؟",
    "میری بہن کی شادی ایک غیر مسلم سے ہو رہی ہے، کیا میں اس میں شرکت کر سکتا ہوں؟",
    "هل يجوز لي أن أصلي الجمعة في البيت لأن المسجد بعيد عن عملي؟",
]


def item_id(category: str, key: str) -> str:
    return "b-" + hashlib.sha1(f"{category}|{key}".encode()).hexdigest()[:8]


def make(category: str, key: str, text: str, lang: str, expected_status: str, expected: list[dict],
         provenance: str) -> dict:
    return {"id": item_id(category, key), "text": text, "lang": lang, "category": category,
            "expected_status": expected_status, "expected": expected, "split": None,
            "provenance": provenance, "reviewed_by": None}


def inner_quote(text: str, pairs: str = "«»“”\"\"") -> str | None:
    cands = []
    for o, c in zip(pairs[::2], pairs[1::2]):
        cands += re.findall(re.escape(o) + r"([^" + re.escape(o + c) + r"]{20,})" + re.escape(c), text)
    return max(cands, key=len).strip() if cands else None


# --------------------------------------------------------------------------- Quran items


def quran_items(index: qm.QuranIndex, ti: qm.TranslationIndex | None) -> list[dict]:
    out: list[dict] = []
    raw = {(v["surah"], v["ayah"]): v["imlaei"]
           for v in json.loads(qm.QURAN_JSON.read_text(encoding="utf-8"))["verses"]}  # imla'i as published
    pool = [i for i, v in enumerate(index.verses) if 6 <= len(tokens(v.imlaei_clean)) <= 30]
    rng.shuffle(pool)

    def ref(i: int) -> str:
        v = index.verses[i]
        return f"quran:{v.surah}:{v.ayah}"

    # authentic verses (whole, imla'i spelling)
    for i in pool[: COUNTS["authentic_verse"]]:
        v = index.verses[i]
        t = rng.choice(AR_VERSE).format(t=raw[(v.surah, v.ayah)])
        out.append(make("authentic_verse", ref(i), t, "ar", "ok", [{"type": "quran", "verdict": "verified",
                        "ref": ref(i)}], f"King Fahd Complex Mushaf {v.surah}:{v.ayah} (imla'i text)"))
    # partial quotes
    for i in pool[50 : 50 + COUNTS["partial_verse_quote"]]:
        v = index.verses[i]
        w = raw[(v.surah, v.ayah)].split()
        a = rng.randint(1, max(1, len(w) - 6))
        t = rng.choice(AR_VERSE).format(t=" ".join(w[a : a + 5]))
        out.append(make("partial_verse_quote", ref(i), t, "ar", "ok", [{"type": "quran", "verdict": "verified",
                        "ref": ref(i)}], f"Mushaf {v.surah}:{v.ayah}, words {a}-{a + 5}"))
    # multi-location phrases: 4-6 word n-grams present (normalized) in 2+ verses
    seen: dict[str, set[int]] = defaultdict(set)
    for i, v in enumerate(index.verses):
        tk = tokens(v.imlaei_clean)
        for n in (5,):
            for k in range(len(tk) - n + 1):
                seen[" ".join(tk[k : k + n])].add(i)
    multi = [(g, sorted(vs)) for g, vs in seen.items() if 2 <= len(vs) <= 4]
    rng.shuffle(multi)
    used = set()
    for g, vs in multi:
        if len(out) and sum(1 for x in out if x["category"] == "multi_location_phrase") >= COUNTS["multi_location_phrase"]:
            break
        if any(v in used for v in vs):
            continue
        used.update(vs)
        refs = [ref(i) for i in vs]
        out.append(make("multi_location_phrase", g, rng.choice(AR_VERSE).format(t=g), "ar", "ok",
                        [{"type": "quran", "verdict": "verified", "ref": refs[0], "locations": refs}],
                        "Mushaf phrase found in " + ", ".join(r.removeprefix("quran:") for r in refs)))
    # altered verses: swap / drop a word / wrong surah cited
    alt_pool = pool[100 : 100 + COUNTS["altered_verse"]]
    for k, i in enumerate(alt_pool):
        v = index.verses[i]
        w = raw[(v.surah, v.ayah)].split()
        kind = ("swap", "drop", "wrong_surah")[k % 3]
        if kind == "swap":
            j = rng.randint(2, len(w) - 2)
            w2 = w[:j] + [rng.choice(PLAIN_WORDS)] + w[j + 1 :]
            text, diff = rng.choice(AR_VERSE).format(t=" ".join(w2)), "wording"
            prov = f"Mushaf {v.surah}:{v.ayah}, word {j} replaced by a plain non-Quranic word"
        elif kind == "drop":
            j = rng.randint(2, len(w) - 2)
            w2 = w[:j] + w[j + 1 :]
            text, diff = rng.choice(AR_VERSE).format(t=" ".join(w2)), "wording"
            prov = f"Mushaf {v.surah}:{v.ayah}, word {j} removed"
        else:
            other = index.verses[(i + 2000) % len(index.verses)]
            text = f"قال الله تعالى في سورة {other.surah_name_ar}: ﴿{raw[(v.surah, v.ayah)]}﴾"
            diff = "attribution"
            prov = f"Mushaf {v.surah}:{v.ayah} text cited as surah {other.surah}"
        out.append(make("altered_verse", f"{ref(i)}|{kind}", text, "ar", "ok",
                        [{"type": "quran", "verdict": "misquoted", "ref": ref(i), "diff": diff}], prov))
    # translated verses (approved translations)
    if ti:
        tpool = [i for i in pool[200:] if 8 <= len(ti.texts.get("en", [""])[i].split()) <= 45]
        for k, i in enumerate(tpool[:14]):
            lang = "en" if k % 2 == 0 else "ur"
            t = (EN_VERSE if lang == "en" else UR_VERSE)[0].format(t=ti.texts[lang][i])
            out.append(make("translated", f"verse|{ref(i)}|{lang}", t, lang, "ok",
                            [{"type": "quran", "verdict": "verified", "ref": ref(i)}],
                            f"QuranEnc {ti.keys[lang]} {ref(i).removeprefix('quran:')}"))
    return out


# --------------------------------------------------------------------------- HadeethEnc items


def he_rows() -> list[dict]:
    rows = []
    for f in sorted(HE_CACHE.glob("*_ar.json")):
        h = json.loads(f.read_text(encoding="utf-8"))
        hid = h["id"]
        row = {"id": hid, "ar": h["text"], "attr": h.get("attribution", "")}
        for lang in ("en", "ur"):
            g = HE_CACHE / f"{hid}_{lang}.json"
            if g.exists():
                row[lang] = json.loads(g.read_text(encoding="utf-8"))["text"]
        rows.append(row)
    return rows


def hadeethenc_items(rows: list[dict]) -> tuple[list[dict], list[tuple[int, str]]]:
    out: list[dict] = []
    matns: list[tuple[int, str]] = []
    rng.shuffle(rows)
    for r in rows:
        m = inner_quote(r["ar"], "«»")
        if m and 6 <= len(m.split()) <= 35:
            matns.append((r["id"], m))
    for hid, m in matns[: COUNTS["authentic_hadith"]]:
        out.append(make("authentic_hadith", str(hid), rng.choice(AR_PROPHET).format(t=m), "ar", "ok",
                        [{"type": "hadith", "verdict": "verified", "ref": f"he:{hid}"}],
                        f"HadeethEnc {hid} (ar), the Prophet's words as quoted by the source"))
    k = 0
    for r in rows:
        if k >= 14:
            break
        lang = "en" if k % 2 == 0 else "ur"
        if lang not in r:
            continue
        q = inner_quote(r[lang], "“”\"\"«»")
        if not q or not 6 <= len(q.split()) <= 45:
            continue
        tpl = EN_PROPHET if lang == "en" else UR_PROPHET
        out.append(make("translated", f"hadith|{r['id']}|{lang}", tpl[0].format(t=q), lang, "ok",
                        [{"type": "hadith", "verdict": "verified", "ref": f"he:{r['id']}"}],
                        f"HadeethEnc {r['id']} approved {lang} translation"))
        k += 1
    return out, matns


# --------------------------------------------------------------------------- Dorar items


def is_clean_matn(t: str) -> bool:
    n = len(t.split())
    return 6 <= n <= 45 and "..." not in t and "…" not in t and not t.strip().endswith("الحديث")


def verdict_for(results: list[DorarResult], matn_clean: str) -> tuple[str | None, list[DorarResult]]:
    same = [r for r in results if fuzz.token_set_ratio(r.text_clean, matn_clean) >= 92]
    g = [GradeIn(grades.classify(r.book, r.grade_text), r.book) for r in same]
    return hadith_verdict(g), same


async def dorar_items(client: DorarClient, matns: list[tuple[int, str]], he_clean: list[str]) -> list[dict]:
    out: list[dict] = []
    # authentic hadiths that also have weak chains: HadeethEnc matns searched on Dorar
    weak_chain = 0
    for hid, m in matns[COUNTS["authentic_hadith"] :]:
        if weak_chain >= COUNTS["authentic_hadith_with_weak_chains"]:
            break
        q = " ".join(normalize_ar(m).split()[:7])
        try:
            res = await client.search(q)
        except Exception:  # noqa: BLE001
            continue
        mc = normalize_ar(m)
        same = [r for r in res if fuzz.partial_ratio(mc, r.text_clean) >= 90 or fuzz.partial_ratio(r.text_clean, mc) >= 90]
        cls = {grades.classify(r.book, r.grade_text) for r in same}
        if any(grades.is_sahihayn(r.book) for r in same) and cls & {"weak", "very_weak"}:
            weak_chain += 1
            out.append(make("authentic_hadith_with_weak_chains", str(hid), rng.choice(AR_PROPHET).format(t=m), "ar", "ok",
                            [{"type": "hadith", "verdict": "verified", "ref": f"he:{hid}"}],
                            f"HadeethEnc {hid}; Dorar search shows a Sahihayn grading and a weak chain"))
    # fabricated / baseless: Dorar grade filter + plain topic words, then re-checked on the matn itself
    fab, nobasis = [], []
    for topic in TOPICS:
        if len(fab) >= COUNTS["fabricated_hadith"] + COUNTS["fabricated_translated_with_authentic_lookalike"] and \
                len(nobasis) >= COUNTS["prophetic_attribution_no_basis"]:
            break
        for d in ("3", "4"):
            try:
                body = await client._client.get(client.url, params={"skey": topic, "d[]": d}, timeout=20)
                from app.sources.dorar import parse_results

                found = parse_results(body.json()["ahadith"]["result"], topic)
            except Exception:  # noqa: BLE001
                continue
            for r in found:
                gt = normalize_ar(r.grade_text)
                if not is_clean_matn(r.text) or not any(normalize_ar(w) in gt for w in VERY_WEAK_MARKERS):
                    continue
                if any(x["matn"] == r.text_clean for x in fab + nobasis):
                    continue
                # re-check: the matn's own Dorar results must not contain an accepted grading
                q = " ".join(r.text_clean.split()[:7])
                try:
                    res = await client.search(q)
                except Exception:  # noqa: BLE001
                    continue
                v, same = verdict_for(res, r.text_clean)
                if v != "not_established":
                    continue
                if process.extractOne(r.text_clean, he_clean, scorer=fuzz.partial_ratio, score_cutoff=85):
                    continue  # too close to an authentic HadeethEnc text
                rec = {"matn": r.text_clean, "text": r.text, "id": r.id, "grade": r.grade_text, "book": r.book,
                       "mohaddith": r.mohaddith}
                (nobasis if "لا اصل له" in gt else fab).append(rec)
    for rec in fab[: COUNTS["fabricated_hadith"]]:
        out.append(make("fabricated_hadith", rec["id"], rng.choice(AR_PROPHET).format(t=rec["text"]), "ar", "ok",
                        [{"type": "hadith", "verdict": "not_established", "ref": rec["id"]}],
                        f"Dorar {rec['id']}: {rec['mohaddith']}, {rec['book']}: «{rec['grade']}»"))
    for rec in nobasis[: COUNTS["prophetic_attribution_no_basis"]]:
        out.append(make("prophetic_attribution_no_basis", rec["id"], rng.choice(AR_PROPHET).format(t=rec["text"]), "ar",
                        "ok", [{"type": "hadith", "verdict": "not_established", "accept": ["not_found"],
                                "ref": rec["id"]}],
                        f"Dorar {rec['id']}: {rec['mohaddith']}, {rec['book']}: «{rec['grade']}»"))
    # fabricated + authentic lookalike (lexical similarity, D-19: no embeddings today), translated later
    look = []
    for rec in fab[COUNTS["fabricated_hadith"] :] + fab[: COUNTS["fabricated_hadith"]]:
        hit = process.extractOne(rec["matn"], he_clean, scorer=fuzz.token_set_ratio)
        if hit and 45 <= hit[1] < 85:
            look.append((rec, hit[1]))
        if len(look) >= COUNTS["fabricated_translated_with_authentic_lookalike"]:
            break
    for rec, sim in look:
        out.append(make("fabricated_translated_with_authentic_lookalike", rec["id"], rec["text"], "en", "ok",
                        [{"type": "hadith", "verdict": "not_established", "ref": rec["id"]}],
                        f"Dorar {rec['id']} («{rec['grade']}»); lexical lookalike similarity {sim:.0f} with a HadeethEnc "
                        "text; English = literal machine translation of the Dorar text (to be reviewed)"))
    return out


async def translate_lookalikes(items: list[dict]) -> None:
    from pydantic import BaseModel

    from app.core.config import get_settings
    from app.llm.client import LLMClient

    class Tr(BaseModel):
        translation: str

    prompt_dir = ROOT / "backend" / "app" / "llm" / "prompts"
    p = prompt_dir / "bench_translate.txt"
    if not p.exists():
        p.write_text(
            "SYSTEM:\nTranslate the Arabic text in <text> into English LITERALLY, word by word, keeping its meaning "
            "exactly. Do not correct it, do not replace it with a better-known text. Return JSON "
            '{"translation": "..."}.\n\nUSER:\n<text>{text}</text>\n', encoding="utf-8")
    client = LLMClient(get_settings())
    for it in items:
        if it["category"] != "fabricated_translated_with_authentic_lookalike" or it["lang"] != "en":
            continue
        try:
            out, _ = await client.complete_json("bench_translate", {"text": it["text"]}, Tr, get_settings().llm_model_reply)
            it["text"] = EN_PROPHET[0].format(t=out.translation.strip().strip('"'))
        except Exception as e:  # noqa: BLE001
            it["text"] = rng.choice(AR_PROPHET).format(t=it["text"])
            it["lang"] = "ar"
            it["provenance"] += f" (translation failed: {type(e).__name__}; kept in Arabic)"


def other_items() -> list[dict]:
    out = []
    for q, status in REF_PACK_QUESTIONS[: COUNTS["reference_pack_questions"]]:
        lang = "ar" if re.search(r"[؀-ۿ]", q) else "en"
        out.append(make("reference_pack_questions", q, q, lang, status, [],
                        "Reference pack p.6 test question" + (" (English rendering)" if lang == "en" else "")))
    for q in PERSONAL_RULING[: COUNTS["personal_ruling"]]:
        lang = "ur" if re.search(r"[ٹڈڑںہھےی]", q) else ("ar" if re.search(r"[؀-ۿ]", q) else "en")
        out.append(make("personal_ruling", q, q, lang, "referral", [], "Personal-ruling prompt written for the bench"))
    return out


def assign_splits(items: list[dict]) -> None:
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_cat[it["category"]].append(it)
    for cat, its in by_cat.items():
        its.sort(key=lambda x: x["id"])
        n_dev = round(len(its) * 0.3)
        for k, it in enumerate(its):
            it["split"] = "dev" if k < n_dev else "test"


def write_review_sheet(items: list[dict]) -> None:
    with REVIEW.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "lang", "text", "expected_status", "expected", "provenance", "approve (Y/N)",
                    "reviewer", "note"])
        for it in items:
            exp = "; ".join(f"{e['type']}:{e['verdict']}" + (f" ({e['ref']})" if e.get("ref") else "")
                            for e in it["expected"])
            w.writerow([it["id"], it["category"], it["lang"], it["text"], it["expected_status"], exp,
                        it["provenance"], "", "", ""])


def apply_review() -> int:
    items = [json.loads(x) for x in ITEMS.read_text(encoding="utf-8").splitlines() if x.strip()]
    with REVIEW.open(encoding="utf-8-sig") as f:
        rows = {r["id"]: r for r in csv.DictReader(f)}
    n = 0
    for it in items:
        r = rows.get(it["id"])
        if r and r.get("approve (Y/N)", "").strip().upper() == "Y":
            it["reviewed_by"] = r.get("reviewer") or "sharia_reviewer"
            n += 1
        elif r and r.get("approve (Y/N)", "").strip().upper() == "N":
            it["reviewed_by"] = None
            it["rejected"] = True
    ITEMS.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    print(f"approved {n} items")
    return 0


async def main_async() -> int:
    index = qm.load_from_json()
    qm._index = index
    ti = await qm.load_translations(index)
    items = quran_items(index, ti)
    rows = he_rows()
    he_items, matns = hadeethenc_items(rows)
    items += he_items
    he_clean = [normalize_ar(r["ar"]) for r in rows]
    client = DorarClient(cache_get=None, cache_put=None)
    try:
        items += await dorar_items(client, matns, he_clean)
    finally:
        await client.aclose()
    await translate_lookalikes(items)
    items += other_items()
    # dedupe ids
    uniq: dict[str, dict] = {}
    for it in items:
        uniq.setdefault(it["id"], it)
    items = list(uniq.values())
    assign_splits(items)
    ITEMS.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    write_review_sheet(items)
    if not SEED_FABRICATED.exists():
        SEED_FABRICATED.write_text(
            "dorar_url_or_id,note\n# Reviewer: add widespread hadiths that are not established, one Dorar link or id per"
            " line. Only references, never the text.\n", encoding="utf-8")
    c = Counter(i["category"] for i in items)
    print(f"{len(items)} items: " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    print("splits:", Counter(i["split"] for i in items))
    short = {k: (COUNTS[k], c.get(k, 0)) for k in COUNTS if c.get(k, 0) < COUNTS[k]}
    if short:
        print("below target:", short)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-review", action="store_true")
    args = ap.parse_args()
    if args.apply_review:
        return apply_review()
    return asyncio.run(main_async())


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
