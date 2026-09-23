# IMS device integration: VOLTRA + ActivForce only

## Source of truth
Coach OS owns client identity, assessments, permissions, and device imports. The Python generator accepts device-neutral `objective_measures`; it does not connect directly to Bluetooth devices or store vendor credentials. No VALD integration.

## VOLTRA I / Beyond+
**Phase 1 (reliable fallback):** import CSV exports from Beyond+ into a private Coach OS staging area. Manufacturer documentation confirms session CSV exports and recorded load, reps, force, velocity, ROM and power, with availability dependent on platform and whether Beyond+ was connected during training. Preserve raw source file privately, record file hash and imported timestamp, deduplicate by device/session/set/rep identity, require explicit client mapping and coach review before attaching to an assessment.

**Phase 2 (optional, access-dependent):** Beyond Cortex beta offers authorized API keys and CLI for workout history, sets and rep statistics. Request beta access from the latest Beyond+ app. The read-only commands include `voltra workout auth-check`, `voltra workout list`, `voltra workout sets <workout-id>` and `voltra workout reps <workout-id> <set-id>`; do not request device-control permissions. Beyond+ also supports Android as of June 2026. Confirm account approval, permitted data scope, stable endpoint contract and vendor terms before implementing. Read-only import first. Never automate loading resistance, changing modes or starting hardware from the program generator.

Normalize unit and protocol: lbs/kg, N if supported, position, joint angle, cable attachment, mount height, resistance mode, side, test date, rep count, force/velocity/power/ROM and firmware when available. Do not compare measurements collected using incompatible protocols.

## ActivForce digital dynamometer and goniometer
The current supported hardware is **ActivForce 2 (blue)** with the current ActivForce app and web dashboard. ActivForce says it does **not** directly integrate with third-party health apps; the dashboard's **Copy Data** feature generates a customizable text report. Start with a coach-pasted, de-identified sample Copy Data report to implement a parser; do not invent a public API or promise Bluetooth access from Coach OS. Support manual entry now: joint, movement, side, active/passive ROM degrees, force value and unit, test position, lever arm if measured, protocol, pain/tolerance and test timestamp. Add text-report import after validating an actual Copy Data sample; optional CSV only if the vendor provides a verified export.

## Generator contract
Both devices map to existing `objective_measures` only after explicit units, protocol identity, provenance and review. Missing or incompatible readings remain missing; never infer values or automatically calculate loads from unsupported units. Asymmetry calculations require matched bilateral tests under the same protocol and should not be treated as diagnostic or sole return-to-sport criteria.

## Privacy and operational rules
Synthetic test data only in CI. Restrict imports to authorized staff, encrypt private files at rest, keep client-identifying data out of logs, use explicit mapping rather than matching by name alone, and retain an audit trail of corrections. Use a manual workflow whenever the vendor API or export is unavailable.

## Vendor documentation (checked September 2026)
- VOLTRA pairing/CSV: https://help.beyond-power.com/en/articles/14247148-connecting-the-beyond-app
- Beyond Cortex beta and access: https://cortex.beyond-power.com/docs/getting-started
- Read-only workout API commands: https://cortex.beyond-power.com/docs/cortex/workout-data
- ActivForce supported model and Copy Data: https://activforce.com/pages/faqs
