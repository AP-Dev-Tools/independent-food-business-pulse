#!/usr/bin/env python3
"""
FHRS Data Processor (mail-merge ready + lean dashboard)
- Parses latest FHRS XML in fhrs_data/<YYYY-MM-DD>/
- Appends *newly-seen* businesses to data/cumulative_new_businesses.csv
  with full fields for mail merge (name, address lines, postcode, rating, etc.)
- Writes tiny counts-only history to data/dashboard_data.json (for the dashboard)
- Writes a small latest summary to data/latest_snapshot.json
"""

from pathlib import Path
from datetime import datetime
import csv
import json
import xml.etree.ElementTree as ET

# ----------------------------
# Helpers
# ----------------------------

def latest_data_dir(base="fhrs_data") -> Path:
    root = Path(base)
    if not root.exists():
        raise FileNotFoundError("No fhrs_data/ folder found. Run the downloader first.")
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError("fhrs_data/ has no dated subfolders.")
    return sorted(dirs)[-1]  # YYYY-MM-DD so lexical max works

def txt(elem, tag):
    v = elem.findtext(tag)
    return v.strip() if v else ""

def read_seen_ids_from_csv(csv_path: Path) -> set:
    seen = set()
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                fid = row.get("FHRSID")
                if fid:
                    seen.add(fid)
    return seen

MAILMERGE_FIELDS = [
    "date_added", "FHRSID", "BusinessName", "BusinessType",
    "AddressLine1", "AddressLine2", "AddressLine3", "AddressLine4",
    "PostCode", "LocalAuthorityName",
    "RatingValue", "RatingDate",
    "SchemeType", "NewRatingPending",
    "Latitude", "Longitude",
    "AddressSingleLine"  # handy combined address
]

def append_new_businesses(csv_path: Path, new_rows: list[dict]):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAILMERGE_FIELDS)
        if is_new_file:
            w.writeheader()
        for row in new_rows:
            w.writerow(row)

def parse_establishments(xml_file: Path) -> list[dict]:
    out = []
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except Exception:
        return out  # skip bad file quietly

    for e in root.findall(".//EstablishmentDetail"):
        # Core
        fhrs_id   = txt(e, "FHRSID")
        name      = txt(e, "BusinessName")
        btype     = txt(e, "BusinessType")
        la_name   = txt(e, "LocalAuthorityName")
        pc        = txt(e, "PostCode")
        rating    = txt(e, "RatingValue")
        rdate     = txt(e, "RatingDate")
        scheme    = txt(e, "SchemeType")
        pending   = txt(e, "NewRatingPending")

        # Address lines (many LAs use up to 4)
        a1 = txt(e, "AddressLine1")
        a2 = txt(e, "AddressLine2")
        a3 = txt(e, "AddressLine3")
        a4 = txt(e, "AddressLine4")

        # Geocode (optional in XML)
        lat = ""
        lon = ""
        geo = e.find("Geocode")
        if geo is not None:
            lat = txt(geo, "Latitude")
            lon = txt(geo, "Longitude")

        # Combined single-line address for mail merges/labels
        parts = [p for p in [a1, a2, a3, a4, pc] if p]
        single_line = ", ".join(parts)

        out.append({
            "FHRSID": fhrs_id,
            "BusinessName": name,
            "BusinessType": btype,
            "AddressLine1": a1,
            "AddressLine2": a2,
            "AddressLine3": a3,
            "AddressLine4": a4,
            "PostCode": pc,
            "LocalAuthorityName": la_name,
            "RatingValue": rating,
            "RatingDate": rdate,
            "SchemeType": scheme,
            "NewRatingPending": pending,
            "Latitude": lat,
            "Longitude": lon,
            "AddressSingleLine": single_line,
        })
    return out

def parse_folder(data_dir: Path) -> list[dict]:
    businesses = []
    for xml in sorted(data_dir.glob("*.xml")):
        businesses.extend(parse_establishments(xml))
    return businesses

def sector_of(b: dict) -> str:
    bt = (b.get("BusinessType") or "").lower()
    nm = (b.get("BusinessName") or "").lower()
    if "mobile" in bt or "mobile" in nm: return "MOBILE"
    if any(k in bt for k in ["restaurant", "cafe", "café", "coffee"]): return "RESTAURANT/CAFE"
    if "take" in bt: return "TAKEAWAY"
    if any(k in bt for k in ["pub", "bar"]): return "PUB/BAR"
    if "hotel" in bt: return "HOTEL"
    return "OTHER"

def counts_summary(biz: list[dict]) -> dict:
    counts = {"total": len(biz), "MOBILE":0, "RESTAURANT/CAFE":0, "TAKEAWAY":0, "PUB/BAR":0, "HOTEL":0, "OTHER":0}
    for b in biz:
        counts[sector_of(b)] += 1
    return counts

def load_counts_history(path: Path) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def upsert_counts_history(path: Path, date_str: str, counts: dict):
    hist = load_counts_history(path)
    if hist and hist[-1].get("date") == date_str:
        hist[-1]["counts"] = counts
    else:
        hist.append({"date": date_str, "counts": counts})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

# ----------------------------
# Main
# ----------------------------

def main():
    today_dir = latest_data_dir()
    run_date = today_dir.name  # YYYY-MM-DD
    print(f"Processing: {today_dir}")

    businesses = parse_folder(today_dir)
    print(f"Parsed {len(businesses):,} establishments")

    data_dir = Path("data"); data_dir.mkdir(parents=True, exist_ok=True)
    cum_csv = data_dir / "cumulative_new_businesses.csv"
    seen = read_seen_ids_from_csv(cum_csv)

    new_rows = []
    for b in businesses:
        fid = b.get("FHRSID")
        if fid and fid not in seen:
            seen.add(fid)
            row = {"date_added": run_date, **b}
            new_rows.append(row)

    if new_rows:
        append_new_businesses(cum_csv, new_rows)
        print(f"New businesses this run: {len(new_rows):,}")
    else:
        print("No new businesses this run (vs cumulative list).")

    # Lean dashboard outputs
    counts = counts_summary(businesses)
    latest_summary = {"date": run_date, "counts": counts, "new_businesses_this_run": len(new_rows)}
    (data_dir / "latest_snapshot.json").write_text(
        json.dumps(latest_summary, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8"
    )
    upsert_counts_history(data_dir / "dashboard_data.json", run_date, counts)

    print("Done.")
    print(f"- {cum_csv.resolve()}")
    print(f"- {(data_dir/'dashboard_data.json').resolve()}")
    print(f"- {(data_dir/'latest_snapshot.json').resolve()}")

if __name__ == "__main__":
    main()
