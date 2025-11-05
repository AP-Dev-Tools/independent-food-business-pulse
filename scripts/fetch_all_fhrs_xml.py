# scripts/fetch_all_fhrs_xml.py
import os, sys, time, subprocess, requests

HEADERS = {
    "User-Agent": "NCASS-FHRS-Updater/1.0",
    "accept": "application/json",
    "x-api-version": "2",
}
BASE = "https://ratings.food.gov.uk"

def get(url, params=None, retries=5, backoff=1.6):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    pass
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(backoff ** (i + 1))
                continue
            r.raise_for_status()
        except Exception:
            time.sleep(backoff ** (i + 1))
    sys.exit(f"Failed to fetch {url}")

def discover_la_ids():
    for url, params in [
        (f"{BASE}/Authorities/basic", None),
        (f"{BASE}/Authorities", {"basic": "true"}),
        (f"{BASE}/Authorities", None),
    ]:
        try:
            data = get(url, params)
            if data:
                items = data.get("authorities") or data.get("Authorities") or data
                if isinstance(items, dict):
                    items = items.get("authorities") or items.get("Authorities") or []
                ids = set()
                for a in items if isinstance(items, list) else []:
                    for k in ("LocalAuthorityId", "LocalAuthorityIdCode", "LocalAuthorityIdNumber", "Id"):
                        v = a.get(k)
                        if isinstance(v, int):
                            ids.add(v)
                        elif isinstance(v, str) and v.isdigit():
                            ids.add(int(v))
                if ids:
                    return sorted(ids)
        except SystemExit as e:
            print(e)
    sys.exit("Could not retrieve any Local Authority IDs from FHRS API.")

def main():
    os.makedirs("data/raw", exist_ok=True)
    # If your custom downloader already produced XMLs, skip
    if any(name.endswith(".xml") for name in os.listdir("data/raw")):
        print("XMLs already present; skipping auto-fetch.")
        return

    ids = discover_la_ids()
    print(f"Discovered {len(ids)} LAs")
    ok = fail = 0
    for i in ids:
        url = f"{BASE}/OpenDataFiles/FHRS{i}_en-GB.xml"
        out = f"data/raw/FHRS_{i}.xml"
        rc = subprocess.call(["curl", "-fsSL", "--retry", "5", "--retry-delay", "2", url, "-o", out])
        if rc == 0:
            ok += 1
        else:
            fail += 1
    print(f"Downloaded {ok} XMLs, {fail} failed.")
    if ok == 0:
        sys.exit("No XMLs downloaded.")

if __name__ == "__main__":
    main()