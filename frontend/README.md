# مِيزان — Frontend

React + Vite interface for the existing Mizan REST API. Arabic RTL with automatic direction for quotations, English and Urdu. No AI, retrieval, authenticity rules, direct source calls, or database connection runs in the browser.

## Run

Use Node.js 22 (22.12+), or Node.js 20.19+.

```sh
cd frontend
npm ci
cp .env.example .env
npm run dev
```

PowerShell: use `Copy-Item .env.example .env`. The default is a clearly labelled demo. Four examples cover the main journey. The expandable demo controls exercise every verdict, special status, source outage, and error; synthetic scenarios explicitly identify their non-religious placeholder text. Arbitrary demo input never receives an invented verification result.

```sh
npm run build
npm run preview -- --port 4173
```

The Vite config uses its native loader, which also avoids config-bundling filesystem restrictions in managed Windows environments. Production output is `frontend/dist`.

## Connect the backend

Set these build-time public variables and rebuild:

```env
VITE_USE_MOCK_API=false
VITE_MIZAN_API_URL=https://your-backend.example
VITE_ENABLE_REPLY=true
VITE_ENABLE_FEEDBACK=false
VITE_API_TIMEOUT_MS=30000
```

`VITE_API_URL` is an alias for the base URL used by `docs/API_CONTRACT.md`; `VITE_MIZAN_API_URL` takes precedence. A missing base URL produces a human-readable configuration error, without falling back to fabricated results. Do not put private API keys in Vite variables. Authentication, if required, must be agreed with the backend team before adding it.

The request follows the checked-in contract: `{text, channel: 'web', lang_hint: null}`. `src/api/mizanApi.js` owns endpoints, timeout, cancellation, transport, feature flags and human errors. `src/api/adapter.js` validates rendering fields, rejects malformed payloads and executable links, and preserves unknown verdicts as review states. Unicode offsets use code points to match Python backend offsets. The UI never computes an authenticity verdict or a confidence score.

Supported: all six verdicts; `ok`, `no_claims`, `evidence_request`, and `referral` (including referrals with claims). Source outages override the verdict label. Grades are displayed verbatim without preference; alternatives are labelled as a different hadith. The UI omits empty fields and confidence percentages.

`GET /api/v1/check/{check_id}` backs `/result/:checkId` and the backend-contract alias `/r/:checkId`. Expired / missing results show a retry and a return to verification. Demo result IDs resolve fixed fixtures and work after refresh; they do not store the user's input.

Reply generation is requested after a result exists. A null reply or `reply_error` keeps the reply box hidden. Optional reply failures do not remove the check result. Feedback is unavailable until enabled; when enabled it uses the exact `wrong_verdict`, `wrong_source`, `other` contract. `getSources()` is prepared for backend-managed source information; the informational homepage currently lists source provider links.

Backend handoff checklist:

- Provide the HTTPS base URL and allow the frontend origin in CORS (GET, POST and Content-Type).
- Confirm the checked-in contract, result retention and Unicode span offsets.
- Confirm reply availability and enable feedback only when its endpoint is ready.
- Test an actual check, an expired result, a source outage, and an optional-endpoint failure on the deployed service.

## Verify

```sh
npm test
npm run build
# Keep npm run preview -- --port 4173 running in another terminal:
npx playwright install chromium
npm run test:ui
```

The UI suite covers the main demo (grading, alternative, reply and clipboard), all verdicts/statuses/errors, multiple claims, native dialog focus, result routes and refresh, character limit, six requested screen sizes (1366/1440/1920 and 390/393/430), overflow, visible primary action, and PWA offline fallback. It collects screenshots in ignored `test-results/`. To use an installed Chrome instead, set `MIZAN_BROWSER_CHANNEL=chrome`; `MIZAN_TEST_URL` and `MIZAN_QA_DIR` can override the preview URL and screenshot directory.

`tests/transport.mjs` separately checks the real API transport against controlled HTTP responses. Start the real-mode preview described in that file; this checks contract handling, not the unavailable live backend.

## Deploy and PWA

Configure static hosting with root directory `frontend`, build command `npm ci && npm run build`, output directory `dist`, and a history fallback to `index.html` for `/result/*` and `/r/*`. Use HTTPS. Hosting and backend service deployment are intentionally left for the team's chosen accounts.

Manifest, standalone mode, 192/512 icons, local font, and a production-only service worker are included. No API responses, input or verification results are cached. Offline navigation displays an explanatory fallback; verification needs connectivity. The app does not write input or results to local/session storage. Backend retention remains the server's responsibility.

Religious demo excerpts and translations are saved source fixtures: HadeethEnc 6267, QuranEnc 94:5, Dorar Yx6dE0Zf. `scripts/fetch-fixtures.mjs` is an authoring tool for refreshing approved excerpts; the website never runs it. The altered-verse fixture is built by replacing a source word with a plain placeholder and explicitly labels this as a test. Synthetic disputed/review states are UI fixtures, not claimed scholarly assessments.

The Arabic font is self-hosted Noto Sans Arabic under the included SIL Open Font License. Icons are original SVG/PNG assets. Telegram, WhatsApp, n8n and backend directories are outside this change.
