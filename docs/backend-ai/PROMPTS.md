# برومبتات Claude Code — جزء Backend + AI

## قبل ما تبدأ

1. حط محتويات هذي الحزمة في جذر الريبو كما هي، وارفعها على `main`:
   `CLAUDE.md`، و`docs/`، ومجلد `docs/reference/` فيه ملفات PDF الأربعة.
2. افتح Claude Code داخل مجلد الريبو. يقرأ `CLAUDE.md` تلقائياً.
3. جهّز هذي الأشياء لأن Claude Code بيوقف ويطلبها:
   - مفتاح مزود النموذج اللغوي، ومفتاح مزود التضمينات (لازم يدعم العربية والأردية، و1024 بُعد).
   - مشروع Supabase مع `DATABASE_URL`.
   - لاحقاً: خدمة Render، وتوكن بوت Telegram.
4. أرسل للمتخصص الشرعي في الفريق `core/grade_rules.py` وجدول §8.2 في `SPEC.md` أول ما يجهزون، و`bench/review_sheet.csv` بعد مهمة B18.

الصق البرومبتات بالترتيب. كل برومبت يغطي مرحلة، وClaude Code يقف عند أي خطوة تحتاجك.

---

## 1. البداية (الصقه أول مرة)

```text
Read CLAUDE.md, then docs/backend-ai/SPEC.md, docs/backend-ai/TASKS.md, docs/API_CONTRACT.md and
docs/backend-ai/AMENDMENTS.md in full. Skim docs/reference/reference-pack.pdf (pages 2, 5, 6, 7 matter most).

Then give me, in under 15 lines:
1. Your understanding of the pipeline in 5 bullets.
2. Anything in SPEC.md that is contradictory or unclear to you.
3. The exact list of keys/accounts you will need from me and at which task.

Do not write code yet.
```

## 2. المرحلة A + B (الأساس والبيانات)

```text
Execute tasks B01 to B09 from docs/backend-ai/TASKS.md in order, following SPEC.md exactly.
Rules:
- One task at a time: implement, write the tests listed in its AC, run pytest, tick it in TASKS.md, commit
  with message "B0x: <title>".
- B02 first priority after B01: run the real smoke test and adapt to the real field names. Save fixtures.
  Log every mismatch with the spec in docs/DECISIONS.md.
- Never type Quran or hadith text yourself; take it from fetched data and fixtures.
- When you hit a HUMAN step, stop, tell me exactly what to do (commands, where to paste what), and
  continue with the next task that does not depend on it.
After each task print: done / how verified / what I must do next.
```

## 3. المرحلة C (خط المعالجة)

```text
Execute tasks B10 to B17 from docs/backend-ai/TASKS.md in order.
Pay special attention to:
- B11: implement every one of the six test cases in SPEC §7.3 by building variants from data/quran.json.
  Classify on the raw alignment score, rank on the adjusted score, apply the containment guard, and diff
  only inside the aligned span.
- B14: hadith same_meaning needs confidence >= 0.85; validate every returned id in code.
- B15: implement the §8.1 order and the §8.2 table exactly; put keyword lists in core/grade_rules.py.
  Write one test per table row. Then stop and print the grade rules and the table for me to send to
  our sharia reviewer.
- B16: the response must validate against docs/API_CONTRACT.md. If you need to change the contract,
  ask me first, because the frontend teammate builds against it.
Start B18 (bench builder) as soon as B05-B09 data exists, in parallel with the pipeline if useful.
```

## 4. المرحلة D (التقييم)

```text
Execute B18, B19, B20.
- Bench items come from source data only, with provenance, reviewed_by null, 30/70 stratified split.
- Produce bench/review_sheet.csv for our sharia reviewer and stop so I can send it.
- After I give you the reviewed CSV, apply it, run tuning on dev ONLY, freeze thresholds (tag
  thresholds-frozen), then run the test split: mizan x3, llm_baseline x3, dorar_direct x1.
- Write docs/EVALUATION.md with tables, charts, the dev/test separation statement and per-language limitations.
Report the headline numbers to me: accuracy, not-established recall, false-verified rate, hallucination
rate for mizan vs llm_baseline, consistency, p50/p95 latency, mean cost per check.
```

## 5. المرحلة E (الميزات الإضافية)

```text
Execute B21 to B24 (ready reply with glossary, authentic alternative, feedback, Telegram bot).
For the bot, give me the exact BotFather steps and the setWebhook command with placeholders.
```

## 6. التسليم

```text
Execute B25 and B26. Then run the full checklist in SPEC §18 and show me each item with pass/fail
and evidence (command output or link). List anything still failing, ordered by impact on the judging criteria.
```

---

## برومبتات مساعدة

**لو انقطعت الجلسة:**

```text
Read CLAUDE.md and docs/backend-ai/TASKS.md. Check git log and the ticked tasks, run pytest, and tell me
where we are and what the next task is. Then continue from there.
```

**لو مصدر خارجي تعطّل أثناء العمل:**

```text
<source> is failing. Follow SPEC §17 for its fallback, make sure the pipeline returns source_unavailable
rather than a wrong verdict, add a test for that path, and tell me what changed.
```

**مراجعة قبل الدمج في main:**

```text
Review the diff of this branch against main as a strict senior reviewer: correctness against SPEC.md,
the golden rules in CLAUDE.md (especially: no model-written grades/texts/urls, no message text in logs,
no secrets), and test coverage. Fix what you find, then summarize.
```
