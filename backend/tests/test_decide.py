"""Decision engine (SPEC §8.2-8.4, D-1, D-5). One test per §8.2 row, plus relation, attribution and statuses."""

from __future__ import annotations

import pytest

from app.pipeline.decide import (
    GradeIn,
    apply_relation,
    attribution_mismatch,
    hadith_verdict,
    has_weak_chains,
    message_status,
)

A, AI, W, VW, U = "accepted", "accepted_isnad", "weak", "very_weak", "unclassified"


def g(cls: str, book: str = "كتاب", he: bool = False) -> GradeIn:
    return GradeIn(cls, book, he)


def test_row1_accepted_from_sahihayn_beats_very_weak() -> None:
    assert hadith_verdict([g(A, "صحيح البخاري"), g(VW), g(W)]) == "verified"


def test_row1_hadeethenc_match_is_verified() -> None:
    assert hadith_verdict([g(A, "", he=True), g(VW)]) == "verified"


def test_row2_accepted_without_very_weak() -> None:
    assert hadith_verdict([g(A), g(W)]) == "verified"


def test_row3_accepted_and_very_weak_disputed() -> None:
    assert hadith_verdict([g(A), g(VW)]) == "disputed"


def test_row4_only_accepted_isnad() -> None:
    assert hadith_verdict([g(AI), g(AI)]) == "verified"


def test_row5_accepted_isnad_with_weak_disputed() -> None:
    assert hadith_verdict([g(AI), g(W)]) == "disputed"
    assert hadith_verdict([g(AI), g(VW)]) == "disputed"


def test_row6_all_weak_not_established() -> None:
    assert hadith_verdict([g(W), g(VW)]) == "not_established"


def test_row7_all_unclassified_needs_review() -> None:
    assert hadith_verdict([g(U), g(U)]) == "needs_review"


def test_d1_unclassified_is_neutral() -> None:
    assert hadith_verdict([g(W), g(U)]) == "not_established"
    assert hadith_verdict([g(AI), g(U)]) == "verified"


def test_no_gradings_is_none() -> None:
    assert hadith_verdict([]) is None


def test_altered_verified_becomes_misquoted() -> None:
    assert apply_relation("verified", "altered") == "misquoted"
    assert apply_relation("not_established", "altered") == "not_established"
    assert apply_relation("verified", "exact") == "verified"


def test_attribution_mismatch() -> None:
    assert attribution_mismatch("Bukhari", ["صحيح مسلم", "مسلم"])
    assert not attribution_mismatch("Bukhari", ["صحيح البخاري", "البخاري"])
    assert not attribution_mismatch("رواه البخاري", ["رواه البخاري ومسلم"])
    assert not attribution_mismatch(None, ["صحيح مسلم"])
    assert not attribution_mismatch("my teacher", ["صحيح مسلم"])  # no book named: nothing to check


def test_weak_chains_note() -> None:
    assert has_weak_chains([g(A, "صحيح البخاري"), g(W)])
    assert not has_weak_chains([g(A), g(U)])


@pytest.mark.parametrize(
    "intent, ruling, n, expected",
    [
        ("claims", False, 2, "ok"),
        ("no_claims", False, 0, "no_claims"),
        ("claims", False, 0, "no_claims"),  # no claim survived validation
        ("evidence_request", False, 0, "evidence_request"),
        ("personal_ruling", True, 0, "referral"),
        ("claims", True, 2, "referral"),  # D-5: claims still verified, status referral
    ],
)
def test_message_status(intent: str, ruling: bool, n: int, expected: str) -> None:
    assert message_status(intent, ruling, n) == expected


def test_source_unavailable_never_positive() -> None:
    from app.pipeline.decide import unmatched_verdict

    assert unmatched_verdict("source_unavailable") == ("not_found", "source_unavailable")
    assert unmatched_verdict("ok") == ("not_found", "ok")


def test_attributed_saying_out_of_scope() -> None:
    from app.pipeline.decide import out_of_scope_attribution

    assert out_of_scope_attribution() == ("not_found", ["out_of_scope_attribution"])
