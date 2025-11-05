#!/usr/bin/env python3
"""
Robust FHRS XML Fetcher
Scrapes the FSA open data page to get all XML download links
More reliable than API which can fail or change
"""
import os
import sys
import re
import time
import requests

BASE_URL = "https://ratings.food.gov.uk"
OPEN_DATA_PAGE = f"{BASE_URL}/open-data"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def get_xml_links():
    """Scrape the open data page for XML download links."""
    print(f"Fetching download links from {OPEN_DATA_PAGE}...")
    try:
        resp = requests.get(OPEN_DATA_PAGE, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error: Could not fetch open data page: {e}")
        return []

    html = resp.text
    # Find all hrefs ending in .xml
    hrefs = re.findall(r'href=["\']([^"\']+\.xml)["\']', html, flags=re.IGNORECASE)
    
    # Convert to absolute URLs and deduplicate
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
    
    print(f"Found {len(full_urls)} XML download links")
    return full_urls

def download_xml(url, output_dir):
    """Download a single XML file."""
    filename = url.split("/")[-1]
    filepath = os.path.join(output_dir, filename)
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        return True, len(r.content)
    except requests.RequestException as e:
        return False, str(e)

def main():
    output_dir = "data/raw"
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if XMLs already present (from custom downloader)
    existing_xmls = [f for f in os.listdir(output_dir) if f.endswith(".xml")]
    if existing_xmls:
        print(f"Found {len(existing_xmls)} existing XML files in {output_dir}")
        print("Skipping download (already present)")
        return
    
    # Get download links
    links = get_xml_links()
    if not links:
        print("Error: No XML links found on open data page")
        sys.exit(1)
    
    # Download all XMLs
    print(f"\nDownloading {len(links)} XML files...")
    successful = 0
    failed = 0
    total_bytes = 0
    
    for i, url in enumerate(links, 1):
        filename = url.split("/")[-1]
        print(f"[{i:3d}/{len(links)}] {filename} ... ", end="", flush=True)
        
        ok, result = download_xml(url, output_dir)
        if ok:
            print(f"✓ ({result/1024/1024:.1f} MB)")
            successful += 1
            total_bytes += result
        else:
            print(f"✗ ({result})")
            failed += 1
        
        # Be nice to the server
        if i < len(links):
            time.sleep(0.2)
    
    # Summary
    print("\n" + "="*60)
    print(f"Downloaded: {successful}/{len(links)} files")
    print(f"Total size: {total_bytes/1024/1024:.1f} MB")
    print(f"Failed: {failed}")
    print("="*60)
    
    if successful == 0:
        print("Error: No files downloaded successfully")
        sys.exit(1)

if __name__ == "__main__":
    main()
