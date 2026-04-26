IMS Program Generator · Deploy Bundle
======================================

What's in this build (Apr 26, 2026):

CARDIO BACKEND
  - cardio_rules.py · contradiction detection, decide_machine_with_audit,
    safe-substitute helper, knee_sensitive Deep Squat veto
  - HIIT block becomes "Conditioning Reset" when intervals blocked
  - Client cardio session pages render full 4-week progression
  - Coach appendix shows DECISIONS section (machine selected, alternatives
    rejected, contradictions resolved)

CARDIO FRONT-END
  - 3-state radio for interval clearance (not_assessed default)
  - Auto-calc HR drop with manual override support
  - Save/load round-trip for cardio profile + concerns + constraint cards
  - Clear form fully resets dynamic state
  - Constraint card summaries update live as fields are filled
  - Preview Data button (JSON modal)

STRENGTH ANCHOR SYSTEM
  - generator/strength_anchor_resolver.py · 132 aliases / 9 groups
  - normalize_exercise_name, build_anchor_aliases, resolve_anchor_for_exercise,
    apply_anchor_to_program_exercise, AnchorUsageTracker
  - Picker prefers TESTED exercise name when alias-matched
  - Strength A AND Strength B both attach week_prescriptions to all exercises
  - Exercise dataclass has anchor_match_method, anchor_source_name,
    anchor_rendered_with_loads as proper fields (so they survive JSON
    serialization)
  - Category-only match attaches rep scheme but nulls wrong-family weight
  - Coach appendix walks actual program objects · shows USED/UNUSED with
    match method, wp ✓/✗, loads ✓/✗ debug indicators
  - Strength math section no longer capped (was 6, now unlimited)

DATA SANITATION
  - "form: ?" → "form: not recorded"
  - "Pulllups" → "Pull-ups" (and other typo normalizations)
  - "bilateral side" → "bilateral"
  - Suspiciously low weights flagged (e.g., "3 lb is unusually light for
    trap_bar deadlift · likely data entry error")
  - Truncated avoid notes flagged

TESTS
  - 119 tests passing
    - 56 strength_system
    - 44 cardio_system (incl. Amanda regression class)
    - 19 strength_anchor_resolver

DEPLOY
  Drop this folder onto Vercel as a fresh project (or replace your existing
  project's contents). vercel.json is included. Python runtime · 3.11+.

KNOWN ISSUE
  Weekly Routine page (section 09) still shows "Zone 2 / intervals" in the
  Recovery column for cardio days even when interval clearance is blocked.
  Static string · not driven by the cardio rules engine. Flagged for next pass.
