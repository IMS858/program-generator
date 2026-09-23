# Exercise library safety audit — development gate

**Status:** Automated inventory added; exercise-level clinical approval is NOT complete. Do not publish this library as coach-approved or enable unsupervised selection for clients with flagged joints.

## Source of truth and provenance
- Read `libraries/exercise_database.json` directly. Do not maintain a second retyped exercise list.
- Jason-supplied exercise **names** are candidate vocabulary, not approval of AI-authored contraindication tags, coaching cues, loads or doses.
- Distinguish Jason-programmed and Jason-corrected content from unreviewed generated entries. Missing provenance means **unreviewed**, not approved.
- The historical 331-name list, 423 canonical IDs and unified generator DB are different populations. Reconcile them with a crosswalk before claiming full coverage.

## Release-blocking exercise review
For each selectable exercise, review canonical ID, name, aliases, movement pattern, equipment, primary and secondary joints, loaded spine, rotation under load, impact, deep knee flexion, and knee/back/shoulder/wrist/meniscus sensitivity. Record reviewer, date, evidence/source and review outcome; do not convert draft tags to approved tags automatically.

For a flagged client, an absent or unreviewed relevant tag is **unknown** and must trigger coach review rather than be interpreted as safe. Active flare, post-surgical status, avoid-loading restrictions and red-flag free text require an explicit coach clearance path; never infer clearance from a mobility label.

## Known code concern to resolve
`Generator._is_heavy_load_for_joint` exempts all `cars`, `spinal_articulation`, `lift_off`, `hover`, `err`, `antiextension`, `isometric` and `breathing` patterns before consulting individual exercise-level pain or surgical precautions. This is not evidence that all such drills are safe for every flagged joint. Add a distinct hard-stop/review rule for active flare and post-surgery rather than treating a mobility exemption as clearance.

## Acceptance tests before release
1. Spine red flag excludes back/front squats, conventional/trap-bar deadlift variants and KB swings; verify aliases and substitution chains.
2. Knee/meniscus flare excludes impact, loaded twisting and deep loaded knee flexion; avoid-listed rower cannot reappear as a cardio alternative.
3. Red joint flag never gets a loaded exercise merely because a tag is missing; candidate is held for coach review.
4. Active flare/post-surgery never gets an automatic CARs, lift-off, PAILs or RAILs clearance.
5. Four-week progression remains conservative for deconditioned, low-recovery and recent post-surgical synthetic personas; coach review of all four weeks and PDF.
6. No duplicate exercises within a session; anchor loads are pattern-specific; client PDF matches reviewed JSON.

**Audit artifacts:** `tests/test_exercise_library_inventory.py` prints the real DB shape, counts, populated safety fields and duplicate-name indicators in CI. The output is an inventory, not a medical safety certification.

**Approval required:** Jason or a qualified IMS coach must sign off on exercise-level safety tags and prescription thresholds before broad automatic use.

## Canonical workbook extraction (2026-09-23)
The source `IMS_Exercise_Database(1).xlsx`, `All Exercises` tab, contains **423** rows with **423 unique canonical IDs and 423 unique names**. Provenance: 306 Jason supplied; 28 Jason programmed; 25 Jason supplied + programmed; 2 Jason corrected; 60 Claude draft unreviewed; 1 Claude draft + Jason programmed; 1 rule only. The `Safety tags set` column is **Yes on 8 / 423** and **No on 415 / 423**. These workbook indicators do not certify clinical safety or prove the generator's separate 604 entries have been reconciled. A UTF-8 CSV was exported for the read-only `scripts/reconcile_exercise_ids.py` tool; the crosswalk has not yet been executed against both complete datasets in one environment.

## Regression gate status
The existing four-week/PDF suite generated an 85-page synthetic coach PDF during the September 23 CI run, but the strict picker patch produced two **no eligible exercise** errors for flagged shoulder and low-back personas and one unrelated anchor-load assertion failure. These are release blockers; do not interpret a fail-closed generator error as a usable completed client plan. The unrestricted tested-exercise match was restored in a follow-up patch; the flagged-persona behavior still needs a coach-approved substitution pool or explicit UI hold workflow. Do not merge or deploy while CI is red.
