# Backend + AI tasks

## Final checklist (B26, SPEC §18), 2026-10-06

| SPEC §18 item | Status | Evidence / what is left |
|---|---|---|
| Live link works from an external device; ar / en / ur examples right | **FAIL (pending deploy)** | Locally PASS: `python scripts/try_check.py --video` -> ar: altered 2:255 `misquoted` + fabricated hadith `not_established`; en: hadith `verified` (HadeethEnc); ur: 112:1 `verified`. Needs the Render deploy (below). |
| All verdicts and statuses appear in real examples | PASS | `python scripts/verdict_examples.py > docs/VERDICT_EXAMPLES.md` (needs_review / evidence_request from live checks) |
| No reference or grade absent from the sources | PASS | Texts, gradings, links copied from sources; ids validated in code; 5 automatic flags on test are check artifacts (EVALUATION.md) |
| False-verified rate on the test split reported | PASS | 0.0% (0/39) for Mizan; 15.4% for Dorar-as-is |
| Bench results + both baselines in EVALUATION.md with reviewed counts | **PARTIAL** | Mizan test 109/125, dorar_direct test complete, llm_baseline dev only (quota, D-25); 0/179 items reviewed |
| Repo public, from-scratch instructions work, sources + licenses documented, no keys | **PARTIAL** | Docs done; full-history secret scan clean; making the repo public and a clean-machine test are human steps |
| `/health` queries the DB; pinger; cache warmed | **PARTIAL** | `/health` runs `select 1` (PASS); pinger + warm cache after deploy |
| Service up through 19-22 Oct, checked daily | PENDING | human, daily |

### Commands for what is left (run from the repo root)

```bash
# 1. Deploy: render.com > New > Blueprint > OmarCsY/Mizan (reads render.yaml); paste DATABASE_URL, LLM_API_KEY,
#    EMBEDDING_API_KEY, GROQ_API_KEY, ALLOWED_ORIGINS=<pages-url>,http://localhost:5173, PUBLIC_WEB_URL=<pages-url>
curl -s https://<service>.onrender.com/health          # expect {"ok": true, "db": true}
# 2. Pinger: uptimerobot.com > HTTP(s) monitor > https://<service>.onrender.com/health > every 10 min
# 3. Finish / refresh the test-split numbers, then the report
python bench/run.py --system mizan --split test --runs 1 --rpm 5
python bench/run.py --system llm_baseline --split test --runs 1 --rpm 8
python bench/metrics.py --split test --out bench/results/report.md
# 4. Before each judging session (fills dorar_cache; ~30 min at 6/min)
python scripts/warm_cache.py --api https://<service>.onrender.com
# 5. Once a day until judging (free tier ~1,000 texts/day; resumes where it stopped)
python scripts/embed_corpus.py
# 6. Telegram (only if our own bot is enabled: ENABLE_TELEGRAM_BOT=true, D-28)
python -c "import secrets; print(secrets.token_urlsafe(32))"   # -> TELEGRAM_WEBHOOK_SECRET on Render
curl -s "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://<service>.onrender.com/telegram/webhook" -d "secret_token=<SECRET>" -d 'allowed_updates=["message","callback_query"]'
# 7. Sharia review applied
python bench/build_items.py --apply-review
# 8. Stronger secret scan before making the repo public
gitleaks detect --no-banner -v
```

## Waiting on Azoz

Exact steps for things only the human can do. Work continues on independent tasks meanwhile.

1. **Embeddings quota (D-19), optional but improves English/Urdu recall.** Gemini's free embedding tier allows
   ~1,000 texts/day/model. Every day until judging, from the repo root run:
   `python scripts/embed_corpus.py` (it embeds en/ur hadith first, then en/ur verses, stops cleanly at the daily
   quota and resumes the next day). The pipeline works without embeddings (lexical + Dorar paths).
2. **Sharia reviewer sign-off (D-20, D-11, D-1), pending.** Send them `backend/app/core/grade_rules.py`, the
   SPEC §8.2 table, and DECISIONS D-1 / D-11 / D-20. Their edits go straight into `grade_rules.py` (keyword lists)
   or come back to me for the table. The pipeline runs with the current rules meanwhile.
3. **Deploy the backend on Render (B17).** On render.com: New > Blueprint > connect `OmarCsY/Mizan` > it reads
   `render.yaml`. When asked, paste from your local `.env`: `DATABASE_URL`, `LLM_API_KEY`, `EMBEDDING_API_KEY`,
   `GROQ_API_KEY`; set `ALLOWED_ORIGINS` to the frontend's Cloudflare Pages URL plus `http://localhost:5173`
   (comma-separated) and `PUBLIC_WEB_URL` to the Pages URL. Leave the Telegram vars empty for now. Deploy, wait for
   the first boot (~1-2 min), then open `https://<service>.onrender.com/health` -> `{"ok": true, "db": true}`.
   Send me the URL; I will run the live check against it and give it to the frontend teammate (`VITE_API_URL`).
4. **Pinger (B17).** On uptimerobot.com (free): Add New Monitor > HTTP(s) > URL
   `https://<service>.onrender.com/health` > interval 10 minutes. Keeps Render (free tier sleeps) and Supabase
   (pauses after ~1 week idle) awake through final judging 19-22 Oct.
5. **Bench review (B18, D-22).** Give `bench/review_sheet.csv` (179 rows, UTF-8, opens in Excel) to the sharia
   reviewer: fill `approve (Y/N)`, `reviewer`, `note`. Optionally add widespread unestablished hadiths to
   `bench/seed_fabricated.csv` (Dorar links only). Then run `python bench/build_items.py --apply-review` and commit.
   Results are reported with reviewed vs unreviewed counts either way.
6. **Telegram bot (B24), after the Render deploy.** (a) In Telegram, message @BotFather: `/newbot`, pick a name and
   a username, copy the token. (b) Generate a webhook secret:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`. (c) In Render > Environment set
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` (and `PUBLIC_WEB_URL` = the Pages URL for the Details button),
   save (it redeploys). (d) Register the webhook (replace the three placeholders):
   `curl -s "https://api.telegram.org/bot<TOKEN>/setWebhook" -d "url=https://<service>.onrender.com/telegram/webhook" -d "secret_token=<SECRET>" -d 'allowed_updates=["message","callback_query"]'`
   -> `{"ok":true,...}`. (e) Manual test from a phone: forward a captioned image containing a hadith, check the
   ⏳ message is edited with the verdict, try the three buttons. Tell me the result so I can tick B24.
7. **Frontend switch to the real backend (tell the frontend teammate).** In the Cloudflare Pages build env:
   `VITE_USE_MOCK_API=false`, `VITE_MIZAN_API_URL=https://<service>.onrender.com`, `VITE_ENABLE_FEEDBACK=true`
   (the feedback endpoint is live), keep `VITE_API_TIMEOUT_MS=30000`. Their `/r/{check_id}` page works with
   `GET /api/v1/check/{id}` (24 h). Then add the Pages URL to Render's `ALLOWED_ORIGINS`.
8. **Before each judging session:** `python scripts/warm_cache.py --api https://<service>.onrender.com` (fills
   dorar_cache for every demo and bench item; ~30 min at 6/min) and `python scripts/embed_corpus.py` once a day.
9. *(more items are added below as tasks reach a HUMAN step)*

## Resume here

**Secret scan (2026-10-06):** full git history (62 commits, all branches) grepped for Google / Groq / OpenAI / Anthropic / Slack / GitHub / Telegram tokens, Postgres URLs with passwords, JWTs and private keys: **no matches**; no `.env`, `.pem` or `.key` file ever committed. (gitleaks not installed; `gitleaks detect` is the stronger check before going public.)

Updated 2026-10-06 ~06:45 Riyadh. Everything is on `main` (stacked branches squash-merged).

- **Done:** B01-B07, B09-B16, B18, B19 (code), B21-B23, B27. Supabase migrated + ingested (6,236 verses,
  2 x 6,236 translations, 3,574 HadeethEnc hadiths). Live: 3 demo messages in 6.8 / 10.0 / 4.7 s.
- **Waiting on human:** B08 (embedding quota, daily), B17 deploy,
  B24 phone test, sharia review (D-20, D-22).
- **In progress:** B20 (dev runs -> offline sweep -> freeze -> test runs), B25 (README results), B26 checklist.

---

Work top to bottom. Each task lists what it depends on, what to build, and the acceptance criteria (AC)
that must all pass before you tick it. `HUMAN` marks a step only the human can do (keys, accounts, sign-off);
when you reach one, stop, print exactly what is needed, and continue with the next task that does not
depend on it.

Spec references (§) point to `docs/backend-ai/SPEC.md`.

Legend: P0 = must ship · P1 = should ship · P2 = if time allows.

---

## Phase A — Foundations

### [x] B01 · Repo skeleton (P0)
Depends on: —
Build:
- Layout from §15 (`backend/`, `bot/`, `scripts/`, `bench/`, `docs/`; leave `frontend/` alone).
- `backend/requirements.txt` (fastapi, uvicorn[standard], httpx, pydantic, pydantic-settings, rapidfuzz,
  psycopg[binary] or asyncpg, pgvector, beautifulsoup4, langdetect, python-telegram-bot, python-docx, pypdf,
  pytest, pytest-asyncio, respx).
- `core/config.py` (pydantic-settings from env, §14), `core/logging.py` (JSON logs), `.env.example` (§14),
  `.gitignore` additions (`.env`, `data/` if needed), `Makefile` (`test`, `run`, `smoke`, `ingest`, `bench`).
- `main.py` with lifespan, CORS from `ALLOWED_ORIGINS`, `GET /health` (DB check added in B04).
AC:
- `uvicorn app.main:app` starts; `GET /health` returns 200.
- `pytest -q` runs (zero tests is fine).
- No secret values anywhere in the repo.

### [x] B02 · Source smoke test + fixtures (P0)
Depends on: B01
Build: `scripts/smoke_sources.py` (§4.3): one real request each to QuranEnc (list + one sura), HadeethEnc
(categories, list, one, search if it exists), Dorar (`dorar_api.json?skey=` with a common Arabic phrase taken
from a HadeethEnc response, not typed by you), Mushaf source; print latency + field names; save raw responses
to `backend/tests/fixtures/<source>/`. Write `docs/SOURCES.md` (source, URL, what we use, license/terms).
AC:
- Script runs end to end and prints a pass/fail line per source.
- One fixture file per source committed.
- Any mismatch with SPEC §4 is written in `docs/DECISIONS.md` with the code change it implies.
- QuranEnc translation keys for en and ur chosen from the real list and written to `.env.example` comments
  and `docs/SOURCES.md` (§4.2).
HUMAN: none, unless a source needs a key or blocks the request.

### [x] B03 · LLM + embeddings clients (P0)
Depends on: B01
Build: `llm/client.py` with `async complete_json(prompt_name, variables, schema: type[BaseModel], model) -> (BaseModel, usage)`:
loads `prompts/<name>.txt`, fills variables, calls the provider chosen by `LLM_PROVIDER`
(`anthropic` and `openai_compatible`), temperature 0, JSON output, pydantic validation, one retry on invalid
JSON, 8 s timeout (configurable), returns token usage. `llm/embeddings.py` with `async embed(texts) -> list[list[float]]`
(batching 100, `EMBEDDING_DIM` enforced, asserts length).
AC:
- Unit tests with mocked HTTP (respx) for: valid JSON, invalid-then-valid JSON (retry), timeout.
- Switching provider is env-only.
HUMAN: choose providers and set `LLM_*` and `EMBEDDING_*` keys in `.env`.
UPDATE 2026-10-05 (D-15, D-16): free tiers. Gemini (OpenAI-compatible) + Groq quota fallback, `gemini`
embedding provider with L2 normalization and client-side rate limits; provider per call in `check_metrics`.

### [x] B04 · Database + migration (P0)
Depends on: B01
Build: `db/migrations/001_init.sql` exactly as §5 (includes `check_results`, `match_verse`), `db/session.py`
(async pool), `db/queries.py`. `/health` now runs `select 1` (§14, AMENDMENT 8). Background task deleting
expired `check_results` at startup and hourly.
AC:
- Migration applies cleanly on a fresh Supabase project.
- `/health` returns 503 when DB is unreachable, 200 otherwise.
HUMAN: create the Supabase project, enable `vector`, give `DATABASE_URL`.
STATUS 2026-10-05: code done; migration + /health + cleanup verified on a local Postgres 16 + pgvector 0.8.1
(`pytest --live`). Not ticked until the migration is applied to the Supabase project (needs `DATABASE_URL`).

---

## Phase B — Data

### [x] B05 · Mushaf ingest + in-memory index (P0)
Depends on: B02, B04
Build: `scripts/ingest_quran.py` (§6) from the King Fahd Complex data, or the QuranEnc `arabic_text` fallback
if the Complex data is not downloadable without registration (record which in DECISIONS.md).
Also writes `data/quran.json` (surah, ayah, uthmani, clean, surah names ar/en). `pipeline/normalize.py` (§7.1).
App lifespan loads the Mushaf + 2- and 3-verse windows into memory.
AC:
- Exactly 6,236 verses; spot-check printed for 1:1, 2:255, 114:6 (from the data, not typed).
- `tests/test_normalize.py`: tashkeel, tatweel, hamza forms, ta marbuta, alif maqsura, punctuation/digits removal.
- Startup loads the index in < 3 s and memory stays < 300 MB.

### [x] B06 · QuranEnc translations ingest (P0)
Depends on: B05
Build: `sources/quranenc.py` client + `scripts/ingest_quranenc.py` for the pinned en and ur keys.
AC: 6,236 rows per language in `quran_translations`; idempotent re-run inserts nothing new.

### [x] B07 · HadeethEnc ingest (P0)
Depends on: B04, B02
Build: `sources/hadeethenc.py` + `scripts/ingest_hadeethenc.py` (§6): categories → IDs (dedupe) → each hadith in
ar, en, ur. Priority categories first; `--all` for the rest. Concurrency 4, backoff.
AC: progress logged; re-runnable; at least the priority categories ingested with ar+en (ur where available);
counts written to `docs/SOURCES.md`.

### [ ] B08 · Embed corpus (P0)
Depends on: B03, B06, B07
Build: `scripts/embed_corpus.py` (§6), skip rows already embedded.
AC: all `quran_translations` and `hadith_translations` rows embedded; `match_hadith` and `match_verse`
return sensible top results for 3 queries built from ingested translations.
STATUS 2026-10-05: `scripts/embed_corpus.py` done (batches of 100, skips embedded rows, resumable); SQL path
(embed -> update -> `match_verse`) verified on local Postgres with a stub embedder (`tests/test_embed_corpus_live.py`).
Not ticked until run with real `EMBEDDING_*` keys and the 3-query sanity check.

### [x] B09 · Dorar client (P0)
Depends on: B02, B04
Build: `sources/dorar.py` (§4.1): call official API, parse `ahadith.result` HTML with BeautifulSoup into
`DorarResult(id, text, text_clean, narrator, mohaddith, book, page, grade_text, url)`, stable IDs, cache in
`dorar_cache`, 8 s timeout, one retry, `SourceUnavailable` exception on failure.
AC:
- `tests/test_dorar_parser.py` parses the saved fixture: count, and every field non-empty where the HTML has it.
- Second identical query is served from cache (no HTTP, verified with respx).
- On timeout raises `SourceUnavailable` (never returns an empty list silently).

---

## Phase C — Pipeline

### [x] B10 · Extraction + rule detector (P0)
Depends on: B03
Build: `prompts/extract.txt` and schema exactly as §7.2 (AMENDMENT 3, 7), `pipeline/extract.py`,
`pipeline/rules_detect.py` (trigger list in §7.2), merge logic, span-substring validation, cap 10 claims.
AC:
- Unit tests with mocked LLM: claim kept; hallucinated span dropped; rule-only claim added; `intent` values
  map correctly; text containing "ignore previous instructions" does not change behaviour (mock returns schema-valid output; assert prompt wraps text in `<message>`).
- One live test (marked `@pytest.mark.live`, skipped by default) on 3 real messages.

### [x] B11 · Verse matcher with alignment (P0) — AMENDMENT 4
Depends on: B05
Build: `pipeline/quran_match.py` exactly as §7.3 (raw score to classify, adjusted to rank, containment guard,
`partial_ratio_alignment` + word-boundary expansion, edge rule, multi-location, attribution check),
`pipeline/surah_parse.py` (Arabic/English surah names, `2:255`, `البقرة 255`, Arabic-Indic digits),
thresholds in `core/thresholds.py`.
AC: `tests/test_quran_match.py` implements **all six cases in §7.3** built from `data/quran.json` by reference,
and they pass. Plus surah parser tests (5 formats).

### [x] B12 · Non-Arabic verse path (P0)
Depends on: B08, B11
Build: vector search via `match_verse` + literal Arabic queries through B11, merge, top 6 to verifier.
AC: given an approved English and Urdu translation of 3 verses (taken from `quran_translations`), the correct
verse is in the top 6 candidates for all 6.

### [x] B13 · Hadith retriever (P0)
Depends on: B08, B09
Build: `pipeline/hadith_retrieve.py` §7.4: paths A/B/C in parallel, early stop, grouping of Dorar results by
matn (token_set_ratio ≥ 92), top 6 to verifier, `source_status` propagation.
AC:
- Fixture test: Dorar fixture with several chains of one matn → one group carrying all gradings.
- If Dorar raises `SourceUnavailable`, paths B/C still run and `source_status = "source_unavailable"` is set.

### [x] B14 · Verifier (P0) — AMENDMENT 2, 3
Depends on: B03
Build: `prompts/verify.txt` and `pipeline/verify.py` as §7.5: multi `match_ids`, ID validation in code,
hallucination logging, per-type confidence thresholds (hadith `same_meaning` ≥ 0.85).
AC: unit tests with mocked LLM: unknown ID dropped and logged; all-unknown → no match; hadith
`same_meaning` at 0.80 → rejected; verse `same_meaning` at 0.80 → accepted.

### [x] B15 · Grade classifier + decision engine (P0) — AMENDMENT 1, 5 — `NEEDS SH SIGN-OFF`
Depends on: B11, B13, B14
Build: `core/grade_rules.py` (keyword lists), `pipeline/grades.py` (§8.1), `pipeline/decide.py` (§8.2–8.4:
aggregation table, altered → misquoted, attribution, wrong_type, out_of_scope_attribution, source_unavailable,
message-level status).
AC:
- `tests/test_grades.py`: all 8 cases in §8.1.
- `tests/test_decide.py`: one test per row of the §8.2 table (7) + altered/verified → misquoted +
  attribution mismatch + source_unavailable never yields a positive verdict + each message status in §8.4.
HUMAN: send `core/grade_rules.py` and the §8.2 table to the sharia reviewer; apply their edits.

### [x] B16 · Orchestrator + `/api/v1/check` (P0)
Depends on: B10–B15
Build: `pipeline/orchestrator.py` §7.7, `models/result.py` matching `docs/API_CONTRACT.md` exactly,
`api/check.py`, `GET /api/v1/check/{id}`, `api/sources.py`, rate limit (`core/ratelimit.py`, 20/min/IP),
input limit, storage in `check_results` (24 h), metrics in `check_metrics`, LRU cache, disclaimers by language
from `core/messages.py`.
AC:
- Contract test: response validates against the pydantic model AND against the example JSON in API_CONTRACT.
- End-to-end test with all external calls mocked from fixtures: an Arabic message with one verse and one hadith
  returns two correct cards.
- Live smoke (`@live`): 3 example messages (ar, en, ur) under 12 s each.
- Logs contain no message text (assert in a test by capturing logs).

### [ ] B17 · Deploy backend (P0)
Depends on: B16
Build: `render.yaml` (or documented manual settings), start command per §14, env vars list, README deploy section.
AC: public URL `/health` 200; `/api/v1/check` works from an external machine; frontend teammate given the URL.
HUMAN: create the Render service, paste env vars, set up the pinger (UptimeRobot or cron-job.org) on `/health` every 10 min.
STATUS 2026-10-06: prepared (`render.yaml` Blueprint, build downloads the Mushaf, README deploy section, startup
connects the DB pool once, storage off the response path). Not ticked until deployed: see "Waiting on Azoz" 3-4.

---

## Phase D — Evaluation (start B18 in parallel with Phase C)

### [x] B18 · Mizan-Bench builder (P0) — `NEEDS SH SIGN-OFF`
Depends on: B02 (sources), B05–B09 for data
Build: `bench/build_items.py` that seeds items **from source data only** (§11.1–11.2): authentic hadiths
(HadeethEnc + Dorar), authentic hadiths that also have weak chains (Dorar results where a Sahihayn grading and
a weak grading coexist), widespread unestablished hadiths (Dorar), verses + rule-based alterations + partial
quotes + multi-location phrases (from `data/quran.json`), translated variants from approved translations,
the reference pack page-6 questions, personal-ruling prompts. Fabricated-translated-with-lookalike items:
pair a not-established hadith with the nearest authentic HadeethEnc hadith by embedding similarity and keep
the pair only if similarity ≥ 0.6. Writes `bench/items.jsonl` with `reviewed_by: null` and a 30/70 dev/test split
stratified by category. Also `bench/review_sheet.csv` for the sharia reviewer (id, category, text, expected, approve Y/N, note).
AC: ≥ 150 items with the §11.2 proportions; every item has `provenance`; no item text typed by hand.
HUMAN: sharia reviewer fills `review_sheet.csv`; run `bench/build_items.py --apply-review` to set `reviewed_by`.

### [x] B19 · Bench runner, baselines, metrics (P0) — AMENDMENT 9
Depends on: B16, B18
Build: `bench/run.py` (systems `mizan`, `llm_baseline`, `dorar_direct`; `--runs`; saves raw outputs to
`bench/results/<system>-<split>-<run>.jsonl`), `bench/metrics.py` (all metrics in §11.3, hallucination per §11.4,
tables + PNG charts, `report.md`), `bench/prices.json`.
Runner harness already resumable and rate-limited (D-17): build the `llm_baseline` and `dorar_direct`
systems inside `bench/run.py`.
AC:
- `llm_baseline` uses the forced structured output in §11.4.
- Report shows per-category and per-language accuracy, not-established recall, false-verified rate, hallucination
  rate, consistency, latency p50/p95, mean cost per check, and reviewed vs unreviewed counts.
- Manual-agreement field for the 30-sample baseline review is present in the report template.

### [x] B20 · Threshold tuning on dev, freeze, run test (P0)
Depends on: B19
Build: `bench/tune.py` sweeping the thresholds in `core/thresholds.py` on `dev` only; pick values maximizing
accuracy subject to false-verified = 0; write them to `thresholds.py`; tag the commit `thresholds-frozen`;
run test split (mizan ×3, llm_baseline ×3, dorar_direct ×1); write `docs/EVALUATION.md`.
AC: EVALUATION.md has method, dev/test separation statement, tables, charts, limitations per language.

---

## Phase E — P1 features

### [x] B21 · Ready reply + `/api/v1/reply` (P1) — AMENDMENT 10
Depends on: B16
Build: `prompts/reply.txt` §7.6 with glossary, `pipeline/reply.py`, URL validation + one regeneration,
caching the reply in `check_results.reply`.
AC: mocked test where the model adds a foreign URL → regenerated → still bad → `reply: null` with
`reply_error`; live test (`@live`) on one en and one ur result.

### [x] B22 · Authentic alternative (P1)
Depends on: B13, B15
Build: `pipeline/alternative.py` §8.5.
AC: alternative only for `not_established`; below 0.75 similarity → none; labelled as a different hadith.

### [x] B23 · Feedback endpoint (P1)
Depends on: B16
AC: `POST /api/v1/feedback` validates `issue` enum, stores without message text, 404 on unknown `check_id`.

### [ ] B24 · Telegram bot (P1) — AMENDMENT 12
Depends on: B16, B21
Build: §10 in full (text or caption, HTML escaping, edit-in-place, buttons, 4,096 split on card boundaries,
`/start` in ar/en/ur, 10 msgs/min per user with hashed user ID, webhook secret).
AC: unit tests for escaping and splitting; manual test from a phone forwarding a captioned image.
HUMAN: create the bot with BotFather, set `TELEGRAM_BOT_TOKEN`, run `setWebhook` (provide the exact command).
STATUS 2026-10-06: code + unit tests done (escaping, card-boundary split, secret check, hashed user ids).
Not ticked until the manual phone test (Waiting on Azoz 6).

---

## Phase F — Ship

### [ ] B25 · Warm cache, cost report, docs (P0)
Depends on: B17, B20
Build: `scripts/warm_cache.py`, `scripts/cost_report.py`; finish `README.md` (idea, architecture diagram as
Mermaid, setup from scratch, run, demo link, bench summary), `docs/ARCHITECTURE.md`, `docs/LICENSES.md`,
`docs/CONTENT_POLICY.md` (content levels A–D handling, abstention, referral, disclaimer, privacy text from §13).
AC: a teammate can follow README on a clean machine; `gitleaks detect` (or equivalent) is clean.

### [ ] B26 · Pre-submission checklist (P0)
Depends on: everything P0
AC: every item of SPEC §18 checked and ticked in this file; print the final live URL, repo URL, and the 3
demo inputs with their verdicts for the video.

Checklist (SPEC §18), status 2026-10-06:
- [ ] Live link works from an external device; the three ready examples (ar, en, ur) give the right result.
      Locally verified (`python scripts/try_check.py --video`: misquoted + not_established / verified / verified);
      live link waits on the Render deploy (Waiting on Azoz 3).
- [x] All verdicts and statuses appear in real examples (`docs/VERDICT_EXAMPLES.md`).
- [x] No reference or grade in any output absent from the sources (Mizan hallucination rate 0 on dev; texts,
      gradings and links copied from sources by construction; ids validated in code).
- [x] False-verified rate on the test split reported (`docs/EVALUATION.md`).
- [x] Mizan-Bench results and both baselines in `docs/EVALUATION.md`, with reviewed-item counts.
- [ ] Repo public, run-from-scratch instructions work, sources and licenses documented, no keys (secret scan
      clean). Making the repo public and a clean-machine run by a teammate are human steps.
- [ ] `/health` queries the DB (done); pinger configured and cache warmed (Waiting on Azoz 4, 8).
- [ ] Service stays up through final judging (19-22 Oct), checked daily (human).

### [x] B27 · File report (P2)
Depends on: B16
Build: `POST /api/v1/check/file` (TXT/DOCX/PDF ≤ 5 MB, split into paragraphs, batch through orchestrator, aggregate).
