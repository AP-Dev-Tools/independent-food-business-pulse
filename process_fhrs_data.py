#!/usr/bin/env python3
"""
FHRS Processor (per-type monthly CSVs + lean dashboard)
- Parses latest FHRS XML in fhrs_data/<YYYY-MM-DD>/
- Appends newly-seen businesses into data/cumulative/<TYPE>/<YYYY-MM>.csv
- Keeps a global dedupe (FHRSID) across ALL types
- Writes tiny dashboard files: data/dashboard_data.json, data/latest_snapshot.json
"""

from pathlib import Path
import csv, json
import xml.etree.ElementTree as ET

MAILMERGE_FIELDS = [
    "date_added","FHRSID","BusinessName","BusinessType",
    "AddressLine1","AddressLine2","AddressLine3","AddressLine4",
    "PostCode","LocalAuthorityName",
    "RatingValue","RatingDate","SchemeType","NewRatingPending",
    "Latitude","Longitude","AddressSingleLine"
]

# ---------- helpers ----------
def latest_data_dir(base="fhrs_data") -> Path:
    root = Path(base); dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs: raise FileNotFoundError("Run the downloader first.")
    return sorted(dirs)[-1]  # YYYY-MM-DD

def txt(e, tag): 
    v = e.findtext(tag); return v.strip() if v else ""

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
    for xml in sorted(data_dir.glob("*.xml")):
        try:
            root = ET.parse(xml).getroot()
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
                "Latitude": "", "Longitude": "",
            }
            geo = e.find("Geocode")
            if geo is not None:
                b["Latitude"] = txt(geo,"Latitude")
                b["Longitude"] = txt(geo,"Longitude")
            parts = [b["AddressLine1"],b["AddressLine2"],b["AddressLine3"],b["AddressLine4"],b["PostCode"]]
            b["AddressSingleLine"] = ", ".join([p for p in parts if p])
            out.append(b)
    return out

def counts_summary(biz: list[dict]) -> dict:
    counts = {"total": len(biz), "MOBILE":0,"RESTAURANT_CAFE":0,"TAKEAWAY":0,"PUB_BAR":0,"HOTEL":0,"OTHER":0}
    for b in biz: counts[sector_of(b)] += 1
    return counts

def load_counts_history(path: Path) -> list[dict]:
    if path.exists():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: return []
    return []

def upsert_counts_history(path: Path, date_str: str, counts: dict):
    hist = load_counts_history(path)
    if hist and hist[-1].get("date")==date_str: hist[-1]["counts"]=counts
    else: hist.append({"date":date_str,"counts":counts})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, separators=(",",":"), ensure_ascii=False), encoding="utf-8")

def read_seen_ids(cum_root: Path) -> set:
    seen = set()
    if not cum_root.exists(): return seen
    for csv_file in cum_root.glob("*/*.csv"):
        try:
            with csv_file.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    fid = row.get("FHRSID")
                    if fid: seen.add(fid)
        except Exception:
            continue
    return seen

def append_rows(csv_path: Path, rows: list[dict]):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAILMERGE_FIELDS)
        if new_file: w.writeheader()
        w.writerows(rows)

# ---------- main ----------
def main():
    today_dir = latest_data_dir()
    run_date = today_dir.name           # YYYY-MM-DD
    run_month = run_date[:7]            # YYYY-MM
    businesses = parse_folder(today_dir)
    print(f"Parsed {len(businesses):,} establishments")

    data_dir = Path("data"); data_dir.mkdir(parents=True, exist_ok=True)
    cum_root = data_dir / "cumulative"; cum_root.mkdir(parents=True, exist_ok=True)

    # global dedupe across all prior type/month CSVs
    seen = read_seen_ids(cum_root)

    # bucket new businesses per type
    buckets = {}  # type -> list[dict]
    new_count = 0
    for b in businesses:
        fid = b.get("FHRSID")
        if not fid or fid in seen: continue
        seen.add(fid)
        row = {"date_added": run_date, **b}
        t = sector_of(b)
        buckets.setdefault(t, []).append(row)
        new_count += 1

    # write per-type monthly CSVs
    for t, rows in buckets.items():
        month_csv = cum_root / t / f"{run_month}.csv"
        append_rows(month_csv, rows)
        print(f"  + {len(rows):,} new → {month_csv}")

    # tiny dashboard files
    counts = counts_summary(businesses)
    (data_dir/"latest_snapshot.json").write_text(
        json.dumps({"date":run_date,"counts":counts,"new_businesses_this_run":new_count},
                   separators=(",",":"), ensure_ascii=False),
        encoding="utf-8"
    )
    upsert_counts_history(data_dir/"dashboard_data.json", run_date, counts)

    # index files (useful for downloads)
    index = {}
    for t_dir in sorted(cum_root.iterdir()):
        if t_dir.is_dir():
            index[t_dir.name] = [p.name for p in sorted(t_dir.glob("*.csv"))]
    (data_dir/"cumulative_index.json").write_text(
        json.dumps(index, separators=(",",":"), ensure_ascii=False), encoding="utf-8"
    )
    print("Done.")

if __name__ == "__main__":
    main()
