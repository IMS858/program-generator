# IMS Method — Assessment & Program Generator

> **Move better. Get stronger. Stay active for life.**
>
> Innovative Movement Solutions · Scripps Ranch, San Diego

A movement coaching platform that turns an in-studio assessment into a personalized 15-page training plan. Built on the IMS Method · joint-first strength training, FRC/FRA/Kinstretch methodology, and structured 4-week progressions individualized by age, training age and conditioning.

**v2.0** adds an optional objective-measurement layer · VALD DynaMo peak isometric force, passive ROM, and VOLTRA mid/end-range compound force feed exercise routing, selection emphasis and load prescription. See [Objective measures](#objective-measures--v20) and [`docs/objective-measures-contract.md`](docs/objective-measures-contract.md).

---

## What's in this repo

| Folder | Purpose |
|---|---|
| `web/` | Browser-based assessment form (served at `/`) |
| `api/` | Vercel serverless function that generates the PDF (served at `/api/generate`) |
| `generator/` | Python program generator · turns assessment data into a 4-week plan |
| `libraries/` | Exercise databases (CARs, PAIL/RAIL, End-Range, Iso Ramping, Base Positions) |
| `config/` | Threshold config · every cutoff the objective layer uses, in one tunable file |
| `docs/` | The `objective_measures` payload contract |
| `assets/` | Logo variants |
| `examples/` | Example client data and reference implementations |
| `tests/` | 217 tests · `python3 -m unittest discover -s tests -t .` |

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

**4-Week Progression · a fixed ladder, individualized per client**

This is a structured calendar, not autoregulation · nothing in the block reads
performance back and adapts to it. Earlier versions of this README and of the
generated PDF called it "autoregulated", which described something the system
does not do. It now says what it is.

Which ladder a client gets is resolved from age, training age, conditioning
level and their recovery factor (`generator/progression_profile.py`). Before
v2.0 every client received the `_default` row regardless.

| Ladder | Who | Compound W1–W4 |
|---|---|---|
| `aggressive` | Under 50, intermediate+, well conditioned | 3×12 · 4×10 · 4×8 · 5×5 |
| `moderate` | Most of the roster | 3×12 · 3×10 · 3×8 · 4×8 |
| `conservative` | 65+, deconditioned, or post-surgical · forced regardless of score | 2×12 · 2×12 · 3×10 · 3×10 |
| `_default` | No age / training age / conditioning on file · the legacy ladder | 3×12 · 3×10 · 4×8 · 4×6 |

The conservative ladder has no peak week. A client who should not be peaking
does not get a week that tells them to.

Low recovery (sleep, stress, resting HR) steps a client one ladder more
conservative. `deconditioned` and `65+` force the conservative ladder outright.

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

## Objective measures · v2.0

Optional. Most clients have no instrumented data for months and some never
will · **absent data produces byte-identical output to v1.0**, and there is a
test class that exists solely to keep it that way.

POST an `objective_measures` object alongside the rest of the payload. Full
schema in [`docs/objective-measures-contract.md`](docs/objective-measures-contract.md). Section 07 of the assessment form captures it directly; the Coach OS build plan is in [`docs/coach-os-assessment-plan.md`](docs/coach-os-assessment-plan.md).

**1 · ROM × force routing.** For each joint with both a ROM reading and an
end-range force reading, the quadrant separates *can't reach because they're
weak there* from *can't reach because tissue won't let them* ·

| ROM | End-range force | Verdict | Route |
|---|---|---|---|
| Limited | Weak | Capacity problem | Load the end range progressively |
| Limited | Normal | Passive restriction | Unload the joint · refer for manual therapy |
| Full | Weak | Uncontrolled range · **highest priority** | Earn control before load |
| Full | Normal | No signal | — |

These are **advisory routes, never vetoes**. A hard contraindication suppresses
any signal that would route work *toward* a blocked joint, and the suppression
is printed on the coach page rather than happening silently. Routes *away* from
a joint always survive · they only add caution.

**2 · Weakest-link emphasis.** Force normalized to bodyweight, ranked across
tested joints, weakest side per joint (not an average). The lowest one or two
bias exercise selection. Selection bias only · it reorders a list the
contraindication router has already approved.

**3 · Load from measured force.** Where a tested anchor doesn't resolve, a
measured isometric value serves as the anchor · load is a percentage of that
client's own measured force rather than a population rep-max formula. A DynaMo
reading anchors single-joint work only; compounds need a VOLTRA pattern match
or a tested lift. Any computed load implausible for the exercise's equipment
**raises rather than prints** (HTTP 422) · a wrong number on a client's plan is
worse than a failed generation.

**4 · Side-aware dose.** When one side is materially weaker — measured
asymmetry above threshold, or a red/yellow gap in the mobility map — the weaker
side earns one extra set on unilateral accessory and corrective work
(`L 4 × 12 · R 3 × 12`). Compounds are excluded: adding a set to one side of a
bilateral lift is not a coherent prescription.

Every force-driven decision is annotated with the measurement and the date that
caused it, on a coach-only page. Nothing measured appears on a client plan.

**Thresholds.** Every cutoff lives in
[`config/objective_thresholds.json`](config/objective_thresholds.json) and
nowhere else. They are unvalidated starting heuristics and are expected to be
tuned.

---

## Versioning

Three stamps travel with every program and every PDF ·

| Stamp | Meaning | Bump when |
|---|---|---|
| `generator_version` | the code that built the plan | anything can change a printed prescription |
| `contract_version` | the shape of the payload Coach OS sends | major on any breaking field change |
| `protocol_version` | the IMS training protocol expressed | block structure or progression philosophy changes |

`POST /api/validate` dry-runs the validator without generating a PDF · Coach OS
can call it on save to surface field problems while the coach is still in front
of the client. `GET /api/version` reports what a deployment is actually running,
which matters when a deploy half-lands.

A payload declaring an unsupported `contract_version` major is refused rather
than half-understood.

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
