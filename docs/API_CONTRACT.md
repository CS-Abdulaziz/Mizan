# Mizan API contract (backend ↔ frontend)

Owner: backend. Any change here is announced to the frontend teammate in the same commit.
Base URL: `VITE_API_URL` (Render URL in production, `http://localhost:8000` locally).
All responses are JSON, UTF-8. Text placeholders below (`<...>`) stand for real source data.

## POST /api/v1/check

Request:

```json
{ "text": "<message, max 4000 chars>", "channel": "web", "lang_hint": null }
```

Errors: `413` text too long · `422` invalid body · `429` rate limited (`Retry-After` header) · `503` service unavailable.

Response (`status: "ok"`):

```json
{
  "check_id": "8f2a19c04b7e4d2f9a1c3e5b7d9f0a12",
  "status": "ok",
  "lang": "en",
  "referral": null,
  "message": null,
  "claims": [
    {
      "index": 0,
      "type": "hadith",
      "span": "<exact quoted text from the message>",
      "span_start": 34,
      "span_end": 92,
      "lang": "en",
      "verdict": "not_established",
      "relation": "same_meaning",
      "confidence": 0.86,
      "evidence": {
        "source": "dorar",
        "text_arabic": "<Arabic text as given by the source>",
        "translation": null,
        "locations": [],
        "gradings": [
          { "mohaddith": "<scholar>", "book": "<book>", "page": "<page or number>",
            "grade_text": "<grading as given>", "grade_class": "very_weak" }
        ],
        "url": "https://dorar.net/..."
      },
      "diff": null,
      "alternative": {
        "source": "hadeethenc",
        "id": 1234,
        "text_arabic": "<authentic hadith text>",
        "translation": "<approved translation in message language>",
        "attribution": "<as given by source>",
        "url": "https://hadeethenc.com/...",
        "label": "different_hadith_related_meaning"
      },
      "notes": [],
      "source_status": "ok"
    },
    {
      "index": 1,
      "type": "quran",
      "span": "<quoted verse>",
      "span_start": 120,
      "span_end": 168,
      "lang": "ar",
      "verdict": "misquoted",
      "relation": "altered",
      "confidence": 1.0,
      "evidence": {
        "source": "quran",
        "text_arabic": "<Uthmani text of the aligned span>",
        "translation": "<approved translation, if message not Arabic>",
        "locations": [
          { "surah": 2, "ayah": 255, "surah_name_ar": "<name>", "surah_name_en": "<name>",
            "url": "https://quranenc.com/..." }
        ],
        "gradings": [],
        "url": "https://quranenc.com/..."
      },
      "diff": {
        "kind": "wording",
        "ops": [ { "op": "replace", "quoted": "<word in quote>", "source": "<word in Mushaf>" } ],
        "details": "<short description>"
      },
      "alternative": null,
      "notes": [],
      "source_status": "ok"
    }
  ],
  "disclaimer": "أداة آلية للتحقق من المصادر، وليست فتوى.",
  "reply_available": true,
  "expires_at": "2026-10-07T21:00:00Z"
}
```

### Field values

| Field | Values |
|---|---|
| `status` | `ok` · `no_claims` · `evidence_request` · `referral` |
| `type` | `quran` · `hadith` · `attributed_saying` |
| `verdict` | `verified` · `misquoted` · `not_established` · `disputed` · `not_found` · `needs_review` |
| `relation` | `exact` · `same_meaning` · `altered` · `null` |
| `evidence.source` | `quran` · `dorar` · `hadeethenc` · `null` (when not found) |
| `grade_class` | `accepted` · `accepted_isnad` · `weak` · `very_weak` · `unclassified` |
| `diff.kind` | `wording` · `attribution` · `wrong_type` |
| `notes[]` | `too_short` · `out_of_scope_attribution` · `multiple_locations` · `takhrij_has_weak_chains` |
| `source_status` | `ok` · `source_unavailable` |
| `referral` | `null` or `{ "reason": "personal_ruling", "text": "<localized referral text>" }` |

### Suggested UI per verdict (icon + text, never colour alone)

| verdict | Icon | Arabic label | Must show |
|---|---|---|---|
| `verified` | ✓ | موثّق | Arabic text, location(s) or source + grading, translation, link. If `relation = same_meaning` on a hadith: «ثابت بالمعنى، واللفظ المعتمد هو...» |
| `misquoted` | ⚠ | منقول بخطأ | `diff` (quoted vs correct), correct text and location, warning not to rely on the altered text |
| `not_established` | ✗ | لا يثبت | all gradings verbatim with scholar + book, link, `alternative` if present (labelled as a different hadith) |
| `disputed` | ⚖ | اختلف المحدثون | all gradings verbatim, no preference, referral line |
| `not_found` | ? | لم يُعثر عليه | «لم نجد مرجعاً مطابقاً في المصادر المتاحة» + referral. If `source_status = source_unavailable`: «المصدر لم يستجب، أعد المحاولة» instead |
| `needs_review` | ? | يحتاج مراجعة مختص | gradings verbatim + referral |

Highlight each `span` in the original text using `span_start` / `span_end` (character offsets into the
submitted text). Foreign-language text inside `dir="auto"` elements.

### Other statuses

```json
{ "check_id": "...", "status": "no_claims", "lang": "ar", "claims": [], "referral": null,
  "message": "<localized: Mizan verifies quoted verses and hadiths and found none; general questions → byenah.com / islamhouse.com>",
  "disclaimer": "...", "reply_available": false, "expires_at": "..." }
```

`evidence_request` has the same shape with its own `message`. `referral` status: `claims` may be non-empty
(claims are still verified) and `referral` is set.

## GET /api/v1/check/{check_id}

Returns the same body as above while it is stored (24 h). `404` after expiry. Used by the result page `/r/{check_id}`.

## POST /api/v1/reply  (P1)

Request `{ "check_id": "...", "lang": "en" }` (lang optional, defaults to the message language).
Response:

```json
{ "check_id": "...", "lang": "en", "reply": "<ready-to-send text>", "reply_error": null }
```

`reply` may be `null` with `reply_error: "validation_failed"`; hide the reply box then.

## POST /api/v1/feedback  (P1)

Request `{ "check_id": "...", "claim_index": 0, "issue": "wrong_verdict", "note": "optional" }`
(`issue`: `wrong_verdict` · `wrong_source` · `other`). Response `{ "ok": true }`.

## GET /api/v1/sources

```json
{ "sources": [ { "name": "<source name>", "url": "https://...", "used_for": "<...>", "license": "<...>" } ],
  "privacy": "<localized privacy text>", "limits": ["<localized limitation>", "..."] }
```

## GET /health

`200 {"ok": true, "db": true}` or `503`.

## POST /api/v1/check/file  (P2, added 2026-10-06; additive, existing shapes unchanged)

`multipart/form-data` with one field `file`: `.txt`, `.docx` or `.pdf`, at most 5 MB. Paragraphs are packed into
chunks of at most 4,000 characters; up to 10 chunks are checked (`truncated: true` if the file had more).

```json
{ "filename": "message.docx", "chunks": 3, "checked_chunks": 3, "truncated": false,
  "summary": { "verified": 2, "not_established": 1 },
  "checks": [ { "chunk": 0, "check_id": "...", "status": "ok" } ],
  "claims": [ { "chunk": 0, "check_id": "...", "index": 0, "type": "hadith", "verdict": "not_established", "...": "same fields as a claim above" } ] }
```

Errors: `413` file too large · `415` unsupported type · `422` empty file · `429` rate limited · `503` unavailable.
Each chunk's full result is available at `GET /api/v1/check/{check_id}` for 24 h.
