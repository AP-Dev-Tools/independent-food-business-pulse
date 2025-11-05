# FHRS GitHub Actions - Fixes & Troubleshooting

## Issues Found & Fixed

### 1. **CRITICAL: Wrong script name in workflow**
**Problem:** Line 72 of `.github/workflows/weekly-update.yml` calls:
```yaml
- name: Build LA deltas (Top-10 growth/reductions)
  run: python build_la_deltas.py
```

**Fix:** Should be:
```yaml
- name: Build LA deltas (Top-10 growth/reductions)
  run: python scripts/make_la_deltas.py
```

---

### 2. **Git commit failures - Large files**
**Problem:** Trying to commit large XML files causes push failures

**Fix:** Updated workflow to only commit small JSON files:
```yaml
# Add only data directory changes, exclude raw XML files
git add data/*.json data/cumulative/*.csv 2>/dev/null || true
```

**Also update .gitignore** to exclude XML files:
```
data/raw/*.xml
data/xml/*.xml
data/fhrs/*.xml
data/downloads/*.xml
```

---

### 3. **Git rebase conflicts**
**Problem:** Workflow fails when trying to rebase with conflicts

**Fix:** Added fallback strategy:
```yaml
git rebase origin/main || {
  echo "Rebase failed, attempting merge strategy"
  git rebase --abort
  git pull origin main --no-rebase || true
}
```

---

## Files to Update

### File 1: `.github/workflows/weekly-update.yml`
Replace the entire file with the corrected version (provided separately).

**Key changes:**
- Line 70: `python scripts/make_la_deltas.py` (was `build_la_deltas.py`)
- Lines 77-87: Improved git commit logic with selective file adding
- Lines 89-94: Better error handling for rebase failures

### File 2: `.gitignore`
Add these lines to exclude large XML files:
```
# Raw XML files (too large for git)
data/raw/*.xml
data/xml/*.xml
data/fhrs/*.xml
data/downloads/*.xml
```

---

## How to Apply These Fixes

### Step 1: Update workflow file
```bash
# Replace .github/workflows/weekly-update.yml with the corrected version
# Then commit:
git add .github/workflows/weekly-update.yml
git commit -m "Fix workflow script path and commit logic"
```

### Step 2: Update .gitignore
```bash
# Edit .gitignore to add XML exclusions
git add .gitignore
git commit -m "Exclude large XML files from git"
```

### Step 3: Clean up any committed XML files (if needed)
```bash
# If XML files were accidentally committed, remove them:
git rm -r --cached data/raw/*.xml data/xml/*.xml data/fhrs/*.xml 2>/dev/null || true
git commit -m "Remove large XML files from git"
```

### Step 4: Push changes
```bash
git push origin main
```

### Step 5: Test the workflow
- Go to your repo on GitHub
- Click "Actions" tab
- Click "Weekly FHRS Data Update" workflow
- Click "Run workflow" button
- Watch the logs for any errors

---

## Common Workflow Errors & Solutions

### Error: "No FHRS XML files present in data/raw"
**Cause:** Download script failed
**Solution:** Check if FSA website is accessible, or run manually

### Error: "fatal: unable to push"
**Cause:** Large files or authentication issues
**Solution:** 
1. Check .gitignore excludes XML files
2. Verify workflow has `contents: write` permission (line 3-4)

### Error: "ModuleNotFoundError: No module named 'requests'"
**Cause:** Dependencies not installed
**Solution:** Check lines 30-33 install dependencies correctly

### Error: "FileNotFoundError: build_la_deltas.py"
**Cause:** This is the main bug - wrong script name
**Solution:** Apply the workflow fix above

---

## Testing Locally Before Pushing

### Test the download script:
```bash
python download_fhrs_data.py
```

### Test the processing script:
```bash
python process_fhrs_data.py
```

### Test the delta script:
```bash
# First ensure you have the prerequisite files
python scripts/make_la_deltas.py
```

### Test the fetch script:
```bash
python scripts/fetch_all_fhrs_xml.py
```

---

## Monitoring Your Workflow

1. **View workflow runs:**
   - https://github.com/AP-Dev-Tools/independent-food-business-pulse/actions

2. **Check logs:**
   - Click on any workflow run
   - Click on "update-data" job
   - Expand each step to see detailed logs

3. **View processed data:**
   - Check `data/dashboard_data.json` in your repo
   - Check `data/la_deltas_latest.json` for growth/reduction stats

---

## Quick Reference: What Each Script Does

| Script | Purpose | Called By |
|--------|---------|-----------|
| `scripts/fetch_all_fhrs_xml.py` | Downloads XML files from FSA | Workflow |
| `download_fhrs_data.py` | Alternative downloader (optional) | Workflow |
| `process_fhrs_data.py` | Parses XMLs, creates dashboard data | Workflow |
| `scripts/make_la_deltas.py` | Calculates growth/reduction stats | Workflow |

---

## Need More Help?

If you're still seeing errors:
1. Copy the error message from GitHub Actions logs
2. Check which step is failing
3. Look for the specific error in the logs (usually red text)
4. Common issues: file paths, missing files, git conflicts

**Remember:** The workflow only commits JSON files, not the large XML files. This keeps your repo size manageable!
