# `objective_measures` · payload contract

Contract version **2.0.0**. `GET /api/version` reports what a deployment is
actually running.

This document covers the optional instrumented-assessment block only. The rest
of the `/api/generate` payload is unchanged from v1.

---

## The one rule

**Optional means optional.** Most clients will have no instrumented data for
months. Some never will. With `objective_measures` absent, empty, or entirely
unparseable, the generated plan is **byte-identical** to what v1.0 produced.
`tests/test_objective_measures.TestGracefulDegradation` exists to keep that
true and should be treated as load-bearing.

Two consequences worth knowing before you integrate:

- **Send partial data freely.** A single joint, one side, no previous
  assessment, no bodyweight — all fine. The generator emits a signal only where
  it has both axes it needs and stays quiet everywhere else.
- **Malformed entries are dropped, not fatal — but only after validation.**
  `POST /api/generate` validates first and returns `400` with every structural
  error at once. Past that gate, individual unreadable rows are skipped and
  reported in `parse_warnings` on the coach page rather than taking the session
  down.

---

## Shape

```jsonc
{
  "contract_version": "2.0.0",          // optional; unsupported major → 400

  "objective_measures": {
    "current": {
      "date": "2026-06-14",             // ISO preferred; several formats accepted
      "bodyweight_lb": 185,             // strongly recommended · see below
      "notes": "",

      "dynamo": [
        { "test": "knee_extension", "side": "L", "value": 60, "unit": "lb" },
        { "test": "knee_extension", "side": "R", "value": 95, "unit": "lb" },
        { "test": "shoulder_er",    "side": "L", "value": 14, "unit": "lb" },
        { "test": "shoulder_er",    "side": "R", "value": 24, "unit": "lb" },
        { "test": "grip",           "side": "L", "value": 95 },
        { "test": "grip",           "side": "R", "value": 98 }
      ],

      "rom": [
        { "joint": "hip", "motion": "ir", "side": "L",
          "degrees": 18, "mode": "passive" },
        { "joint": "shoulder", "motion": "flexion", "side": "L",
          "degrees": 172 }
      ],

      "voltra": [
        { "pattern": "trap_bar_deadlift", "position": "mid_range",
          "value": 300, "joint": "hip" },
        { "pattern": "trap_bar_deadlift", "position": "end_range",
          "value": 120, "joint": "hip" }
      ]
    },

    "previous": { /* same shape · omit entirely on a first assessment */ }
  }
}
```

A bare single assessment is also accepted — `dynamo` / `rom` / `voltra` at the
top of `objective_measures` with no `current` wrapper.

---

## Fields

### `dynamo[]` · VALD peak isometric force

| Field | Required | Notes |
|---|---|---|
| `test` | yes | Must be a known id (below). An unknown id is a `400`, not a silent drop — a typo'd test name is exactly the failure this gate exists to catch. |
| `value` | yes | Number, 0–1000. |
| `unit` | no | `lb` (default), `kg`, or `N`. Anything else is a `400`. |
| `side` | no | `L`, `R`, or `bilateral` (default). Send both sides — asymmetry and weak-side logic depend on it. |

Known `test` ids:

```
grip                shoulder_ir         shoulder_er         shoulder_abduction
shoulder_flexion    hip_abduction       hip_adduction       hip_ir
hip_er              hip_extension       knee_extension      knee_flexion
ankle_dorsiflexion  ankle_plantarflexion  elbow_flexion     elbow_extension
```

### `rom[]` · passive range of motion, degrees

| Field | Required | Notes |
|---|---|---|
| `joint` | yes | Canonical: `knee` `shoulder` `hip` `lumbar` `cervical` `wrist` `elbow` `ankle`. Common aliases resolve (`low_back` → `lumbar`, `neck` → `cervical`). |
| `motion` | yes | `ir` `er` `flexion` `extension` `abduction` `adduction` `dorsiflexion` … Long forms resolve (`internal_rotation` → `ir`). |
| `degrees` | yes | −30 to 200. |
| `side` | no | Defaults to `bilateral`. |
| `mode` | no | Defaults to `passive`. |

A flat object form is tolerated for Coach OS convenience:
`{"shoulder_flexion_L": 148, "hip_ir_L": 18}`.

### `voltra[]` · compound isometric, mid-range vs end-range

| Field | Required | Notes |
|---|---|---|
| `pattern` | yes | Free text, snake_cased. Words longer than three characters are matched against exercise names, so `trap_bar_deadlift` will anchor a "Trap Bar Deadlift". |
| `position` | yes | `mid_range` or `end_range`. Anything else is a `400`. |
| `value` | yes | Number. |
| `joint` | no | Canonical joint, if the pattern maps cleanly to one. Lets the reading participate in ROM × force routing. |

Send **both positions for the same pattern**. The end-range/mid-range ratio is
the most direct end-range force measurement available and takes precedence over
bodyweight-normalized DynaMo values in classification.

---

## Why bodyweight matters

Without `bodyweight_lb`, force cannot be normalized against the per-test
ratios in `config/objective_thresholds.json`. The system falls back to
contralateral asymmetry, which still ranks joints and still detects a weak
side — but the resulting signals are marked `"confidence": "low"` and say so on
the coach page. Weakest-link ranking also becomes relative rather than absolute.

Send it if you have it. An InBody or BOD POD reading from the same visit is
fine.

---

## What the data drives

| Input present | What it enables |
|---|---|
| ROM **and** end-range force on the same joint | ROM × force routing (the quadrant) |
| Three or more tested joints | Weakest-link selection emphasis |
| Both sides of a test | Asymmetry flags · side-aware dose |
| A tested joint on single-joint work with real equipment tagging | Load from measured force |
| `previous` block | Deltas since last assessment on the coach page |

One axis alone produces nothing. A joint with ROM but no force, or force but no
ROM, emits no signal — a half-measured joint is where a confident-sounding
route does the most damage.

---

## Responses

| Status | Meaning |
|---|---|
| `200` | PDF. `X-IMS-Generator-Version`, `X-IMS-Contract-Version`, `X-IMS-Protocol-Version` headers; `X-IMS-Warnings` when non-blocking warnings fired. |
| `400` | `{"error": "invalid_payload", "errors": [...], "warnings": [...]}`. Every error at once, so it takes one round trip to fix. Nothing was generated. |
| `422` | `{"error": "implausible_load", ...}`. A computed load was not physically sensible for the exercise's equipment. Deliberately a failure rather than a printed number — check the force reading, the equipment tagging, and `load_from_force` in the threshold config. |
| `500` | A bug. The trace comes back in the body. |

`POST /api/validate` runs the same validation and returns `{"ok": true,
"warnings": [...]}` without generating anything. Call it on save so field
problems surface while the coach is still in front of the client.

---

## Thresholds

Every cutoff — ROM norms, force ratios, asymmetry gates, load percentages,
plausibility bands, progression ladders — lives in
[`config/objective_thresholds.json`](../config/objective_thresholds.json).
Nothing is inline in the generator.

They are **unvalidated starting heuristics**. They are coach judgment expressed
as numbers, not published norms, and they are expected to move as IMS
accumulates data. Changing one is a config edit and a test run, not a code
change.

---

## Safety contract

Worth stating plainly, because it is the part that must not drift:

- Measured signals are **advisory routes, never vetoes**. Nothing in the
  objective layer can add an exercise the contraindication router rejected.
- A hard contraindication (concern checkbox, active `constraints_rich` status,
  or a joint named in `red_flags`) **suppresses** any signal that would route
  work toward that joint. Suppression is recorded and printed, never silent.
- Signals routing work *away* from a joint always survive — they only ever add
  caution.
- A DynaMo reading anchors **single-joint work only**. A 14 lb shoulder ER
  measurement has no business setting the load on a trap bar deadlift.
- Measured force is a **fallback** anchor. A real tested lift always wins.
- Nothing measured appears on a client-facing page. Force data is coach
  language and lives on the coach pages, where every decision is printed
  alongside the measurement and date that caused it.
