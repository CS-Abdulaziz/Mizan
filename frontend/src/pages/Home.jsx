import { useEffect, useRef, useState } from "react";
import { checkText, humanError, USE_MOCK } from "../api/mizanApi.js";
import { examples, scenarios, scenarioText } from "../mocks/responses.js";
import Results from "../components/Results.jsx";

export default function Home() {
  const [text, setText] = useState(""),
    [scenario, setScenario] = useState(""),
    [result, setResult] = useState(null),
    [original, setOriginal] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const controller = useRef(null),
    input = useRef(null),
    retryText = useRef("");
  const count = Array.from(text).length;
  useEffect(() => () => controller.current?.abort(), []);
  function fill(value, id = "") {
    setText(value);
    setScenario(id);
    setResult(null);
    setError("");
    input.current?.focus();
  }
  async function verify(event) {
    event?.preventDefault();
    if (busy || !text.trim()) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const submitted = text;
    retryText.current = submitted;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const data = await checkText(submitted, {
        scenario,
        signal: abort.signal,
      });
      if (!abort.signal.aborted) {
        setResult(data);
        setOriginal(submitted);
        requestAnimationFrame(() =>
          document.getElementById("results-title")?.focus(),
        );
      }
    } catch (error) {
      if (error.name !== "AbortError") setError(humanError(error));
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }
  return (
    <>
      <section className="hero">
        <p className="eyebrow">مِيزان / مدقق الاقتباسات الشرعية متعدد اللغات</p>
        <h1>
          تحقّق من الاقتباس
          <br />
          <span>قبل أن تنشره.</span>
        </h1>
        <p className="intro">
          من اقتباس متداول، إلى مصدر يمكنك التحقق منه.
          <br />
          للآيات والأحاديث بالعربية والإنجليزية والأردية.
        </p>
      </section>
      <section className="verify-layout" id="verify">
        <form className="verification" onSubmit={verify} aria-busy={busy}>
          <div className="row">
            <label htmlFor="quote-input">ما النص الذي تريد التحقق منه؟</label>
            <span className="mini-label">01 / التحقق</span>
          </div>
          <textarea
            id="quote-input"
            ref={input}
            dir={text ? "auto" : "rtl"}
            value={text}
            disabled={busy}
            onChange={(e) => {
              setText(e.target.value);
              setScenario("");
              setError("");
              setResult(null);
            }}
            placeholder="الصق رسالة أو نصًا يحتوي على آية أو حديث…"
            aria-describedby="input-hint character-count"
          />
          <div className="editor-bottom">
            <span
              id="character-count"
              className={count > 4000 ? "over-limit" : "muted"}
              dir="ltr"
            >
              {count.toLocaleString("en")} / 4,000
            </span>
            <button
              type="button"
              className="quiet"
              disabled={!text || busy}
              onClick={() => fill("")}
            >
              مسح النص
            </button>
          </div>
          <div className="examples">
            <span className="muted">جرّب مثالًا</span>
            {examples.map((example) => (
              <button
                type="button"
                disabled={busy}
                key={example.id}
                onClick={() => fill(example.text)}
                dir="auto"
              >
                {example.label}
              </button>
            ))}
          </div>
          <div className="submit-row">
            <button
              className="primary"
              disabled={busy || !text.trim() || count > 4000}
            >
              {busy ? (
                "جارٍ التحقق من الاقتباسات…"
              ) : (
                <>
                  تحقّق <span aria-hidden="true">←</span>
                </>
              )}
            </button>
            <p id="input-hint" className="muted">
              النتيجة مرتبطة بمصدر.
              <br />
              مِيزان لا يصدر الفتاوى.
            </p>
          </div>
          {busy && (
            <div className="loading" role="status">
              <span className="pulse" aria-hidden="true" />
              <div>
                <strong>جارٍ التحقق من الاقتباسات…</strong>
                <p>تحليل النص · البحث في المصادر · التحقق من المطابقة</p>
              </div>
            </div>
          )}
          {error && (
            <div className="error" role="alert">
              <p>{error}</p>
              <button
                type="button"
                className="secondary"
                onClick={verify}
                disabled={
                  text !== retryText.current || !text.trim() || count > 4000
                }
              >
                إعادة المحاولة
              </button>
            </div>
          )}
        </form>
        <aside className="verify-note">
          <span className="note-symbol" aria-hidden="true">
            “
          </span>
          <h2>المصدر أولًا.</h2>
          <p>
            لا تكفي شهرة الاقتباس لإثباته. تعرّف إلى نصّه المعتمد، وحكم المصدر،
            وأي اختلاف في نقله.
          </p>
          <hr />
          <span className="eyebrow">اقتباس · مطابقة · مصدر</span>
          <p className="small">
            يمكن التحقق من أكثر من اقتباس في الرسالة نفسها.
          </p>
        </aside>
      </section>
      {USE_MOCK && (
        <details className="demo-tools">
          <summary>نسخة تجريبية — استعراض حالات الواجهة</summary>
          <p>
            الأمثلة نتائج ثابتة لعرض تجربة الاستخدام. النصوص الأخرى تتطلب ربط
            خدمة التحقق.
          </p>
          <label htmlFor="scenario">حالة العرض</label>
          <select
            id="scenario"
            value={scenario}
            disabled={busy}
            onChange={(e) => fill(scenarioText(e.target.value), e.target.value)}
          >
            <option value="">اختر حالة</option>
            {scenarios.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </details>
      )}
      {result && (
        <Results
          key={`${result.check_id}-${original}`}
          result={result}
          originalText={original}
        />
      )}
      <section className="how" id="how">
        <div className="section-heading">
          <span className="eyebrow">من النص إلى المصدر</span>
          <h2>كيف يعمل مِيزان؟</h2>
        </div>
        <ol>
          {[
            "نستخرج الاقتباسات",
            "نبحث في المصادر المعتمدة",
            "نقارن النص بالمصدر",
            "نعرض الحكم والمصدر",
          ].map((step, i) => (
            <li key={step}>
              <span>0{i + 1}</span>
              <h3>{step}</h3>
            </li>
          ))}
        </ol>
      </section>
      <section className="sources-section" id="sources">
        <div>
          <span className="eyebrow">مراجع يمكن الرجوع إليها</span>
          <h2>
            وضوح في النتيجة.
            <br />
            وثقة في المصدر.
          </h2>
          <p>
            خدمة مِيزان تعتمد على النص القرآني المعتمد، وترجمات القرآن
            والأحاديث، وأحكام المحدثين من المصادر التالية.
          </p>
        </div>
        <div className="source-list">
          {[
            [
              "الدرر السنية",
              "أحكام المحدثين وتخريج الأحاديث",
              "https://dorar.net",
            ],
            [
              "HadeethEnc",
              "النصوص والترجمات المعتمدة للأحاديث",
              "https://hadeethenc.com/ar",
            ],
            [
              "QuranEnc",
              "ترجمات معاني القرآن الكريم",
              "https://quranenc.com/ar",
            ],
          ].map(([name, desc, url]) => (
            <a key={name} href={url} target="_blank" rel="noopener noreferrer">
              <div>
                <h3>{name}</h3>
                <p>{desc}</p>
              </div>
              <span aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      </section>
      <section className="about" id="about">
        <h2>تحقّق قبل أن تنشر.</h2>
        <p>
          مِيزان يساعدك على التثبت من الاقتباس ومصدره. لا ينشئ أدلة جديدة، ولا
          يستبدل أهل الاختصاص في الفتوى. النصوص المنقولة والترجمات قد تختلف؛
          لذلك يبقى الرجوع إلى المصدر جزءًا من النتيجة.
        </p>
        <p className="muted">
          في الخدمة الفعلية، تُحفظ النتائج لمدة محدودة وفق سياسة الخادم (حتى 24
          ساعة). هذه الواجهة لا تحفظ النص المُدخل في سجل محلي.
        </p>
      </section>
    </>
  );
}
