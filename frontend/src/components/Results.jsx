import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { VERDICTS, safeUrl, quoteSegments } from "../api/adapter.js";
import {
  FEATURES,
  USE_MOCK,
  generateReply,
  submitFeedback,
  humanError,
} from "../api/mizanApi.js";

const sources = {
  dorar: "الدرر السنية",
  hadeethenc: "موسوعة الأحاديث النبوية",
  quran: "النص القرآني المعتمد",
  quranenc: "QuranEnc",
};
const types = {
  hadith: "حديث نبوي",
  quran: "آية قرآنية",
  attributed_saying: "قول منسوب",
};
export function SourceLink({ url, children = "عرض المصدر" }) {
  const href = safeUrl(url);
  return href ? (
    <a
      className="source-link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children} <span aria-hidden="true">↗</span>
    </a>
  ) : null;
}
export function VerdictBadge({ claim }) {
  const unavailable = claim.source_status === "source_unavailable";
  const [icon, label] = unavailable
    ? ["!", "تعذر الوصول للمصدر"]
    : VERDICTS[claim.verdict];
  return (
    <span className={`verdict ${unavailable ? "unavailable" : claim.verdict}`}>
      <span aria-hidden="true">{icon}</span> {label}
    </span>
  );
}
function Gradings({ evidence }) {
  return (
    <>
      {evidence?.gradings?.map((grade, i) => (
        <div className="grading" key={i}>
          {grade.grade_text && (
            <p>
              <span className="muted">حكم المصدر: </span>
              <strong dir="auto">{grade.grade_text}</strong>
            </p>
          )}
          {[
            grade.mohaddith,
            grade.book,
            grade.page && `الصفحة / الرقم: ${grade.page}`,
          ].filter(Boolean).length > 0 && (
            <p className="muted" dir="auto">
              {[
                grade.mohaddith,
                grade.book,
                grade.page && `الصفحة / الرقم: ${grade.page}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
      ))}
    </>
  );
}
function Feedback({ resultId, claimIndex }) {
  const dialog = useRef(null),
    trigger = useRef(null);
  const [issue, setIssue] = useState("wrong_verdict"),
    [note, setNote] = useState(""),
    [state, setState] = useState(""),
    [busy, setBusy] = useState(false);
  const available = FEATURES.feedback && !USE_MOCK;
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setState("");
    try {
      await submitFeedback({
        check_id: resultId,
        claim_index: claimIndex,
        issue,
        note,
      });
      setState("شكرًا لك. وصل بلاغك للمراجعة.");
    } catch {
      setState("تعذر إرسال البلاغ. حاول لاحقًا.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="quiet"
        onClick={() => {
          setState("");
          dialog.current.showModal();
        }}
      >
        إبلاغ عن مشكلة
      </button>
      <dialog
        ref={dialog}
        aria-labelledby={`feedback-${claimIndex}`}
        onClose={() => trigger.current?.focus()}
      >
        <form onSubmit={submit}>
          <div className="row">
            <h3 id={`feedback-${claimIndex}`}>إبلاغ عن مشكلة</h3>
            <button
              type="button"
              className="quiet"
              aria-label="إغلاق"
              onClick={() => dialog.current.close()}
            >
              ✕
            </button>
          </div>
          {available ? (
            <>
              <label htmlFor={`issue-${claimIndex}`}>نوع المشكلة</label>
              <select
                id={`issue-${claimIndex}`}
                value={issue}
                onChange={(e) => setIssue(e.target.value)}
              >
                <option value="wrong_verdict">الحكم غير صحيح</option>
                <option value="wrong_source">المصدر غير مناسب</option>
                <option value="other">مشكلة أخرى</option>
              </select>
              <label htmlFor={`note-${claimIndex}`}>ملاحظة (اختياري)</label>
              <textarea
                id={`note-${claimIndex}`}
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                dir="auto"
              />
              <button
                className="primary"
                disabled={busy || state.startsWith("شكرًا")}
              >
                {busy ? "جارٍ الإرسال…" : "إرسال البلاغ"}
              </button>
            </>
          ) : (
            <p>
              الإبلاغ غير متاح في هذه النسخة. يمكنك مراجعة رابط المصدر للتحقق من
              البيانات.
            </p>
          )}
          <p role="status">{state}</p>
        </form>
      </dialog>
    </>
  );
}
export function ClaimCard({ claim, resultId }) {
  const evidence = claim.evidence;
  const unavailable = claim.source_status === "source_unavailable";
  return (
    <article className="claim" aria-labelledby={`claim-${claim.index}`}>
      <div className="claim-header">
        <span className="eyebrow">
          {String(claim.index + 1).padStart(2, "0")} /{" "}
          {types[claim.type] || "اقتباس"}
        </span>
        <VerdictBadge claim={claim} />
      </div>
      <h3 id={`claim-${claim.index}`} className="quote" dir="auto">
        {claim.span}
      </h3>
      {unavailable && (
        <p className="notice">
          تعذر الوصول إلى أحد المصادر حاليًا. حاول مرة أخرى؛ تعذّر الوصول لا
          يعني عدم وجود الاقتباس.
        </p>
      )}
      {!unavailable && claim.verdict === "not_found" && (
        <p>
          لم نجد مرجعًا مطابقًا في المصادر المتاحة. راجع جهة مؤهلة قبل نسبة
          النص.
        </p>
      )}
      {!unavailable && ["disputed", "needs_review"].includes(claim.verdict) && (
        <p>
          هذا الاقتباس يحتاج إلى مراجعة مختص. تُعرض أحكام المصادر كما وردت دون
          ترجيح.
        </p>
      )}
      {claim.verdict === "misquoted" && (
        <p className="notice">
          لا تعتمد على النص المنقول بصيغته الحالية؛ راجع النص الصحيح من المصدر.
        </p>
      )}
      {claim.relation === "same_meaning" && claim.verdict === "verified" && (
        <p className="muted">
          ثابت بالمعنى، واللفظ المعتمد هو النص الوارد في المصدر.
        </p>
      )}
      {evidence?.text_arabic && (
        <div className="source-text">
          <span className="eyebrow">
            {claim.verdict === "misquoted"
              ? "النص الصحيح"
              : "النص العربي من المصدر"}
          </span>
          <p dir="auto">{evidence.text_arabic}</p>
        </div>
      )}
      <Gradings evidence={evidence} />
      {evidence?.source && (
        <div className="row source-row">
          <span>{sources[evidence.source] || evidence.source}</span>
          <SourceLink url={evidence.url} />
        </div>
      )}
      {claim.alternative && (
        <section className="alternative">
          <span className="eyebrow">بديل صحيح</span>
          <h4>حديث آخر في المعنى نفسه</h4>
          <p dir="auto">{claim.alternative.text_arabic}</p>
          {claim.alternative.translation && (
            <p dir="auto">{claim.alternative.translation}</p>
          )}
          {claim.alternative.attribution && (
            <p className="muted" dir="auto">
              {claim.alternative.attribution}
            </p>
          )}
          <SourceLink url={claim.alternative.url}>عرض مصدر البديل</SourceLink>
        </section>
      )}
      {claim.diff ||
      evidence?.translation ||
      evidence?.locations?.length ||
      evidence?.attribution ||
      claim.notes?.length ? (
        <details>
          <summary>عرض التفاصيل</summary>
          {evidence?.translation && (
            <div>
              <span className="eyebrow">ترجمة المصدر</span>
              <p dir="auto">{evidence.translation}</p>
            </div>
          )}
          {evidence?.attribution && (
            <p className="muted" dir="auto">
              {evidence.attribution}
            </p>
          )}
          {evidence?.locations?.map((loc, i) => (
            <p key={i}>
              السورة: {loc.surah_name_ar || loc.surah} · الآية: {loc.ayah}{" "}
              <SourceLink url={loc.url} />
            </p>
          ))}
          {claim.diff && (
            <div className="diff">
              <p>{claim.diff.details}</p>
              <span className="eyebrow">الفروق الواردة من الخدمة</span>
              {claim.diff.ops?.map((op, i) => (
                <div key={i} className="diff-op">
                  <span>
                    {{
                      replace: "استبدال",
                      insert: "إضافة",
                      delete: "حذف",
                      equal: "مطابق",
                    }[op.op] || "فرق"}
                  </span>
                  {op.quoted && (
                    <span>
                      النص المنقول: <del dir="auto">{op.quoted}</del>
                    </span>
                  )}
                  {op.source && (
                    <span>
                      النص الصحيح: <ins dir="auto">{op.source}</ins>
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {claim.notes?.map((note, i) => (
            <p key={i} className="muted">
              {{
                too_short: "النص قصير وقد يحتاج إلى سياق أطول.",
                out_of_scope_attribution:
                  "نسبة القول خارج نطاق المصادر المتاحة.",
                multiple_locations: "للنص أكثر من موضع في المصادر.",
                takhrij_has_weak_chains:
                  "بعض طرق التخريج ضعيفة؛ راجع أحكام المصدر كاملة.",
              }[note] || note}
            </p>
          ))}
        </details>
      ) : null}
      <div className="claim-footer">
        <Feedback resultId={resultId} claimIndex={claim.index} />
      </div>
    </article>
  );
}
function Reply({ result }) {
  const [reply, setReply] = useState(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function load() {
    setBusy(true);
    setMessage("");
    try {
      const text = await generateReply(result);
      if (mounted.current) {
        setReply(text);
        if (!text) setMessage("الرد الجاهز غير متاح لهذه النتيجة.");
      }
    } catch (error) {
      if (mounted.current) setMessage(humanError(error));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(reply);
      setMessage("تم نسخ الرد.");
    } catch {
      setMessage("تعذر النسخ التلقائي. حدد النص وانسخه يدويًا.");
    }
  }
  if (!FEATURES.reply || !result.reply_available || !result.claims.length)
    return null;
  return (
    <section className="reply">
      <div className="row">
        <div>
          <span className="eyebrow">مشاركة مسؤولة</span>
          <h3>رد جاهز</h3>
        </div>
        {reply ? (
          <button type="button" className="secondary" onClick={copy}>
            نسخ الرد
          </button>
        ) : (
          <button
            type="button"
            className="secondary"
            onClick={load}
            disabled={busy}
          >
            {busy ? "جارٍ تجهيز الرد…" : "تجهيز رد مهذب"}
          </button>
        )}
      </div>
      {reply && (
        <textarea aria-label="الرد الجاهز" readOnly dir="auto" value={reply} />
      )}
      <p role="status" className="muted">
        {message}
      </p>
    </section>
  );
}
const statusTitles = {
  no_claims: "لم نجد آية أو حديثًا مقتبسًا في النص.",
  evidence_request: "مِيزان يتحقق من الأدلة الموجودة، ولا ينشئ أدلة جديدة.",
  referral: "هذا السؤال يحتاج إلى جهة مؤهلة للإفتاء.",
};
export default function Results({ result, originalText }) {
  return (
    <section className="results" aria-labelledby="results-title">
      <div className="result-heading">
        <div>
          <span className="eyebrow">
            نتيجة التحقق{USE_MOCK ? " · عرض تجريبي" : ""}
          </span>
          <h2 id="results-title" tabIndex={-1}>
            {result.claims.length
              ? `تم العثور على ${result.claims.length} ${result.claims.length === 1 ? "اقتباس" : "اقتباسات"}`
              : "اكتمل فحص النص"}
          </h2>
        </div>
        <Link
          className="quiet"
          to={`/result/${encodeURIComponent(result.check_id)}`}
        >
          فتح صفحة النتيجة ←
        </Link>
      </div>
      {result.status !== "ok" && (
        <div className="special">
          <h3>{statusTitles[result.status]}</h3>
          {result.message && <p dir="auto">{result.message}</p>}
          {result.referral?.text && <p dir="auto">{result.referral.text}</p>}
          <SourceLink url={result.referral?.url}>جهة الإحالة</SourceLink>
        </div>
      )}
      {originalText && (
        <details className="original">
          <summary>الاقتباسات في النص المُدخل</summary>
          <p dir="auto">
            {quoteSegments(originalText, result.claims).map((part, i) =>
              part.marked ? (
                <mark key={i}>{part.text}</mark>
              ) : (
                <span key={i}>{part.text}</span>
              ),
            )}
          </p>
        </details>
      )}
      {result.claims.map((claim) => (
        <ClaimCard key={claim.index} claim={claim} resultId={result.check_id} />
      ))}
      <Reply key={result.check_id} result={result} />
      <p className="disclaimer">
        {result.disclaimer || "أداة آلية للتحقق من المصادر، وليست فتوى."}
      </p>
    </section>
  );
}
