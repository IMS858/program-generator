# IMS Program Generator · Deploy Guide

Fresh repo + fresh Vercel project, end to end.

## 1 · Create the GitHub repo

```bash
# Unzip this bundle to a folder you want to be the repo root
unzip ims-fresh-repo.zip
cd ims-fresh

# Initialize git
git init
git add .
git commit -m "Initial commit · IMS program generator"

# Create the repo on GitHub (any name) · then push
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

## 2 · Connect Vercel

1. Go to https://vercel.com → New Project
2. Import the GitHub repo
3. Framework preset · **Other** (Vercel will auto-detect Python from `vercel.json`)
4. Root directory · leave blank (the repo root)
5. Build command · leave blank
6. Output directory · leave blank
7. Click **Deploy**

Vercel will install Python deps from `requirements.txt` and run `app.py` as the entrypoint.

## 3 · Verify

After deploy completes, open the production URL. You should see ·
- "IMS Movement Assessment" header
- Section 05 · Strength Testing Anchors
- Section 06b · Client Concerns
- Section 06c · Cardio Capacity & Machine Tolerance (with the 3-state Interval Clearance radio)
- Three buttons at the bottom · **Generate Client Plan / Generate Coach Plan / Generate Full Plan**

If you see the OLD UI ("Background", "Strength Markers", single "Generate PDF Plan" button), it's browser cache. Hard-refresh with Cmd+Shift+R (Mac) or Ctrl+F5 (Windows). The new build sends `Cache-Control: no-cache` on `/` so this shouldn't recur.

## 4 · Test it

Generate a plan with these test anchors to confirm the strength resolver works ·

```
Incline Bench Press · press_horizontal · per_hand · 30 lb × 5RM · clean
Hip Thrust · hinge · total_load · 235 lb × 3RM · clean
3 Point Row · pull_horizontal · per_hand · 35 lb × 3RM · clean
```

Open the Full Plan and check the strength tables ·
- Incline Bench Press · should show `@ 22.5 lb /hand` in W1
- 3 Point Row · should show `@ 25 lb /hand` in W1
- Hip Thrust (or Single-Leg Hip Bridge if alias-matched) · should show `@ 170 lb` in W1

Coach appendix should list all three under USED STRENGTH ANCHORS with `match: exact` and `loads ✓`.

## What's in this build (Apr 26, 2026)

### Cardio
- Engine detects contradictions (primary in avoid list, baseline on avoided machine, knee-sensitive with all bikes avoided)
- HIIT block becomes "Conditioning Reset" when interval clearance is blocked · Z2 only, no sprint language
- Client cardio session pages render full 4-week progression
- Coach appendix shows DECISIONS section · machine selected, alternatives rejected, contradictions resolved
- Front-end · 3-state radio for clearance, auto-calc HR drop, save/load round-trip, Preview Data modal, full clearForm reset

### Strength anchors
- New `generator/strength_anchor_resolver.py` · 132 aliases / 9 movement groups
- Picker prefers the tested exercise name when alias-matched (so "3 Point Row" appears in the table, not "Single Arm Dumbbell Row")
- Strength A AND Strength B both attach week_prescriptions
- Exercise dataclass has anchor metadata as proper fields (so they survive JSON serialization)
- Category-only matches attach rep scheme but null wrong-family weights (no more 170 lb on a TRX bodyweight exercise)
- Coach appendix walks the actual program objects · USED / UNUSED with match method, wp ✓/✗, loads ✓/✗

### Data sanitation
- "form: ?" → "form: not recorded"
- "Pulllups" → "Pull-ups"
- "bilateral side" → "bilateral"
- Suspiciously low weights flagged ("3 lb is unusually light for trap_bar deadlift · likely data entry error")
- Truncated avoid notes flagged

### Tests · 119 passing
- 56 strength_system
- 44 cardio_system (includes Amanda regression class)
- 19 strength_anchor_resolver

## Known limitations

- Weekly Routine page (section 09) still shows static "Zone 2 / intervals" text in the Recovery column even when intervals are blocked. This is a stale string in the renderer · not driven by the cardio rules engine. Flagged for next pass.

## Stack

- Python 3.11+
- Flask 3.x
- ReportLab (PDF generation)
- pypdf (test introspection)

`requirements.txt` pins everything.
