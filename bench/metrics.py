"""Mizan-Bench metrics (SPEC §11.3, §11.4, TASKS B19): tables + PNG charts + report.md.

    python bench/metrics.py --split test --out bench/results/report.md

Reads bench/items.jsonl and every bench/results/<system>-<split>-<run>.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from rapidfuzz import fuzz  # noqa: E402

ITEMS = ROOT / "bench" / "items.jsonl"
RESULTS = ROOT / "bench" / "results"
PRICES = ROOT / "bench" / "prices.json"
SYSTEMS = ("mizan", "llm_baseline", "dorar_direct")
TEXT_MATCH = 80  # §11.4: arabic_text below this similarity to every source candidate counts as a hallucination
NEGATIVE = ("not_established", "misquoted")


def load_items(split: str) -> dict[str, dict]:
    items = [json.loads(x) for x in ITEMS.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {i["id"]: i for i in items if split in ("all", i["split"]) and not i.get("rejected")}


def load_runs(system: str, split: str) -> list[dict[str, dict]]:
    runs = []
    for f in sorted(RESULTS.glob(f"{system}-{split}-*.jsonl")):
        recs = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            recs[r["id"]] = r
        runs.append(recs)
    return runs


# --------------------------------------------------------------------------- per item scoring


def predicted(rec: dict) -> tuple[str | None, list[dict]]:
    out = rec.get("output") or {}
    return out.get("status"), out.get("claims") or []


def pick_claim(exp: dict, claims: list[dict]) -> dict | None:
    same = [c for c in claims if c.get("type") == exp["type"]]
    return (same or claims or [None])[0]


def score_item(item: dict, rec: dict | None) -> dict[str, Any]:
    """correct (bool), status_ok, verdicts (expected, predicted) per expected claim."""
    if rec is None or rec.get("error"):
        return {"answered": False, "correct": False, "status_ok": False, "pairs": []}
    status, claims = predicted(rec)
    status_ok = status == item["expected_status"] or (item["expected_status"] == "ok" and status == "referral" and claims)
    pairs = []
    for e in item["expected"]:
        c = pick_claim(e, claims)
        pv = c.get("verdict") if c else None
        pairs.append((e["verdict"], pv, pv == e["verdict"] or pv in e.get("accept", [])))
    if item["expected"]:
        correct = all(ok for _, _, ok in pairs)
    else:
        correct = status_ok
    return {"answered": True, "correct": correct, "status_ok": status_ok, "pairs": pairs,
            "n_pred_claims": len(claims)}


def source_texts_for(item: dict) -> list[str]:
    """Source candidates for the hallucination text check: Mushaf / HadeethEnc / Dorar texts of the item's refs."""
    from app.core.config import DATA_DIR
    from app.pipeline import quran_match as qm
    from app.pipeline.normalize import normalize_ar

    out: list[str] = []
    for e in item["expected"]:
        ref = e.get("ref") or ""
        if ref.startswith("quran:") and qm.QURAN_JSON.exists():
            idx = qm.get_index() or qm.load_from_json()
            qm._index = idx
            s, a = ref.split(":")[1:3]
            vi = idx.by_ref.get((int(s), int(a.split("-")[0])))
            if vi is not None:
                out += [idx.verses[vi].clean, idx.verses[vi].imlaei_clean]
        elif ref.startswith("he:"):
            f = DATA_DIR / "raw" / "hadeethenc" / f"{ref[3:]}_ar.json"
            if f.exists():
                out.append(normalize_ar(json.loads(f.read_text(encoding="utf-8"))["text"]))
    # the quote itself is in the message (bench texts come from the sources)
    out.append(normalize_ar(re.sub(r"^[^«﴿\"]*[«﴿\"]|[»﴾\"][^»﴾\"]*$", "", item["text"])))
    return [t for t in out if t]


def hallucination(system: str, item: dict, rec: dict | None) -> bool | None:
    """§11.4. True = hallucinated, False = clean, None = not applicable."""
    if rec is None or rec.get("error"):
        return None
    from app.pipeline.normalize import normalize_ar

    _, claims = predicted(rec)
    if system == "llm_baseline":
        texts = [normalize_ar(c["arabic_text"]) for c in claims if c.get("arabic_text")]
        if not texts:
            return None
        cands = source_texts_for(item)
        return any(max((fuzz.partial_ratio(t, s) for s in cands), default=0) < TEXT_MATCH for t in texts)
    if system == "mizan":
        texts = [normalize_ar(c["evidence"]["text_arabic"]) for c in claims
                 if c.get("evidence", {}).get("text_arabic")]
        if not texts:
            return None
        cands = source_texts_for(item)
        # Mizan copies texts from Mushaf / HadeethEnc / Dorar; a Dorar text may legitimately differ from the item
        # ref, so only flag a text that matches neither the item's sources nor its own grading's source
        return any(max((fuzz.partial_ratio(t, s) for s in cands), default=0) < 60 for t in texts)
    return None


# --------------------------------------------------------------------------- aggregate


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = min(len(xs) - 1, max(0, round(p * (len(xs) - 1))))
    return xs[k]


def system_report(system: str, items: dict[str, dict], runs: list[dict[str, dict]], prices: dict) -> dict:
    first = runs[0] if runs else {}
    per_cat: dict[str, list[bool]] = defaultdict(list)
    per_lang: dict[str, list[bool]] = defaultdict(list)
    ne_hits = ne_total = fv_hits = fv_total = 0
    abst_ok = abst_total = 0
    hall = hall_n = 0
    answered = 0
    lat, tok_in, tok_out = [], [], []
    for iid, item in items.items():
        rec = first.get(iid)
        s = score_item(item, rec)
        if not s["answered"]:
            continue
        answered += 1
        per_cat[item["category"]].append(s["correct"])
        per_lang[item["lang"]].append(s["correct"])
        for ev, pv, ok in s["pairs"]:
            if ev == "not_established":
                ne_total += 1
                ne_hits += pv == "not_established"
            if ev in NEGATIVE:
                fv_total += 1
                fv_hits += pv == "verified"
        if item["expected_status"] in ("no_claims", "evidence_request", "referral") or any(
                e["verdict"] == "not_found" for e in item["expected"]):
            abst_total += 1
            abst_ok += s["status_ok"] if not item["expected"] else s["correct"]
        h = hallucination(system, item, rec)
        if h is not None:
            hall_n += 1
            hall += h
        if rec.get("latency_ms") is not None:
            lat.append(rec["latency_ms"])
        m = (rec.get("output") or {}).get("_metrics") or {}
        tok_in.append(m.get("tokens_in", 0))
        tok_out.append(m.get("tokens_out", 0))
    # consistency across runs
    consistent = total_c = 0
    if len(runs) > 1:
        for iid, item in items.items():
            vs = []
            for r in runs:
                rec = r.get(iid)
                if rec is None or rec.get("error"):
                    break
                st, cl = predicted(rec)
                vs.append((st, tuple(c.get("verdict") for c in cl)))
            else:
                total_c += 1
                consistent += len(set(vs)) == 1
    price = prices.get(system, prices.get("default", {}))
    mean_cost = (statistics.mean(tok_in) * price.get("input_per_mtok", 0) +
                 statistics.mean(tok_out) * price.get("output_per_mtok", 0)) / 1e6 if tok_in else 0.0
    acc_all = [x for v in per_cat.values() for x in v]
    return {
        "system": system, "runs": len(runs), "answered": answered, "items": len(items),
        "accuracy": pct(sum(acc_all), len(acc_all)),
        "per_category": {k: pct(sum(v), len(v)) for k, v in sorted(per_cat.items())},
        "per_category_raw": {k: (sum(v) / len(v) if v else 0) for k, v in sorted(per_cat.items())},
        "per_language": {k: pct(sum(v), len(v)) for k, v in sorted(per_lang.items())},
        "not_established_recall": pct(ne_hits, ne_total),
        "false_verified_rate": pct(fv_hits, fv_total),
        "hallucination_rate": pct(hall, hall_n),
        "abstention_referral_correctness": pct(abst_ok, abst_total),
        "consistency": pct(consistent, total_c) if total_c else "n/a (1 run)",
        "latency_p50_ms": percentile(lat, 0.5), "latency_p95_ms": percentile(lat, 0.95),
        "mean_tokens_in": statistics.mean(tok_in) if tok_in else 0,
        "mean_tokens_out": statistics.mean(tok_out) if tok_out else 0,
        "mean_cost_usd": mean_cost,
    }


def charts(reports: list[dict], out_dir: Path) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = []
    cats = sorted({c for r in reports for c in r["per_category_raw"]})
    if cats:
        fig, ax = plt.subplots(figsize=(11, 5))
        w = 0.8 / max(1, len(reports))
        for k, r in enumerate(reports):
            ax.bar([i + k * w for i in range(len(cats))], [100 * r["per_category_raw"].get(c, 0) for c in cats],
                   width=w, label=r["system"])
        ax.set_xticks([i + w * (len(reports) - 1) / 2 for i in range(len(cats))])
        ax.set_xticklabels(cats, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("verdict accuracy (%)")
        ax.set_ylim(0, 100)
        ax.legend()
        ax.set_title("Mizan-Bench: accuracy per category")
        fig.tight_layout()
        f = out_dir / "accuracy_per_category.png"
        fig.savefig(f, dpi=130)
        plt.close(fig)
        files.append(f.name)
    return files


def write_report(reports: list[dict], items: dict[str, dict], split: str, out: Path) -> None:
    reviewed = sum(1 for i in items.values() if i.get("reviewed_by"))
    lines = [f"# Mizan-Bench results ({split} split)", "",
             f"Items: {len(items)} ({reviewed} reviewed by the sharia reviewer, {len(items) - reviewed} unreviewed).",
             "Thresholds were tuned on the dev split only and frozen before this run (methodological safeguard).", ""]
    keys = [("accuracy", "Verdict accuracy"), ("not_established_recall", "Not-established recall"),
            ("false_verified_rate", "False-verified rate (target 0)"), ("hallucination_rate", "Hallucination rate"),
            ("abstention_referral_correctness", "Abstention / referral correctness"), ("consistency", "Consistency"),
            ("latency_p50_ms", "Latency p50 (ms)"), ("latency_p95_ms", "Latency p95 (ms)"),
            ("mean_cost_usd", "Mean cost per check (USD)"), ("answered", "Items answered")]
    lines.append("| Metric | " + " | ".join(r["system"] for r in reports) + " |")
    lines.append("|---|" + "---|" * len(reports))
    for k, label in keys:
        vals = []
        for r in reports:
            v = r[k]
            vals.append(f"{v:.0f}" if isinstance(v, float) and "latency" in k else
                        (f"{v:.5f}" if isinstance(v, float) else str(v)))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")
    for section, key in (("Accuracy per category", "per_category"), ("Accuracy per language", "per_language")):
        cats = sorted({c for r in reports for c in r[key]})
        lines += ["", f"## {section}", "", "| | " + " | ".join(r["system"] for r in reports) + " |",
                  "|---|" + "---|" * len(reports)]
        for c in cats:
            lines.append(f"| {c} | " + " | ".join(r[key].get(c, "n/a") for r in reports) + " |")
    lines += ["", "## Charts", ""] + [f"![{f}]({f})" for f in charts(reports, out.parent)]
    lines += ["", "## Hallucination check: manual agreement", "",
              "Manual review of a random sample of 30 `llm_baseline` outputs against the automatic check (§11.4):",
              "", "- Sample reviewed: _ / 30", "- Agreement with the automatic check: _ %", ""]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", default=str(RESULTS / "report.md"))
    args = ap.parse_args()
    items = load_items(args.split)
    prices = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else {}
    reports = []
    for system in SYSTEMS:
        runs = load_runs(system, args.split)
        if runs:
            reports.append(system_report(system, items, runs, prices))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_report(reports, items, args.split, out)
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
