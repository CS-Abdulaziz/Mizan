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
        "from quran_verses order by id"
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


def same_word(a: str, b: str) -> bool:
    """Equal, or a known Uthmani / imla'i spelling variant: alif written or not, waw or ya written for alif,
    doubled letters (e.g. the two spellings of 'the heavens' or 'the prayer')."""
    if a == b:
        return True
    if min(len(a), len(b)) < 3:
        return False
    waw, ya, alif = "و", "ي", "ا"
    for x, y in ((a, b), (a.replace(waw, alif), b.replace(waw, alif)), (a.replace(ya, alif), b.replace(ya, alif))):
        if _skeleton(x) == _skeleton(y):
            return True
    return False


def word_diff(q: list[str], src: list[str]) -> list[DiffOp]:
    """Word-level differences between the quote and the aligned Mushaf span (edge rule applied)."""
    ops: list[DiffOp] = []
    codes = difflib.SequenceMatcher(None, q, src, autojunk=False).get_opcodes()
    for k, (tag, i1, i2, j1, j2) in enumerate(codes):
        if tag == "equal":
            continue
        qa, sa = q[i1:i2], src[j1:j2]
        if tag == "insert" and (k == 0 or k == len(codes) - 1):
            continue  # Mushaf words at the edges of the aligned span: partial quoting, not an alteration
        if tag == "replace":
            if "".join(qa) == "".join(sa) or same_word("".join(qa), "".join(sa)):
                continue  # words split / joined differently, or one spelling variant
            if len(qa) == len(sa) and all(same_word(x, y) for x, y in zip(qa, sa)):
                continue
        op = {"replace": "replace", "delete": "insert", "insert": "delete"}[tag]
        ops.append(DiffOp(op, " ".join(qa), " ".join(sa)))
    return ops


# ----------------------------------------------------------------------- core


def _verse_tokens(index: QuranIndex, vi: int, form: str) -> list[str]:
    v = index.verses[vi]
    return tokens(v.clean if form == "clean" else v.imlaei_clean)


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
        ops=word_diff(q_tokens, aligned), tok_start=tok_start - first_off, tok_end=tok_end - first_off,
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
                if q_tokens and all(any(same_word(t, x) for x in vt) for t in q_tokens):
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
