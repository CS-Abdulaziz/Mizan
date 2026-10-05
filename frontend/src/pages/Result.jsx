import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getResult, humanError } from "../api/mizanApi.js";
import Results from "../components/Results.jsx";
export default function Result() {
  const { checkId } = useParams();
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    getResult(checkId, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(humanError(err));
      });
    return () => controller.abort();
  }, [checkId, attempt]);
  return (
    <div className="result-page">
      <Link className="quiet" to="/">
        → العودة إلى التحقق
      </Link>
      {data ? (
        <Results result={data} />
      ) : error ? (
        <div className="error" role="alert">
          <h1>تعذر عرض النتيجة</h1>
          <p>{error}</p>
          <button
            className="secondary"
            onClick={() => setAttempt((a) => a + 1)}
          >
            إعادة المحاولة
          </button>
          <Link className="source-link" to="/">
            تحقق من نص جديد
          </Link>
        </div>
      ) : (
        <p role="status" className="loading">
          جارٍ تحميل النتيجة…
        </p>
      )}
    </div>
  );
}
