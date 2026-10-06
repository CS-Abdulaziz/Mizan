import ar from "./fixtures/hadith-ar.json";
import en from "./fixtures/hadith-en.json";
import ur from "./fixtures/hadith-ur.json";
// Placeholder only: mock fixtures never contain scripture (texts come from the sources at run time).
const quran = {
  arabic_text: "<نص من المصدر> (آية)",
  url: "https://quranenc.com/en/browse/english_rwwad/94/5",
};
import dorar from "./fixtures/dorar.json";

export const examples = [
  {
    id: "china",
    label: "حديث متداول",
    text: "قال رسول الله ﷺ: <نص من المصدر> (حديث لا يثبت)",
  },
  { id: "quran", label: "آية منقولة", text: quran.arabic_text },
  { id: "english", label: "English example", text: en.title },
  { id: "urdu", label: "Urdu example", text: ur.title },
];
export const scenarios = [
  ["china", "لا يثبت + البديل"],
  ["quran", "آية موثّقة"],
  ["english", "English"],
  ["urdu", "اردو"],
  ["misquoted", "منقول بخطأ"],
  ["disputed", "اختلف فيه"],
  ["not_found", "لم يُعثر عليه"],
  ["needs_review", "مراجعة مختص"],
  ["source_unavailable", "المصدر غير متاح"],
  ["multiple", "اقتباسات متعددة"],
  ["no_claims", "لا اقتباسات"],
  ["evidence_request", "طلب دليل"],
  ["referral", "إحالة + اقتباس"],
  ["network", "خطأ الشبكة"],
  ["server", "خطأ الخدمة"],
  ["timeout", "انتهاء المهلة"],
  ["expired", "نتيجة منتهية"],
];
const disclaimer = "أداة آلية للتحقق من المصادر، وليست فتوى.";
const evidence = {
  source: "hadeethenc",
  text_arabic: ar.title,
  url: ar.url,
  attribution: ar.attribution,
  gradings: [{ grade_text: ar.grade }],
  locations: [],
};
const baseClaim = {
  index: 0,
  type: "hadith",
  span: ar.title,
  lang: "ar",
  verdict: "verified",
  relation: "same_meaning",
  confidence: 0.96,
  evidence,
  alternative: null,
  notes: [],
  source_status: "ok",
};
export function fixture(id) {
  const result = {
    check_id: `demo-${id}`,
    status: "ok",
    lang: "ar",
    claims: [],
    referral: null,
    message: null,
    disclaimer,
    reply_available: true,
    expires_at: new Date(Date.now() + 86400000).toISOString(),
  };
  const claim = structuredClone(baseClaim);
  if (id === "china") {
    claim.span = examples[0].text.slice("قال رسول الله ﷺ: ".length);
    Object.assign(claim, {
      verdict: "not_established",
      relation: "exact",
      evidence: dorar,
      alternative: {
        source: "hadeethenc",
        id: ar.id,
        text_arabic: ar.title,
        attribution: ar.attribution,
        url: ar.url,
        label: "different_hadith_related_meaning",
      },
    });
  } else if (id === "quran" || id === "misquoted") {
    Object.assign(claim, {
      type: "quran",
      span: quran.arabic_text,
      relation: "exact",
      evidence: {
        source: "quran",
        text_arabic: quran.arabic_text,
        url: quran.url,
        locations: [{ surah: 94, ayah: 5 }],
        gradings: [],
      },
    });
    if (id === "misquoted") {
      const words = quran.arabic_text.split(" ");
      const old = words[words.length - 1];
      words[words.length - 1] = "مثال";
      Object.assign(claim, {
        span: words.join(" "),
        verdict: "misquoted",
        relation: "altered",
        diff: {
          kind: "wording",
          ops: [{ op: "replace", quoted: "مثال", source: old }],
          details: "نص محرّف للاختبار فقط: استُبدلت كلمة من النص بكلمة عامة.",
        },
      });
    }
  } else if (id === "english" || id === "urdu") {
    const source = id === "english" ? en : ur;
    result.lang = id === "english" ? "en" : "ur";
    claim.span = source.title;
    claim.lang = result.lang;
    claim.evidence = {
      ...evidence,
      translation: source.title,
      url: source.url,
    };
  } else if (
    ["disputed", "not_found", "needs_review", "source_unavailable"].includes(id)
  ) {
    claim.span = "اقتباس افتراضي لاختبار العرض — ليس نصًا شرعيًا";
    claim.verdict = id === "source_unavailable" ? "not_found" : id;
    claim.evidence = null;
    claim.notes = [
      "الحالة تجريبية لعرض الواجهة فقط، ولا تمثل حكمًا على نص شرعي.",
    ];
    if (id === "source_unavailable") claim.source_status = "source_unavailable";
  } else if (["no_claims", "evidence_request", "referral"].includes(id)) {
    result.status = id;
    result.reply_available = false;
    if (id === "no_claims")
      result.message =
        "مِيزان مخصص للتحقق من الاقتباسات الشرعية، وليس للإجابة العامة عن الأسئلة الإسلامية.";
    if (id === "evidence_request")
      result.message = "الصق الآية أو الحديث الذي تريد التحقق من نسبته ومصدره.";
    if (id === "referral") {
      result.referral = {
        reason: "personal_ruling",
        text: "اعرض المسألة على جهة مؤهلة للإفتاء تراعي تفاصيل حالتك.",
      };
      result.claims = [claim];
    }
    return result;
  } else if (id === "multiple") {
    result.claims = [
      fixture("china").claims[0],
      { ...fixture("quran").claims[0], index: 1 },
      { ...baseClaim, index: 2 },
    ];
    return result;
  }
  result.claims = [claim];
  return result;
}
export function scenarioText(id) {
  const example = examples.find((e) => e.id === id);
  if (example) return example.text;
  if (id === "multiple")
    return fixture(id)
      .claims.map((c) => c.span)
      .join("\n");
  if (id === "misquoted") return fixture(id).claims[0].span;
  return (
    {
      no_claims: "مرحبًا، كيف حالك اليوم؟",
      evidence_request: "أعطني حديثًا يثبت هذا الكلام.",
      referral: "هل يجوز لي هذا في حالتي الشخصية؟",
    }[id] || "نص تجريبي لاختبار حالة الواجهة."
  );
}
export async function mockCheck(text, scenario, signal) {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, 950);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
  const id =
    scenario || examples.find((e) => e.text.trim() === text.trim())?.id;
  if (!id) throw new Error("demo_only");
  if (["network", "server", "timeout", "expired"].includes(id))
    throw new Error(id);
  const result = fixture(id);
  result.claims = result.claims.map((c) => {
    const offset = text.indexOf(c.span);
    return offset < 0
      ? c
      : {
          ...c,
          span_start: Array.from(text.slice(0, offset)).length,
          span_end: Array.from(text.slice(0, offset) + c.span).length,
        };
  });
  return result;
}
export function mockReply(result) {
  if (result.claims[0]?.verdict === "not_established")
    return `شكرًا لك على المشاركة. وفق المصدر المرفق، هذا الاقتباس لا يثبت. يمكنك الاطلاع على الحكم هنا: ${dorar.url}\nوهذا حديث آخر في فضل طلب العلم: «${ar.title}»\n${ar.url}\nهذا رد تجريبي، وأداة مِيزان ليست جهة إفتاء.`;
  return `شكرًا لك على المشاركة. هذه نتيجة تجريبية؛ يمكنك مراجعة الاقتباس من خلال مصدره:\n${result.claims[0]?.evidence?.url || ""}\n${disclaimer}`;
}
