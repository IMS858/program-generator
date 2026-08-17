"""
IMS · VALD DynaMo API → objective_measures.

WHERE THIS LIVES AND WHY.

The ingest itself — OAuth, the incremental cursor, athlete→client identity,
storage — belongs in Coach OS. It is stateful and this service is not: no
database, no secrets store, no scheduler, and a hard requirement to stay
synchronous and fast.

What belongs HERE is the VOCABULARY. The generator owns the canonical test ids,
and a mapping table that lives in two places drifts. So Coach OS handles the
network and hands raw VALD test objects to this module (directly, or over
POST /api/vald/transform), and gets back a validated objective_measures block.
One source of truth for what a test is called.

WHAT THE API ACTUALLY RETURNS (verified against VALD's External DynaMo API
documentation, not assumed):

  * Test metadata is paged 50 at a time from
    /v2022q2/teams/{tenantId}/tests, filtered by a modifiedFromUtc cursor.
  * Per-test detail at /v2022q2/tests/{testId} carries
    `repetitionTypeSummaries` — one entry per side, already split, with
    maxForceNewtons, maxRangeOfMotionDegrees and RFD precomputed.
  * `testCategory` is "Strength" or "RangeofMotion".
  * Test identity is bodyRegion + movement (+ position for display). VALD
    explicitly warns against using laterality or attachments to build a test
    name — it breaks aggregation across similar tests. So the mapping key here
    is (bodyRegion, movement) and nothing else.
  * Force is in NEWTONS. ROM is in DEGREES and can be negative (an extension
    deficit); VALD's own example is -32°.
  * Rate of force development is already computed per side. It does NOT
    require pulling and parsing force traces, which is what the original plan
    assumed. It is free in the same payload.

DESIGN RULE · an unmapped test is SKIPPED WITH A WARNING, never fatal. The
generator's API rejects an unknown test id with a 400, which is right for a
hand-typed payload and wrong for a batch sync: one novel movement type must not
fail an entire assessment. Everything unmapped comes back in `warnings` so it
can be added to the table deliberately.
"""

from typing import Optional

# (bodyRegion, movement) → canonical test id.
# Keys are lowercased and stripped of spaces/underscores before lookup, so
# "InternalRotation", "Internal Rotation" and "internal_rotation" all match.
VALD_TEST_MAP = {
    # ── Knee ──
    ("knee", "extension"): "knee_extension",
    ("knee", "flexion"): "knee_flexion",
    # ── Hip ──
    ("hip", "abduction"): "hip_abduction",
    ("hip", "adduction"): "hip_adduction",
    ("hip", "flexion"): "hip_flexion",
    ("hip", "extension"): "hip_extension",
    ("hip", "internalrotation"): "hip_ir",
    ("hip", "externalrotation"): "hip_er",
    ("hip", "isometricmidthighpull"): "imtp",
    # ── Shoulder ──
    ("shoulder", "internalrotation"): "shoulder_ir",
    ("shoulder", "externalrotation"): "shoulder_er",
    ("shoulder", "abduction"): "shoulder_abduction",
    ("shoulder", "adduction"): "shoulder_adduction",
    ("shoulder", "flexion"): "shoulder_flexion",
    ("shoulder", "extension"): "shoulder_extension",
    # ── Ankle ──
    ("ankle", "dorsiflexion"): "ankle_dorsiflexion",
    ("ankle", "plantarflexion"): "ankle_plantarflexion",
    ("ankle", "inversion"): "ankle_inversion",
    ("ankle", "eversion"): "ankle_eversion",
    # ── Elbow ──
    ("elbow", "flexion"): "elbow_flexion",
    ("elbow", "extension"): "elbow_extension",
    # ── Hand / grip ──
    ("hand", "grip"): "grip",
    ("hand", "squeeze"): "grip",
    ("grip", "grip"): "grip",
    ("wrist", "flexion"): "wrist_flexion",
    ("wrist", "extension"): "wrist_extension",
    # ── Neck / trunk · laterality "None" ──
    ("neck", "flexion"): "cervical_flexion",
    ("neck", "extension"): "cervical_extension",
    ("neck", "lateralflexion"): "cervical_lateral_flexion",
    ("cervical", "flexion"): "cervical_flexion",
    ("cervical", "extension"): "cervical_extension",
    ("trunk", "flexion"): "trunk_flexion",
    ("trunk", "extension"): "trunk_extension",
}

# ROM readings map onto the joint/motion vocabulary rather than a test id.
VALD_ROM_MAP = {
    ("knee", "extension"): ("knee", "extension"),
    ("knee", "flexion"): ("knee", "flexion"),
    ("hip", "internalrotation"): ("hip", "ir"),
    ("hip", "externalrotation"): ("hip", "er"),
    ("hip", "flexion"): ("hip", "flexion"),
    ("hip", "abduction"): ("hip", "abduction"),
    ("shoulder", "flexion"): ("shoulder", "flexion"),
    ("shoulder", "abduction"): ("shoulder", "abduction"),
    ("shoulder", "internalrotation"): ("shoulder", "ir"),
    ("shoulder", "externalrotation"): ("shoulder", "er"),
    ("ankle", "dorsiflexion"): ("ankle", "dorsiflexion"),
    ("ankle", "plantarflexion"): ("ankle", "plantarflexion"),
}

_SIDE_MAP = {
    "leftside": "L",
    "rightside": "R",
    "left": "L",
    "right": "R",
    "none": "bilateral",
    "": "bilateral",
}


def _norm(value) -> str:
    return (str(value or "").strip().lower()
            .replace(" ", "").replace("_", "").replace("-", ""))


def _side(value) -> str:
    return _SIDE_MAP.get(_norm(value), "bilateral")


def _iso_date(value) -> Optional[str]:
    """YYYY-MM-DD out of VALD's UTC timestamps."""
    if not value:
        return None
    s = str(value)
    return s[:10] if len(s) >= 10 and s[4] == "-" else None


def transform_tests(tests, warnings=None) -> dict:
    """Turn a list of VALD DynaMo test objects into one MeasureSet dict.

    Accepts the detailed per-test shape (the one carrying
    `repetitionTypeSummaries`). Returns the `current`/`previous` inner shape of
    an objective_measures block · the caller decides which slot it goes in.

    Never raises. Anything it cannot map is described in ``warnings``.
    """
    warnings = warnings if warnings is not None else []
    dynamo, rom = [], []
    dates = []

    for i, test in enumerate(tests or []):
        if not isinstance(test, dict):
            warnings.append(f"test[{i}] skipped · not an object")
            continue

        category = _norm(test.get("testCategory"))
        region = _norm(test.get("bodyRegion"))
        movement = _norm(test.get("movement"))
        test_id = test.get("id")
        date = _iso_date(test.get("startTimeUTC"))
        if date:
            dates.append(date)

        summaries = test.get("repetitionTypeSummaries")
        if not isinstance(summaries, list) or not summaries:
            # VALD's guidance is to prefer repetitionTypeSummaries; fall back to
            # the raw repetitions array only when summaries are absent.
            summaries = test.get("repetitions") or []
        if not summaries:
            warnings.append(
                f"{test.get('bodyRegion')} {test.get('movement')} skipped · "
                f"no repetition data on test {test_id}")
            continue

        if category == "rangeofmotion":
            mapped = VALD_ROM_MAP.get((region, movement))
            if not mapped:
                warnings.append(
                    f"ROM test '{test.get('bodyRegion')} {test.get('movement')}' "
                    f"has no mapping · skipped, add it to VALD_ROM_MAP")
                continue
            joint, motion = mapped
            for rep in summaries:
                deg = rep.get("maxRangeOfMotionDegrees",
                              rep.get("rangeOfMotionDegrees"))
                if deg is None:
                    continue
                rom.append({
                    "joint": joint,
                    "motion": motion,
                    "side": _side(rep.get("laterality") or test.get("laterality")),
                    "degrees": round(float(deg), 1),
                    "mode": "active",   # DynaMo ROM is client-driven, not passive
                    "source": "vald_api",
                    "source_id": test_id,
                })
            continue

        if category != "strength":
            warnings.append(f"test category '{test.get('testCategory')}' "
                            f"not handled · skipped")
            continue

        mapped = VALD_TEST_MAP.get((region, movement))
        if not mapped:
            warnings.append(
                f"strength test '{test.get('bodyRegion')} {test.get('movement')}' "
                f"has no mapping · skipped, add it to VALD_TEST_MAP")
            continue

        for rep in summaries:
            newtons = rep.get("maxForceNewtons")
            if newtons in (None, 0):
                continue
            metrics = {}
            for src, dst in (
                ("maxRateOfForceDevelopmentNewtonsPerSecond", "rfd_n_per_s"),
                ("avgTimeToPeakForceSeconds", "time_to_peak_s"),
                ("maxImpulseNewtonSeconds", "impulse_ns"),
                ("maxNetPeakForceNewtons", "net_peak_force_n"),
            ):
                if rep.get(src) is not None:
                    metrics[dst] = round(float(rep[src]), 2)
            if rep.get("repCount") is not None:
                metrics["reps"] = rep["repCount"]

            dynamo.append({
                "test": mapped,
                "side": _side(rep.get("laterality") or test.get("laterality")),
                "value": round(float(newtons), 1),
                "unit": "N",
                "source": "vald_api",
                "source_id": test_id,
                "metrics": metrics,
            })

    out = {"dynamo": dynamo, "rom": rom}
    if dates:
        # An assessment is a session, not an instant · take the latest test.
        out["date"] = max(dates)
    return out


def build_objective_measures(current_tests, previous_tests=None,
                             bodyweight_lb=None, warnings=None) -> Optional[dict]:
    """Assemble a full objective_measures block from two batches of tests.

    Returns None when nothing usable came back · that is the ordinary
    no-data path and it must stay free.
    """
    warnings = warnings if warnings is not None else []
    current = transform_tests(current_tests, warnings)
    if not current["dynamo"] and not current["rom"]:
        return None
    if bodyweight_lb:
        current["bodyweight_lb"] = bodyweight_lb

    payload = {"current": current}
    if previous_tests:
        previous = transform_tests(previous_tests, warnings)
        if previous["dynamo"] or previous["rom"]:
            payload["previous"] = previous
    return payload


def unmapped_tests(tests) -> list:
    """Every (bodyRegion, movement) pair in a batch with no mapping.

    Worth running over a month of real data before trusting the sync · it tells
    you exactly what the studio measures that the table does not know about.
    """
    seen, missing = set(), []
    for test in (tests or []):
        if not isinstance(test, dict):
            continue
        region = _norm(test.get("bodyRegion"))
        movement = _norm(test.get("movement"))
        category = _norm(test.get("testCategory"))
        table = VALD_ROM_MAP if category == "rangeofmotion" else VALD_TEST_MAP
        key = (region, movement, category)
        if key in seen or (region, movement) in table:
            continue
        seen.add(key)
        missing.append({
            "bodyRegion": test.get("bodyRegion"),
            "movement": test.get("movement"),
            "testCategory": test.get("testCategory"),
        })
    return missing
