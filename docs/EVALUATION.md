# Mizan-Bench evaluation

## Method

**Items.** 179 items built by `bench/build_items.py` from source data only (no text typed by hand): verses,
partial quotes, multi-location phrases and rule-based alterations from the King Fahd Complex Mushaf; approved
QuranEnc translations (en, ur); authentic hadiths and approved translations from HadeethEnc; authentic hadiths that
also have weak chains on Dorar; fabricated / baseless hadiths from Dorar's gradings; the reference pack's page-6
test questions; personal-ruling prompts. Every item has a provenance line. Composition follows SPEC §11.2 scaled
to ~0.5 (DECISIONS D-22). All items are `reviewed_by: null` until the team's sharia reviewer approves them in
`bench/review_sheet.csv`; the report always states reviewed vs unreviewed counts.

**Splits.** 30 % dev (54 items) / 70 % test (125 items), stratified by category. **Thresholds were tuned on the
dev split only, then frozen (git tag `thresholds-frozen`) before the test split was run once per system.** The
dev split also drove the fixes logged as D-23 and D-24; the test split was never inspected before freezing.

**Systems** (SPEC §11.4):
- `mizan`: the full pipeline (3 runs, for consistency).
- `llm_baseline`: the same LLM with no retrieval, forced to the same structured output per claim
  (`verdict`, `source_book`, `grade_text`, `arabic_text`) (3 runs).
- `dorar_direct`: Dorar search with the message as-is, no extraction or back-translation (1 run).

**Metrics** (`bench/metrics.py`): verdict accuracy per category and language; not-established recall;
false-verified rate (target 0); hallucination rate (baseline: `arabic_text` below 80 partial-ratio similarity to
every Mushaf / HadeethEnc / Dorar candidate for the item; Mizan: evidence text not traceable to the item's sources);
abstention / referral correctness; consistency across runs; latency p50 / p95; mean cost per check
(`bench/prices.json`: 0 on the free tiers).

**Runtime conditions.** Free tiers only (D-15 - D-21): Gemini Flash models with fallback to Groq
`openai/gpt-oss-120b` under quota pressure, so both `mizan` and `llm_baseline` were partly served by Groq; the
provider mix is recorded per check. Embeddings were limited to ~1,000 texts/day (D-19), so vector paths were
mostly unavailable during the runs; results reflect the lexical + Dorar paths. Items whose LLM calls failed on
every provider were re-run after the quota window and never scored as failures.

## Results (test split, 125 items, all three systems complete)

**False-verified rate (fabricated, altered or misattributed text labelled authentic): Mizan 0.0% (0/39) vs
LLM alone 20.5% (8/39) vs Dorar searched as-is 15.4% (6/39).**

| Metric | mizan | llm_baseline | dorar_direct |
|---|---|---|---|
| False-verified rate (target 0) | **0.0%** (0/39) | 20.5% (8/39) | 15.4% (6/39) |
| Verdict accuracy | **99.2%** (124/125) | 73.6% (92/125) | 49.6% (62/125) |
| Not-established recall | 96.2% (25/26) | 30.8% (8/26) | 80.8% (21/26) |
| Hallucination flags (automatic check) | 4.8% (5/104, manual check pending) | 8.0% (7/87) | n/a |
| Abstention / referral correctness | 100% (20/20) | 95.0% (19/20) | 0% (0/20) |
| Latency p50 / p95 | 9.9 s / 18.5 s | 5.5 s / 9.8 s | 1.9 s / 2.8 s |
| Mean cost per check | $0 (free tiers) | $0 | $0 |
| Items answered | 125 | 125 | 125 |

- `llm_baseline` was served by Gemini for 89 items and by Groq (`openai/gpt-oss-120b`) for the remaining 36, after
  the Gemini free-tier quota ran out (D-25); Mizan's provider mix is recorded per check in `check_metrics`.
- **Consistency was not measured**: one run per system (D-25), not the planned three.
- **All 179 bench items are unreviewed** (sharia review pending, D-22); every number above is on unreviewed items.
- Test numbers are for the code at tag `thresholds-frozen`; the later fix D-27 (evidence-request detector) is not
  reflected. Per-category and per-language tables and the chart: `bench/results/report.md`; raw outputs:
  `bench/results/*-test-1.jsonl`.
- **D-31 re-run:** after the post-freeze fix D-31 (strict spelling tolerance; found by manual testing on the live site), the 42 verse items of the test split were re-run: **no verdict and no number changed**. Pre-fix outputs: `bench/results/pre_d31/`.
- Hallucination flags: the automatic check (§11.4) flagged 5 Mizan outputs; they are being checked by hand and the
  numbers stay as computed until then.

## Limitations per language

- **Arabic.** Verse matching is deterministic over both Uthmani and imla'i spellings; spelling variants outside
  the known patterns err towards `misquoted`, never `verified` (D-23). Hadith verdicts depend on Dorar's first 15
  results per query; Sahihayn gradings not among them can turn an authentic hadith into `disputed` (D-11, pending).
- **English.** Verses: lexical match on the approved Rowwad translation; other translations of the Quran
  (e.g. Sahih International wording) match less well without embeddings. Hadiths: Dorar via the model's literal
  Arabic back-translation, plus HadeethEnc's approved translations.
- **Urdu.** Same as English with the Junagarhi translation; Urdu script is distinguished from Arabic by its
  extra letters; recall is lower than Arabic.
- **All.** Sayings attributed to scholars or Companions are out of scope. `prophetic_attribution_no_basis` has a
  single item (D-22), so that category's numbers are anecdotal.

## Hallucination check: manual agreement

A random sample of 30 `llm_baseline` outputs is to be reviewed by hand against the automatic check; the agreement
rate is reported here.

- Sample reviewed: _ / 30
- Agreement: _ %
