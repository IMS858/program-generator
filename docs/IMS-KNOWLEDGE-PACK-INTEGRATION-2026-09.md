# IMS September 2026 knowledge-pack integration gate

Source materials: Jason's decision register D-001..D-040, IMS Knowledge Transfer, IMS programming rules, synthetic generator test cases, and IMS Exercise Database (423 canonical exercises; 447 registry rows including aliases). This document tracks *source authority*, not automatic permission to prescribe.

## Precedence
1. Later explicit Jason decisions supersede older choices. D-005 replaces D-004: four-week compound ladder 3x12 / 3x10 / 4x8 / 4x6; RPE 7 / 7-8 / 8 / 8-9. Do not automatically create six-week pyramid plans.
2. Confirmed hard contraindications outrank exercise anchors, test-derived signals, exercise categories, and equipment availability. D-013 prohibits every trap-bar variant and KB swings with spine red flags, including ordinary SI flags; resolve strength_markers.json conflict D-027 in favor of D-013.
3. Blocked interval clearance means Zone 2 only throughout plan and both PDFs (D-014).
4. D-017..D-019: ActivForce 2, belted manual isometric force including hip flexion, and explicitly classified active/passive ROM. No VALD-specific workflow.
5. VOLTRA dynamic workout CSV is descriptive, not a peak isometric test. D-028 protocol classification unresolved: no dynamic data into force anchors, force/ROM quadrant, or estimated 1RM.
6. Saved reviewed plan JSON is authoritative; PDFs are derived exports; coach approval precedes publishing (D-032).

## Exercise database ingestion contract
- Key every canonical exercise by EX-0001..EX-0423; maintain the 447-row alias registry separately. A name and grouping are approved *candidates*, not approved prescriptions.
- Only type=alias entries with the *same canonical exercise ID* may inherit a strength anchor. Exact > alias > category for candidate matching, but a category match must never transfer a numerical load to a different movement family.
- Keep Pull-Up EX-0192 and Lat Pulldown EX-0198 distinct. Keep Hip Thrust EX-0121 and Single-Leg Glute Bridge EX-0129 distinct. Jason's 3 Point Row is alias of DB Row EX-0175.
- Store safety-tag provenance separately. The uploaded workbook marks safety tags missing on the majority of rows; Claude-draft tags/cues are not Jason-approved. For flagged joints, missing tags require review, not silent 'safe' classification (D-025 proposed policy; fail closed until decision).
- Never automatically prescribe a coach recovery/table-work modality to clients to perform unsupervised.

## Automated test rollout
- **Confirmed, binding**: TC-01..04 spine/joint/cardio routing; TC-07..09 session pairing, no duplicates, anchor precedence; TC-14 four-week ladder; TC-16 verified RM and technical max, except exact form reduction remains open.
- **Split into binding and pending subassertions**: TC-11 2:1 pulling intent confirmed, counting method unapproved; TC-12 CARs precede warmup as Jason stated, full vs priority-only default open; TC-16 5-10% form reduction range proposed until point chosen; TC-17 threshold 12% vs 15% open; TC-21 power concept approved but dose and eligibility open.
- **Approval-gated**: TC-05 permanent surgery flags, TC-06 untagged safety policy, TC-10 force-signal suppression implementation, TC-13 VOLTRA modes/eccentric restrictions, TC-15 individualized ladder, TC-20 side-aware +1 set. Do not turn proposed expected values into silently binding behavior.
- **Measurement safety**: reject ambiguous embedded-unit strings; accept numeric value plus explicit unit only; enforce plausible force and measurement date/side/protocol; verify kg/N conversion and provenance. Dynamic VOLTRA export cannot create a force anchor.
- **PDF acceptance**: extract text from actual rendered client and coach PDFs for each synthetic fixture. Confirm each week's exercises/doses, Zone 2 only when blocked, no prohibited exercise, long constraints wrapped, and no coach-only notes in client PDF. No successful generator-only assertion substitutes for PDF validation.

## Unresolved Jason decisions
D-006 block/retest cadence; D-015 full vs priority CARs; D-020 inconsistency threshold; D-022 force-derived loading; D-024 meaningful-change thresholds; D-025 missing-tag handling; D-026 alias vs substitution exceptions; D-028 VOLTRA test types. Also test-specific approvals noted above. Default these to coach review or non-prescriptive display rather than inventing thresholds.

## Release gates
1. Import exercise IDs and aliases with duplicate/collision tests; preserve the existing generator library and annotate migration mappings rather than replacing it blindly.
2. Run confirmed synthetic cases through JSON + both actual PDFs; report failures separately from unapproved expectations.
3. Review real anonymized assessments with Jason and record changes as versioned decisions.
4. Confirm Coach OS private evidence storage, draft/edit/re-render/publish permissions and authenticated end-to-end flows before any production release.
