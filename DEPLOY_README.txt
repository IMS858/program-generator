IMS PROGRAM GENERATOR · FRESH DEPLOY PACKAGE
=============================================

Complete working repo · ready to deploy from a fresh GitHub repo.

NEW IN THIS BUILD
-----------------

CONCERN-AWARE EXERCISE FILTERING
- 8 joint concern checkboxes in the form (knee, shoulder, lower back, hip,
  neck, wrist, elbow, ankle)
- Picker filters loaded exercises through flagged joints
- Spine concerns (lower_back) trigger spine-safe pool routing · trap bar
  and KB swings come off the menu automatically
- Knee concerns (bad_knee) trigger unilateral hip-emphasis patterns
- Shoulder concerns trigger neutral grip / supported variants

JOINT CARE BLOCK
- Auto-generated when client has flagged concerns
- 2 default drills per red-flagged joint · Passive CARs + Light Flexibility
- Same gentle dose all 4 weeks · no progression until cleared
- Coach can swap or expand once they review

GOALS PAGE NARRATES THE LISTENING
- Page 4 echoes back · concerns, FRA priorities, red-flagged mobility,
  formal constraints
- "OUR APPROACH" section explains what's being filtered and why
- Coach and client both SEE that the system caught what was reported

DEPLOY STEPS
------------

1. Create your fresh GitHub repo
2. Unzip this package locally · cd into the unzipped folder
3. git init
4. git add .
5. git commit -m "Initial commit · IMS Program Generator with concern-aware filtering"
6. git branch -M main
7. git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
8. git push -u origin main
9. Connect to Vercel · vercel.com → New Project → Import GitHub Repo
10. Click Deploy · Vercel reads vercel.json automatically

VERIFY
------

1. Form loads · scroll to Section 06b "Client Concerns"
2. Check "bad_knee" · fill in concern notes
3. Generate plan
4. PDF Page 4 (Goals) should mirror back the bad knee
5. Strength A picks should be hip-emphasis (Step Up, RDL · NOT Goblet Squat)
6. Joint Care block should appear before Mobility Prep with Knee Passive CARs

RUN TESTS LOCALLY (optional)
----------------------------

  pip install -r requirements.txt
  python3 -m unittest tests.test_strength_system -v

Should report · 32 tests passing.
