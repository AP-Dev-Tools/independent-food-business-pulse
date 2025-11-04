#!/usr/bin/env python3
"""
FHRS Data Downloader - Simple Version
Downloads Food Hygiene Rating data directly from FSA open data page.
Much faster and more reliable than the API version!
"""

import requests
import re
from datetime import datetime
from pathlib import Path
import time

OUTPUT_DIR = "fhrs_data"
BASE_URL = "https://ratings.food.gov.uk"
OPEN_DATA_PAGE = f"{BASE_URL}/open-data"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def create_output_directory():
    """Create timestamped directory for downloads"""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path(OUTPUT_DIR) / timestamp
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_download_links():
    """Scrape the open data page to get all download links"""
    print("Fetching download links from FSA website...")
    
    try:
        response = requests.get(OPEN_DATA_PAGE, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # Find all XML download links
        # Pattern: /api/open-data-files/FHRS###en-GB.xml
        pattern = r'/api/open-data-files/FHRS\d+en-GB\.xml'
        links = re.findall(pattern, response.text)
        
        # Remove duplicates and create full URLs
        unique_links = list(set(links))
        full_urls = [BASE_URL + link for link in unique_links]
        
        print(f"Found {len(full_urls)} local authority data files")
        return full_urls
        
    except requests.RequestException as e:
        print(f"\nError connecting to FSA website: {e}")
        print("\nTroubleshooting:")
        print("1. Check your internet connection")
        print("2. Make sure you can access: https://ratings.food.gov.uk")
        print("3. Try again in a few minutes")
        return None

def download_file(url, output_dir):
    """Download a single XML file"""
    filename = url.split('/')[-1]
    filepath = output_dir / filename
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=60)
        response.raise_for_status()
        
        # Save to file
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Calculate file size in MB
        file_size = len(response.content) / (1024 * 1024)
        
        return True, file_size
        
    except requests.RequestException as e:
        return False, str(e)

def main():
    print("=" * 70)
    print("FHRS Data Downloader - Simple & Fast Version")
    print("=" * 70)
    print()
    print("This downloads all UK food hygiene data directly from FSA.")
    print("Much more reliable than the API version!")
    print()
    
    # Create output directory
    output_dir = create_output_directory()
    print(f"Saving files to: {output_dir}")
    print()
    
    # Get download links
    download_links = get_download_links()
    
    if not download_links:
        print("\nCould not fetch download links. Please try again later.")
        input("\nPress Enter to exit...")
        return
    
    # Download all files
    print(f"\nDownloading {len(download_links)} files...")
    print("-" * 70)
    
    successful_downloads = 0
    failed_downloads = []
    total_size_mb = 0
    
    for i, url in enumerate(download_links, 1):
        filename = url.split('/')[-1]
        authority_id = filename.replace('FHRS', '').replace('en-GB.xml', '')
        
        print(f"[{i}/{len(download_links)}] Authority {authority_id}...", end=" ", flush=True)
        
        success, result = download_file(url, output_dir)
        
        if success:
            print(f"✓ ({result:.1f} MB)")
            successful_downloads += 1
            total_size_mb += result
        else:
            print(f"✗ Failed")
            failed_downloads.append(filename)
        
        # Small delay to be nice to the server
        time.sleep(0.2)
    
    # Summary
    print()
    print("=" * 70)
    print("DOWNLOAD COMPLETE!")
    print("=" * 70)
    print(f"✓ Successfully downloaded: {successful_downloads}/{len(download_links)} files")
    print(f"✓ Total data downloaded: {total_size_mb:.1f} MB")
    print(f"✓ Data saved to: {output_dir}")
    
    if failed_downloads:
        print(f"\n⚠ Failed downloads ({len(failed_downloads)}):")
        for name in failed_downloads[:10]:
            print(f"  - {name}")
        if len(failed_downloads) > 10:
            print(f"  ... and {len(failed_downloads) - 10} more")
    
    # Create metadata file
    metadata_file = output_dir / "download_metadata.txt"
    with open(metadata_file, 'w') as f:
        f.write(f"Download Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Files Downloaded: {successful_downloads}\n")
        f.write(f"Total Size: {total_size_mb:.1f} MB\n")
        f.write(f"Failed Downloads: {len(failed_downloads)}\n")
        f.write(f"Source: {OPEN_DATA_PAGE}\n")
    
    print(f"\n✓ Metadata saved to: {metadata_file}")
    print("\n" + "=" * 70)
    print("🎉 SUCCESS! Data is ready to use!")
    print("=" * 70)
    print("\nNEXT STEPS:")
    print("1. Open: fhrs-dashboard-auto-tracking.html")
    print(f"2. Select folder: {output_dir}")
    print("3. Click 'Process Data'")
    print("4. Done!")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
