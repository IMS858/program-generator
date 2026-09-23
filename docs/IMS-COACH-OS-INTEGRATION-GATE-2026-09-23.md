# IMS Coach OS integration gate — 2026-09-23

**Status:** development audit; NOT production approval. No client data was copied into the generator. PR #1 remains draft.

## 1. Supabase access control — applied and verified

Project: IMS Coach OS. Applied migration `restrict_objective_measurements_to_ims_staff`.

- Replaced `measurements_auth` (authenticated `USING true / WITH CHECK true`) with `measurements_staff_all` (staff predicate `(select public.is_trainer())` for both).
- Replaced `session_measurements_auth` (authenticated `true/true`) with staff-only ALL plus client-owned SELECT (`client_id = (select auth.uid())`).
- Verified `pg_policies` reflects all three replacement policies. **Live impersonated JWT tests have not yet been performed**; do not claim complete cross-account isolation until owner/trainer/client A/client B API tests pass.
- Remaining security advisor notices: one `intake_tokens` RLS table without policies (may intentionally be server-only), four authenticated-executable SECURITY DEFINER functions (two staff-gated session-counter mutations; `is_owner` and `is_trainer` role checks), `citext` in public, and leaked-password protection not enabled. Review and test before modifying existing auth flows.
- Performance advisors identified missing FK indexes and auth function re-evaluation. These are follow-up migration work, not permission to weaken RLS.

## 2. Canonical exercise reconciliation — read-only findings

- `public.canonical_exercise_queue`: **423** entries; all **423 pending** mapping review.
- **27** entries have one exact-name candidate, **396** have no exact candidate, **0** have ambiguous exact candidates.
- Only **8 / 423** source rows indicate safety tags present. `public.exercise_reviews` contains **0** completed reviews.
- The generator/Supabase exercise library has **604** entries. Exact-name candidates are NOT approved mappings or safe substitutions. Preserve source status, canonical ID, aliases and manual reviewer/date/notes; do not infer contraindication clearance from names.
- For flagged joints, post-surgical status, active flare or missing evidence, the generator must return an explicit coach-review hold rather than silently choosing a plausible exercise.

## 3. Generator and client-workflow acceptance

- Generator branch `audit/fix-generator-reliability-2026-09`, draft PR #1: https://github.com/IMS858/program-generator/pull/1
- CI run #99 passed **284 tests** after correcting synthetic persona assertions for strength + cardio sessions, actual `week_number` schema and expected coach-review holds: https://github.com/IMS858/program-generator/actions/runs/35893691753
- Verify in a staging environment using fictional client A and B: (a) client A cannot read B's assessments, measurements, session measurements, documents or draft programs; (b) trainer can access authorized clients; (c) unpublished programs are not client-visible; (d) coach-review holds display clearly and block PDF publishing; (e) edited four-week reviewed JSON exactly matches rendered PDF, including rotating exercises and page boundaries; (f) ActivForce 2 readings preserve device/test/side/position/unit/date and cannot silently become a load prescription.
- The Google Drive `IMS-Plan-System-v3` document provides a reference layout for intake, body composition, mobility, strength, nutrition and goals; treat it as a UI reference, not as authorization to import identifiable client data.
- Vercel access to the `innovative-movement-solutions` team returned **403 scope authorization**. Reconnect that team scope before staging deployment or browser E2E checks. No deployment or merge was performed.

## Release hold

A green generator unit suite is necessary but not sufficient. Obtain qualified coach sign-off for safety tags/substitution pools, pass cross-account JWT tests and staged end-to-end PDF review, resolve Vercel scope access, and keep PR #1 unmerged until these gates are satisfied.
