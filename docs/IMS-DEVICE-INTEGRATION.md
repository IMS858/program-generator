# IMS device integration: VOLTRA + ActivForce only

## Source of truth
Coach OS owns client identity, assessments, permissions, and device imports. The Python generator accepts device-neutral `objective_measures`; it does not connect directly to Bluetooth devices or store vendor credentials. No VALD integration.

## VOLTRA I / Beyond+
**Selected IMS launch workflow (September 2026):** import CSV exports from Beyond+ into a private Coach OS staging area. Manufacturer documentation confirms session CSV exports and recorded load, reps, force, velocity, ROM and power, with availability dependent on platform and whether Beyond+ was connected during training. Preserve raw source file privately, record file hash and imported timestamp, deduplicate by device/session/set/rep identity, require explicit client mapping and coach review before attaching to an assessment.

**Deferred, not required for launch:** Beyond Cortex beta offers authorized API keys and CLI for workout history, sets and rep statistics. Request beta access from the latest Beyond+ app. The read-only commands include `voltra workout auth-check`, `voltra workout list`, `voltra workout sets <workout-id>` and `voltra workout reps <workout-id> <set-id>`; do not request device-control permissions. Beyond+ also supports Android as of June 2026. Confirm account approval, permitted data scope, stable endpoint contract and vendor terms before implementing. Read-only import first. Never automate loading resistance, changing modes or starting hardware from the program generator.

Normalize unit and protocol: lbs/kg, N if supported, position, joint angle, cable attachment, mount height, resistance mode, side, test date, rep count, force/velocity/power/ROM and firmware when available. Do not compare measurements collected using incompatible protocols.

## ActivForce digital dynamometer and goniometer
The current supported hardware is **ActivForce 2 (blue)** with the current ActivForce app and web dashboard. ActivForce says it does **not** directly integrate with third-party health apps; the dashboard's **Copy Data** feature generates a customizable text report. **Selected IMS launch workflow: structured manual entry.** Do not build an ActivForce importer or require report uploads for launch. A coach enters measurements during testing; optional future report import requires a de-identified sample. Do not invent a public API or promise Bluetooth access from Coach OS. Manual entry fields: joint, movement, side, active/passive ROM degrees, force value and unit, test position, lever arm if measured, protocol, pain/tolerance and test timestamp. Manual entry is the source of truth at launch; optional report import is deferred.

## Generator contract
Both devices map to existing `objective_measures` only after explicit units, protocol identity, provenance and review. Missing or incompatible readings remain missing; never infer values or automatically calculate loads from unsupported units. Asymmetry calculations require matched bilateral tests under the same protocol and should not be treated as diagnostic or sole return-to-sport criteria.

## Privacy and operational rules
Synthetic test data only in CI. Restrict imports to authorized staff, encrypt private files at rest, keep client-identifying data out of logs, use explicit mapping rather than matching by name alone, and retain an audit trail of corrections. Use a manual workflow whenever the vendor API or export is unavailable.

## Vendor documentation (checked September 2026)
- VOLTRA pairing/CSV: https://help.beyond-power.com/en/articles/14247148-connecting-the-beyond-app
- Beyond Cortex beta and access: https://cortex.beyond-power.com/docs/getting-started
- Read-only workout API commands: https://cortex.beyond-power.com/docs/cortex/workout-data
- ActivForce supported model and Copy Data: https://activforce.com/pages/faqs

## Confirmed IMS implementation decision
- VOLTRA: Beyond+ CSV import now; no Cortex beta access and no API dependency for launch. Obtain a de-identified real export before mapping vendor-specific columns.
- ActivForce 2: manual data entry in Coach OS now, with input validation and explicit units; no API or importer required.
- Both: show source, assessment date, test protocol and coach verification before measurements affect programming.

## Verified Beyond+ CSV sample (provided by IMS)
Actual header contains 17 columns: set/rep index, base/eccentric/chains weights (lb), ROM (m), duration (s), mean/peak velocity (m/s), mean/peak power (W), and six sampled concentric/eccentric force/velocity/power traces. The last six columns contain **semicolon-separated arrays inside CSV cells**, not single scalar measurements. Eccentric velocity and power are signed negative in the provided sample; preserve those signs. The export does **not** contain client ID, exercise, side, session timestamp or training mode, so require coach-supplied context and do not infer them. The validated pure parser is `generator/voltra_csv.py`; Coach OS import UI and private persistence remain separate work.
