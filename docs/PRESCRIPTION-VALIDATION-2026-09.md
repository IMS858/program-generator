# Generator prescription validation — 2026-09

## Implemented and tested
- Reject malformed/missing threshold configuration instead of silently replacing it with empty defaults.
- Validate mass units and plausible lean/total body mass before estimating nutrition; support explicitly labelled kg and legacy pounds.
- Reviewed PDF contract rejects week-to-week exercise or block changes that week-one-based session pages would misrepresent, while allowing week-specific dose changes.
- Synthetic API scenarios exercise general strength, constrained two-day training, low recovery with missing body composition, and kg-labelled body composition; verify JSON plan, four weeks, and PDF header.

## Release blocker discovered by scenario testing
The initial generator intentionally rotates some exercises and blocks between weeks, but the existing PDF's detailed session pages draw from week one. The reviewed-program validator now correctly rejects this structural drift rather than quietly misrepresenting later weeks. The initial generator still produces a PDF with the legacy week-one-based presentation. Before production, either render each week's distinct exercises on week-specific PDF pages and update the editor accordingly, or make initial generation hold exercise/block structure constant while retaining week-specific doses. **Do not weaken the reviewed validator to allow silent mismatch.**

## Remaining prescription-quality review
- Coach review of synthetic PDFs and exercise selection for red joints, pain, equipment constraints, training age, cardio tolerance, progression and recovery.
- Remove/retire legacy VALD/DynaMo naming and unsafe implicit ROM-mode defaults; support ActivForce 2 contract explicitly.
- Full Coach OS authenticated assessment-to-publish test in isolated environment.
