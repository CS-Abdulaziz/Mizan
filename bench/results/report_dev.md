# Mizan-Bench results (dev split)

Items: 54 (0 reviewed by the sharia reviewer, 54 unreviewed).
Thresholds were tuned on the dev split only and frozen before this run (methodological safeguard).

| Metric | mizan | llm_baseline | dorar_direct |
|---|---|---|---|
| Verdict accuracy | 87.0% (47/54) | 22.2% (12/54) | 42.6% (23/54) |
| Not-established recall | 60.0% (6/10) | 0.0% (0/10) | 80.0% (8/10) |
| False-verified rate (target 0) | 0.0% (0/16) | 0.0% (0/16) | 25.0% (4/16) |
| Hallucination rate | 0.0% (0/41) | 0.0% (0/23) | n/a |
| Abstention / referral correctness | 88.9% (8/9) | 66.7% (6/9) | 0.0% (0/9) |
| Consistency | n/a (1 run) | n/a (1 run) | n/a (1 run) |
| Latency p50 (ms) | 8091 | 2999 | 1526 |
| Latency p95 (ms) | 63537 | 4326 | 1989 |
| Mean cost per check (USD) | 0.00000 | 0.00000 | 0.00000 |
| Items answered | 54 | 54 | 54 |

## Accuracy per category

| | mizan | llm_baseline | dorar_direct |
|---|---|---|---|
| altered_verse | 83.3% (5/6) | 50.0% (3/6) | 0.0% (0/6) |
| authentic_hadith | 100.0% (8/8) | 0.0% (0/8) | 87.5% (7/8) |
| authentic_hadith_with_weak_chains | 66.7% (2/3) | 33.3% (1/3) | 100.0% (3/3) |
| authentic_verse | 100.0% (6/6) | 16.7% (1/6) | 33.3% (2/6) |
| fabricated_hadith | 75.0% (6/8) | 0.0% (0/8) | 100.0% (8/8) |
| fabricated_translated_with_authentic_lookalike | 0.0% (0/2) | 0.0% (0/2) | 0.0% (0/2) |
| multi_location_phrase | 100.0% (2/2) | 0.0% (0/2) | 50.0% (1/2) |
| partial_verse_quote | 100.0% (2/2) | 0.0% (0/2) | 50.0% (1/2) |
| personal_ruling | 100.0% (3/3) | 66.7% (2/3) | 0.0% (0/3) |
| reference_pack_questions | 83.3% (5/6) | 66.7% (4/6) | 0.0% (0/6) |
| translated | 100.0% (8/8) | 12.5% (1/8) | 12.5% (1/8) |

## Accuracy per language

| | mizan | llm_baseline | dorar_direct |
|---|---|---|---|
| ar | 87.5% (35/40) | 20.0% (8/40) | 55.0% (22/40) |
| en | 84.6% (11/13) | 30.8% (4/13) | 0.0% (0/13) |
| ur | 100.0% (1/1) | 0.0% (0/1) | 100.0% (1/1) |

## Charts

![accuracy_per_category.png](accuracy_per_category.png)

## Hallucination check: manual agreement

Manual review of a random sample of 30 `llm_baseline` outputs against the automatic check (§11.4):

- Sample reviewed: _ / 30
- Agreement with the automatic check: _ %

