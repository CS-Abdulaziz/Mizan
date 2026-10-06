"""Collect one real example per verdict and per message status from Mizan's bench outputs (TASKS B26).

    python scripts/verdict_examples.py > docs/VERDICT_EXAMPLES.md

Inputs are bench items (built from sources) whose recorded Mizan output had that verdict / status and matched the
expected one where possible. Examples that no bench item produced are listed from live checks in EXTRA.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERDICTS = ["verified", "misquoted", "not_established", "disputed", "not_found", "needs_review"]
STATUSES = ["ok", "no_claims", "evidence_request", "referral"]
# Live checks run on 2026-10-06 for outcomes no bench item produced (inputs from source data / plain requests).
EXTRA = {
    "needs_review": ("قال رسول الله ﷺ: «اهجُهُمْ فوالذي نفسُ محمدٍ بيدِه لهو أشدُّ عليهم من النَّبلِ»",
                     "Dorar dorar:37b426787c73; its only grading «غريب» (تخريج الكشاف) is unclassified -> needs_review"),
    "evidence_request": ("أعطني حديثًا يثبت أن الصدقة تطيل العمر", "plain request (no quote) -> evidence_request"),
}


def main() -> int:
    items = {json.loads(x)["id"]: json.loads(x) for x in (ROOT / "bench" / "items.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()}
    found_v: dict[str, tuple] = {}
    found_s: dict[str, tuple] = {}
    for f in sorted(glob.glob(str(ROOT / "bench" / "results" / "mizan-*.jsonl"))):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            it, out = items.get(r["id"]), r.get("output") or {}
            if not it or r.get("error"):
                continue
            exp = {e["verdict"] for e in it["expected"]}
            for c in out.get("claims", []):
                v = c["verdict"]
                if v not in found_v or (v in exp and found_v[v][2] is False):
                    found_v[v] = (it, c, v in exp)
            st = out.get("status")
            if st not in found_s or (st == it["expected_status"] and found_s[st][1] is False):
                found_s[st] = (it, st == it["expected_status"])
    print("# Real examples of every verdict and status\n")
    print("Each input below went through the full pipeline (bench outputs in `bench/results/`, or a live check).\n")
    print("| Outcome | Input (from sources) | Mizan output | Matches the bench expectation? | Source of the input |")
    print("|---|---|---|---|---|")
    for v in VERDICTS:
        if v in found_v:
            it, c, ok = found_v[v]
            ev = c.get("evidence") or {}
            where = ", ".join(f"{x['surah']}:{x['ayah']}" for x in ev.get("locations", [])) or ev.get("source") or ""
            diff = (c.get("diff") or {}).get("kind")
            out = f"`{v}`" + (f" ({diff})" if diff else "") + (f" - {where}" if where else "")
            exp = ", ".join(e["verdict"] for e in it["expected"])
            print(f"| verdict `{v}` | {it['text'][:160]} | {out} | {'yes' if ok else 'no (expected ' + exp + ')'} | "
                  f"{it['provenance'][:90]} |")
        elif v in EXTRA:
            print(f"| verdict `{v}` | {EXTRA[v][0]} | `{v}` | live check | {EXTRA[v][1]} |")
    for s in STATUSES:
        if s in found_s:
            it, ok = found_s[s]
            print(f"| status `{s}` | {it['text'][:160]} | `{s}` | {'yes' if ok else 'no (expected ' + it['expected_status'] + ')'} | "
                  f"{it['provenance'][:90]} |")
        elif s in EXTRA:
            print(f"| status `{s}` | {EXTRA[s][0]} | `{s}` | live check | {EXTRA[s][1]} |")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())
