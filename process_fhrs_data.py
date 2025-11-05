#!/usr/bin/env python3
import os, re, json, gzip, csv
from datetime import datetime
from xml.etree import ElementTree as ET
from collections import defaultdict, Counter

# --- Flexible roots to search for FHRS XML drops ---
SEARCH_ROOTS = [
    "data/raw",
    "data/fhrs",
    "data/downloads",
    "data/xml",
    "data",          # fallback
]

# Sector mapping (FHRS BusinessType -> our sector keys)
# NOTE: We only track specific business types, not "Other" to save space
BTYPE_TO_SECTOR = {
    "Mobile caterer":                       "MOBILE",
    "Restaurant/Cafe/Canteen":             "RESTAURANT_CAFE",
    "Pub/bar/nightclub":                   "PUB_BAR",
    "Takeaway/sandwich shop":              "TAKEAWAY",
    "Hotel/bed & breakfast/guest house":   "HOTEL",
}
SECTORS = ["MOBILE","RESTAURANT_CAFE","PUB_BAR","TAKEAWAY","HOTEL"]  # No OTHER - we don't track it

# Output paths
OUT_DASHBOARD = "data/dashboard_data.json"
OUT_LATEST    = "data/latest_snapshot.json"
OUT_LA_LAST   = "data/la_totals_last.json"      # consumed by workflow delta step
OUT_LA_CURR   = "data/la_totals_current.json"   # for inspection
OUT_SEEN      = "data/seen_ids.txt.gz"
OUT_CSV_DIR   = "data/cumulative"               # Only tracked sectors (no OTHER)
OUT_INDEX     = "data/cumulative_index.json"
OUT_SNAPSHOTS = "data/snapshots"                # Daily snapshot counts (lightweight)

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# CSV columns for new businesses
CSV_COLUMNS = [
    "date_added", "FHRSID", "BusinessName", "BusinessType", 
    "AddressLine1", "AddressLine2", "AddressLine3", "AddressLine4", 
    "PostCode", "LocalAuthorityName", "RatingValue", "RatingDate",
    "SchemeType", "NewRatingPending", "Latitude", "Longitude", "AddressSingleLine"
]

def iter_xml_files(base: str):
    for dirpath, _, files in os.walk(base):
        for fn in files:
            if fn.lower().endswith(".xml"):
                yield os.path.join(dirpath, fn)

def find_best_xml_dir() -> tuple[str, list[str]]:
    """
    Pick the most likely directory to process:
    - Prefer a root that exists and contains XMLs.
    - If it has YYYY-MM-DD subfolders, choose the latest by folder name.
    - Else use the directory in that root that contains the most XML files.
    Returns (chosen_dir, xml_file_list).
    """
    best_dir, best_files = None, []

    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue

        # Case 1: dated subfolders
        dated = [d for d in os.listdir(root)
                 if DATE_DIR_RE.match(d) and os.path.isdir(os.path.join(root, d))]
        if dated:
            latest = os.path.join(root, sorted(dated)[-1])
            files = list(iter_xml_files(latest))
            if files:
                return latest, files  # found a dated batch

        # Case 2: pick the subdir with most XMLs
        candidates = []
        for dirpath, _, files in os.walk(root):
            xmls = [f for f in files if f.lower().endswith(".xml")]
            if xmls:
                candidates.append((dirpath, len(xmls)))
        if candidates:
            # choose the dir with max XML count
            candidates.sort(key=lambda x: x[1], reverse=True)
            cand_dir = candidates[0][0]
            files = list(iter_xml_files(cand_dir))
            if len(files) > len(best_files):
                best_dir, best_files = cand_dir, files

    return (best_dir, best_files)

def safe_text(elem, tag):
    x = elem.find(tag)
    return (x.text or "").strip() if x is not None else ""

def load_previous_seen_ids() -> set:
    """Load previously seen business IDs from gzipped file."""
    if not os.path.exists(OUT_SEEN):
        print("[info] No previous seen_ids file found - treating all as new")
        return set()
    
    try:
        with gzip.open(OUT_SEEN, "rt", encoding="utf-8") as f:
            ids = set(line.strip() for line in f if line.strip())
        print(f"[ok] Loaded {len(ids)} previously seen business IDs")
        return ids
    except Exception as e:
        print(f"[warn] Could not load previous IDs: {e}")
        return set()

def parse_snapshot(xml_files: list[str], previous_seen: set):
    """
    Returns:
      per_LA_totals: { "LA name": {"MOBILE":n,...,"HOTEL":m}, ... }
      national_counts: {"MOBILE":n,...,"HOTEL":m,"total":N}
      current_seen_ids: set of FHRSID strings
      new_businesses: list of dicts with full business details
    """
    per_LA = defaultdict(lambda: Counter({s:0 for s in SECTORS}))
    national = Counter({s:0 for s in SECTORS})
    current_seen_ids = set()
    new_businesses = []

    for path in xml_files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
            continue

        for est in root.iterfind(".//EstablishmentDetail"):
            fhrsid = safe_text(est, "FHRSID")
            if not fhrsid:
                continue
                
            btype = safe_text(est, "BusinessType")
            la_name = safe_text(est, "LocalAuthorityName")
            
            # Map to sector - if not in our tracked types, skip it entirely
            sector = BTYPE_TO_SECTOR.get(btype)
            if not sector:
                continue  # Skip OTHER - we don't track it
            
            per_LA[la_name][sector] += 1
            national[sector] += 1
            current_seen_ids.add(fhrsid)
            
            # Check if this is a NEW business
            if fhrsid not in previous_seen:
                # Build address single line
                addr_parts = [
                    safe_text(est, "AddressLine1"),
                    safe_text(est, "AddressLine2"),
                    safe_text(est, "AddressLine3"),
                    safe_text(est, "AddressLine4"),
                    safe_text(est, "PostCode")
                ]
                address_single = ", ".join(p for p in addr_parts if p)
                
                new_businesses.append({
                    "FHRSID": fhrsid,
                    "BusinessName": safe_text(est, "BusinessName"),
                    "BusinessType": btype,
                    "AddressLine1": safe_text(est, "AddressLine1"),
                    "AddressLine2": safe_text(est, "AddressLine2"),
                    "AddressLine3": safe_text(est, "AddressLine3"),
                    "AddressLine4": safe_text(est, "AddressLine4"),
                    "PostCode": safe_text(est, "PostCode"),
                    "LocalAuthorityName": la_name,
                    "RatingValue": safe_text(est, "RatingValue"),
                    "RatingDate": safe_text(est, "RatingDate"),
                    "SchemeType": safe_text(est, "SchemeType"),
                    "NewRatingPending": safe_text(est, "NewRatingPending"),
                    "Latitude": safe_text(est, "Geocode/Latitude"),
                    "Longitude": safe_text(est, "Geocode/Longitude"),
                    "AddressSingleLine": address_single,
                    "Sector": sector
                })

    national_total = sum(national[s] for s in SECTORS)
    national["total"] = national_total

    per_LA_out = {}
    for la, counts in per_LA.items():
        row = {s:int(counts.get(s,0)) for s in SECTORS}
        per_LA_out[la] = row

    national_out = {s:int(national.get(s,0)) for s in (SECTORS+["total"])}

    print(f"[ok] Found {len(new_businesses)} new businesses this run")
    return per_LA_out, national_out, current_seen_ids, new_businesses

def write_new_businesses_to_csv(new_businesses: list, snap_date: str):
    """
    Write new businesses to CSV files, organized by:
    - data/cumulative/{SECTOR}/{YYYY-MM}.csv
    
    Appends to existing file if it exists for this month.
    """
    if not new_businesses:
        print("[info] No new businesses to write to CSV")
        return
    
    # Group by sector
    by_sector = defaultdict(list)
    for biz in new_businesses:
        sector = biz.pop("Sector")  # Remove sector key, not in CSV
        biz["date_added"] = snap_date
        by_sector[sector].append(biz)
    
    # Track what we're writing for the index
    index_entry = {
        "date": snap_date,
        "files": {}
    }
    
    # Write each sector
    for sector, businesses in by_sector.items():
        # Create directory structure
        sector_dir = os.path.join(OUT_CSV_DIR, sector)
        os.makedirs(sector_dir, exist_ok=True)
        
        # Monthly file: YYYY-MM.csv
        year_month = snap_date[:7]  # "2025-11"
        csv_path = os.path.join(sector_dir, f"{year_month}.csv")
        
        # Check if file exists to determine if we need headers
        file_exists = os.path.exists(csv_path)
        
        # Append to file
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerows(businesses)
        
        count = len(businesses)
        index_entry["files"][sector] = {
            "file": f"{sector}/{year_month}.csv",
            "count": count
        }
        print(f"[ok] Wrote {count} new {sector} businesses to {csv_path}")
    
    # Update cumulative index
    update_cumulative_index(index_entry)

def update_cumulative_index(new_entry: dict):
    """
    Update or create the cumulative index file that tracks all CSV files.
    Format: { "snapshots": [ {"date": "2025-11-05", "files": {...}}, ... ] }
    """
    index_data = {"snapshots": []}
    
    if os.path.exists(OUT_INDEX):
        try:
            with open(OUT_INDEX, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception as e:
            print(f"[warn] Could not load index, creating new: {e}")
    
    # Remove any existing entry for this date
    index_data["snapshots"] = [
        s for s in index_data.get("snapshots", []) 
        if s.get("date") != new_entry["date"]
    ]
    
    # Add new entry
    index_data["snapshots"].append(new_entry)
    index_data["snapshots"].sort(key=lambda x: x.get("date", ""))
    
    # Write back
    with open(OUT_INDEX, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"[ok] Updated cumulative index: {OUT_INDEX}")

def update_monthly_snapshot(snap_date: str, national_counts: dict):
    """
    Update monthly snapshot file with today's counts.
    Creates lightweight files: data/snapshots/YYYY-MM.json
    Only stores counts, not business details.
    """
    os.makedirs(OUT_SNAPSHOTS, exist_ok=True)
    
    year_month = snap_date[:7]  # "2025-11"
    snapshot_file = os.path.join(OUT_SNAPSHOTS, f"{year_month}.json")
    
    # Load existing month data or create new
    month_data = {"month": year_month, "days": []}
    if os.path.exists(snapshot_file):
        try:
            with open(snapshot_file, "r", encoding="utf-8") as f:
                month_data = json.load(f)
        except Exception:
            pass
    
    # Remove existing entry for this date (in case of re-run)
    month_data["days"] = [
        d for d in month_data.get("days", []) 
        if d.get("date") != snap_date
    ]
    
    # Add today's counts
    day_entry = {
        "date": snap_date,
        "MOBILE": national_counts.get("MOBILE", 0),
        "RESTAURANT_CAFE": national_counts.get("RESTAURANT_CAFE", 0),
        "TAKEAWAY": national_counts.get("TAKEAWAY", 0),
        "PUB_BAR": national_counts.get("PUB_BAR", 0),
        "HOTEL": national_counts.get("HOTEL", 0),
        "total": national_counts.get("total", 0)
    }
    month_data["days"].append(day_entry)
    
    # Sort by date
    month_data["days"].sort(key=lambda x: x.get("date", ""))
    
    # Write back
    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(month_data, f, ensure_ascii=False, indent=2)
    
    print(f"[ok] Updated monthly snapshot: {snapshot_file}")

def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def infer_snapshot_date(chosen_dir: str) -> str:
    base = os.path.basename(chosen_dir.rstrip("/"))
    if DATE_DIR_RE.match(base):
        return base
    # If parent is a date, use that
    parent = os.path.basename(os.path.dirname(chosen_dir))
    if DATE_DIR_RE.match(parent):
        return parent
    # Fallback: today UTC
    return datetime.utcnow().strftime("%Y-%m-%d")

def main():
    print("="*70)
    print("FHRS DATA PROCESSOR")
    print("="*70)
    
    # Find XML files
    chosen_dir, files = find_best_xml_dir()
    if not chosen_dir or not files:
        raise FileNotFoundError(
            "No FHRS XML files were found under any of: "
            + ", ".join(SEARCH_ROOTS)
        )
    
    snap_date = infer_snapshot_date(chosen_dir)
    print(f"[ok] Processing snapshot date: {snap_date}")
    print(f"[ok] Found {len(files)} XML files in: {chosen_dir}")
    
    # Load previous seen IDs
    previous_seen = load_previous_seen_ids()
    
    # Parse current snapshot and identify new businesses
    per_LA_totals, national_counts, current_seen_ids, new_businesses = parse_snapshot(files, previous_seen)
    
    # Write new businesses to CSV files
    write_new_businesses_to_csv(new_businesses, snap_date)
    
    # Update monthly snapshot (lightweight daily counts)
    update_monthly_snapshot(snap_date, national_counts)
    
    # --- Write LA totals for delta step ---
    write_json(OUT_LA_LAST, per_LA_totals)
    write_json(OUT_LA_CURR, per_LA_totals)
    print(f"[ok] Wrote LA totals to {OUT_LA_LAST}")

    # --- Update dashboard series ---
    dashboard_series = read_json(OUT_DASHBOARD, [])
    dashboard_series = [row for row in dashboard_series if row.get("date") != snap_date]
    dashboard_series.append({
        "date": snap_date,
        "counts": {
            "total":           national_counts.get("total", 0),
            "MOBILE":          national_counts.get("MOBILE", 0),
            "RESTAURANT_CAFE": national_counts.get("RESTAURANT_CAFE", 0),
            "TAKEAWAY":        national_counts.get("TAKEAWAY", 0),
            "PUB_BAR":         national_counts.get("PUB_BAR", 0),
            "HOTEL":           national_counts.get("HOTEL", 0),
            # No OTHER - we don't track it
        }
    })
    dashboard_series.sort(key=lambda r: r.get("date",""))
    write_json(OUT_DASHBOARD, dashboard_series)
    print(f"[ok] Updated dashboard data: {OUT_DASHBOARD}")

    # --- Latest snapshot (national) ---
    write_json(OUT_LATEST, {
        "date": snap_date,
        "counts": {
            "total":           national_counts.get("total", 0),
            "MOBILE":          national_counts.get("MOBILE", 0),
            "RESTAURANT_CAFE": national_counts.get("RESTAURANT_CAFE", 0),
            "TAKEAWAY":        national_counts.get("TAKEAWAY", 0),
            "PUB_BAR":         national_counts.get("PUB_BAR", 0),
            "HOTEL":           national_counts.get("HOTEL", 0),
            # No OTHER - we don't track it
        },
        "new_businesses_this_run": len(new_businesses)
    })
    print(f"[ok] Updated latest snapshot: {OUT_LATEST}")

    # --- Persist current seen IDs (gzipped for size) ---
    try:
        os.makedirs(os.path.dirname(OUT_SEEN), exist_ok=True)
        with gzip.open(OUT_SEEN, "wt", encoding="utf-8") as f:
            for _id in sorted(current_seen_ids):
                f.write(_id + "\n")
        print(f"[ok] Saved {len(current_seen_ids)} business IDs to {OUT_SEEN}")
    except Exception as e:
        print(f"[error] Could not save seen IDs: {e}")

    print("\n" + "="*70)
    print("PROCESSING COMPLETE!")
    print("="*70)
    print(f"✓ Total businesses in snapshot: {national_counts.get('total', 0):,}")
    print(f"✓ New businesses found: {len(new_businesses):,}")
    print(f"✓ CSV files updated in: {OUT_CSV_DIR}")
    print(f"✓ Daily snapshot saved to: {OUT_SNAPSHOTS}")
    print("="*70)

if __name__ == "__main__":
    main()
