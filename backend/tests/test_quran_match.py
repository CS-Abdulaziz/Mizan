"""Verse matcher (SPEC §7.3, AMENDMENT 4, DECISIONS D-2, D-3, D-13).

Every quote is built from data/quran.json by reference (surah:ayah, token slices, one word swapped for a
plain non-Quranic word). No verse text is typed here.
"""

from __future__ import annotations

import pytest

from app.pipeline import quran_match as qm
from app.pipeline import surah_parse
from app.pipeline.normalize import tokens

pytestmark = pytest.mark.skipif(
    not qm.QURAN_JSON.exists(), reason="data/quran.json missing: run python scripts/ingest_quran.py"
)

PLAIN_WORD = "حاسوب"  # 'computer': a plain modern word that does not occur in the Quran


@pytest.fixture(scope="module")
def idx() -> qm.QuranIndex:
    index = qm.load_from_json()
    qm._index = index
    return index


def v(idx: qm.QuranIndex, s: int, a: int) -> qm.Verse:
    return idx.verses[idx.by_ref[(s, a)]]


def refs(idx: qm.QuranIndex, verses: tuple[int, ...]) -> list[tuple[int, int]]:
    return [(idx.verses[i].surah, idx.verses[i].ayah) for i in verses]


def test_plain_word_is_not_quranic(idx: qm.QuranIndex) -> None:
    assert all(PLAIN_WORD not in tokens(x.imlaei_clean) for x in idx.verses)


def test_case1_one_word_swapped_in_full_verse(idx: qm.QuranIndex) -> None:
    t = tokens(v(idx, 2, 255).imlaei_clean)
    q = list(t)
    original = q[7]
    q[7] = PLAIN_WORD
    m = qm.match_arabic(" ".join(q), None, idx)
    assert m.status == "misquoted_candidate"
    assert refs(idx, m.best.verses) == [(2, 255)]  # not 3:2, although 3:2 is contained in the quote
    assert [(o.op, o.quoted, o.source) for o in m.best.ops] == [("replace", PLAIN_WORD, original)]


def test_case2_correct_partial_quote(idx: qm.QuranIndex) -> None:
    q = " ".join(tokens(v(idx, 2, 255).imlaei_clean)[10:17])
    m = qm.match_arabic(q, None, idx)
    assert m.status == "verified" and refs(idx, m.locations[0]) == [(2, 255)] and m.best.ops == []


def test_case3_phrase_in_two_verses(idx: qm.QuranIndex) -> None:
    q = " ".join(tokens(v(idx, 2, 153).imlaei_clean)[-4:])
    m = qm.match_arabic(q, None, idx)
    assert m.status == "verified"
    locs = [refs(idx, loc)[0] for loc in m.locations]
    assert (2, 153) in locs and (8, 46) in locs


def test_case4_short_verse_that_opens_another(idx: qm.QuranIndex) -> None:
    m = qm.match_arabic(v(idx, 3, 2).imlaei_clean, None, idx)
    assert m.status == "verified"
    assert [refs(idx, loc)[0] for loc in m.locations] == [(3, 2), (2, 255)]


def test_case5_correct_text_wrong_surah_cited(idx: qm.QuranIndex) -> None:
    m = qm.match_arabic(v(idx, 2, 255).imlaei_clean, "Al-Imran 2", idx)
    assert m.status == "attribution"
    assert refs(idx, m.locations[0]) == [(2, 255)]


def test_case6_under_three_words_no_attribution(idx: qm.QuranIndex) -> None:
    m = qm.match_arabic(" ".join(tokens(v(idx, 2, 255).imlaei_clean)[:2]), None, idx)
    assert m.status == "too_short" and m.note == "too_short"


def test_d2_short_quote_with_matching_citation(idx: qm.QuranIndex) -> None:
    q = " ".join(tokens(v(idx, 2, 255).imlaei_clean)[:2])
    m = qm.match_arabic(q, "2:255", idx)
    assert m.status == "verified" and refs(idx, m.locations[0]) == [(2, 255)]


def test_d2_short_quote_with_wrong_citation(idx: qm.QuranIndex) -> None:
    q = " ".join(tokens(v(idx, 2, 255).imlaei_clean)[-2:])
    m = qm.match_arabic(q, "1:1", idx)
    assert m.status == "too_short" and m.note == "too_short"


def test_d3_uthmani_salah_spelling_matches_imlaei_quote(idx: qm.QuranIndex) -> None:
    """A verse whose Uthmani spelling of 'the prayer' differs from the imla'i one must match an imla'i quote."""
    target = None
    for x in idx.verses:
        ut, im = tokens(x.clean), tokens(x.imlaei_clean)
        if len(ut) == len(im) and 6 <= len(im) <= 25:
            pairs = [(a, b) for a, b in zip(ut, im) if a != b]
            if any(a.endswith("لوه") and b.endswith("لاه") for a, b in pairs):
                target = x
                break
    assert target is not None, "no verse with the Uthmani/imla'i salah spelling difference found in the data"
    m = qm.match_arabic(target.imlaei_clean, None, idx)
    assert m.status == "verified"
    assert (target.surah, target.ayah) in [refs(idx, loc)[0] for loc in m.locations]
    # and the Uthmani form matches as well
    assert qm.match_arabic(target.uthmani, None, idx).status == "verified"


def test_uthmani_display_span_comes_from_data(idx: qm.QuranIndex) -> None:
    q = " ".join(tokens(v(idx, 2, 255).clean)[10:17])
    m = qm.match_arabic(q, None, idx)
    span = qm.uthmani_span(idx, m.best)
    assert span and span in v(idx, 2, 255).uthmani


def test_word_diff_ignores_spelling_variants_and_edges() -> None:
    assert qm.same_word("السموات", "السماوات") and qm.same_word("الصلوه", "الصلاه")
    assert not qm.same_word("يعلمون", "تعلمون")
    # Mushaf words before/after the quoted part are not alterations
    assert qm.word_diff(["ب", "ج"], ["ا", "ب", "ج", "د"]) == []


@pytest.mark.parametrize(
    "cited, expected",
    [
        ("2:255", (2, 255)),
        ("Quran 2/255", (2, 255)),
        ("Al-Baqarah 255", (2, 255)),
        ("البقرة 255", (2, 255)),
        ("سورة البقرة، الآية ٢٥٥", (2, 255)),
        ("Surah 2, verse 255", (2, 255)),
        ("Al-Imran 2", (3, 2)),
        ("سورة الفاتحة", (1, None)),
        ("سورة ص", (38, None)),
        ("سورة ق 5", (50, 5)),
        ("سورة طه", (20, None)),
        ("سورة يس", (36, None)),
        ("Bukhari", None),
        (None, None),
    ],
)
def test_surah_parser(idx: qm.QuranIndex, cited: str | None, expected: tuple | None) -> None:
    assert surah_parse.parse(cited) == expected
