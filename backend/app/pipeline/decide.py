"""Decision engine (SPEC §8.2-8.4, AMENDMENT 1, 7; DECISIONS D-1, D-5). NEEDS SH SIGN-OFF (pending, D-20).

Pure functions: no I/O, no model calls. The orchestrator gathers the inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.pipeline.grades import is_sahihayn
from app.pipeline.normalize import normalize_ar


@dataclass(frozen=True)
class GradeIn:
    grade_class: str  # accepted | accepted_isnad | weak | very_weak | unclassified
    book: str = ""
    from_hadeethenc: bool = False


def hadith_verdict(gradings: list[GradeIn]) -> str | None:
    """SPEC §8.2 table with D-1 (unclassified gradings are neutral). None when there is no grading at all."""
    if not gradings:
        return None
    classified = [g for g in gradings if g.grade_class != "unclassified"]
    if not classified:
        return "needs_review"  # row 7: all gradings unclassified
    classes = {g.grade_class for g in classified}
    accepted = [g for g in classified if g.grade_class == "accepted"]
    if any(g.from_hadeethenc or is_sahihayn(g.book) for g in accepted):
        return "verified"  # row 1
    if accepted and "very_weak" not in classes:
        return "verified"  # row 2
    if accepted:
        return "disputed"  # row 3: accepted vs very weak
    if classes == {"accepted_isnad"}:
        return "verified"  # row 4
    if "accepted_isnad" in classes:
        return "disputed"  # row 5: accepted_isnad with weak / very_weak
    return "not_established"  # row 6: all weak / very_weak


def apply_relation(verdict: str, relation: str | None) -> str:
    """Altered + verified -> misquoted; altered + not_established stays not_established (§8.2)."""
    if relation == "altered" and verdict == "verified":
        return "misquoted"
    return verdict


def has_weak_chains(gradings: list[GradeIn]) -> bool:
    return any(g.grade_class in ("weak", "very_weak") for g in gradings)


# Books people cite, with the Arabic words that identify them in Dorar book / scholar names and in
# HadeethEnc attributions ("رواه البخاري ومسلم").
BOOKS: dict[str, tuple[list[str], list[str]]] = {
    # key: (latin aliases, arabic words)
    "bukhari": (["bukhari", "bukhaari"], ["البخاري"]),
    "muslim": (["muslim"], ["مسلم"]),
    "abu_dawud": (["abu dawud", "abu dawood", "abu daud", "abi dawud"], ["ابو داود", "ابي داود"]),
    "tirmidhi": (["tirmidhi", "tirmizi", "tirmithi"], ["الترمذي"]),
    "nasai": (["nasai", "nasa'i", "nasaai", "nisai"], ["النسايي"]),
    "ibn_majah": (["ibn majah", "ibn maja"], ["ابن ماجه"]),
    "ahmad": (["ahmad", "musnad"], ["احمد", "المسند"]),
    "malik": (["malik", "muwatta"], ["مالك", "الموطا"]),
}


def cited_books(claimed_source: str | None) -> set[str]:
    if not claimed_source:
        return set()
    low = claimed_source.lower()
    ar = " " + normalize_ar(claimed_source) + " "
    out = set()
    for key, (latin, arabic) in BOOKS.items():
        if any(re.search(rf"\b{re.escape(a)}\b", low) for a in latin) or any(f" {normalize_ar(w)} " in ar for w in arabic):
            out.add(key)
    return out


def books_in_sources(texts: list[str]) -> set[str]:
    """Which known books appear in the matched sources' book / scholar / attribution strings."""
    joined = " " + " ".join(normalize_ar(t) for t in texts) + " "
    return {key for key, (_, arabic) in BOOKS.items() if any(f" {normalize_ar(w)} " in joined for w in arabic)}


def attribution_mismatch(claimed_source: str | None, source_texts: list[str]) -> bool:
    """§8.2: the claim names a book that is not among the matched sources."""
    cited = cited_books(claimed_source)
    if not cited:
        return False
    return not (cited & books_in_sources(source_texts))


def message_status(intent: str, personal_ruling_request: bool, n_claims: int) -> str:
    """§8.4 with D-5: referral takes precedence over ok; claims are still verified and returned."""
    if personal_ruling_request or intent == "personal_ruling":
        return "referral"
    if n_claims > 0:
        return "ok"
    if intent == "evidence_request":
        return "evidence_request"
    return "no_claims"


def unmatched_verdict(source_status: str) -> tuple[str, str]:
    """No accepted match. Never a positive verdict; an outage is reported as such, not as absence (§4.1)."""
    return "not_found", ("source_unavailable" if source_status == "source_unavailable" else "ok")


def out_of_scope_attribution() -> tuple[str, list[str]]:
    """Sayings attributed to scholars / Companions are out of scope (§1)."""
    return "not_found", ["out_of_scope_attribution"]
