# System Architecture & Data Flow

## 📊 Complete Workflow Visualization

```
┌─────────────────────────────────────────────────────────────────┐
│                    MONDAY 9 AM - AUTOMATION TRIGGERS            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: Download XML Files                                     │
│  • Fetches ~400 XML files from FSA                              │
│  • Total size: ~100-150 MB                                      │
│  • Stored in: data/raw/ (NOT committed to git)                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: Load Previous State                                    │
│  • Reads: data/seen_ids.txt.gz (~1.5MB compressed)              │
│  • Contains: ~637,000 business IDs from last week               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: Parse Current Snapshot                                 │
│  • Reads all XML files                                          │
│  • Extracts: ~637,500 total businesses                          │
│  • Identifies: ~500 NEW businesses (not in previous IDs)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: Generate CSV Files (NEW BUSINESSES ONLY)               │
│                                                                  │
│  500 new businesses split by type:                              │
│  ├─ 45 Mobile Caterers      → data/cumulative/MOBILE/2025-11.csv│
│  ├─ 180 Restaurants/Cafes   → .../RESTAURANT_CAFE/2025-11.csv   │
│  ├─ 120 Takeaways           → .../TAKEAWAY/2025-11.csv          │
│  ├─ 90 Pubs/Bars            → .../PUB_BAR/2025-11.csv           │
│  ├─ 25 Hotels               → .../HOTEL/2025-11.csv             │
│  └─ 40 Other                → .../OTHER/2025-11.csv             │
│                                                                  │
│  Files are APPENDED TO (not rewritten) if month file exists     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: Update Dashboard JSON Files                            │
│  • dashboard_data.json - Timeline series (~2KB)                 │
│  • latest_snapshot.json - Current totals (~500 bytes)           │
│  • la_totals_last.json - For delta calculation (~40KB)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: Calculate LA Rankings                                  │
│  • Compares current vs previous LA totals                       │
│  • Generates: la_deltas_latest.json (~5KB)                      │
│  • Top 10 growth + top 10 reductions per sector                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: Save Updated State                                     │
│  • Writes: data/seen_ids.txt.gz with all 637,500 IDs            │
│  • Creates: cumulative_index.json (~1KB)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 8: Commit to GitHub (SMALL FILES ONLY)                    │
│  ✅ data/*.json files                                            │
│  ✅ data/cumulative/*/*.csv files                                │
│  ✅ data/seen_ids.txt.gz                                         │
│  ❌ data/raw/*.xml (excluded by .gitignore)                      │
│                                                                  │
│  Total committed: ~150KB                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DASHBOARD AUTO-UPDATES                       │
│  Users open fhrs-dashboard-ULTIMATE.html                         │
│  → Fetches data/*.json from GitHub                              │
│  → Displays updated trends, totals, rankings                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 File Size Breakdown

### What's Stored Where:

```
LOCAL ONLY (Not in Git):
├── data/raw/*.xml              150 MB    (Downloaded weekly, deleted after)
├── data/downloads/*.xml         --       (Mirror, not used)
└── fhrs_data/                   --       (Old download location)

COMMITTED TO GIT:
├── data/
│   ├── dashboard_data.json       2 KB    (Timeline data, grows slowly)
│   ├── latest_snapshot.json      500 B   (Current totals)
│   ├── la_deltas_latest.json     5 KB    (Rankings)
│   ├── la_totals_last.json      40 KB    (For comparisons)
│   ├── seen_ids.txt.gz         1.5 MB    (All business IDs, compressed)
│   ├── cumulative_index.json     1 KB    (CSV file index)
│   └── cumulative/
│       ├── MOBILE/
│       │   ├── 2025-11.csv      15 KB
│       │   └── 2025-12.csv      18 KB
│       ├── RESTAURANT_CAFE/
│       │   └── 2025-11.csv      42 KB
│       ├── PUB_BAR/
│       │   └── 2025-11.csv      28 KB
│       ├── TAKEAWAY/
│       │   └── 2025-11.csv      35 KB
│       └── HOTEL/
│           └── 2025-11.csv      12 KB

TOTAL REPO SIZE: ~5 MB (well within GitHub's limits)
```

---

## 🔄 Data Update Frequency

```
AUTOMATED:
├── Weekly data collection         Every Monday 9 AM
├── New business detection         Automatic during collection
├── CSV file updates               Automatic (appends to monthly file)
├── Dashboard JSON refresh         Automatic after processing
└── LA ranking recalculation       Automatic after processing

MANUAL TRIGGER:
└── GitHub Actions "Run workflow"  On-demand anytime

DASHBOARD REFRESH:
└── Opens fhrs-dashboard.html      Fetches latest from GitHub
```

---

## 📤 Export Capabilities

```
DASHBOARD EXPORTS:

1. Timeline Data Export
   ├── Button: "Export Chart Data"
   ├── Format: CSV
   ├── Contains: Date, Total, Mobile, Restaurants, Pubs, Takeaways
   ├── Scope: All historical data points
   └── Use case: Trend analysis, reports, presentations

2. New Business List Export
   ├── Button: "Download latest CSV (Action)"
   ├── Format: CSV with full business details
   ├── Filtered by: Selected business type
   ├── Scope: Current month's new businesses
   └── Use case: Mail campaigns, lead generation
```

---

## 💾 Storage Efficiency Strategy

### Problem: 637,000+ businesses = huge dataset
### Solution: Multi-layer optimization

```
TECHNIQUE 1: Gzip Compression
├── Uncompressed IDs: 50+ MB (text file with 637k lines)
└── Gzipped IDs:      1.5 MB (97% reduction!)

TECHNIQUE 2: Monthly Splits
├── One massive CSV: Would grow forever, eventually break
└── Monthly files:   ~20-50 KB each, manageable forever

TECHNIQUE 3: Incremental Processing
├── Full scan:  Parse 637k businesses every time
└── Incremental: Only track the ~500 NEW businesses

TECHNIQUE 4: Exclude Raw Data from Git
├── XML files: 150 MB weekly downloads
└── Git repo:  Only processed results (~5 MB total)

RESULT: System scales indefinitely without size issues!
```

---

## 🎯 Decision Tree: When Files Get Updated

```
NEW WEEK STARTS:
├─ Is it Monday 9 AM?
│  ├─ YES → Workflow triggers automatically
│  └─ NO → Wait (or manual trigger available)
│
├─ Download XMLs
│  └─ Store in data/raw/ (local only)
│
├─ Load previous seen_ids.txt.gz
│  ├─ Exists? → Load ~637k IDs
│  └─ Missing? → Treat all as new (first run)
│
├─ Parse XMLs and find current businesses
│  └─ Total found: ~637,500
│
├─ Calculate NEW = Current - Previous
│  ├─ First run: All 637,500 are "new"
│  └─ Later runs: ~500 new per week
│
├─ Write NEW businesses to CSV
│  ├─ Check if YYYY-MM.csv exists for this sector
│  ├─ YES → APPEND new rows
│  └─ NO → CREATE file with headers + new rows
│
├─ Update all JSON files
│  ├─ dashboard_data.json (add new date point)
│  ├─ latest_snapshot.json (update totals)
│  ├─ la_totals_last.json (current LA counts)
│  └─ la_deltas_latest.json (LA rankings)
│
├─ Save current state
│  └─ Write seen_ids.txt.gz with all 637,500 IDs
│
└─ Commit to GitHub
   ├─ Stage only: data/*.json, data/cumulative/*.csv
   ├─ Ignore: data/raw/*.xml
   └─ Push to main branch
```

---

## 🚨 Safety Mechanisms

### Size Protection:
1. ✅ .gitignore excludes XML files
2. ✅ Workflow only stages specific files
3. ✅ Gzip compression for ID tracking
4. ✅ Monthly CSV splits prevent bloat

### Error Handling:
1. ✅ Workflow continues if downloader fails (fallback exists)
2. ✅ Rebase failure triggers merge fallback
3. ✅ Missing previous state = safe first-run mode
4. ✅ CSV append errors don't break workflow

### Data Integrity:
1. ✅ Previous state backed up before processing
2. ✅ Atomic file writes (temp → rename)
3. ✅ Git ensures version history
4. ✅ Index file tracks all CSV exports

---

This visualization shows how your system handles large datasets efficiently 
while keeping GitHub repo size manageable forever! 🎉
