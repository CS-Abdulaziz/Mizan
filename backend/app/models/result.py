"""Response models: exactly the shapes in docs/API_CONTRACT.md (shared with the frontend)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["verified", "misquoted", "not_established", "disputed", "not_found", "needs_review"]
Status = Literal["ok", "no_claims", "evidence_request", "referral"]
GradeClass = Literal["accepted", "accepted_isnad", "weak", "very_weak", "unclassified"]
Note = Literal["too_short", "out_of_scope_attribution", "multiple_locations", "takhrij_has_weak_chains"]


class Location(BaseModel):
    surah: int
    ayah: int
    surah_name_ar: str
    surah_name_en: str
    url: str


class Grading(BaseModel):
    mohaddith: str
    book: str
    page: str
    grade_text: str
    grade_class: GradeClass


class Evidence(BaseModel):
    source: Literal["quran", "dorar", "hadeethenc"] | None = None
    text_arabic: str | None = None
    translation: str | None = None
    locations: list[Location] = Field(default_factory=list)
    gradings: list[Grading] = Field(default_factory=list)
    url: str | None = None


class DiffOp(BaseModel):
    op: str
    quoted: str
    source: str


class Diff(BaseModel):
    kind: Literal["wording", "attribution", "wrong_type"]
    ops: list[DiffOp] = Field(default_factory=list)
    details: str | None = None


class Alternative(BaseModel):
    source: Literal["hadeethenc", "dorar"]
    id: int | str
    text_arabic: str
    translation: str | None = None
    attribution: str | None = None
    url: str
    label: Literal["different_hadith_related_meaning"] = "different_hadith_related_meaning"


class ClaimResult(BaseModel):
    index: int
    type: Literal["quran", "hadith", "attributed_saying"]
    span: str
    span_start: int
    span_end: int
    lang: str
    verdict: Verdict
    relation: Literal["exact", "same_meaning", "altered"] | None = None
    confidence: float = 0.0
    evidence: Evidence = Field(default_factory=Evidence)
    diff: Diff | None = None
    alternative: Alternative | None = None
    notes: list[Note] = Field(default_factory=list)
    source_status: Literal["ok", "source_unavailable"] = "ok"


class Referral(BaseModel):
    reason: Literal["personal_ruling"] = "personal_ruling"
    text: str


class CheckResult(BaseModel):
    check_id: str
    status: Status
    lang: str
    referral: Referral | None = None
    message: str | None = None
    claims: list[ClaimResult] = Field(default_factory=list)
    disclaimer: str
    reply_available: bool = False
    expires_at: str


class CheckRequest(BaseModel):
    text: str
    channel: Literal["web", "telegram", "api"] = "web"
    lang_hint: str | None = None
