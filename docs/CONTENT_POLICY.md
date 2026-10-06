# Content policy

How Mizan applies the challenge's binding scientific standard (reference pack pp. 2, 5): content levels, source
traceability, abstention, referral, disclaimer and privacy. Grading rules and the verdict table are pending the
team sharia reviewer's sign-off (DECISIONS D-20).

## Scope

Mizan verifies **quoted texts**: Quran verses and hadiths attributed to the Prophet ﷺ. It does not issue fatwas,
judge people or groups, prefer one scholar's grading over another, or answer general questions. Sayings attributed
to scholars or Companions are out of scope and returned as `not_found` with the note `out_of_scope_attribution`.

## Content levels (reference pack p. 2)

| Level | Examples | Mizan's handling |
|---|---|---|
| A: stable original information | Quran text, authentic hadiths | Direct, sourced verdict: Uthmani text + surah:ayah + approved translation + link; hadith text + scholar + book + grading as given + link. |
| B: explanation and reasoning | Concepts, general questions | Not answered. Status `no_claims` with a pointer to byenah.com / islamhouse.com. |
| C: disputed or sensitive | Scholars' differing gradings | `disputed` only when an accepted grading meets a very weak one for the same matn; every grading shown verbatim, no preference, plus a referral line. Gradings Mizan cannot classify -> `needs_review` with referral. |
| D: fatwa / personal case | Rulings about one's own situation | Status `referral`: Mizan states it is a source-verification tool, not a fatwa body, and refers to a qualified authority. Quotes in the same message are still verified (D-5). |

## Traceability and anti-hallucination (p. 5)

- Every Arabic text, grading, book name and link in a result is copied from the sources (Mushaf, QuranEnc,
  HadeethEnc, Dorar). The model never writes them: it only picks among candidate ids, which are validated in code;
  unknown ids are dropped and logged as hallucinations.
- The ready reply is generated only from the decided facts; any link not present in those facts is rejected
  (one regeneration, then no reply).
- Generated text (the ready reply) is kept separate from the source texts on the card.

## Abstention over guessing

- Low confidence, no matching reference, or a quote too short to judge -> `not_found` ("no matching reference
  found in the available sources"), never a positive verdict.
- A source outage is reported as `source_unavailable` ("the source did not respond"), never as absence.
- A translated hadith is accepted as "same meaning" only at verifier confidence >= 0.85, and a different hadith with
  a similar meaning is never treated as the quote (AMENDMENT 3). An authentic alternative is offered only for a
  `not_established` hadith and is always labelled as a *different hadith on a related meaning*.
- Requests to *find* evidence get status `evidence_request`: Mizan refuses to produce evidence and explains it
  verifies quotes.

## Terminology and translation

The ready reply uses the approved term equivalents from the reference-pack glossary (p. 7) and keeps the Arabic
term with a short gloss when the equivalent is insufficient (AMENDMENT 10). Verse translations are the approved
QuranEnc translations; hadith translations are HadeethEnc's approved translations. No machine translation is
shown as a source.

## Disclaimer and transparency

Every result carries: «أداة آلية للتحقق من المصادر، وليست فتوى.» (English / Urdu equivalents by message language).
The bot's /start message states it is an automated tool and not a fatwa service.

## Privacy

User-facing text (served as `privacy` by `GET /api/v1/sources` for the About page, in Arabic, English and
Urdu; source: `backend/app/core/messages.py`):

> تُحفظ نتيجة التحقق 24 ساعة لعرض التفاصيل والرد الجاهز ثم تُحذف. لا تُحفظ هوية المرسل ولا يُستنتج منها أي
> شيء عن معتقده. يعمل ميزان على الخطة المجانية لمزوّد النموذج اللغوي، وقد يستخدم المزوّد النصوص المُرسلة
> لتحسين خدماته؛ فلا تُرسل بيانات شخصية أو حساسة.

> A check result is stored for 24 hours to show its details and the ready reply, then deleted. The sender's
> identity is not stored and nothing is inferred about their beliefs. Mizan runs on the free tier of its
> language-model provider, which may use submitted text to improve its services, so do not submit personal
> or sensitive information.

What this means in practice:

- **Model provider (free tier, DECISIONS D-15).** Message text is sent to the language-model provider
  (Google Gemini; Groq as fallback when Gemini's quota is exhausted or it is unavailable) for extraction,
  comparison and the ready reply, and quoted spans are sent to the embedding provider (Gemini).
- **Storage.** Check results (which contain the quoted spans) are kept 24 hours in `check_results`, then
  deleted by an hourly job (SPEC §5, §13). Dorar search queries derived from quotes are cached in
  `dorar_cache` for the duration of the challenge.
- **Logs and telemetry.** Logs never contain message text (tested). `check_metrics` stores counts, latency,
  token usage and which provider served each call, never text. Feedback stores ids and the issue type only.
- **Telegram.** User IDs are kept only as a salted hash for rate limiting (SPEC §13).
- **No profiling.** Nothing is inferred about a user's beliefs.
