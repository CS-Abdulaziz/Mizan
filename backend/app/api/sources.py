"""GET /api/v1/sources: sources, links, licenses + privacy and limits text for the About page."""

from __future__ import annotations

from fastapi import APIRouter

from app.core import messages as M

router = APIRouter(prefix="/api/v1")

SOURCES = [
    {"name": "Mushaf (King Fahd Complex, Hafs)", "url": "https://qurancomplex.gov.sa/quran-dev/",
     "used_for": "Quran text (Uthmani display, imla'i matching)", "license": "© King Fahd Complex; used as published"},
    {"name": "QuranEnc", "url": "https://quranenc.com",
     "used_for": "Approved English (Rowwad) and Urdu (Junagarhi) translations", "license": "Terms of QuranEnc"},
    {"name": "HadeethEnc", "url": "https://hadeethenc.com",
     "used_for": "Authentic hadiths with approved translations", "license": "Terms of HadeethEnc"},
    {"name": "Dorar.net hadith encyclopedia", "url": "https://dorar.net/hadith",
     "used_for": "Scholars' gradings, sources and widespread unestablished hadiths", "license": "Terms of Dorar.net"},
]


@router.get("/sources")
async def sources(lang: str = "ar") -> dict:
    return {"sources": SOURCES, "privacy": M.localized(M.PRIVACY, lang), "limits": M.LIMITS.get(lang, M.LIMITS["ar"])}
