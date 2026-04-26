IMS PROGRAM GENERATOR · FRESH DEPLOY PACKAGE
=============================================

NEW · Cardio Rules engine

Backend audit complete. The cardio system is now driven by a real engine:

  generator/cardio_rules.py · 6 public functions

  1. normalize_cardio_profile(profile, concerns, constraints_rich)
     Merges all 3 input streams into a single normalized dict.
     Maps concern keys + rich constraint keys to canonical cardio limitations.
     Drops cleared constraints. Sets active_flare_up + post_surgery flags.
     Computes HR drop + quality (strong/normal/poor).

  2. choose_primary_cardio_machine(normalized) → (machine, rationale)
     Respects coach's primary if safe. Reroutes if risky for active limit.
     Defaults to safe priority list per joint limit.
     Falls back to stationary_bike if nothing set.

  3. determine_interval_clearance(normalized) → blocked|z2_only|controlled|full
     not_cleared / active flare / post-surgery → blocked
     poor HR recovery / deconditioned / high stress → z2_only
     cleared_for_intervals → full
     default → controlled

  4. generate_cardio_progression(normalized) → {1:..., 2:..., 3:..., 4:...}
     Three paths · deconditioned / blocked-or-z2_only / full-clearance
     Weaves baseline test data into rationale when present.

  5. generate_cardio_coach_flags(normalized) → list[str]
     Joint-specific flags + clearance flag + HR recovery commentary.

  6. filter_finishers_by_cardio_limitations(pool, normalized)
     Removes contraindicated finishers based on normalized limitations.
     Replacement pools provided for knee/back/shoulder when filter wipes pool.


PDF MODE BEHAVIOR
-----------------

  Client Plan
    Primary cardio machine in the prescription line
    4-week progression text
    Joint-friendly finishers only (no impact for knee-sensitive)
    No coach flags, no math, no warnings

  Coach Plan
    Cardio · Test Data section (baseline numbers, HR recovery)
    Machine Choice with rationale
    Interval Clearance status (BLOCKED / Z2_ONLY / CONTROLLED / FULL)
    Coach Flags section · color-coded by severity
    Picker substitution rationale

  Full Plan
    Everything in Client Plan + Coach Appendix at the end


TESTS
-----

  python3 -m unittest tests.test_strength_system  · 56 tests
  python3 -m unittest tests.test_cardio_system    · 36 tests
  Total · 92 tests passing


DEPLOY · standard Vercel flow.
