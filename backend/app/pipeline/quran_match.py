"""Verse matcher (SPEC §7.3). This module holds the in-memory Mushaf index (B05); matching below (B11).

At startup the whole Mushaf (6,236 verses) is loaded into memory, plus windows of 2 and 3 consecutive
verses within the same surah, so quotes spanning verses can be matched. Each window has two matching
forms (DECISIONS D-3): normalized Uthmani and normalized imla'i.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import DATA_DIR
from app.core.logging import get_logger

log = get_logger(__name__)

BULK_LOAD_TIMEOUT_S = 120  # one-off startup loads of whole tables from a remote DB

QURAN_JSON = DATA_DIR / "quran.json"
WINDOW_SIZES = (1, 2, 3)


@dataclass(frozen=True, slots=True)
class Verse:
    id: int
    surah: int
    ayah: int
    uthmani: str
    clean: str
    imlaei_clean: str
    surah_name_ar: str
    surah_name_en: str


@dataclass(frozen=True, slots=True)
class Window:
    start: int  # index into QuranIndex.verses
    size: int  # number of consecutive verses (same surah)
    clean: str
    imlaei_clean: str


@dataclass
class QuranIndex:
    verses: list[Verse]
    windows: list[Window] = field(default_factory=list)
    by_ref: dict[tuple[int, int], int] = field(default_factory=dict)
    corpus_clean: list[str] = field(default_factory=list)  # aligned with windows
    corpus_imlaei: list[str] = field(default_factory=list)  # aligned with windows

    def __post_init__(self) -> None:
        self.by_ref = {(v.surah, v.ayah): i for i, v in enumerate(self.verses)}
        for size in WINDOW_SIZES:
            for i in range(len(self.verses) - size + 1):
                span = self.verses[i : i + size]
                if span[0].surah != span[-1].surah:
                    continue
                self.windows.append(
                    Window(
                        start=i,
                        size=size,
                        clean=" ".join(v.clean for v in span),
                        imlaei_clean=" ".join(v.imlaei_clean for v in span),
                    )
                )
        self.corpus_clean = [w.clean for w in self.windows]
        self.corpus_imlaei = [w.imlaei_clean for w in self.windows]

    def verse(self, surah: int, ayah: int) -> Verse | None:
        i = self.by_ref.get((surah, ayah))
        return self.verses[i] if i is not None else None

    @property
    def n_surahs(self) -> int:
        return len({v.surah for v in self.verses})


def load_from_json(path: Path = QURAN_JSON) -> QuranIndex:
    data = json.loads(path.read_text(encoding="utf-8"))
    return QuranIndex(
        [
            Verse(
                id=v["id"], surah=v["surah"], ayah=v["ayah"], uthmani=v["uthmani"], clean=v["clean"],
                imlaei_clean=v["imlaei_clean"], surah_name_ar=v["surah_name_ar"], surah_name_en=v["surah_name_en"],
            )
            for v in data["verses"]
        ]
    )


async def load_from_db() -> QuranIndex:
    from app.db.session import get_pool

    pool = await get_pool()
    rows = await pool.fetch(
        "select id, surah, ayah, text_uthmani, text_clean, text_imlaei_clean, surah_name_ar, surah_name_en "
        "from quran_verses order by id",
        timeout=BULK_LOAD_TIMEOUT_S,
    )
    return QuranIndex(
        [
            Verse(
                id=r["id"], surah=r["surah"], ayah=r["ayah"], uthmani=r["text_uthmani"], clean=r["text_clean"],
                imlaei_clean=r["text_imlaei_clean"], surah_name_ar=r["surah_name_ar"] or "",
                surah_name_en=r["surah_name_en"] or "",
            )
            for r in rows
        ]
    )


_index: QuranIndex | None = None


async def load_index() -> QuranIndex | None:
    """Load data/quran.json if present, else quran_verses from the DB (DECISIONS D-10). Never raises."""
    global _index
    t0 = time.perf_counter()
    try:
        _index = load_from_json() if QURAN_JSON.exists() else await load_from_db()
    except Exception as e:  # noqa: BLE001 - the API still starts; checks report source_unavailable
        log.error("quran_index_load_failed", extra={"error": type(e).__name__})
        return None
    log.info(
        "quran_index_loaded",
        extra={
            "verses": len(_index.verses),
            "windows": len(_index.windows),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        },
    )
    return _index


def get_index() -> QuranIndex | None:
    return _index


# =========================================================================== matching (B11, SPEC §7.3)

import difflib  # noqa: E402
import itertools  # noqa: E402
import re  # noqa: E402
from typing import Literal  # noqa: E402

from rapidfuzz import fuzz, process  # noqa: E402

from app.core import thresholds as T  # noqa: E402
from app.pipeline import surah_parse  # noqa: E402
from app.pipeline.normalize import normalize_ar, tokens  # noqa: E402

Status = Literal["verified", "misquoted_candidate", "needs_verifier", "no_match", "too_short", "attribution"]
EXTRACT_LIMIT = 60  # windows pulled per corpus before collapsing to distinct verse spans
PREFILTER_VERSES = 150  # verses shortlisted by the word index before exact partial_ratio scoring
PREFILTER_VERSES_LONG = 40  # for quotes over 12 words


def word_key(t: str) -> str:
    """Spelling-tolerant word key (waw / ya / alif / hamza / doubled letters folded), for the prefilter only."""
    return _skeleton(t.replace("و", "ا").replace("ي", "ا"))


def _word_index(index: QuranIndex) -> tuple[dict[str, set[int]], dict[str, float], dict[int, list[int]]]:
    """key -> verse indices; key -> idf; verse index -> windows containing it. Built once per index."""
    cached = getattr(index, "_word_index_cache", None)
    if cached is not None:
        return cached
    import math

    postings: dict[str, set[int]] = {}
    for vi, v in enumerate(index.verses):
        for t in set(tokens(v.clean)) | set(tokens(v.imlaei_clean)):
            postings.setdefault(word_key(t), set()).add(vi)
    n = len(index.verses)
    idf = {k: math.log(n / len(vs)) for k, vs in postings.items()}
    windows_of: dict[int, list[int]] = {}
    for wi, w in enumerate(index.windows):
        for vi in range(w.start, w.start + w.size):
            windows_of.setdefault(vi, []).append(wi)
    index._word_index_cache = (postings, idf, windows_of)  # type: ignore[attr-defined]
    return index._word_index_cache  # type: ignore[attr-defined]


def _shortlist_windows(index: QuranIndex, q_tokens: list[str]) -> list[int]:
    postings, idf, windows_of = _word_index(index)
    score: dict[int, float] = {}
    for k in {word_key(t) for t in q_tokens}:
        for vi in postings.get(k, ()):
            score[vi] = score.get(vi, 0.0) + idf[k]
    limit = PREFILTER_VERSES if len(q_tokens) <= 12 else PREFILTER_VERSES_LONG  # long quotes are distinctive
    top = sorted(score, key=lambda vi: -score[vi])[:limit]
    return sorted({wi for vi in top for wi in windows_of.get(vi, ())})


@dataclass(frozen=True)
class DiffOp:
    op: str  # replace | insert (words only in the quote) | delete (Mushaf words missing from the quote)
    quoted: str
    source: str


@dataclass
class Candidate:
    verses: tuple[int, ...]  # indices into QuranIndex.verses covered by the aligned span
    raw: float
    adj: float
    form: str  # clean (normalized Uthmani) | imlaei
    contained: bool
    ops: list[DiffOp]
    tok_start: int  # aligned token range inside the covered verses' text (in `form`)
    tok_end: int


@dataclass
class VerseMatch:
    status: Status
    best: Candidate | None = None
    locations: list[tuple[int, ...]] = field(default_factory=list)  # verified locations, best first
    candidates: list[Candidate] = field(default_factory=list)  # distinct spans, best first (for the verifier)
    cited: tuple[int, int | None] | None = None
    note: str | None = None


# ----------------------------------------------------------------------- spelling tolerance (D-13)


def _skeleton(w: str) -> str:
    w = w.replace("ا", "").replace("ء", "")  # alif, hamza
    out: list[str] = []
    for ch in w:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


DAGGER_ALIF = "\u0670"
SMALL_WAW, SMALL_YEH, SMALL_HIGH_YEH = "\u06E5", "\u06E6", "\u06E7"
HAMZA_ABOVE = "\u0654"
_LETTER_WITH_DAGGER = re.compile("([\u0648\u0649\u064A])(?=[\u064B-\u0652]*\u0670)")  # و / ى / ي carrying a dagger alif


def uthmani_variants(word: str) -> set[str]:
    """Accepted modern spellings of ONE Uthmani word, licensed only by that word's own marks (D-31):
    dagger alif written as alif or not; a waw / ya carrying a dagger alif written as alif (الصلوٰة -> الصلاة);
    small waw / ya written as letters; a hamza mark on a seat written as ء / و / ي. Plus the plain normalized form."""
    out = {normalize_ar(word)}
    with_alif = word.replace(DAGGER_ALIF, "\u0627")
    seat_alif = _LETTER_WITH_DAGGER.sub("\u0627", word)
    cands = {with_alif, seat_alif, seat_alif.replace(DAGGER_ALIF, "")}
    cands |= {c.replace(SMALL_WAW, "\u0648").replace(SMALL_YEH, "\u064A").replace(SMALL_HIGH_YEH, "\u064A") for c in set(cands)}
    if HAMZA_ABOVE in word:
        cands |= {c.replace("\u0640" + HAMZA_ABOVE, carrier).replace(HAMZA_ABOVE, "") for c in set(cands)
                  for carrier in ("\u0621", "\u0648", "\u064A")}
        cands |= {re.sub("\u0640?[\u064B-\u0652]*" + HAMZA_ABOVE, carrier, c) for c in set(cands)
                  for carrier in ("\u0621", "\u0648", "\u064A")}
    out |= {normalize_ar(c) for c in cands}
    return {x for x in out if x and " " not in x}


def verse_variants(index: QuranIndex, vi: int, form: str) -> list[frozenset[str]]:
    """Per token of verse `vi` in `form`: the exact token, the accepted forms of the matching Uthmani word, and the
    token at the same position in the other Mushaf text (imla'i <-> Uthmani alignment). Cached on the index."""
    cache = getattr(index, "_variant_cache", None)
    if cache is None:
        cache = index._variant_cache = {}  # type: ignore[attr-defined]
    key = (vi, form)
    if key in cache:
        return cache[key]
    v = index.verses[vi]
    clean, iml = tokens(v.clean), tokens(v.imlaei_clean)
    uth = [w for w in v.uthmani.split() if normalize_ar(w)]
    uth_ok = len(uth) == len(clean)
    paired = len(clean) == len(iml)
    own = clean if form == "clean" else iml
    res: list[frozenset[str]] = []
    for i, t in enumerate(own):
        acc = {t}
        if paired:
            acc |= {clean[i], iml[i]}
        if uth_ok and (form == "clean" or paired):
            acc |= uthmani_variants(uth[i])
        res.append(frozenset(acc))
    cache[key] = res
    return res


def word_diff(q: list[str], src: list[str], src_var: list[frozenset[str]] | None = None) -> list[DiffOp]:
    """Word-level differences between the quote and the aligned Mushaf span (edge rule applied).

    A quote word equals a Mushaf word only if it is one of that word's accepted forms (D-31). Words split or joined
    differently (يا ايها / يايها) are accepted only when the joined quote equals a joined combination of accepted forms."""
    var = src_var if src_var is not None and len(src_var) == len(src) else [frozenset({t}) for t in src]
    ops: list[DiffOp] = []
    qs = [q[i] for i in range(len(q))]
    # map each quote token to the source position it matches, so SequenceMatcher sees accepted forms as equal
    canon = list(src)
    q_norm = []
    for t in qs:
        q_norm.append(t)
    matcher_q = [next((canon[j] for j in range(len(src)) if t in var[j]), t) for t in q_norm]
    codes = difflib.SequenceMatcher(None, matcher_q, canon, autojunk=False).get_opcodes()
    for k, (tag, i1, i2, j1, j2) in enumerate(codes):
        if tag == "equal":
            continue
        qa, sa = q[i1:i2], src[j1:j2]
        if tag == "insert" and (k == 0 or k == len(codes) - 1):
            continue  # Mushaf words at the edges of the aligned span: partial quoting, not an alteration
        if tag == "replace":
            if len(qa) == len(sa) and all(x in var[j1 + n] for n, x in enumerate(qa)):
                continue
            if len(sa) <= 3 and len(qa) <= 3:
                combos = {"".join(c) for c in itertools.product(*[sorted(var[j]) for j in range(j1, j2)])}
                if "".join(qa) in combos:
                    continue  # words split / joined differently
        op = {"replace": "replace", "delete": "insert", "insert": "delete"}[tag]
        ops.append(DiffOp(op, " ".join(qa), " ".join(sa)))
    return ops


# ----------------------------------------------------------------------- core


def _verse_tokens(index: QuranIndex, vi: int, form: str) -> list[str]:
    v = index.verses[vi]
    return tokens(v.clean if form == "clean" else v.imlaei_clean)


def _window_variants(index: QuranIndex, w: Window, form: str) -> list[frozenset[str]]:
    out: list[frozenset[str]] = []
    for vi in range(w.start, w.start + w.size):
        out.extend(verse_variants(index, vi, form))
    return out


def _score_window(index: QuranIndex, q: str, q_tokens: list[str], w: Window, form: str) -> Candidate:
    text = w.clean if form == "clean" else w.imlaei_clean
    al = fuzz.partial_ratio_alignment(q, text)
    raw = al.score if al else 0.0
    ds, de = (al.dest_start, al.dest_end) if al else (0, len(text))
    ds = text.rfind(" ", 0, ds) + 1
    nxt = text.find(" ", max(de - 1, ds))
    de = len(text) if nxt == -1 else nxt
    tok_start = text[:ds].count(" ")
    aligned = tokens(text[ds:de])
    tok_end = tok_start + len(aligned)
    covered: list[int] = []
    pos = 0
    for vi in range(w.start, w.start + w.size):
        n = len(_verse_tokens(index, vi, form))
        if pos < tok_end and pos + n > tok_start:
            covered.append(vi)
        pos += n
    first_off = sum(len(_verse_tokens(index, vi, form)) for vi in range(w.start, covered[0])) if covered else 0
    len_ratio = min(len(q), len(text)) / max(len(q), len(text))
    adj = raw * (0.85 + 0.15 * len_ratio)
    contained = len(q_tokens) > T.QURAN_CONTAINMENT_RATIO * len(tokens(text))
    return Candidate(
        verses=tuple(covered), raw=raw, adj=adj, form=form, contained=contained,
        ops=word_diff(q_tokens, aligned, _window_variants(index, w, form)[tok_start:tok_end]),
        tok_start=tok_start - first_off, tok_end=tok_end - first_off,
    )


def _candidates(index: QuranIndex, q: str) -> list[Candidate]:
    q_tokens = tokens(q)
    shortlist = _shortlist_windows(index, q_tokens)
    pulled: dict[tuple[int, str], float] = {}
    for form, corpus in (("clean", index.corpus_clean), ("imlaei", index.corpus_imlaei)):
        sub = {wi: corpus[wi] for wi in shortlist}
        for _, score, wi in process.extract(
            q, sub, scorer=fuzz.partial_ratio, limit=EXTRACT_LIMIT, score_cutoff=T.QURAN_CANDIDATE_RAW - 10
        ):
            pulled[(wi, form)] = score
    by_span: dict[tuple[int, ...], Candidate] = {}
    for (wi, form), _ in sorted(pulled.items(), key=lambda kv: -kv[1]):
        c = _score_window(index, q, q_tokens, index.windows[wi], form)
        if not c.verses:
            continue
        prev = by_span.get(c.verses)
        # per covered span keep the reading with fewer diffs, then the higher raw score
        if prev is None or (len(c.ops), -c.raw) < (len(prev.ops), -prev.raw):
            by_span[c.verses] = c
    return sorted(by_span.values(), key=lambda c: -c.adj)[: max(T.QURAN_TOP_K, T.QURAN_MAX_LOCATIONS * 2)]


def cited_matches(cited: tuple[int, int | None], verses: tuple[int, ...], index: QuranIndex) -> bool:
    s, a = cited
    return any(index.verses[vi].surah == s and (a is None or index.verses[vi].ayah == a) for vi in verses)


def _short_quote(index: QuranIndex, q_tokens: list[str], cited: tuple[int, int | None] | None) -> VerseMatch:
    """D-2: under QURAN_MIN_WORDS words. Only judgeable deterministically against a cited ayah."""
    if cited and cited[1] is not None:
        vi = index.by_ref.get((cited[0], cited[1]))
        if vi is not None:
            for form in ("clean", "imlaei"):
                vt = _verse_tokens(index, vi, form)
                vv = verse_variants(index, vi, form)
                if q_tokens and all(any(t in acc for acc in vv) for t in q_tokens):
                    c = Candidate((vi,), 100.0, 100.0, form, False, [], 0, len(vt))
                    return VerseMatch("verified", best=c, locations=[(vi,)], candidates=[c], cited=cited)
    return VerseMatch("too_short", cited=cited, note="too_short")


def match_arabic(quote: str, claimed_source: str | None = None, index: QuranIndex | None = None) -> VerseMatch:
    index = index or get_index()
    if index is None:
        raise RuntimeError("Mushaf index not loaded")
    q = normalize_ar(quote)
    q_tokens = tokens(q)
    cited = surah_parse.parse(claimed_source)
    if len(q_tokens) < T.QURAN_MIN_WORDS:
        return _short_quote(index, q_tokens, cited)

    cands = _candidates(index, q)
    usable = [c for c in cands if not c.contained]
    if not usable:
        return VerseMatch("no_match", candidates=cands, cited=cited)

    clean_hits = [c for c in usable if c.raw >= T.QURAN_VERIFIED_RAW and not c.ops]
    if clean_hits:
        locations: list[tuple[int, ...]] = []
        for c in clean_hits:  # distinct places only: skip spans overlapping a better-ranked location
            if not any(set(c.verses) & set(loc) for loc in locations):
                locations.append(c.verses)
        locations = locations[: T.QURAN_MAX_LOCATIONS]
        status: Status = "verified"
        if cited and not any(cited_matches(cited, loc, index) for loc in locations):
            status = "attribution"
        return VerseMatch(status, best=clean_hits[0], locations=locations, candidates=usable, cited=cited)

    best = usable[0]
    if best.raw >= T.QURAN_CANDIDATE_RAW and best.ops:
        return VerseMatch("misquoted_candidate", best=best, candidates=usable, cited=cited)
    if best.raw >= T.QURAN_CANDIDATE_RAW:
        return VerseMatch("needs_verifier", best=best, candidates=usable, cited=cited)  # D-2: 80-95, no diffs
    return VerseMatch("no_match", candidates=usable, cited=cited)


# ----------------------------------------------------------------------- display helpers


def uthmani_span(index: QuranIndex, c: Candidate) -> str:
    """Uthmani text of the aligned span (display always uses Uthmani, SPEC §7.1)."""
    words: list[str] = []
    for vi in c.verses:
        words.extend(w for w in index.verses[vi].uthmani.split() if normalize_ar(w))
    n_clean = sum(len(_verse_tokens(index, vi, "clean")) for vi in c.verses)
    n_form = sum(len(_verse_tokens(index, vi, c.form)) for vi in c.verses)
    if len(words) == n_clean == n_form and 0 <= c.tok_start < c.tok_end <= len(words):
        return " ".join(words[c.tok_start : c.tok_end])
    return " ".join(index.verses[vi].uthmani for vi in c.verses)


def candidate_text_clean(index: QuranIndex, c: Candidate) -> str:
    """Normalized imla'i text of the covered verses (sent to the verifier as the candidate text)."""
    return " ".join(index.verses[vi].imlaei_clean for vi in c.verses)


# =========================================================================== non-Arabic path (B12, D-19)

import re as _re  # noqa: E402

_FOOTNOTE = _re.compile(r"\[\d+\]")
_NON_WORD = _re.compile(r"[^\w\s]", _re.UNICODE)
_URDU_MARKS = _re.compile(r"[ؐ-ًؚ-ٰٟ]")


def normalize_translation(s: str) -> str:
    """Lowercase, drop footnote markers, diacritics and punctuation (English / Urdu)."""
    s = _FOOTNOTE.sub(" ", s)
    s = _URDU_MARKS.sub("", s.lower())
    s = _NON_WORD.sub(" ", s)
    return " ".join(s.split())


@dataclass
class TranslationIndex:
    """Approved QuranEnc translations in memory, per language: texts aligned with verse indices."""

    texts: dict[str, list[str]] = field(default_factory=dict)  # lang -> display text per verse index
    clean: dict[str, list[str]] = field(default_factory=dict)  # lang -> normalized text per verse index
    keys: dict[str, str] = field(default_factory=dict)  # lang -> QuranEnc translation key


_translations: TranslationIndex | None = None


def _build_translations(index: QuranIndex, rows: list[tuple[int, str, str, str]]) -> TranslationIndex:
    """rows: (verse_id, lang, tr_key, text)."""
    ti = TranslationIndex()
    id_to_idx = {v.id: i for i, v in enumerate(index.verses)}
    for vid, lang, key, text in rows:
        if lang not in ti.texts:
            ti.texts[lang] = [""] * len(index.verses)
            ti.clean[lang] = [""] * len(index.verses)
            ti.keys[lang] = key
        i = id_to_idx.get(vid)
        if i is not None:
            ti.texts[lang][i] = _FOOTNOTE.sub("", text).strip()
            ti.clean[lang][i] = normalize_translation(text)
    return ti


async def load_translations(index: QuranIndex | None = None) -> TranslationIndex | None:
    """From quran_translations in the DB, else from the local QuranEnc cache (data/raw/quranenc). Never raises."""
    global _translations
    index = index or get_index()
    if index is None:
        return None
    rows: list[tuple[int, str, str, str]] = []
    try:
        from app.db.session import get_pool

        pool = await get_pool()
        rows = [(r["verse_id"], r["lang"], r["tr_key"], r["text"])
                for r in await pool.fetch("select verse_id, lang, tr_key, text from quran_translations", timeout=BULK_LOAD_TIMEOUT_S)]
    except Exception as e:  # noqa: BLE001
        log.warning("translations_db_unavailable", extra={"error": type(e).__name__})
    if not rows:
        from app.core.config import get_settings

        s = get_settings()
        by_ref = {(v.surah, v.ayah): v.id for v in index.verses}
        for lang, key in (("en", s.quranenc_key_en), ("ur", s.quranenc_key_ur)):
            d = DATA_DIR / "raw" / "quranenc" / key
            for f in sorted(d.glob("*.json")) if d.exists() else []:
                for r in json.loads(f.read_text(encoding="utf-8")):
                    vid = by_ref.get((r["surah"], r["ayah"]))
                    if vid:
                        rows.append((vid, lang, key, r["translation"]))
    if not rows:
        log.warning("translations_unavailable")
        return None
    _translations = _build_translations(index, rows)
    log.info("translations_loaded", extra={"langs": sorted(_translations.texts)})
    return _translations


def get_translations() -> TranslationIndex | None:
    return _translations


@dataclass
class VerseCandidate:
    verses: tuple[int, ...]
    score: float  # 0-100, best evidence across paths
    via: set[str] = field(default_factory=set)  # lexical | arabic | vector


def lexical_translation_candidates(span: str, lang: str, top_k: int | None = None) -> list[VerseCandidate]:
    ti = _translations
    if ti is None or lang not in ti.clean:
        return []
    q = normalize_translation(span)
    if len(q.split()) < 2:
        return []
    k = top_k or T.VERSE_LEXICAL_TOP_K
    best: dict[int, float] = {}
    for scorer in (fuzz.token_set_ratio, fuzz.partial_ratio, fuzz.ratio):
        for _, score, i in process.extract(q, ti.clean[lang], scorer=scorer, limit=k * 4):
            best[i] = max(best.get(i, 0.0), score)
    # same mild length adjustment as the Arabic matcher, so a short verse quoted in full beats longer
    # verses that merely contain its words
    texts = ti.clean[lang]
    adj = {i: sc * (0.85 + 0.15 * min(len(q), len(texts[i])) / max(len(q), len(texts[i]), 1)) for i, sc in best.items()}
    ranked = sorted(adj.items(), key=lambda kv: -kv[1])[:k]
    return [VerseCandidate((i,), sc, {"lexical"}) for i, sc in ranked]


def arabic_query_candidates(ar_queries: list[str], index: QuranIndex) -> list[VerseCandidate]:
    out: list[VerseCandidate] = []
    for q in ar_queries:
        if len(tokens(normalize_ar(q))) < T.QURAN_MIN_WORDS:
            continue
        m = match_arabic(q, None, index)
        for c in m.candidates[:3]:
            if not c.contained and c.raw >= T.QURAN_CANDIDATE_RAW:
                out.append(VerseCandidate(c.verses, c.raw, {"arabic"}))
    return out


async def vector_candidates(span: str, lang: str, index: QuranIndex) -> list[VerseCandidate]:
    """match_verse over embedded translations. Skipped (empty) when embeddings or the DB are unavailable."""
    try:
        from app.db.session import get_pool
        from app.llm.embeddings import embed

        vec = (await embed([span], input_type="query"))[0]
        pool = await get_pool()
        rows = await pool.fetch("select verse_id, score from match_verse($1, $2, $3)", vec, lang, T.VERSE_VECTOR_TOP_K)
    except Exception as e:  # noqa: BLE001 - optional path (D-19)
        log.info("verse_vector_path_skipped", extra={"error": type(e).__name__})
        return []
    id_to_idx = {v.id: i for i, v in enumerate(index.verses)}
    return [VerseCandidate((id_to_idx[r["verse_id"]],), float(r["score"]) * 100, {"vector"})
            for r in rows if r["verse_id"] in id_to_idx]


def merge_candidates(groups: list[list[VerseCandidate]], top: int) -> list[VerseCandidate]:
    merged: dict[tuple[int, ...], VerseCandidate] = {}
    for group in groups:
        for c in group:
            m = merged.get(c.verses)
            if m is None:
                merged[c.verses] = VerseCandidate(c.verses, c.score, set(c.via))
            else:
                m.score = max(m.score, c.score)
                m.via |= c.via
    # evidence from more than one path ranks first, then the score
    return sorted(merged.values(), key=lambda c: (-len(c.via), -c.score))[:top]


async def match_translation(span: str, lang: str, ar_queries: list[str], index: QuranIndex | None = None,
                            use_vectors: bool = True) -> list[VerseCandidate]:
    """SPEC §7.3 non-Arabic quote: candidates for the verifier (top VERSE_VERIFIER_TOP)."""
    index = index or get_index()
    if index is None:
        return []
    lexical = lexical_translation_candidates(span, lang)
    arabic = arabic_query_candidates(ar_queries, index)
    vector = await vector_candidates(span, lang, index) if use_vectors else []
    return merge_candidates([lexical, arabic, vector], T.VERSE_VERIFIER_TOP)
