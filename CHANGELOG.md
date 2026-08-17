# Changelog

## v2.0.0 — objective measurement layer

Generator `v2.0.0` · contract `2.0.0` · protocol `ims-block-1.2`

Built against the post-audit revised plan. Phases 0 through 3 all landed.

### Phase 0 — prerequisites

- **Deleted the legacy `_fill_load()` load path.** It regexed free text out of
  `strength_marker_results`, took 70% of the first number it found, and
  appended a load to the dose string *after* `_attach_week_prescriptions` had
  already resolved a proper per-week load from the same client's test data.
  Two mechanisms writing the same field, one of them a regex, with no defined
  precedence. Five call sites removed. One mechanism writes load now.
  `strength_marker_results` is still accepted and is shown to the coach; it
  cannot touch a dose.
- **Server-side validation and `contract_version`.** New `generator/validation.py`.
  Type errors and out-of-range values are hard `400`s carrying every error at
  once; unknown fields warn and proceed. A payload declaring an unsupported
  contract major is refused. Added `POST /api/validate` and `GET /api/version`;
  version headers on every generate response.
- **"Autoregulated" is gone.** It described a fixed calendar with no
  performance input. `progression_mode` is now resolved from the client's real
  profile — `fixed_4week_block` or `individualized_4week_block · <ladder>`.
  README's progression section was also wrong in a second way (it described a
  week-4 deload the generator has never produced) and now matches the code.
- **Dead fields resolved.** `red_flags` now feeds the exercise picker as
  joint-level vetoes. `coach_notes` (the six-row textarea someone was typing
  into every week) and the legacy marker results render on a new coach page.
  `rom_degrees` feeds the ROM × force quadrant. `training_age_years` and
  `conditioning_level` added to the form and wired to Phase 2.

### Phase 1 — fits existing extension points

- **ROM × force routing** (`generator/rom_force_routing.py`) extends the
  contraindication engine with a new signal source. Advisory routes, never
  vetoes. `apply_precedence()` is the single place safety precedence is
  enforced and is proved by `TestPrecedence`.
- **Weakest-link emphasis** (`generator/weakest_link.py`) reorders
  already-approved candidate lists toward the weakest tested joint. Uses the
  weaker side per joint, not an average.
- **Load from measured isometric force** (`generator/force_load.py`), fallback
  anchor only — a tested lift always wins. Implausible loads raise (`422`)
  rather than print.

### Phase 2 — no force data required

- **Variable volume and progression** (`generator/progression_profile.py`).
  A 68-year-old deconditioned client and a 28-year-old athlete no longer
  receive the same 3×12 → 3×10 → 4×8 → 4×6. Four ladders, selected by score
  from age, training age and conditioning, with hard downshifts for 65+,
  deconditioned and post-surgical, plus a recovery-driven step down.

### Phase 3 — the plumbing

- **Side-aware dose** (`generator/side_dose.py`). `MobilityRating.side` is
  finally read. `_strength_dose()` gained `assessment` and `side` parameters,
  the dose format gained a per-side form (`L 4 × 12 · R 3 × 12`), and the PDF
  cell renderer understands it. Unilateral accessory and corrective work only.

### Found during the build, not in the plan

- **Generation was not reproducible.** The HIIT finisher was seeded with
  `hash(context)`, which Python salts per process, so the same assessment
  produced different finishers on different runs. Replaced with `crc32`.
  Without this the byte-identical regression test could not exist.
- **The 4-week ladder was hard-coded in three places** —
  `generator._strength_dose`, `plan_pdf._WEEK_4_TEMPLATE` and
  `strength_math.WEEK_TEMPLATES`. Phase 2 was dead on arrival until all three
  resolved through one source: the PDF template silently overwrote whatever
  the generator decided.
- **A DynaMo reading was anchoring compound lifts.** Caught by the plausibility
  guard the plan asked for: a 14 lb shoulder ER measurement was setting the
  load on a trap bar deadlift. DynaMo anchors single-joint work only now.
- **Per-side dose contradicted explicit doses.** Accessory exercises with a
  block-builder dose (`3 × 8/side · 2-sec hold`) were being split against the
  generic ladder, printing a per-side dose that disagreed with the dose on the
  same row. The explicit dose is now the base.
- **Two PDF glyph bugs.** The embedded serif has no `▲`/`→` glyphs and rendered
  them as unrelated letters. ASCII only on those lines.

### Not done

- `cardio_rules.py` is still a thousand lines of unread veto tables. Nothing
  here touches it. It is still carrying unexamined risk and still deserves its
  own pass.
- Rate of force development from DynaMo traces (lives in the ingest layer,
  not the generator), per-client VOLTRA resistance curves, the shared record
  with Kinetic Recovery, and the composite client score are all untouched.

## v2.1.0 — assessment capture

- **Section 07 · Objective Measures** added to `web/index.html`. DynaMo battery
  (five tests, both sides) pre-loaded on open, passive ROM rows, VOLTRA
  mid/end-range, optional previous assessment for change tracking. Unit toggle
  (lb/kg/N). Nothing entered means the key is omitted entirely — the documented
  no-data path, not an empty object.
- **Form/server vocabulary drift tests.** The server rejects an unknown DynaMo
  test id with a `400` rather than dropping it silently, which makes drift
  between the form's dropdown and the server's list an outage instead of quiet
  data loss. Three tests now assert the two lists agree, that every ROM joint
  the form offers is canonical, and that every ROM motion it offers has a norm
  in the threshold config (without one, a reading can never fire a quadrant).
- **`docs/coach-os-assessment-plan.md`** — data model, capture UI spec, profile
  UI changes, and the tenant boundary, sequenced against the two-week hardware
  deadline.
