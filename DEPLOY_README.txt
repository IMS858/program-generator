IMS PROGRAM GENERATOR · FRESH DEPLOY PACKAGE
=============================================

This zip contains the COMPLETE working repo · everything needed to deploy
from a fresh GitHub repo. Just unzip, push, deploy.

WHAT'S INSIDE
-------------

Repo root files ·
  .gitignore               · excludes __pycache__, .vercel, etc.
  app.py                   · Flask entry point (Vercel runs this)
  vercel.json              · explicit Vercel config for Python
  requirements.txt         · flask · reportlab · Pillow
  README.md                · project overview
  DEPLOY.md                · longer deploy notes
  LICENSE                  · MIT
  DEPLOY_README.txt        · this file

assets/                    · IMS logos (4 PNGs)
  ims_logo_full.png
  ims_logo_tight.png
  ims_logo_white.png
  ims_mark_only.png

examples/                  · sample client payload
  README.md
  example_sarah.py

generator/                 · the program-building engine
  generator.py             · main builder · 4-week block · picker · mobility
  plan_pdf.py              · PDF rendering · 4-week strength table · pages
  strength_markers.json    · legacy marker library (still referenced)
  strength_math.py         · NEW · IMS Technical Training Max math
  strength_testing.py      · NEW · StrengthTest dataclass · 18 fields

libraries/                 · exercise databases (JSON)
  base_position_library.json
  cars_library.json
  exercise_database.json   · 604 exercises · v2.4
  iso_ramping_library.json
  pails_rails_library.json

tests/                     · unit + acceptance tests
  __init__.py
  test_strength_system.py  · 26 tests across 6 categories

web/                       · the form
  index.html               · client intake form with Strength Testing Anchors


DEPLOY STEPS
------------

1. Create your fresh GitHub repo (name it whatever, e.g. ims-program-generator)

2. Unzip this package locally · cd into the unzipped folder

3. Initialize and push ·
     git init
     git add .
     git commit -m "Initial commit · IMS Program Generator v1.0"
     git branch -M main
     git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
     git push -u origin main

4. Connect to Vercel ·
     - Go to vercel.com → New Project
     - Import the GitHub repo
     - Vercel will auto-detect Python from vercel.json
     - Click Deploy

5. Wait ~1 minute for first build to finish

6. Visit your Vercel URL · the form should load


VERIFY THE DEPLOY
-----------------

1. Form loads · scroll to Section 05 · "Strength Testing Anchors"
   should show collapsible cards

2. Fill in a quick test client ·
     Name: Test
     Age range: any
     Strength days: 3
     Cardio days: 1
     FRA priority: Hip IR L+R
     Mobility row: hip / IR / L / yellow
     Strength Anchor: DB Bench Press · per_hand · 8RM = 50

3. Click Generate Plan · PDF should download

4. Open the PDF ·
     - Page 10 (LB Day 1 strength A) · should show personalized loads
     - Page 16 (LB Day 4 strength A) · should show DIFFERENT squats
       than Day 1 (variation working)
     - Page 23 · should say "How we keep adapting" · NOT "Notice, adjust, grow"


RUN TESTS LOCALLY (optional)
----------------------------

  pip install -r requirements.txt
  python3 -m unittest tests.test_strength_system -v

Should report · 26 tests passing in ~14 seconds.


IF SOMETHING 500s
-----------------

Vercel → your project → Deployments → latest → Runtime Logs tab.
Trigger the error in your browser, then check the logs for a Python
traceback. That'll point to the issue immediately.
