# Review amendments to technical spec v1.0

All 13 are already merged into `SPEC.md` (search for `[AMENDMENT n]`). This file explains why, so the team
and the sharia reviewer can check the reasoning. The full review with evidence tables is the shared team doc
"ميزان — مراجعة الوثيقة التقنية".

| # | Change | v1.0 section | Why | Where now |
|---|---|---|---|---|
| 1 | "Scholars differ" only when there is a real conflict on the matn; Sahihayn / HadeethEnc / accepted-without-very-weak → verified | 8.2 | Dorar returns one matn through several chains; a weak chain is not a dispute about the hadith. v1.0 would label many Sahihayn hadiths "disputed". | SPEC §8.2 |
| 2 | Verifier returns `match_ids` (list) | 7.5 | Decision needs all gradings of the same matn; one ID made the verdict depend on which result the model picked and broke consistency across runs | SPEC §7.5 |
| 3 | Literal back-translation; hadith `same_meaning` ≥ 0.85; "similar meaning ≠ same text" | 7.2, 7.5 | A translated fabricated hadith can be "corrected" by the model into an authentic lookalike and stamped verified — the most dangerous possible error | SPEC §7.2, §7.5, bench category |
| 4 | Verse matching: classify on raw alignment score, rank on adjusted; containment guard; diff only inside the aligned span; multiple locations | 7.3 | Measured: altered Ayat al-Kursi gave 3:2 a raw 100; a correct partial quote produced 2 insert ops vs the full verse and an adjusted score of 86.9 — v1.0 would mislabel it | SPEC §7.3 |
| 5 | Grade classification checks source book and bracketed matn verdict first; chain-level grades are a separate class | 8.1 | Measured: "[صحيح] وهذا إسناد ضعيف" → weak and "أخرجه البخاري" → unclassified under v1.0 | SPEC §8.1 |
| 6 | Results stored 24 h in `check_results`; privacy text updated | 9, 10.2, 13 | `/reply` and bot "details" need the stored result, which v1.0's "store nothing" contradicted | SPEC §5, §9, §13 |
| 7 | Message-level `status`: no_claims, evidence_request, referral | 8.2, 9 | Judges will likely try the reference pack's page-6 questions, which contain no quotes | SPEC §8.4 |
| 8 | `/health` queries the DB | 12, 14 | Supabase free projects pause after about a week idle; final judging is 19–22 Oct | SPEC §14 |
| 9 | Baseline forced to structured output; automatic hallucination check + 30-item manual agreement | 11.3, 11.4 | v1.0 metric was not computable from free-text baseline output | SPEC §11.4 |
| 10 | Approved glossary in the reply prompt | 8.4 | Reference pack requires approved term equivalents over machine translation | SPEC §7.6 |
| 11 | Dorar returns HTML in JSON (15 results); cache everything before judging; outage ≠ not found | 4, 17 | Parser needs a real fixture; cloud IPs may be throttled | SPEC §4.1 |
| 12 | Telegram: text or caption, HTML escaping, split on card boundaries | 10.2 | Forwarded media carry text in `caption`; unescaped `<` makes Telegram reject the message | SPEC §10 |
| 13 | Pin QuranEnc translation keys | 4, 6 | Indexing and display must use the same approved translation | SPEC §4.2 |

Points 8, 11, 12 and 13 are based on documented service behaviour and must be confirmed by `smoke_sources.py`
(task B02). Points 4 and 5 were confirmed by running v1.0's own code.

Refinement beyond the review doc: §8.2 adds `needs_review` for gradings that are all unclassified (v1.0
had "display as-is with referral" but no verdict value for it), and rule 3 keeps `disputed` when an accepted
grading meets a very-weak one (e.g. صحيح vs موضوع) so genuine conflicts are not hidden. Both need sharia sign-off.
