# IMS Method — Assessment & Program Generator

> **Move better. Get stronger. Stay active for life.**
>
> Innovative Movement Solutions · Scripps Ranch, San Diego

A movement coaching platform that turns an in-studio assessment into a personalized 15-page training plan. Built on the IMS Method · joint-first strength training, FRC/FRA/Kinstretch methodology, and 4-week autoregulated progressions.

---

## What's in this repo

| Folder | Purpose |
|---|---|
| `web/` | Browser-based assessment form (served at `/`) |
| `api/` | Vercel serverless function that generates the PDF (served at `/api/generate`) |
| `generator/` | Python program generator · turns assessment data into a 4-week plan |
| `libraries/` | Exercise databases (CARs, PAIL/RAIL, End-Range, Iso Ramping, Base Positions) |
| `assets/` | Logo variants |
| `examples/` | Example client data and reference implementations |

---

## Quick start

### Deploy to Vercel (recommended)

The web form talks to a serverless Python function that generates the PDF on demand. Full setup in **[DEPLOY.md](DEPLOY.md)**.

TL;DR:
1. Push this repo to GitHub
2. Connect it to [vercel.com](https://vercel.com) → Import Project → Deploy
3. Done · your form is live at `your-project.vercel.app`

### Run locally (for development)

```bash
git clone https://github.com/YOUR_USERNAME/ims-method.git
cd ims-method
pip install -r requirements.txt
```

Requires Python 3.9+ and Lora + Poppins fonts installed on your system (free from Google Fonts).

### 2 · Run an example

```bash
python examples/example_sarah.py
```

This will ·
- Build a 4-week program for the example client "Sarah"
- Save `examples/sarah_program.json`
- Render `examples/sarah_plan.pdf` (14 pages)

### 3 · Use with a real client

**Option A — Web intake (recommended)**

Open `web/index.html` in any browser. Fill out the form during or after an in-studio assessment. Tap *Generate Plan Data*. Download the `.py` file it produces, place it in `examples/`, then run it ·

```bash
python examples/client_YOUR_CLIENT.py
```

**Option B — Code directly**

Copy `examples/example_sarah.py` to `examples/client_your_name.py`, edit the fields, and run it.

---

## The IMS Method · what the generator does

Every plan follows the same architecture ·

1. **Passive Stretch** · 2 min at priority joint
2. **Mobility Prep (RAILs-based)** · Lift-Offs / Hovers / ERRs at priority joints (no PAIL/RAIL combos here)
3. **Strength A** · 2 compound lifts, individualized to constraints
4. **Strength B** · 2–3 accessory + corrective lifts
5. **Dynamic Cool Down** · PAIL/RAIL combos allowed (end of session only) + daily CARs

**4-Week Progression · autoregulated**

- Week 1 · establish pattern
- Week 2 · push one progression lever (load, reps, iso hold, or tempo)
- Week 3 · extend or add a second lever
- Week 4 · deload -30–40% and re-test

**FRA Priority Rotation**

For multi-session weeks, priorities rotate across training days. Lower-body priorities land on LB days, upper-body priorities on UB days, cardio day gets no FRA focus.

**Constraints**

Spine-sensitive clients automatically get split squats and SL RDLs instead of traditional back squats and deadlifts. Pass `constraints=["SI_joint_sensitivity", "no_axial_loading"]` to activate.

**Nutrition (optional)**

If BOD POD data is provided, the generator calculates ·
- RMR via Katch-McArdle (lean mass-driven, more accurate than weight-only estimators)
- TDEE via activity factor
- Macro targets matched to strategy (maintenance / fat-loss / strength / endurance)
- Sample daily meal flow

---

## Web form

`web/index.html` is a single-file app. No build step, no dependencies. Drop it on any static host (GitHub Pages, Netlify, Vercel, or even a USB stick) and it works.

**What it captures ·**

- Client basics (name, age, sex, background, frequency)
- Primary goal
- FRA priorities (unlimited · add/remove rows)
- Mobility map with traffic-light rating (red/yellow/green)
- Strength markers tested (freeform · exercise name + result)
- Constraints
- Body composition (optional · BOD POD)
- Nutrition strategy
- Coach notes

**Outputs ·**

- Copy JSON to clipboard
- Download `.json`
- Download `.py` file ready to run through the generator

---

## Development

**Generator · `generator/generator.py`**
Core program builder. `Generator().build_program(assessment)` → `Program` (4 weeks, N sessions each).

**PDF · `generator/plan_pdf.py`**
Editorial 15-page PDF renderer using Lora serif + Poppins sans. Matches the imsmethod.com aesthetic · deep navy background, sky-blue italic emphasis, cream body text, 4-week progression tables for strength blocks.

**Exercise libraries · `libraries/*.json`**
568 unified exercises across 8 libraries (CARs, PAIL/RAIL, End-Range, Iso Ramping, Full Range, Base Positions, Strength Markers, Assessment Logic).

---

## Roadmap

- [ ] Session notes / client feedback capture
- [ ] Real photography in PDF placeholders
- [ ] Supabase/Vercel backend for assessment persistence
- [ ] Retest workflow (Block 2 progression from Block 1 results)
- [ ] InBody integration for full body comp (visceral fat, body water)

---

## License

MIT · see `LICENSE`

---

**Innovative Movement Solutions**
10625 Scripps Ranch Blvd, Suite D · San Diego, CA 92131 · (619) 937-1434
[imsmethod.com](https://imsmethod.com)
