"""Grade classification (SPEC §8.1): grading phrases, not scripture."""

from __future__ import annotations

import pytest

from app.pipeline.grades import classify


@pytest.mark.parametrize(
    "book, grading, expected",
    [
        ("any", "صحيح", "accepted"),
        ("any", "ضعيف جداً", "very_weak"),
        ("any", "حسن صحيح", "accepted"),
        ("any", "إسناده صحيح", "accepted_isnad"),
        ("any", "[صحيح] وهذا إسناد ضعيف", "accepted"),  # v1.0 gave weak
        ("any", "رجاله ثقات", "unclassified"),
        ("صحيح البخاري", "أخرجه البخاري", "accepted"),  # v1.0 gave unclassified
        ("any", "لم يصح", "very_weak"),
    ],
)
def test_spec_cases(book: str, grading: str, expected: str) -> None:
    assert classify(book, grading) == expected


@pytest.mark.parametrize(
    "grading, expected",
    [
        ("[ضعيف] وله شاهد", "weak"),
        ("منكر جداً", "very_weak"),
        ("إسناده ضعيف", "weak"),
        ("أخرجه أبو داود", "unclassified"),
        ("سكت عنه", "unclassified"),
        ("أخرجه في صحيحه", "unclassified"),  # whole-word match: «صحيحه» is not «صحيح» (D-11, pending SH)
        ("صحيح لغيره", "accepted"),
        ("مرسل", "weak"),
    ],
)
def test_more_phrases(grading: str, expected: str) -> None:
    assert classify("كتاب", grading) == expected


def test_sahih_muslim_book_wins_over_text() -> None:
    assert classify("صحيح مسلم", "") == "accepted"
