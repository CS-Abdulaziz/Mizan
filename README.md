# Mizan | مِيزان

Multilingual Islamic quotation verifier. The frontend treats the verification backend as a REST service.

## Frontend demo

```sh
cd frontend
npm ci
npm run build
npm run preview
```

See [frontend/README.md](frontend/README.md) for development, demo examples, API configuration, validation, PWA and deployment instructions. The demo uses clearly labelled fixed source-backed fixtures; real verification requires the backend base URL.

The backend-to-frontend interface is documented in [docs/API_CONTRACT.md](docs/API_CONTRACT.md).

## Backend (FastAPI)

Python 3.11. Full setup from scratch:

```sh
cd backend && pip install -r requirements.txt && cd ..
cp .env.example .env                      # fill DATABASE_URL, LLM_*, EMBEDDING_*, GROQ_API_KEY
python scripts/migrate.py                 # schema on Supabase (pgvector)
python scripts/ingest_quran.py            # Mushaf (King Fahd Complex) -> data/quran.json + quran_verses
python scripts/ingest_quranenc.py         # approved en/ur translations
python scripts/ingest_hadeethenc.py --all # HadeethEnc ar/en/ur
python scripts/embed_corpus.py            # optional, daily (free-tier quota, see docs/DECISIONS.md D-19)
cd backend && uvicorn app.main:app --reload --port 8000
```

Tests: `cd backend && pytest -q` (unit) and `pytest -q --live` (real sources, model and DB).
Try the full pipeline on demo messages: `python scripts/try_check.py`.

### Deploy (Render)

`render.yaml` is a Render Blueprint: New > Blueprint > this repo, region Singapore, then paste the secret env
values when asked (`DATABASE_URL`, `LLM_API_KEY`, `EMBEDDING_API_KEY`, `GROQ_API_KEY`, `ALLOWED_ORIGINS`, ...).
The build step downloads the Mushaf from the King Fahd Complex (`ingest_quran.py --no-db`), so the Quran text is
never committed. Health check: `GET /health` (queries the DB, so a pinger keeps both Render and Supabase awake).
Startup loads the Mushaf, the approved translations and the HadeethEnc index (about 1 minute on first boot).
