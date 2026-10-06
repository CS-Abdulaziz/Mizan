"""Threshold tuning on the DEV split only (SPEC §11.2, TASKS B20).

Free-tier quotas rule out re-running the LLM for every threshold combination, so the sweep is offline:
- verse matcher (deterministic): re-run `match_arabic` on the dev Arabic verse items for each
  (QURAN_VERIFIED_RAW, QURAN_CANDIDATE_RAW) pair;
- verifier confidence: recompute verdicts from the confidences stored in bench/results/mizan-dev-1.jsonl for
  each acceptance threshold (a stored claim below a threshold becomes not_found). This can only tighten
  thresholds; looser values would need new model calls.
Selection: highest dev accuracy subject to false-verified = 0; ties keep the SPEC default.

    python bench/tune.py            # prints the sweep and the chosen values
    python bench/tune.py --write    # writes the chosen values into backend/app/core/thresholds.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import thresholds as T  # noqa: E402
from app.pipeline import quran_match as qm  # noqa: E402

THRESHOLDS = ROOT / "backend" / "app" / "core" / "thresholds.py"
VERSE_CATS = {"authentic_verse", "partial_verse_quote", "multi_location_phrase", "altered_verse"}

spec = importlib.util.spec_from_file_location("bench_metrics", ROOT / "bench" / "metrics.py")
metrics = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(metrics)  # type: ignore[union-attr]


def quote_of(text: str) -> str:
    m = re.search(r"[﴿«]([^﴾»]+)[﴾»]", text)
    if m:
        return m.group(1)
    return re.sub(r"^[^:]*:\s*", "", text)


def matcher_sweep(items: list[dict]) -> list[tuple[float, float, int, int, int]]:
    index = qm.load_from_json()
    qm._index = index
    dev = [i for i in items if i["category"] in VERSE_CATS and i["lang"] == "ar"]
    rows = []
    for vr in (94.0, 95.0, 96.0, 97.0, 98.0):
        for cr in (75.0, 80.0, 85.0):
            T.QURAN_VERIFIED_RAW, T.QURAN_CANDIDATE_RAW = vr, cr
            correct = fv = 0
            for it in dev:
                exp = it["expected"][0]["verdict"]
                cited = None
                m = re.search(r"في سورة ([^:﴿]+)", it["text"])
                if m:
                    cited = m.group(1).strip()
                vm = qm.match_arabic(quote_of(it["text"]), cited, index)
                pred = {"verified": "verified", "attribution": "misquoted", "misquoted_candidate": "misquoted"}.get(
                    vm.status, "not_found")
                correct += pred == exp
                fv += pred == "verified" and exp != "verified"
            rows.append((vr, cr, correct, fv, len(dev)))
    T.QURAN_VERIFIED_RAW, T.QURAN_CANDIDATE_RAW = 96.0, 80.0
    return rows


def verifier_sweep(items: dict[str, dict]) -> list[tuple[float, int, int, int]]:
    f = ROOT / "bench" / "results" / "mizan-dev-1.jsonl"
    if not f.exists():
        return []
    recs = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = []
    for t in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
        correct = fv = n = 0
        for r in recs:
            it = items.get(r["id"])
            if it is None or r.get("error"):
                continue
            out = json.loads(json.dumps(r["output"]))
            for c in out.get("claims", []):
                # only verifier-decided hadith claims carry a confidence below 1.0
                if c.get("type") == "hadith" and c.get("relation") in ("exact", "same_meaning") and c["confidence"] < t:
                    c["verdict"] = "not_found"
            s = metrics.score_item(it, {"output": out})
            n += 1
            correct += s["correct"]
            fv += any(p == "verified" and e in metrics.NEGATIVE for e, p, _ in s["pairs"])
        rows.append((t, correct, fv, n))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    items = {i["id"]: i for i in (json.loads(x) for x in (ROOT / "bench" / "items.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()) if i["split"] == "dev"}
    m_rows = matcher_sweep(list(items.values()))
    print("verse matcher (dev, Arabic verse items): VERIFIED_RAW CANDIDATE_RAW correct false_verified n")
    for r in m_rows:
        print("  ", r)
    ok = [r for r in m_rows if r[3] == 0]
    best = max(ok, key=lambda r: (r[2], r[0] == 96.0 and r[1] == 80.0)) if ok else (96.0, 80.0, 0, 0, 0)
    v_rows = verifier_sweep(items)
    print("hadith verifier exact/same_meaning floor (dev, all items): threshold correct false_verified n")
    for r in v_rows:
        print("  ", r)
    vbest = None
    if v_rows:
        okv = [r for r in v_rows if r[2] == 0] or v_rows
        vbest = max(okv, key=lambda r: (r[1], -abs(r[0] - T.HADITH_EXACT_CONF)))
    print(f"chosen: QURAN_VERIFIED_RAW={best[0]} QURAN_CANDIDATE_RAW={best[1]}"
          + (f" HADITH_EXACT_CONF={max(vbest[0], T.HADITH_EXACT_CONF)}" if vbest else ""))
    if args.write:
        s = THRESHOLDS.read_text(encoding="utf-8")
        s = re.sub(r"QURAN_VERIFIED_RAW = [\d.]+", f"QURAN_VERIFIED_RAW = {best[0]}", s)
        s = re.sub(r"QURAN_CANDIDATE_RAW = [\d.]+", f"QURAN_CANDIDATE_RAW = {best[1]}", s)
        if vbest and vbest[0] > T.HADITH_EXACT_CONF:
            s = re.sub(r"HADITH_EXACT_CONF = [\d.]+", f"HADITH_EXACT_CONF = {vbest[0]}", s)
        THRESHOLDS.write_text(s, encoding="utf-8")
        print("written to", THRESHOLDS)
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
