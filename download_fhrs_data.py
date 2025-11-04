#!/usr/bin/env python3
"""
FHRS Data Downloader - Simple Version
Downloads Food Hygiene Rating data directly from FSA open data page.
Much faster and more reliable than the API version!
"""

import sys
import re
import time
from datetime import datetime
from pathlib import Path

import requests

# ----------------------------
# Configuration
# ----------------------------
OUTPUT_DIR = "fhrs_data"
BASE_URL = "https://ratings.food.gov.uk"
OPEN_DATA_PAGE = f"{BASE_URL}/open-data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # No cookies/proxies required
}

# ----------------------------
# Helpers
# ----------------------------
def create_output_directory() -> Path:
    """Create date-stamped directory for this run."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path(OUTPUT_DIR) / timestamp
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_download_links():
    """Scrape the FHRS open-data page for all XML links (absolute URLs)."""
    print("Fetching download links from FSA website...")
    try:
        resp = requests.get(OPEN_DATA_PAGE, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"\nError connecting to FSA website: {e}")
        print("\nTroubleshooting:")
        print("  1) Check your internet connection")
        print("  2) Try opening https://ratings.food.gov.uk/open-data in a browser")
        print("  3) Try again in a few minutes")
        return None

    html = resp.text

    # Find all hrefs ending in .xml (covers LA files + national files)
    hrefs = re.findall(r'href=["\']([^"\']+\.xml)["\']', html, flags=re.IGNORECASE)
    # Normalise to absolute URLs
    full_urls = []
    seen = set()
    for h in hrefs:
        if h.startswith("http"):
            url = h
        else:
            url = BASE_URL + h if h.startswith("/") else f"{BASE_URL}/{h}"
        if url not in seen:
            seen.add(url)
            full_urls.append(url)

    if not full_urls:
        print("No XML links found on the page. The page layout may have changed.")
        return None

    print(f"Found {len(full_urls)} local authority data files")
    return full_urls


def download_file(url: str, output_dir: Path):
    """Download a single XML file to output_dir. Returns (success, size_mb or error str)."""
    filename = url.split("/")[-1]
    filepath = output_dir / filename

    try:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        size_mb = len(r.content) / (1024 * 1024)
        return True, size_mb
    except requests.RequestException as e:
        return False, str(e)


# ----------------------------
# Main
# ----------------------------
def main():
    print("=" * 70)
    print("FHRS DATA DOWNLOADER")
    print("=" * 70)

    output_dir = create_output_directory()
    print(f"Output folder: {output_dir}\n")

    links = get_download_links()
    if not links:
        # Already printed an error above
        sys.exit(1)

    successful = 0
    failed = []
    total_mb = 0.0

    for i, url in enumerate(links, start=1):
        filename = url.split("/")[-1]
        print(f"[{i:03d}/{len(links)}] {filename} ... ", end="", flush=True)
        ok, result = download_file(url, output_dir)
        if ok:
            print(f"✓ ({result:.1f} MB)")
            successful += 1
            total_mb += result
        else:
            print("✗")
            failed.append((filename, result))
        time.sleep(0.2)  # be kind to the server

    # Summary
    print("\n" + "=" * 70)
    print("DOWNLOAD COMPLETE!")
    print("=" * 70)
    print(f"✓ Successfully downloaded: {successful}/{len(links)} files")
    print(f"✓ Total data downloaded: {total_mb:.1f} MB")
    print(f"✓ Data saved to: {output_dir}")

    if failed:
        print(f"\n⚠ Failed downloads ({len(failed)}):")
        for name, err in failed[:10]:
            print(f"  - {name}: {err}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")

    # Metadata file
    metadata_file = output_dir / "download_metadata.txt"
    with open(metadata_file, "w", encoding="utf-8") as f:
        f.write("FHRS Download Metadata\n")
        f.write(f"Timestamp: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Source page: {OPEN_DATA_PAGE}\n")
        f.write(f"Files attempted: {len(links)}\n")
        f.write(f"Files successful: {successful}\n")
        f.write(f"Total size (MB): {total_mb:.2f}\n")

    print(f"\n✓ Metadata saved to: {metadata_file}")

    print("\n" + "=" * 70)
    print("🎉 SUCCESS! Data is ready to use!")
    print("=" * 70)
    print("\nNEXT STEPS:")
    print("1. Open your dashboard HTML")
    print(f"2. Select folder: {output_dir}")
    print("3. Click 'Process Data'")

    # IMPORTANT: This guard prevents GitHub Actions from hanging/crashing.
    if sys.stdin.isatty():
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
