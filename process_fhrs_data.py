#!/usr/bin/env python3
"""
FHRS processor:
- Baseline of seen FHRSIDs (data/seen_ids.txt.gz) so monthly CSVs only contain NEW businesses since last run
- Per-type monthly CSVs: data/cumulative/<TYPE>/<YYYY-MM>.csv
- Dashboard counts history: data/dashboard_data.json (+ data/latest_snapshot.json)
- NEW: Top 10 Growth/Reductions by Local Authority per sector:
    * writes data/la_deltas_<YYYY-MM-DD>.json
    * writes data/la_deltas_latest.json (symlink copy for the dashboard)
    * persists previous totals in data/la_totals_last.json for next-run comparisons
"""

from pathlib import Path
import csv, json, gzip
import xml.etree.ElementTree as ET

MAILMERGE_FIELDS = [
    "date_added","FHRSID","BusinessName","BusinessType",
    "AddressLine1","AddressLine2","AddressLine3","AddressLine4",
    "PostCode","LocalAuthorityName","RatingValue","RatingDate",
    "SchemeType","NewRatingPending","Latitude","Longitude","AddressSingleLine"
]

# ------------ helpers ------------

def latest_data_dir(base="fhrs_data") -> Path:
    root = Path(base)
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError("No fhrs_data/ folder with dated subfolders. Run the downloader first.")
    return sorted(dirs)[-1]  # YYYY-MM-DD folder

def txt(e, tag):
    v = e.findtext(tag)
    return v.strip() if v else ""

def sector_of(b: dict) -> str:
    bt = (b.get("BusinessType") or "").lower()
    nm = (b.get("BusinessName") or "").lower()
    if "mobile" in bt or "mobile" in nm: return "MOBILE"
    if any(k in bt for k in ["restaurant","cafe","café","coffee"]): return "RESTAURANT_CAFE"
    if "take" in bt: return "TAKEAWAY"
    if any(k in bt for k in ["pub","bar"]): return "PUB_BAR"
    if "hotel" in bt: return "HOTEL"
    return "OTHER"

def parse_folder(data_dir: Path) -> list[dict]:
    out = []
    for xmlp in sorted(data_dir.glob("*.xml")):
        try:
            root = ET.parse(xmlp).getroot()
        except Exception:
            continue
        for e in root.findall(".//EstablishmentDetail"):
            b = {
                "FHRSID": txt(e,"FHRSID"),
                "BusinessName": txt(e,"BusinessName"),
                "BusinessType": txt(e,"BusinessType"),
                "AddressLine1": txt(e,"AddressLine1"),
                "AddressLine2": txt(e,"AddressLine2"),
                "AddressLine3": txt(e,"AddressLine3"),
                "AddressLine4": txt(e,"AddressLine4"),
                "PostCode": txt(e,"PostCode"),
                "LocalAuthorityName": txt(e,"LocalAuthorityName"),
                "RatingValue": txt(e,"RatingValue"),
                "RatingDate": txt(e,"RatingDate"),
                "SchemeType": txt(e,"SchemeType"),
                "NewRatingPending": txt(e,"NewRatingPending"),
                "Latitude": "", "Longitude": ""
            }
            geo = e.find("Geocode")
            if geo is not None:
                b["Latitude"] = txt(geo,"Latitude")
                b["Longitude"] = txt(geo,"Longitude")
            parts = [b["AddressLine1"], b["AddressLine2"], b["AddressLine3"], b["AddressLine4"], b["PostCode"]]
            b["AddressSingleLine"] = ", ".join([p for p in parts if p])
            out.append(b)
    return out

def counts_summary(biz: list[dict]) -> dict:
    c = {"total": len(biz), "MOBILE":0, "RESTAURANT_CAFE":0, "TAKEAWAY":0, "PUB_BAR":0, "HOTEL":0, "OTHER":0}
    for b in biz:
        c[sector_of(b)] += 1
    return c

def upsert_counts_history(path: Path, date_str: str, counts: dict):
    hist = []
    if path.exists():
        try:
            hist = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            hist = []
    if hist and hist[-1].get("date") == date_str:
        hist[-1]["counts"] = counts
    else:
        hist.append({"date": date_str, "counts": counts})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

def load_seen_ids(path: Path) -> set[str]:
    if not path.exists(): return set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_seen_ids(path: Path, ids: set[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for i in sorted(ids):
            f.write(i + "\n")

def append_rows(csv_path: Path, rows: list[dict]):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAILMERGE_FIELDS)
        if new_file: w.writeheader()
        w.writerows(rows)

# --- LA totals & deltas ---

SECTORS = ["MOBILE","RESTAURANT_CAFE","TAKEAWAY","PUB_BAR","HOTEL","OTHER"]

def la_totals(businesses: list[dict]) -> dict:
    """
    Returns: { LA: { "total": N, "MOBILE": n1, "RESTAURANT_CAFE": n2, ... } }
    """
    out = {}
    for b in businesses:
        la = (b.get("LocalAuthorityName") or "").strip() or "UNKNOWN"
        t = sector_of(b)
        d = out.setdefault(la, {"total": 0, **{s:0 for s in SECTORS}})
        d["total"] += 1
        d[t] += 1
    return out

def compute_deltas(prev: dict, curr: dict) -> dict:
    """
    Build per-sector top 10 growth and reductions by LA.
    Returns:
      {
        "date": "YYYY-MM-DD",
        "by_sector": {
          "MOBILE": { "growth": [{la, delta, current}], "reductions": [...] },
          ...
        }
      }
    """
    by_sector = {}
    las = set(prev.keys()) | set(curr.keys())
    for s in SECTORS:
        rows = []
        for la in las:
            p = prev.get(la, {})
            c = curr.get(la, {})
            pv = int(p.get(s, 0))
            cv = int(c.get(s, 0))
            dv = cv - pv
            if dv != 0:
                rows.append({"la": la, "delta": dv, "current": cv})
        growth = sorted([r for r in rows if r["delta"] > 0], key=lambda x: x["delta"], reverse=True)[:10]
        reductions = sorted([r for r in rows if r["delta"] < 0], key=lambda x: x["delta"])[:10]
        by_sector[s] = {"growth": growth, "reductions": reductions}
    return by_sector

# ------------ main ------------

def main():
    today_dir = latest_data_dir()
    run_date = today_dir.name            # YYYY-MM-DD
    run_month = run_date[:7]             # YYYY-MM

    businesses = parse_folder(today_dir)
    print(f"Parsed {len(businesses):,} establishments")

    data_dir = Path("data"); data_dir.mkdir(parents=True, exist_ok=True)
    cum_root = data_dir / "cumulative"; cum_root.mkdir(parents=True, exist_ok=True)

    # --- baseline for "new businesses" CSVs
    seen_path = data_dir / "seen_ids.txt.gz"
    seen = load_seen_ids(seen_path)
    first_run = (len(seen) == 0)

    new_rows_by_type = {}
    new_count = 0
    for b in businesses:
        fid = b.get("FHRSID")
        if not fid: continue
        if fid not in seen:
            if not first_run:  # only record as "new" after baseline exists
                t = sector_of(b)
                new_rows_by_type.setdefault(t, []).append({"date_added": run_date, **b})
                new_count += 1
            seen.add(fid)

    for t, rows in new_rows_by_type.items():
        out_csv = cum_root / t / f"{run_month}.csv"
        append_rows(out_csv, rows)
        print(f"+ {len(rows):,} new → {out_csv}")

    save_seen_ids(seen_path, seen)

    # --- dashboard counts
    counts = counts_summary(businesses)
    (data_dir / "latest_snapshot.json").write_text(
        json.dumps({"date": run_date, "counts": counts, "new_businesses_this_run": new_count},
                   separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8"
    )
    upsert_counts_history(data_dir / "dashboard_data.json", run_date, counts)

    # --- LA totals & deltas (for Top 10 sections)
    curr_totals = la_totals(businesses)
    prev_totals_path = data_dir / "la_totals_last.json"
    prev_totals = {}
    if prev_totals_path.exists():
        try:
            prev_totals = json.loads(prev_totals_path.read_text(encoding="utf-8"))
        except Exception:
            prev_totals = {}

    deltas_payload = {
        "date": run_date,
        "by_sector": compute_deltas(prev_totals, curr_totals)
    }

    # Write deltas (date-stamped + latest)
    deltas_file = data_dir / f"la_deltas_{run_date}.json"
    deltas_latest = data_dir / "la_deltas_latest.json"
    for p, payload in [(deltas_file, deltas_payload), (deltas_latest, deltas_payload)]:
        p.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # Persist current totals for next comparison
    prev_totals_path.write_text(json.dumps(curr_totals, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    print("Done.")
    if first_run:
        print("Seeded baseline (no new-business CSVs on first run).")
    else:
        print(f"New businesses this run: {new_count:,}")
    print(f"Wrote LA deltas: {deltas_file.name} and la_deltas_latest.json")

if __name__ == "__main__":
    main()
