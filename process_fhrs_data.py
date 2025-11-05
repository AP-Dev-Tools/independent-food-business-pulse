#!/usr/bin/env python3
import os, re, json, gzip
from datetime import datetime
from xml.etree import ElementTree as ET
from collections import defaultdict, Counter

RAW_ROOT = "data/raw"

# Sector mapping (FHRS BusinessType -> our sector keys)
BTYPE_TO_SECTOR = {
    "Mobile caterer":               "MOBILE",
    "Restaurant/Cafe/Canteen":     "RESTAURANT_CAFE",
    "Pub/bar/nightclub":           "PUB_BAR",
    "Takeaway/sandwich shop":      "TAKEAWAY",
    "Hotel/bed & breakfast/guest house": "HOTEL",
}
SECTORS = ["MOBILE","RESTAURANT_CAFE","PUB_BAR","TAKEAWAY","HOTEL","OTHER"]

OUT_DASHBOARD = "data/dashboard_data.json"
OUT_LATEST    = "data/latest_snapshot.json"
OUT_LA_LAST   = "data/la_totals_last.json"      # expected by the workflow delta step
OUT_LA_CURR   = "data/la_totals_current.json"   # kept for compatibility
OUT_SEEN      = "data/seen_ids.txt.gz"          # optional; handy for future use

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def find_latest_raw_dir(root: str) -> str:
    """
    Pick the lexicographically latest YYYY-MM-DD folder under data/raw.
    """
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Raw folder not found: {root}")
    dated = [d for d in os.listdir(root) if DATE_DIR_RE.match(d) and os.path.isdir(os.path.join(root,d))]
    if not dated:
        # Fallback: allow XMLs directly under data/raw
        return root
    return os.path.join(root, sorted(dated)[-1])

def iter_xml_files(base: str):
    for dirpath, _, files in os.walk(base):
        for fn in files:
            if fn.lower().endswith(".xml"):
                yield os.path.join(dirpath, fn)

def safe_text(elem, tag):
    x = elem.find(tag)
    return (x.text or "").strip() if x is not None else ""

def parse_snapshot(xml_dir: str):
    """
    Returns:
      per_LA_totals: { "LA name": {"MOBILE":n,...,"OTHER":m}, ... }
      national_counts: {"MOBILE":n,...,"OTHER":m,"total":N}
      seen_ids: set of FHRSID strings
    """
    per_LA = defaultdict(lambda: Counter({s:0 for s in SECTORS}))
    national = Counter({s:0 for s in SECTORS})
    seen_ids = set()

    files = list(iter_xml_files(xml_dir))
    if not files:
        raise FileNotFoundError(f"No XML files found in {xml_dir}")

    for path in files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
            # skip bad file; continue robustly
            continue

        for est in root.iterfind(".//EstablishmentDetail"):
            fhrsid   = safe_text(est, "FHRSID")
            btype    = safe_text(est, "BusinessType")
            la_name  = safe_text(est, "LocalAuthorityName")

            sector = BTYPE_TO_SECTOR.get(btype, "OTHER")
            per_LA[la_name][sector] += 1
            national[sector] += 1
            if fhrsid:
                seen_ids.add(fhrsid)

    # total is ALL categories (incl OTHER) — the dashboard JS will ignore OTHER when needed
    national_total = sum(national[s] for s in SECTORS)
    national["total"] = national_total

    # Coerce defaultdict/Counter to plain dicts with all sector keys present
    per_LA_out = {}
    for la, counts in per_LA.items():
        row = {s:int(counts.get(s,0)) for s in SECTORS}
        per_LA_out[la] = row

    national_out = {s:int(national.get(s,0)) for s in (SECTORS+["total"])}

    return per_LA_out, national_out, seen_ids

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

def main():
    latest_dir = find_latest_raw_dir(RAW_ROOT)
    # Derive snapshot date from folder name if possible, else today
    base_name = os.path.basename(latest_dir.rstrip("/"))
    if DATE_DIR_RE.match(base_name):
        snap_date = base_name
    else:
        snap_date = datetime.utcnow().strftime("%Y-%m-%d")

    per_LA_totals, national_counts, seen_ids = parse_snapshot(latest_dir)

    # --- Write LA totals for the delta step ---
    write_json(OUT_LA_LAST, per_LA_totals)
    write_json(OUT_LA_CURR, per_LA_totals)  # compatibility/inspection

    # --- Update dashboard series ---
    dashboard_series = read_json(OUT_DASHBOARD, [])
    # Remove any existing entry for this date, then append fresh
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
            "OTHER":           national_counts.get("OTHER", 0),
        }
    })
    # Keep series ordered by date
    dashboard_series.sort(key=lambda r: r.get("date",""))
    write_json(OUT_DASHBOARD, dashboard_series)

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
            "OTHER":           national_counts.get("OTHER", 0),
        },
        # we no longer calculate new-business list here; keep 0 for compatibility
        "new_businesses_this_run": 0
    })

    # --- Optional: persist seen IDs for future use ---
    try:
        os.makedirs(os.path.dirname(OUT_SEEN), exist_ok=True)
        with gzip.open(OUT_SEEN, "wt", encoding="utf-8") as f:
            for _id in sorted(seen_ids):
                f.write(_id + "\n")
    except Exception:
        pass

    print(f"[ok] Processed {latest_dir}")
    print(f"[ok] Wrote {OUT_LA_LAST} (and {OUT_LA_CURR})")
    print(f"[ok] Updated {OUT_DASHBOARD} and {OUT_LATEST}")

if __name__ == "__main__":
    main()
