#!/usr/bin/env python3
"""
FHRS Data Processor
Processes downloaded FHRS XML files, identifies new businesses, and maintains cumulative CSV
"""

import os
import json
import csv
from datetime import datetime
from xml.etree import ElementTree as ET
from pathlib import Path

# Business type sectors we track
SECTORS = {
    'MOBILE': 'Mobile caterer',
    'RESTAURANT': 'Restaurant/Cafe/Canteen',
    'PUB': 'Pub/bar/nightclub',
    'TAKEAWAY': 'Takeaway/sandwich shop'
}

def load_previous_snapshot():
    """Load the most recent snapshot from history"""
    snapshot_file = Path('data/latest_snapshot.json')
    if snapshot_file.exists():
        with open(snapshot_file, 'r') as f:
            return json.load(f)
    return None

def save_snapshot(date, businesses):
    """Save current snapshot"""
    os.makedirs('data', exist_ok=True)
    
    snapshot = {
        'date': date,
        'businesses': businesses,
        'counts': {
            SECTORS['MOBILE']: sum(1 for b in businesses if b['type'] == SECTORS['MOBILE']),
            SECTORS['RESTAURANT']: sum(1 for b in businesses if b['type'] == SECTORS['RESTAURANT']),
            SECTORS['PUB']: sum(1 for b in businesses if b['type'] == SECTORS['PUB']),
            SECTORS['TAKEAWAY']: sum(1 for b in businesses if b['type'] == SECTORS['TAKEAWAY']),
            'total': len(businesses)
        }
    }
    
    # Save latest snapshot
    with open('data/latest_snapshot.json', 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    # Also save to history
    os.makedirs('data/history', exist_ok=True)
    with open(f'data/history/snapshot_{date}.json', 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    return snapshot

def parse_xml_files(data_dir):
    """Parse all XML files in the data directory"""
    businesses = []
    
    xml_files = list(Path(data_dir).glob('*.xml'))
    print(f"Found {len(xml_files)} XML files to process")
    
    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            for establishment in root.findall('.//EstablishmentDetail'):
                biz_type = establishment.findtext('BusinessType', '').strip()
                
                # Only process businesses in our tracked sectors
                if biz_type in SECTORS.values():
                    business = {
                        'id': establishment.findtext('FHRSID', '').strip(),
                        'name': establishment.findtext('BusinessName', '').strip(),
                        'type': biz_type,
                        'la': establishment.findtext('LocalAuthorityName', '').strip(),
                        'addressLine1': establishment.findtext('AddressLine1', '').strip(),
                        'addressLine2': establishment.findtext('AddressLine2', '').strip(),
                        'addressLine3': establishment.findtext('AddressLine3', '').strip(),
                        'addressLine4': establishment.findtext('AddressLine4', '').strip(),
                        'postcode': establishment.findtext('PostCode', '').strip(),
                        'ratingValue': establishment.findtext('RatingValue', '').strip(),
                        'ratingDate': establishment.findtext('RatingDate', '').strip()
                    }
                    businesses.append(business)
        
        except Exception as e:
            print(f"Error processing {xml_file}: {e}")
    
    print(f"Parsed {len(businesses)} businesses from XML files")
    return businesses

def identify_new_businesses(current_businesses, previous_snapshot):
    """Identify businesses that are new compared to previous snapshot"""
    if not previous_snapshot:
        print("No previous snapshot - all businesses are 'new'")
        return current_businesses
    
    previous_ids = set(b['id'] for b in previous_snapshot['businesses'])
    new_businesses = [b for b in current_businesses if b['id'] not in previous_ids]
    
    print(f"Found {len(new_businesses)} new businesses")
    return new_businesses

def append_to_cumulative_csv(new_businesses, date):
    """Append new businesses to cumulative CSV"""
    csv_file = Path('data/cumulative_new_businesses.csv')
    file_exists = csv_file.exists()
    
    os.makedirs('data', exist_ok=True)
    
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        fieldnames = [
            'Date Added', 'FHRS ID', 'Business Name', 'Type',
            'Address Line 1', 'Address Line 2', 'Address Line 3', 'Address Line 4',
            'Postcode', 'Local Authority', 'Rating Value', 'Rating Date'
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # Write header if file is new
        if not file_exists:
            writer.writeheader()
        
        # Write new businesses
        for business in new_businesses:
            writer.writerow({
                'Date Added': date,
                'FHRS ID': business['id'],
                'Business Name': business['name'],
                'Type': business['type'],
                'Address Line 1': business['addressLine1'],
                'Address Line 2': business['addressLine2'],
                'Address Line 3': business['addressLine3'],
                'Address Line 4': business['addressLine4'],
                'Postcode': business['postcode'],
                'Local Authority': business['la'],
                'Rating Value': business['ratingValue'],
                'Rating Date': business['ratingDate']
            })
    
    print(f"Appended {len(new_businesses)} businesses to cumulative CSV")

def update_dashboard_data(snapshots):
    """Create a JSON file with all snapshots for the dashboard to load"""
    os.makedirs('data', exist_ok=True)
    
    with open('data/dashboard_data.json', 'w') as f:
        json.dump(snapshots, f, indent=2)
    
    print(f"Updated dashboard data with {len(snapshots)} snapshots")

def main():
    """Main processing function"""
    print("=" * 60)
    print("FHRS Data Processor")
    print("=" * 60)
    
    # Determine date for this run
    date = datetime.now().strftime('%Y-%m-%d')
    print(f"Processing date: {date}")
    
    # Find the most recent data directory
    data_dirs = sorted(Path('fhrs_data').glob('*'), reverse=True)
    if not data_dirs:
        print("ERROR: No data directories found in fhrs_data/")
        return
    
    latest_data_dir = data_dirs[0]
    print(f"Using data directory: {latest_data_dir}")
    
    # Load previous snapshot
    previous_snapshot = load_previous_snapshot()
    if previous_snapshot:
        print(f"Loaded previous snapshot from {previous_snapshot['date']}")
    else:
        print("No previous snapshot found - this is the first run")
    
    # Parse XML files
    current_businesses = parse_xml_files(latest_data_dir)
    
    # Save current snapshot
    current_snapshot = save_snapshot(date, current_businesses)
    
    # Identify new businesses
    new_businesses = identify_new_businesses(current_businesses, previous_snapshot)
    
    # Append to cumulative CSV
    if new_businesses:
        append_to_cumulative_csv(new_businesses, date)
    else:
        print("No new businesses to add to cumulative CSV")
    
    # Load all historical snapshots for dashboard
    history_files = sorted(Path('data/history').glob('snapshot_*.json'))
    all_snapshots = []
    for hist_file in history_files:
        with open(hist_file, 'r') as f:
            all_snapshots.append(json.load(f))
    
    # Update dashboard data
    update_dashboard_data(all_snapshots)
    
    print("=" * 60)
    print("Processing complete!")
    print(f"Total businesses: {current_snapshot['counts']['total']:,}")
    print(f"New businesses: {len(new_businesses):,}")
    print("=" * 60)

if __name__ == '__main__':
    main()
