# Licenses and terms

## Data sources

| Source | What we use | Terms as found (2026-10-06) | How we comply |
|---|---|---|---|
| King Fahd Complex for the Printing of the Holy Quran, developer data (`qurancomplex.gov.sa/quran-dev`) | Hafs Mushaf text v3.0 (Uthmani + imla'i) | Published for developers; footer "جميع الحقوق محفوظة"; no explicit redistribution license | Not committed to git; downloaded at build/ingest time (D-10). Text shown unchanged, with source attribution. |
| QuranEnc (`quranenc.com`) | Approved translations: English (Rowwad), Urdu (Junagarhi) | Public API of the Encyclopedia of Translations of the Quran | Translations shown verbatim with a link to the verse page; only fixtures committed. |
| HadeethEnc (`hadeethenc.com`) | Hadith texts, grades, attributions, approved translations | Public API of the Encyclopedia of Translated Prophetic Hadiths | Shown verbatim with a link to the hadith page; only fixtures committed. |
| Dorar.net hadith encyclopedia (`dorar.net`) | Official search API (`dorar_api.json`): texts, scholars, books, gradings | Official public API documented at `dorar.net/article/389` | Gradings shown verbatim with scholar and book and a link to Dorar's search; results cached; descriptive User-Agent; no scraping beyond the API. |
| Reference pack (challenge) | Content levels, standard, page-6 test questions, glossary | Provided to participants | Used for policy, bench questions and the reply glossary. |

The team should confirm the source terms with the organizers before the repo is public; nothing in the repo
redistributes full source datasets (fixtures are small samples).

## Software

| Package | License |
|---|---|
| FastAPI, Starlette, Pydantic, pydantic-settings, Uvicorn, httpx, respx | MIT / BSD-3 |
| rapidfuzz | MIT |
| asyncpg | Apache-2.0 |
| pgvector (Python) | MIT |
| beautifulsoup4, lxml | MIT, BSD-3 |
| langdetect | Apache-2.0 |
| python-telegram-bot | LGPL-3.0 (used as an unmodified library) |
| anthropic (optional provider) | MIT |
| pytest, pytest-asyncio | MIT / Apache-2.0 |
| matplotlib (bench charts) | PSF-based |

## Model providers

Gemini API and Groq are used on their free tiers (D-15). Google's terms for the unpaid Gemini API allow inputs
to be used to improve its products; Groq's data terms should be checked by the team. Because of this, the About
page privacy text (`core/messages.PRIVACY`) tells users the provider may use submitted text and asks them not to
send personal or sensitive information.
