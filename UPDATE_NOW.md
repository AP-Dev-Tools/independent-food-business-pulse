# QUICK FIX REFERENCE

## ⚡ 3 Files to Update RIGHT NOW

### 1. Replace: `scripts/fetch_all_fhrs_xml.py`
**Why:** Fixes the workflow failure you saw
**With:** `fetch_all_fhrs_xml.py` (from outputs)
**Location:** `scripts/fetch_all_fhrs_xml.py`

### 2. Replace: `process_fhrs_data.py`
**Why:** Removes "OTHER", saves 50% space
**With:** `process_fhrs_data_v2.py` (from outputs)
**Location:** `process_fhrs_data.py` (root directory)
**Note:** Rename v2 → regular name

### 3. Replace: `scripts/make_la_deltas.py`
**Why:** Consistency - no OTHER in rankings
**With:** `make_la_deltas.py` (from outputs)
**Location:** `scripts/make_la_deltas.py`

---

## 📋 Already Updated Earlier (Check These Too)

### 4. `.github/workflows/weekly-update.yml`
**Status:** Should already be updated from earlier
**Check:** Line 70 should say `python scripts/make_la_deltas.py`

### 5. `.gitignore`
**Status:** Should already be updated from earlier
**Check:** Should exclude `data/raw/*.xml` etc.

---

## 🚀 After Updating - Test It

```bash
# Commit all changes
git add scripts/fetch_all_fhrs_xml.py
git add process_fhrs_data.py
git add scripts/make_la_deltas.py
git commit -m "Fix fetch script, remove OTHER tracking"
git push

# Then trigger workflow manually on GitHub
# Actions → Weekly FHRS Data Update → Run workflow
```

---

## ✅ What's Fixed

| Problem | Solution | File |
|---------|----------|------|
| Workflow fails at fetch | New fetch script uses web scraping | `scripts/fetch_all_fhrs_xml.py` |
| Don't want OTHER data | Remove from all processing | `process_fhrs_data.py` |
| LA rankings include OTHER | Remove from deltas | `scripts/make_la_deltas.py` |

---

## 📊 Space Savings

**Before:** ~1.5 MB seen_ids + 6 CSV types
**After:** ~700 KB seen_ids + 5 CSV types

**Saved:** 50% on tracking data!

---

## 🎯 What You Now Get

**CSVs Generated:**
- ✅ MOBILE/2025-11.csv
- ✅ RESTAURANT_CAFE/2025-11.csv
- ✅ PUB_BAR/2025-11.csv
- ✅ TAKEAWAY/2025-11.csv
- ✅ HOTEL/2025-11.csv
- ❌ ~~OTHER/2025-11.csv~~ (not created)

**Dashboard Shows:**
- ✅ Mobile Caterers trend
- ✅ Restaurants/Cafes trend
- ✅ Pubs/Bars trend
- ✅ Takeaways trend
- ✅ Hotels trend
- ❌ ~~Other~~ (not tracked)

---

That's it! Update those 3 files and you're good to go! 🎉
