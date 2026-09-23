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

## Follow-up verification and role-escalation fix (2026-09-23)

- CI run #100 on audit commit `d76b7bf` passed: https://github.com/IMS858/program-generator/actions/runs/35894684784
- Supabase migration `prevent_client_profile_role_escalation` added a BEFORE UPDATE trigger to prevent non-owner/non-service-role changes to `profiles.id`, `profiles.role` or `profiles.deleted_at`. This closes a privilege-escalation path where a self-update policy alone did not protect privileged columns. Verified with a real existing client identity under `SET LOCAL ROLE authenticated`: attempted `client -> trainer` update raised `insufficient_privilege`, role remained `client`, and the transaction was rolled back. This is a database policy test, not an HTTP/session-token penetration test.
- Rolled-back role-simulation checks: an unrecognized synthetic authenticated identity saw 0 client/assessment/program/canonical/coach-artifact rows; an existing client identity saw exactly 1 client row and 0 canonical/coach-artifact rows; an existing staff identity saw 22 clients, 4 assessments, 24 programs and 423 canonical queue rows. Measurements tables are currently empty; verify nonempty ownership isolation with synthetic fixture rows before release.
- The exercise review queue is prioritized: priority 1 = 132, priority 2 = 149, priority 3 = 142. These priorities are workflow ordering, **not** exercise safety certification. All 423 remain pending; 27 have unique exact candidates, 396 lack exact candidates and 0 safety reviews are complete.
- Additional audit concern: client UPDATE policies on `sessions` need column-level restriction or a trigger before release so a client cannot alter staff-owned scheduling/payment/completion fields. Verify application write paths before narrowing permissions.
