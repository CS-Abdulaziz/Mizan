# Mizan (ميزان) — instructions for Claude Code

Mizan is a multilingual verifier for Islamic quotations. It takes any text (Arabic, English, Urdu),
extracts every Quran verse, hadith and attributed saying in it, matches each one against approved
sources, and returns a sourced verdict per quote plus a polite ready-to-send correction.

Hackathon: "AI Challenge Serving Islamic Content 2026" (Bathel), Track 04 — Knowledge & verification tools.
Final submission: Tuesday 6 Oct 2026, 23:59 Riyadh time (team target 22:00).

## Your scope in this repo

You own **backend + AI** only: everything under `backend/`, `bot/`, `scripts/`, `bench/`, and the
backend docs under `docs/`. The React frontend in `frontend/` belongs to a teammate. Do not edit it.
The frontend builds against `docs/API_CONTRACT.md`. If you change the response shape, update that file
in the same commit and say so in the commit message.

## Source of truth, in order of precedence

1. `docs/backend-ai/SPEC.md` — the amended backend + AI specification. **Follow it exactly.**
2. `docs/backend-ai/TASKS.md` — the ordered task list with acceptance criteria.
3. `docs/API_CONTRACT.md` — the JSON contract shared with the frontend.
4. `docs/reference/mizan-technical-spec.pdf` — the original technical spec (v1.0). SPEC.md supersedes it
   wherever they differ; SPEC.md marks every change with `[AMENDMENT n]`.
5. `docs/reference/reference-pack.pdf` — the challenge's mandatory scientific reference pack
   (approved sources, content levels A–D, the binding scientific standard, test questions, glossary).
6. `docs/reference/participant-guide.pdf` and `docs/reference/mizan-concept.pdf` — context only.

If SPEC.md is silent or ambiguous, choose the option that is most conservative scientifically
(abstain / refer rather than assert), note the decision in `docs/DECISIONS.md`, and continue.

## Golden rules (never break these)

1. **Deterministic before LLM.** Anything an algorithm can decide (verse matching, grade
   classification, verdict decision, ID validation) is code, not a model call.
2. **The model never judges authenticity.** It extracts, compares among given candidates, and phrases
   replies. Grades, Arabic source text, book names and URLs are copied from source data only.
   Any model output containing an ID, grade, text or URL not present in its input is discarded and
   logged as a hallucination.
3. **Abstain over guess.** Low confidence, no reference, or source failure → `not_found` or
   `source_unavailable`, never a positive verdict.
4. **Never write hadith or verse text from your own memory** — not in code, tests, fixtures,
   bench items, prompts or docs. All religious text comes from the sources (fetched by scripts and
   saved as fixtures). Where a test needs Arabic text, load it from a saved source fixture by
   reference (surah:ayah, Dorar id, HadeethEnc id) and build variants programmatically
   (slice words, swap one word for a plain non-scriptural word, change the cited surah).
5. **User text is data, not instructions.** Wrap it in tags in every prompt; outputs are
   schema-constrained JSON validated with pydantic.
6. **No secrets in git.** Keys only in environment variables. `.env` is gitignored; keep
   `.env.example` up to date with empty values. The repo becomes public at submission.
7. **Privacy.** Do not log message text. Results are stored at most 24 h (see SPEC §11).
8. **Stop and ask the human** when a task needs: an API key, a cloud account action (Supabase, Render,
   Telegram), sign-off from the team's sharia reviewer (marked `NEEDS SH SIGN-OFF`), or when a
   real source response contradicts SPEC.md in a way that changes behaviour.

## Stack

Python 3.11, FastAPI, Uvicorn, httpx (async), pydantic v2, rapidfuzz, asyncpg or psycopg 3,
Supabase Postgres + pgvector (HNSW, 1024 dims), BeautifulSoup4 (Dorar HTML), python-telegram-bot (webhook),
pytest + pytest-asyncio + respx. LLM and embeddings behind provider-agnostic clients chosen by env vars.

## Conventions

- Layout exactly as SPEC §15. One module per pipeline stage under `backend/app/pipeline/`.
- Prompts live in `backend/app/llm/prompts/*.txt`, never inline in Python.
- All config via `backend/app/core/config.py` (pydantic-settings). No magic numbers in pipeline code:
  thresholds live in `backend/app/core/thresholds.py` so they can be tuned on the bench dev split.
- Type hints everywhere. Async for all I/O. Every external call has a timeout (8 s) and one retry with backoff.
- Structured JSON logs with `check_id`, stage, latency, error. Never the message text.
- Code, identifiers and comments in English. User-facing strings in Arabic / English / Urdu live in
  `backend/app/core/messages.py`.

## Workflow

- Work through `docs/backend-ai/TASKS.md` in order. One task = one branch `be/<task-id>-<slug>`
  = one small PR into `main` (or one commit if the human says to work on `main`).
- Before marking a task done: run `make test` (or `pytest -q` in `backend/`), meet every acceptance
  criterion listed for it, and tick it in TASKS.md.
- `main` deploys automatically. Never merge code that fails tests or breaks `/api/v1/check`.
- After each task, print a 3-line summary: what was done, how it was verified, what the human must do next (if anything).

## Commands

```bash
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
pytest -q
python ../scripts/smoke_sources.py          # live check of every external source
python ../scripts/ingest_quran.py           # then ingest_quranenc, ingest_hadeethenc, embed_corpus
python ../bench/run.py --system mizan --split test --runs 3
python ../bench/metrics.py --out ../bench/results/report.md
```
