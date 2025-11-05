#!/usr/bin/env python3
import json, os, sys
from datetime import date

CUR_PATH  = "data/la_totals_last.json"      # written by process_fhrs_data.py
PREV_PATH = "data/__prev_la_totals.json"    # saved earlier in the workflow
OUT_LATEST = "data/la_deltas_latest.json"
OUT_DATED  = f"data/la_deltas_{date.today().isoformat()}.json"

# Only tracked sectors - no OTHER
SECTORS = ["MOBILE","RESTAURANT_CAFE","PUB_BAR","TAKEAWAY","HOTEL"]

def load(path):
    if not os.path.exists(path): return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize(d):
    """
    Accept either shape:
      A) { "LA": {"MOBILE":n, "RESTAURANT_CAFE":m, ...}, ... }
      B) { "MOBILE": {"LA":n,...}, "RESTAURANT_CAFE": {"LA":m,...}, ... }
    Return shape A.
    """
    if not d: return {}
    if set(d.keys()) & set(SECTORS):  # looks like shape B
        out = {}
        for s in SECTORS:
            for la, v in (d.get(s) or {}).items():
                out.setdefault(la, {})[s] = int(v or 0)
        return out
    return d

def empty_scaffold():
    return {
        "date": date.today().isoformat(),
        "by_sector": { s: {"growth": [], "reductions": []} for s in SECTORS }
    }

def main():
    os.makedirs("data", exist_ok=True)

    cur_raw  = load(CUR_PATH)
    prev_raw = load(PREV_PATH) or {}

    if not cur_raw:
        out = empty_scaffold()
        with open(OUT_LATEST, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[warn] Missing {CUR_PATH}; wrote empty scaffold.")
        return

    cur  = normalize(cur_raw)
    prev = normalize(prev_raw)

    by_sector = {}
    for s in SECTORS:
        growth, reductions = [], []
        all_las = set(cur.keys()) | set(prev.keys())
        for la in all_las:
            cv = int((cur.get(la) or {}).get(s, 0))
            pv = int((prev.get(la) or {}).get(s, 0))
            delta = cv - pv
            if delta > 0:
                growth.append({"la": la, "delta": delta, "current": cv})
            elif delta < 0:
                reductions.append({"la": la, "delta": delta, "current": cv})
        growth.sort(key=lambda x: x["delta"], reverse=True)
        reductions.sort(key=lambda x: x["delta"])  # most negative first
        by_sector[s] = {"growth": growth[:10], "reductions": reductions[:10]}

    out = {"date": date.today().isoformat(), "by_sector": by_sector}
    with open(OUT_LATEST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    with open(OUT_DATED, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"[ok] Wrote {OUT_LATEST} and {OUT_DATED}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)
