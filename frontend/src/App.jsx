import { useState } from "react";
import { Link, Routes, Route } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Result from "./pages/Result.jsx";
import { USE_MOCK } from "./api/mizanApi.js";
export default function App() {
  const [menu, setMenu] = useState(false);
  return (
    <>
      <a className="skip" href="#main">
        انتقل إلى المحتوى
      </a>
      {USE_MOCK && (
        <div className="demo-banner">
          نسخة تجريبية للعرض — النتائج أمثلة ثابتة وليست تحققًا مباشرًا.
        </div>
      )}
      <header>
        <div className="nav">
          <Link className="brand" to="/" aria-label="مِيزان، الصفحة الرئيسية">
            <img src="/icon.svg" width="36" height="36" alt="" />
            <span>
              مِيزان<small>MIZAN</small>
            </span>
          </Link>
          <button
            className="menu-button"
            type="button"
            aria-expanded={menu}
            aria-controls="nav-links"
            onClick={() => setMenu((m) => !m)}
          >
            {menu ? "إغلاق" : "القائمة"}
          </button>
          <nav
            id="nav-links"
            aria-label="التنقل الرئيسي"
            className={menu ? "open" : ""}
          >
            {[
              ["تحقق", "verify"],
              ["كيف يعمل", "how"],
              ["المصادر", "sources"],
              ["عن مِيزان", "about"],
            ].map(([label, id]) => (
              <a href={`/#${id}`} key={id} onClick={() => setMenu(false)}>
                {label}
              </a>
            ))}
          </nav>
          <span className="nav-caption">تحقّق قبل أن تنشر.</span>
        </div>
      </header>
      <main id="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/result/:checkId" element={<Result />} />
          <Route path="/r/:checkId" element={<Result />} />
          <Route
            path="*"
            element={
              <div className="result-page">
                <h1>الصفحة غير موجودة.</h1>
                <Link to="/">العودة إلى مِيزان</Link>
              </div>
            }
          />
        </Routes>
      </main>
      <footer>
        <Link className="brand" to="/">
          مِيزان
        </Link>
        <p>أداة آلية للتحقق من المصادر، وليست فتوى.</p>
        <span>العربية · English · اردو</span>
      </footer>
    </>
  );
}
