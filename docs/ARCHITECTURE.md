# Mizan architecture (backend + AI)

Mizan takes any message (Arabic, English, Urdu), extracts every quoted verse, hadith and attributed saying,
matches each one against approved sources, and returns a sourced verdict per quote plus a polite ready reply.
The building rule is **deterministic before LLM**: matching, grading, verdicts and id checks are code; the model
only extracts, compares among given candidates, and phrases.

```mermaid
flowchart LR
    U[Web app / Telegram / API] -->|POST /api/v1/check| O[Orchestrator]
    O --> X[Extract: 1 LLM call + rule detector]
    X -->|each claim, in parallel| R{Route}
    R -->|Arabic text, any type (D-4)| Q[Verse matcher: Mushaf in memory, Uthmani + imla'i]
    R -->|en / ur verse| T[Translation path: lexical + Arabic queries + vectors]
    R -->|hadith| H[Hadith retriever: Dorar + HadeethEnc local + vectors]
    Q --> V[Verifier: LLM picks among candidate ids]
    T --> V
    H --> V
    V --> D[Decision engine: grade rules + verdict table]
    Q -->|exact match| D
    D --> C[Cards: verdict, source text, gradings, links]
    C -->|24 h| S[(Supabase: check_results, metrics, dorar_cache)]
    C -->|POST /api/v1/reply| P[Ready reply: LLM, facts only, URL-checked]
```

| Stage | Module | Deterministic? | Notes |
|---|---|---|---|
| Intake | `pipeline/orchestrator.py` | yes | 4,000 chars, language, LRU cache, 20 req/min/IP |
| Extraction | `pipeline/extract.py`, `rules_detect.py` | LLM + rules | spans must be substrings (offsets from the message); Arabic-script queries only; lead-ins trimmed (D-23) |
| Verse matcher | `pipeline/quran_match.py` | yes | rapidfuzz alignment on both spellings, containment guard, diff inside the aligned span, multi-location, attribution (SPEC §7.3, D-2, D-3, D-13) |
| Translation path | `quran_match.match_translation` | yes (+ optional vectors) | approved QuranEnc translations in memory (D-19) |
| Hadith retrieval | `pipeline/hadith_retrieve.py` | yes | Dorar (cached) with matn grouping; HadeethEnc local index; vectors optional |
| Verifier | `pipeline/verify.py` | LLM, constrained | sees ids + texts only, never gradings; ids validated in code |
| Grades / verdict | `pipeline/grades.py`, `decide.py`, `core/grade_rules.py` | yes | SPEC §8.1-8.4 + D-1; pending sharia sign-off (D-20) |
| Alternative | `pipeline/alternative.py` | vectors | only for not_established, labelled as a different hadith |
| Reply | `pipeline/reply.py` | LLM | built from decided facts only; foreign URLs rejected |
| Bot | `bot/telegram_bot.py` | - | webhook in the same process |

## Providers (free tiers, D-15 - D-21)

- LLM: Gemini through its OpenAI-compatible endpoint (extract/reply `gemini-3.6-flash`, verify `gemini-3.5-flash`),
  fallback to the other Gemini Flash models, then Groq `openai/gpt-oss-120b`. Every call records its provider in
  `check_metrics.llm_providers`.
- Embeddings: `gemini-embedding-001`, 1024 dims, L2-normalized; about 1,000 texts/day on the free tier, so vector
  paths are optional and the lexical / Dorar paths carry the pipeline (D-19).

## Data

| Store | Content | Lifetime |
|---|---|---|
| Memory (startup) | Mushaf 6,236 verses + 18,366 windows (2 spellings), approved translations, HadeethEnc index | process |
| `quran_verses`, `quran_translations` | Mushaf + QuranEnc en/ur | permanent |
| `hadiths`, `hadith_translations` | HadeethEnc ar/en/ur (+ embeddings) | permanent |
| `dorar_cache` | parsed Dorar results per normalized query | the challenge |
| `check_results` | result JSON + ready replies | 24 h |
| `check_metrics`, `feedback` | counts, latency, tokens, providers; feedback without message text | permanent |

Privacy: logs never contain message text; Telegram user ids are salted hashes; results are deleted after 24 h
(SPEC §13, `docs/CONTENT_POLICY.md`).
