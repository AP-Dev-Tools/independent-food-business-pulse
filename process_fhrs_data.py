#!/usr/bin/env python3
import os, re, json, gzip
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
BTYPE_TO_SECTOR = {
    "Mobile caterer":                       "MOBILE",
    "Restaurant/Cafe/Canteen":             "RESTAURANT_CAFE",
    "Pub/bar/nightclub":                   "PUB_BAR",
    "Takeaway/sandwich shop":              "TAKEAWAY",
    "Hotel/bed & breakfast/guest house":   "HOTEL",
}
SECTORS = ["MOBILE","RESTAURANT_CAFE","PUB_BAR","TAKEAWAY","HOTEL","OTHER"]

OUT_DASHBOARD = "data/dashboard_data.json"
OUT_LATEST    = "data/latest_snapshot.json"
OUT_LA_LAST   = "data/la_totals_last.json"      # consumed by workflow delta step
OUT_LA_CURR   = "data/la_totals_current.json"   # for inspection
OUT_SEEN      = "data/seen_ids.txt.gz"

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

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

def parse_snapshot(xml_files: list[str]):
    """
    Returns:
      per_LA_totals: { "LA name": {"MOBILE":n,...,"OTHER":m}, ... }
      national_counts: {"MOBILE":n,...,"OTHER":m,"total":N}
      seen_ids: set of FHRSID strings
    """
    per_LA = defaultdict(lambda: Counter({s:0 for s in SECTORS}))
    national = Counter({s:0 for s in SECTORS})
    seen_ids = set()

    for path in xml_files:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
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

    national_total = sum(national[s] for s in SECTORS)
    national["total"] = national_total

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
    chosen_dir, files = find_best_xml_dir()
    if not chosen_dir or not files:
        raise FileNotFoundError(
            "No FHRS XML files were found under any of: "
            + ", ".join(SEARCH_ROOTS)
        )

    snap_date = infer_snapshot_date(chosen_dir)
    per_LA_totals, national_counts, seen_ids = parse_snapshot(files)

    # --- Write LA totals for delta step ---
    write_json(OUT_LA_LAST, per_LA_totals)
    write_json(OUT_LA_CURR, per_LA_totals)

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
            "OTHER":           national_counts.get("OTHER", 0),
        }
    })
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
        "new_businesses_this_run": 0
    })

    # --- Optional: persist seen IDs ---
    try:
        os.makedirs(os.path.dirname(OUT_SEEN), exist_ok=True)
        with gzip.open(OUT_SEEN, "wt", encoding="utf-8") as f:
            for _id in sorted(seen_ids):
                f.write(_id + "\n")
    except Exception:
        pass

    print(f"[ok] Parsed {len(files)} XML files from: {chosen_dir}")
    print(f"[ok] Wrote {OUT_LA_LAST} / {OUT_LA_CURR}")
    print(f"[ok] Updated {OUT_DASHBOARD} and {OUT_LATEST}")

if __name__ == "__main__":
    main()
