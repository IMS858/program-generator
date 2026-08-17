# Coach OS · assessment capture + profile UI

**Hardware lands in ~2 weeks.** This plan is organized around one deadline and
one asymmetry:

> You can visualize a measurement any time. You cannot go back and take one you
> never took.

Everything in Sprint A exists to make sure that on day one of the DynaMo and
VOLTRA being in the studio, numbers get captured, stored, and attached to the
right client. Nothing else is allowed to compete with that.

The generator side is already done and tested — it accepts an
`objective_measures` object and returns a plan that routes off it. Contract in
[`docs/objective-measures-contract.md`](objective-measures-contract.md). Coach
OS's job is to capture, store, and display.

---

## Sprint A · before the hardware arrives (2 weeks)

**Definition of done:** Jason can walk a client through a full instrumented
assessment on an iPad, hit save, and generate a plan off it — even if nothing
looks pretty yet.

### A1 · Data model (day 1–2)

Three tables. Deliberately not four — measurements do not get their own
lifecycle separate from the assessment that produced them.

```sql
-- one instrumented assessment event
assessments (
  id                uuid primary key,
  client_id         uuid not null references clients(id),
  coach_id          uuid not null references coaches(id),
  measured_on       date not null,
  bodyweight_lb     numeric,
  status            text not null default 'draft',   -- draft | final
  notes             text,
  created_at        timestamptz default now(),
  finalized_at      timestamptz
);

-- one reading. force and ROM share a table on purpose · they are the same
-- shape and every consumer wants them together.
measurements (
  id                uuid primary key,
  assessment_id     uuid not null references assessments(id) on delete cascade,
  kind              text not null,      -- force | rom
  device            text not null,      -- dynamo | voltra | goniometer
  test              text not null,      -- knee_extension | shoulder_flexion | trap_bar_deadlift
  side              text not null default 'bilateral',   -- L | R | bilateral
  position          text,               -- mid_range | end_range (voltra only)
  value             numeric not null,
  unit              text not null,      -- lb | kg | N | deg
  entered_by        text not null default 'manual',      -- manual | vald_api
  created_at        timestamptz default now()
);

-- what the generator decided, snapshotted. NOT recomputed on read.
generated_plans (
  id                uuid primary key,
  client_id         uuid not null references clients(id),
  assessment_id     uuid references assessments(id),
  generator_version text not null,
  contract_version  text not null,
  protocol_version  text not null,
  request_payload   jsonb not null,
  objective_summary jsonb,              -- program.objective, verbatim
  progression       jsonb,              -- program.progression, verbatim
  pdf_url           text,
  created_at        timestamptz default now()
);
```

Two decisions worth defending:

**Store the request payload, not just the result.** When a threshold changes
six months from now and a plan looks different, you need to be able to prove
what went in. `request_payload` is the audit trail.

**Never recompute a past plan's routing.** `objective_summary` is a snapshot.
The thresholds are going to move — that's the whole point of putting them in a
config file — and a plan the client trained off must keep saying what it said
when they trained off it.

RLS: assessments and measurements are scoped to `client_id` through the
existing IMS Core coaching relationship. **Tenants must not appear anywhere in
this policy.** See "the tenant boundary" below.

### A2 · Capture screen (day 3–7) — the critical path

This is the piece that must be right. Everything else can be ugly.

The capture UI is a **coach-with-a-client-in-front-of-them** interface, not a
data entry form. Design constraints that follow from that:

- **The battery is pre-loaded.** Five DynaMo tests, both sides, already on
  screen when the page opens. No "add row" before the first number.
- **Numeric keypad, tab order down the column.** Coach reads L knee, R knee, L
  hip, R hip off the device. Tab order must match the order the numbers arrive
  in, which is per-test bilateral, not all-lefts-then-all-rights.
- **Autosave on blur.** Never a save button standing between a measurement and
  the database. The assessment is a `draft` row from the first keystroke.
- **Nothing is required.** Partial assessments are normal — a client with a
  flared shoulder skips shoulder tests. The generator handles partial data by
  emitting no signal for half-measured joints; the UI must not fight that with
  required-field validation.
- **Show last time's number, greyed, next to the input.** This is the single
  highest-value affordance on the screen. It catches transcription errors in
  the moment (a 60 that should have been 160) and it lets the coach say
  something useful to the client during the assessment instead of two days
  later.

A working reference implementation already exists: section 07 of
`web/index.html` in the generator repo. It's a single-file, no-build version of
exactly this screen and it round-trips to a generated PDF today. **Use it as the
spec, and as the fallback** if Coach OS slips — a coach with a browser and that
form can capture a full assessment on day one regardless of what else is ready.

### A3 · Wire generate to the stored assessment (day 8–9)

Coach OS builds the `objective_measures` object from the latest two `final`
assessments for that client and POSTs it with the rest of the payload. The
previous assessment comes from the database, not from the coach retyping it.

Call `POST /api/validate` on save. It returns the same errors `/api/generate`
would, without generating anything — so a bad measurement surfaces while the
coach is still in the room, not two days later when they go to print a plan.

Handle `422 implausible_load` explicitly with a visible message. It means a
number, an equipment tag, or a threshold is wrong, and it needs a human.

### A4 · Dry run (day 10) — do not skip

Before the hardware arrives, run three real client files through the whole
path with **invented numbers**: capture → save → generate → read the coach PDF.
You are testing the plumbing, not the numbers.

What you're specifically looking for: does the coach page tell you something
you'd actually act on, and does anything on it look confidently wrong? The
thresholds are unvalidated heuristics. This is the cheapest moment to find out
that one of them is embarrassing.

---

## Sprint B · first four weeks of real data

Now the hardware is in the room and numbers are accumulating. Nothing here
blocks capture.

### B1 · Client profile — the measurement tab

**Where the profile UI work actually starts.** One new tab on the existing
client profile. Four blocks, in this order:

1. **Latest assessment, with deltas.** The measure table, previous value beside
   current, change flagged only when it clears the meaningfulness threshold.
   Unflagged changes render in grey — most of them are noise and presenting
   them as progress teaches the coach to distrust the whole panel.
2. **The quadrant.** A 2×2, joints plotted, with the suppressed ones visibly
   suppressed. This is the screen that earns the equipment. It's also the one
   Jason can turn toward the client and explain in fifteen seconds.
3. **Asymmetry bars.** L/R per test, threshold line drawn.
4. **Trend, once there are three or more assessments.** Not before — a
   two-point line is a slope with no error bars and it will get over-read.

### B2 · Profile header changes

Small, everywhere: a "last assessed" chip with the date, amber past ~75 days
(the config's staleness warning), and a one-tap "start assessment" from the
profile. Retest cadence is the thing that will actually slip, and the fix is
making the gap visible on a screen Jason already looks at.

### B3 · Client-facing view — deliberately later, deliberately less

Nothing measured currently appears on a client plan and that should stay true
by default. When it does ship, ship **one** thing: a single joint's change over
time, chosen by the coach, with plain-language framing.

The temptation here is a composite score. It is motivating and shareable and
it is also the easiest way to invent precision you do not have. If it gets
built, define it conservatively and publish the definition.

---

## Sprint C · after the pattern is established (~8 weeks in)

- **VALD API ingest.** Replaces manual entry for DynaMo. Needs the Hub seat
  question resolved. Not urgent: manual entry of ten numbers takes under a
  minute and is not the bottleneck.
- **Rate of force development.** The DynaMo API returns force traces, not just
  peaks. How fast a client reaches force declines earlier with age than how
  much they reach. Nearly free once ingest exists, and it lives in the data
  layer — it does not touch the generator.
- **Threshold tuning UI.** Once there are ~30 assessments, the config numbers
  can be reviewed against the roster instead of against intuition. An admin
  screen for this beats editing JSON in github.dev.

---

## The tenant boundary — decide this before writing the RLS policy

"Change the UI on all the profiles" needs one distinction made explicit,
because it is structural and it is easier to get right now than to unwind.

**Client assessment data belongs to IMS Core coaching. It is not tenant data.**

- Laryssa, Kevin, Ashley, Andrew and Gabe are independent practitioners. The
  portal's relationship to them is landlord-to-tenant.
- A tenant seeing IMS coaching clients' force measurements is not a feature —
  it cuts against the flat-rent structure and it is a privacy problem
  independent of that.
- So: **two different profile surfaces, not one with permissions layered on.**
  The client profile (with the measurement tab) lives in the coaching side of
  Coach OS. The tenant profile stays what it is.

The referral workflow is the legitimate bridge, and it should carry a
*referral*, not a dataset: "Jason is referring this client to you for X," with
the client's consent, not a window into their assessment history. If a shared
objective record with a co-located practice is ever worth building, it costs a
real permissions model and an explicit client consent step — worth doing
deliberately, not worth arriving at by accident through a profile redesign.

---

## What I'd cut if the two weeks compress

In order, first to go:

1. Trend charts (B4) — needs three assessments to exist anyway
2. Anything client-facing (B3)
3. The quadrant visual (B1.2) — the coach PDF already prints it in words
4. Profile header chips (B2)

**Never cut:** the data model, the capture screen, and the dry run. If only
those three exist when the boxes are opened, you are fine. If the capture
screen is late and the charts are beautiful, you have lost measurements you
cannot get back.
