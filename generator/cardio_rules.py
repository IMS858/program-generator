"""
Cardio Rules · the brain of cardio prescription.

This module is the single source of truth for cardio decisions.
It takes the structured CardioProfile (from cardio_profile.py) plus
the rest of the assessment context (concerns + rich constraints) and
produces concrete prescriptions, machine choices, flags, and filters.

Public API (each function is independently callable and testable) ·

  normalize_cardio_profile(profile, concerns, constraints_rich)
      → dict of normalized limitations + raw context

  choose_primary_cardio_machine(normalized)
      → (machine_id, rationale_text)

  determine_interval_clearance(normalized)
      → "blocked" | "z2_only" | "controlled" | "full"

  generate_cardio_progression(normalized)
      → dict {1: {...}, 2: {...}, 3: {...}, 4: {...}}

  generate_cardio_coach_flags(normalized)
      → list[str] of coach-facing flag sentences

  filter_finishers_by_cardio_limitations(pool, normalized)
      → filtered pool list

The module is dependency-free except for cardio_profile (for the modality
constants). It never crashes on bad input · empty / missing fields are
treated as "no signal" and routed to safe defaults.
"""

from __future__ import annotations
from typing import Optional


# ─── CONSTANTS ───────────────────────────────────────────────

MODALITIES = {
    "upright_bike", "stationary_bike", "arc_trainer", "assault_bike",
    "rower", "skierg",
}

MODALITY_DISPLAY = {
    "upright_bike": "Upright Bike",
    "stationary_bike": "Stationary Bike",
    "arc_trainer": "Arc Trainer",
    "assault_bike": "Assault Bike",
    "rower": "Rower",
    "skierg": "SkiErg",
}

# Joint-limitation flags (a normalized profile's "limitations" list)
JOINT_LIMITS = {
    "knee_sensitive", "hip_sensitive", "low_back_sensitive",
    "shoulder_sensitive", "wrist_sensitive",
}

CONDITION_LIMITS = {
    "conditioning_beginner", "deconditioned", "high_stress_poor_recovery",
}

INTERVAL_FLAGS = {"cleared_for_intervals", "not_cleared_for_intervals"}


# ─── 1 · NORMALIZE ───────────────────────────────────────────

# Map every form of incoming concern/constraint key to a canonical
# cardio limitation. Keys are normalized (lowercase, underscores).
_CONCERN_TO_LIMIT = {
    # Knee
    "bad_knee": "knee_sensitive",
    "knee": "knee_sensitive",
    "knee_pain": "knee_sensitive",
    "post_surgery_knee": "knee_sensitive",
    "meniscus": "knee_sensitive",
    "acl": "knee_sensitive",
    "mcl": "knee_sensitive",
    # Shoulder
    "bad_shoulder": "shoulder_sensitive",
    "shoulder": "shoulder_sensitive",
    "shoulder_pain": "shoulder_sensitive",
    "post_surgery_shoulder": "shoulder_sensitive",
    "chronic_shoulder_impingement": "shoulder_sensitive",
    "labrum": "shoulder_sensitive",
    # Lumbar / low back
    "lower_back": "low_back_sensitive",
    "low_back": "low_back_sensitive",
    "back": "low_back_sensitive",
    "lumbar": "low_back_sensitive",
    "back_pain": "low_back_sensitive",
    "chronic_low_back": "low_back_sensitive",
    "si_joint_sensitivity": "low_back_sensitive",
    "no_axial_loading": "low_back_sensitive",
    "disc_issue": "low_back_sensitive",
    "lumbar_issue": "low_back_sensitive",
    # Hip
    "hip": "hip_sensitive",
    "bad_hip": "hip_sensitive",
    "hip_pain": "hip_sensitive",
    "post_surgery_hip": "hip_sensitive",
    # Wrist / elbow
    "wrist": "wrist_sensitive",
    "bad_wrist": "wrist_sensitive",
    "wrist_pain": "wrist_sensitive",
    "elbow": "wrist_sensitive",  # treat elbow load similarly for cardio routing
    "bad_elbow": "wrist_sensitive",
    "elbow_pain": "wrist_sensitive",
}


def _norm_key(s) -> str:
    if s is None:
        return ""
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def normalize_cardio_profile(profile, concerns=None, constraints_rich=None) -> dict:
    """Merge cardio_profile.limitations + concerns + rich constraints into a
    single normalized dict the rest of the engine can rely on.

    Returns a dict ·
        {
            "primary_modality":     str | None,
            "secondary_modalities": list[str],
            "avoid_modalities":     list[str],
            "limitations":          list[str],   # canonical cardio flags
            "z2_baseline":          dict,        # raw Z2 baseline, possibly empty
            "interval_test":        dict,
            "hr_recovery":          dict + drop + quality,
            "active_flare_up":      bool,        # any rich constraint with status=active_flare_up
            "post_surgery":         bool,
            "sources":              dict,        # which inputs contributed which limitations
        }

    The "limitations" list is the union of (a) profile.limitations,
    (b) mapped concerns, (c) mapped rich constraint keys (skipping cleared status).
    """
    limits: set[str] = set()
    sources: dict[str, list[str]] = {}

    def _add(limit, source):
        if not limit:
            return
        limits.add(limit)
        sources.setdefault(limit, []).append(source)

    # ── Direct profile limitations ──
    if profile is not None:
        for l in (getattr(profile, "limitations", None) or []):
            key = _norm_key(l)
            if key:
                _add(key, "cardio_profile")

    # ── Concerns mapping ──
    for c in (concerns or []):
        key = _norm_key(c)
        if not key:
            continue
        mapped = _CONCERN_TO_LIMIT.get(key)
        if mapped:
            _add(mapped, f"concern:{key}")

    # ── Rich constraints mapping ──
    active_flare = False
    post_surgery = False
    for cr in (constraints_rich or []):
        if not isinstance(cr, dict):
            continue
        status = _norm_key(cr.get("status"))
        ckey = _norm_key(cr.get("key"))
        # Cleared constraints don't drive filtering
        if status == "cleared":
            continue
        if status == "active_flare_up":
            active_flare = True
        if status == "post_surgery":
            post_surgery = True

        mapped = _CONCERN_TO_LIMIT.get(ckey)
        if mapped:
            label = f"constraint:{ckey}"
            if status:
                label += f":{status}"
            _add(mapped, label)

        # Avoid_notes free-text · scan for joint keywords
        avoid = _norm_key(cr.get("avoid_notes"))
        for kw, lim in (("knee", "knee_sensitive"),
                         ("shoulder", "shoulder_sensitive"),
                         ("low_back", "low_back_sensitive"),
                         ("lumbar", "low_back_sensitive"),
                         ("hip", "hip_sensitive"),
                         ("wrist", "wrist_sensitive")):
            if kw in avoid:
                _add(lim, f"avoid_notes:{ckey or 'other'}")

    # ── Carry through profile fields (with safe defaults) ──
    primary_modality = getattr(profile, "primary_modality", None) if profile else None
    secondary = list(getattr(profile, "secondary_modalities", None) or []) if profile else []
    avoid = list(getattr(profile, "avoid_modalities", None) or []) if profile else []

    # Z2/interval/HR data · serialize to plain dicts for downstream use
    def _to_dict(x):
        if x is None:
            return {}
        if isinstance(x, dict):
            return dict(x)
        if hasattr(x, "__dict__"):
            return {k: v for k, v in x.__dict__.items() if not k.startswith("_")}
        return {}

    z2 = _to_dict(getattr(profile, "z2_baseline", None) if profile else None)
    iv = _to_dict(getattr(profile, "interval_test", None) if profile else None)
    hrr = _to_dict(getattr(profile, "hr_recovery", None) if profile else None)

    # Compute drop if missing
    if not hrr.get("drop_one_min") and hrr.get("end_hr") and hrr.get("one_min_hr"):
        try:
            hrr["drop_one_min"] = max(0, int(hrr["end_hr"]) - int(hrr["one_min_hr"]))
        except (TypeError, ValueError):
            pass
    drop = hrr.get("drop_one_min")
    if isinstance(drop, (int, float)) and drop is not None:
        if drop >= 18:
            hrr["quality"] = "strong"
        elif drop >= 12:
            hrr["quality"] = "normal"
        else:
            hrr["quality"] = "poor"
    else:
        hrr["quality"] = None

    return {
        "primary_modality": primary_modality,
        "secondary_modalities": secondary,
        "avoid_modalities": avoid,
        "limitations": sorted(limits),
        "z2_baseline": z2,
        "interval_test": iv,
        "hr_recovery": hrr,
        "active_flare_up": active_flare,
        "post_surgery": post_surgery,
        "sources": sources,
    }


# ─── 2 · MACHINE SELECTION ───────────────────────────────────

# Per-limitation, ordered-by-preference safe machine list
_SAFE_MACHINES_BY_LIMIT = {
    "knee_sensitive":     ["stationary_bike", "upright_bike", "arc_trainer"],
    "low_back_sensitive": ["stationary_bike", "upright_bike", "arc_trainer"],
    "shoulder_sensitive": ["stationary_bike", "upright_bike", "arc_trainer"],
    "hip_sensitive":      ["upright_bike", "stationary_bike", "arc_trainer"],
    "wrist_sensitive":    ["stationary_bike", "upright_bike", "arc_trainer"],
}

# Machines flagged as risky for each limitation (not just "less safe" but
# actively contraindicated unless explicitly tolerated).
_RISKY_MACHINES_BY_LIMIT = {
    "knee_sensitive":     [],  # all 6 are usable for knee if tolerated; bike/arc preferred
    "low_back_sensitive": ["rower"],   # avoid rower unless tolerated
    "shoulder_sensitive": ["skierg", "assault_bike"],  # arms-driven
    "hip_sensitive":      [],
    "wrist_sensitive":    ["rower", "skierg", "assault_bike"],  # grip-heavy
}


def _machine_is_safe(machine: str, normalized: dict) -> bool:
    """A machine is safe if it isn't on any active limitation's risky list,
    UNLESS the coach explicitly marked it as a tolerated *secondary*.

    Primary alone doesn't override · the coach may have set the primary
    before flagging the limitation. Only `secondary_modalities` counts as
    explicit "yes, tested, this is fine despite the limitation."
    """
    if not machine:
        return False
    secondary_tolerated = set(normalized.get("secondary_modalities", []))

    avoid = set(normalized.get("avoid_modalities", []))
    if machine in avoid:
        return False

    for limit in normalized.get("limitations", []):
        risky = _RISKY_MACHINES_BY_LIMIT.get(limit, [])
        if machine in risky and machine not in secondary_tolerated:
            return False
    return True


def choose_primary_cardio_machine(normalized: dict) -> tuple[str, str]:
    """Pick the primary cardio machine based on normalized profile.

    Returns (machine_id, rationale_text).

    Algorithm ·
      1. If the coach picked a primary_modality and it's safe, use it.
      2. If primary is risky, walk the safest list for the dominant
         joint limitation and pick the first the coach hasn't put on
         the avoid list.
      3. If no signal at all, fallback to stationary_bike (universal).
    """
    primary = normalized.get("primary_modality")

    # 1 · explicit primary, if safe
    if primary and _machine_is_safe(primary, normalized):
        return (primary, "Coach-selected primary modality · client tolerates")

    # 2 · primary is set but risky
    if primary and not _machine_is_safe(primary, normalized):
        # Find the conflicting limitation for the rationale
        conflicting = []
        for limit in normalized.get("limitations", []):
            if primary in _RISKY_MACHINES_BY_LIMIT.get(limit, []):
                conflicting.append(limit.replace("_", " "))
        rationale_part = (f"Primary ({MODALITY_DISPLAY.get(primary, primary)}) "
                          f"conflicts with {', '.join(conflicting)}. ") if conflicting else ""

        # Walk safe lists in priority order based on which limits are present
        # Prefer the most specific list among active limits
        priority_limits = [
            "knee_sensitive", "low_back_sensitive", "shoulder_sensitive",
            "hip_sensitive", "wrist_sensitive",
        ]
        for limit in priority_limits:
            if limit in normalized["limitations"]:
                for candidate in _SAFE_MACHINES_BY_LIMIT[limit]:
                    if _machine_is_safe(candidate, normalized):
                        return (candidate,
                                f"{rationale_part}Routed to safe alt "
                                f"({MODALITY_DISPLAY.get(candidate, candidate)}) for {limit.replace('_', ' ')}")
        # No specific limit matched · fall through
        return ("stationary_bike", f"{rationale_part}Defaulted to stationary bike (universal-safe)")

    # 3 · no primary set · pick from limits
    for limit in normalized.get("limitations", []):
        if limit in _SAFE_MACHINES_BY_LIMIT:
            for candidate in _SAFE_MACHINES_BY_LIMIT[limit]:
                if _machine_is_safe(candidate, normalized):
                    return (candidate,
                            f"No primary specified · routed to "
                            f"{MODALITY_DISPLAY.get(candidate, candidate)} for {limit.replace('_', ' ')}")

    # 4 · absolute fallback
    return ("stationary_bike",
            "No primary specified, no joint limits flagged · default stationary bike")


# ─── 3 · INTERVAL CLEARANCE ──────────────────────────────────

def determine_interval_clearance(normalized: dict) -> str:
    """Return one of ·
        "blocked"     · no intervals, period
        "z2_only"     · pure aerobic, no pickups, no intervals
        "controlled"  · short pickups OK, no full interval blocks
        "full"        · controlled intervals fine

    Hierarchy (most restrictive wins) ·
      - not_cleared_for_intervals      → blocked
      - active flare-up                → blocked
      - post_surgery (this block)      → blocked
      - poor HR recovery               → z2_only
      - deconditioned/beginner         → z2_only
      - high stress / poor recovery    → z2_only
      - cleared_for_intervals          → full
      - default                        → controlled
    """
    limits = set(normalized.get("limitations", []))

    if "not_cleared_for_intervals" in limits:
        return "blocked"
    if normalized.get("active_flare_up"):
        return "blocked"
    if normalized.get("post_surgery"):
        return "blocked"

    hrr_quality = normalized.get("hr_recovery", {}).get("quality")
    if hrr_quality == "poor":
        return "z2_only"

    if "deconditioned" in limits or "conditioning_beginner" in limits:
        return "z2_only"
    if "high_stress_poor_recovery" in limits:
        return "z2_only"

    if "cleared_for_intervals" in limits:
        return "full"

    return "controlled"


# ─── 4 · 4-WEEK PROGRESSION ──────────────────────────────────

def generate_cardio_progression(normalized: dict) -> dict:
    """Build a 4-week Block 1 progression dict.

    Returns {1: {...}, 2: {...}, 3: {...}, 4: {...}}, each entry has ·
        focus       · short title (week label)
        main        · prescription text shown to client
        rationale   · why this prescription
        machine     · machine label for that week
        coach_note  · internal note (None if nothing to add)
    """
    machine_id, machine_rationale = choose_primary_cardio_machine(normalized)
    machine_label = MODALITY_DISPLAY.get(machine_id, machine_id)
    secondary = [MODALITY_DISPLAY.get(m, m) for m in normalized.get("secondary_modalities", [])
                  if m != machine_id]
    machine_with_alt = (f"{machine_label}  ·  alt: {', '.join(secondary)}"
                         if secondary else machine_label)

    clearance = determine_interval_clearance(normalized)
    limits = set(normalized.get("limitations", []))
    is_decond = "deconditioned" in limits or "conditioning_beginner" in limits

    # Pull baseline test data when available · weave into rationale
    z2 = normalized.get("z2_baseline", {}) or {}
    baseline_summary = None
    if z2.get("avg_hr") or z2.get("rpe") or z2.get("avg_watts"):
        bits = []
        if z2.get("avg_hr"):
            bits.append(f"avg HR {z2['avg_hr']}")
        if z2.get("rpe") is not None:
            bits.append(f"RPE {z2['rpe']}")
        if z2.get("avg_watts"):
            bits.append(f"{z2['avg_watts']} W")
        baseline_summary = " · ".join(bits)

    def _wk(focus, main, rationale, coach=None):
        return {
            "focus": focus,
            "main": main,
            "rationale": rationale,
            "machine": machine_with_alt,
            "machine_id": machine_id,
            "machine_rationale": machine_rationale,
            "coach_note": coach,
        }

    # ── DECONDITIONED / BEGINNER PATH ──
    if is_decond:
        return {
            1: _wk(
                "Week 1 · Zone 2 Foundation",
                "8-12 min Zone 2 · RPE 4 · nasal breathing · stop if you lose conversational pace",
                ("Establish baseline tolerance. " +
                 (f"Last test: {baseline_summary}." if baseline_summary else "")),
                coach="Conservative ramp · build tolerance before duration",
            ),
            2: _wk(
                "Week 2 · Zone 2 Build",
                "10-15 min Zone 2 · RPE 4-5 · same machine, same resistance",
                "Slightly longer at the same intensity · let the engine grow.",
                coach="Hold intensity, add 2-5 min only",
            ),
            3: _wk(
                "Week 3 · Zone 2 Sustain",
                "12-18 min Zone 2 · RPE 4-5 · same modality preferred",
                "Confidence building · same dose, more comfort.",
                coach="No intervals this block · pure aerobic",
            ),
            4: _wk(
                "Week 4 · Zone 2 Retest",
                "Retest 10-min Zone 2 · same machine, same RPE · note HR drop vs Week 1",
                "We measure progress by HR at the same workload, not chasing harder.",
                coach="Compare avg HR to Week 1 · drop = progress",
            ),
        }

    # ── BLOCKED INTERVALS PATH (z2_only or blocked) ──
    if clearance in ("blocked", "z2_only"):
        rationale_suffix = ""
        if clearance == "blocked":
            if normalized.get("active_flare_up"):
                rationale_suffix = " Active flare-up · keeping cardio purely aerobic."
            elif "not_cleared_for_intervals" in limits:
                rationale_suffix = " Not cleared for intervals · pure aerobic this block."
            elif normalized.get("post_surgery"):
                rationale_suffix = " Post-surgery · pure aerobic this block."
        elif normalized.get("hr_recovery", {}).get("quality") == "poor":
            rationale_suffix = " HR recovery is in the poor range · we build duration before intensity."

        return {
            1: _wk(
                "Week 1 · Zone 2 Base",
                "12-15 min Zone 2 · RPE 4-5 · nasal breathing only",
                ("Build aerobic base. If you can't nasal breathe, slow down." + rationale_suffix),
                coach=("Z2 only this block" if clearance != "blocked" else "Intervals BLOCKED"),
            ),
            2: _wk(
                "Week 2 · Zone 2 Extended",
                "15-18 min Zone 2 · RPE 4-5 · same machine",
                "Same zone, longer duration · capacity build.",
            ),
            3: _wk(
                "Week 3 · Zone 2 Sustained",
                "18-22 min Zone 2 · same intensity · own the pace",
                "Hold quality at duration · no need to push harder yet.",
            ),
            4: _wk(
                "Week 4 · Zone 2 Retest",
                "Retest 10-min Zone 2 · same machine, same RPE · note HR drop vs Week 1",
                "We measure progress by HR at the same workload.",
                coach="Compare avg HR to baseline · expect drop",
            ),
        }

    # ── CLEARED FOR INTERVALS PATH (full clearance) ──
    if clearance == "full":
        return {
            1: _wk(
                "Week 1 · Zone 2 Baseline",
                "12-15 min Zone 2 · RPE 4-5 · nasal breathing",
                "Establish a clean Z2 base before adding intensity.",
            ),
            2: _wk(
                "Week 2 · Zone 2 Build",
                "15-18 min Zone 2 · RPE 4-5 · same modality · resistance same or +1",
                "Same zone, longer duration · capacity build.",
            ),
            3: _wk(
                "Week 3 · Zone 2 + Controlled Pickups",
                "18-22 min Z2 base · include 4 × 30-sec controlled pickups · RPE 6-7 on the pickup, "
                "full recovery between",
                "First intensity exposure · short windows, plenty of recovery.",
                coach="Pickups OK if joint tolerance was clean in Z2 baseline",
            ),
            4: _wk(
                "Week 4 · Controlled Interval Session",
                "5 min Z2 warmup · 6 rounds (20s hard / 70s easy) · 5 min cooldown · "
                "use machine you tolerate best",
                "Threshold exposure · stop if joint tolerance drops or HR doesn't recover.",
                coach="Full interval block · re-test in W5 if program continues",
            ),
        }

    # ── DEFAULT (controlled) PATH ──
    return {
        1: _wk(
            "Week 1 · Zone 2 Base",
            "12-15 min Zone 2 · RPE 4-5 · nasal breathing",
            "Build aerobic base.",
        ),
        2: _wk(
            "Week 2 · Zone 2 Extended",
            "15-18 min Zone 2 · RPE 4-5",
            "Same zone, longer duration · capacity build.",
        ),
        3: _wk(
            "Week 3 · Zone 2 + Light Pickups",
            "18-22 min Z2 · 3 × 20-sec pickups in the back half · RPE 6, full recovery",
            "Light intensity exposure · protect the aerobic base.",
            coach="Skip pickups if joint complaints showed up",
        ),
        4: _wk(
            "Week 4 · Zone 2 Retest",
            "Retest 10-min Z2 baseline · same machine, same RPE",
            "Measure progress by HR at the same workload.",
            coach="Compare avg HR to baseline",
        ),
    }


# ─── 5 · COACH FLAGS ─────────────────────────────────────────

def generate_cardio_coach_flags(normalized: dict) -> list[str]:
    """Generate coach-only flag sentences for the appendix."""
    flags = []
    limits = set(normalized.get("limitations", []))
    clearance = determine_interval_clearance(normalized)
    hrr = normalized.get("hr_recovery", {})

    # Joint flags
    if "knee_sensitive" in limits:
        flags.append("Knee-sensitive client · avoid impact finishers (lateral bounds, jump rope, "
                     "deep squat holds). Prefer bike or arc trainer.")
    if "low_back_sensitive" in limits:
        flags.append("Low-back sensitivity · avoid rower unless specifically tolerated. "
                     "Skip aggressive KB swings and heavy hinge conditioning.")
    if "shoulder_sensitive" in limits:
        flags.append("Shoulder-sensitive client · avoid SkiErg and Assault Bike arms unless "
                     "specifically tolerated. High-volume battle ropes off the menu.")
    if "hip_sensitive" in limits:
        flags.append("Hip sensitivity · avoid lateral bounds and aggressive ballistic hinging.")
    if "wrist_sensitive" in limits:
        flags.append("Wrist sensitivity · avoid grip-dominant cardio (rower/SkiErg) and battle ropes.")

    # Interval clearance
    if clearance == "blocked":
        if normalized.get("active_flare_up"):
            flags.append("Active flare-up flagged · NO intervals this block. Z2 only.")
        elif "not_cleared_for_intervals" in limits:
            flags.append("Not cleared for intervals · keep cardio Zone 2 only this block.")
        elif normalized.get("post_surgery"):
            flags.append("Post-surgery · NO intervals this block. Reassess at W5.")
    elif clearance == "z2_only":
        if hrr.get("quality") == "poor":
            flags.append("Poor HR recovery · progress duration before intensity. "
                         "Reassess HR recovery at W4 retest.")
        elif "deconditioned" in limits or "conditioning_beginner" in limits:
            flags.append("Deconditioned client · build aerobic base first. "
                         "No intervals until tolerance is established.")
    elif clearance == "controlled":
        flags.append("Default cardio progression · controlled pickups in W3 if joints tolerate.")
    elif clearance == "full":
        if hrr.get("quality") == "strong":
            flags.append("Cleared for intervals + strong HR recovery · controlled intervals "
                         "in W4 are appropriate.")
        else:
            flags.append("Cleared for intervals · controlled progression. Watch joint response "
                         "at W3 pickups before W4 interval block.")

    # HR recovery context
    if hrr.get("drop_one_min") is not None and hrr.get("quality"):
        q = hrr["quality"]
        d = hrr["drop_one_min"]
        if q == "strong":
            flags.append(f"Strong HR recovery (-{d} bpm in 1 min) · good capacity to push.")
        elif q == "normal":
            flags.append(f"Normal HR recovery (-{d} bpm in 1 min) · standard progression.")
        elif q == "poor":
            flags.append(f"Poor HR recovery (-{d} bpm in 1 min) · prioritize duration.")

    return flags


# ─── 6 · FINISHER FILTER ─────────────────────────────────────

# Cardio-limitation veto lists for HIIT/conditioning finisher pools.
# Substring match (case-insensitive) on the exercise name.
_FINISHER_VETOES_BY_LIMIT = {
    "knee_sensitive": [
        "lateral bound", "lateral hop",
        "alternating reverse lunge", "reverse lunge",
        "jump rope",
        "kettlebell swing",  # aggressive · veto by default for knee-sensitive
        "deep squat",
        "box jump", "broad jump", "depth jump",
        "burpee", "skater",
        "step-up", "step up",
        "plyo push-up",
    ],
    "low_back_sensitive": [
        "rower sprint", "rowing sprint",
        "kettlebell swing",
        "med ball slam", "broad jump", "burpee",
        "deep squat", "plyo push-up",
        "heavy hinge",
    ],
    "shoulder_sensitive": [
        "skierg",
        "assault bike",  # arm-driven version
        "battle rope",
        "med ball slam", "plyo push-up",
    ],
    "wrist_sensitive": [
        "battle rope", "med ball slam",
        "burpee", "plyo push-up",
        "farmer carry",
        "rower", "skierg",
    ],
    "hip_sensitive": [
        "kettlebell swing", "lateral bound", "skater",
        "burpee", "broad jump", "depth jump",
    ],
    "high_stress_poor_recovery": [
        "box jump", "depth jump", "broad jump", "burpee",
        "skater", "lateral bound", "lateral hop", "plyo push-up",
    ],
    "not_cleared_for_intervals": [
        "sprint", "interval", "swing", "slam", "jump", "bound",
        "hop", "burpee", "skater",
    ],
}


def filter_finishers_by_cardio_limitations(pool, normalized: dict) -> list:
    """Filter a finisher pool against cardio limitations.

    `pool` is a list of items where item[0] is the exercise name string.
    (Tuple shape is preserved so the existing HIIT builder keeps working.)
    Items whose name contains any veto substring for an active limitation
    are removed.
    """
    if not pool:
        return []
    if not normalized:
        return list(pool)

    limits = set(normalized.get("limitations", []))
    if not limits:
        return list(pool)

    vetoes = set()
    for limit in limits:
        vetoes.update(_FINISHER_VETOES_BY_LIMIT.get(limit, []))

    if not vetoes:
        return list(pool)

    out = []
    for entry in pool:
        # Tolerate both tuples and dicts and Exercise-like objects
        if isinstance(entry, tuple):
            name = str(entry[0]).lower()
        elif isinstance(entry, dict):
            name = str(entry.get("name", "")).lower()
        else:
            name = str(getattr(entry, "name", "")).lower()
        if any(v in name for v in vetoes):
            continue
        out.append(entry)
    return out


# ─── REPLACEMENT POOLS · used when filtering kills too many options ──

# When a knee-sensitive client gets every option vetoed, we offer these
# as drop-in safe replacements. The tuple shape matches the HIIT builder.
KNEE_SAFE_FINISHERS = [
    ("Stationary Bike Intervals", "30 sec on / 60 sec off × 5", "Knee-friendly intensity · pure aerobic"),
    ("Upright Bike Intervals", "30 sec on / 60 sec off × 5", "Quad-friendly resistance · zero impact"),
    ("Arc Trainer Intervals", "30 sec on / 60 sec off × 5", "No impact · full leg engagement"),
    ("Farmer Carry Intervals", "30 sec heavy carry / 30 sec rest × 4", "Grip + core + posture"),
    ("Backward Sled Drag", "10 yd × 4 rounds · 45 sec rest", "Quad-friendly · no patella stress"),
    ("Dead Bug Variations", "30 sec × 3 rounds", "Anti-extension core · no joint stress"),
    ("Battle Rope Slams", "30 sec on / 30 sec off × 5", "Standing or half-kneeling · no jumping"),
]

LOW_BACK_SAFE_FINISHERS = [
    ("Stationary Bike Intervals", "30 sec on / 60 sec off × 5", "Spine-neutral · zero impact"),
    ("Arc Trainer Intervals", "30 sec on / 60 sec off × 5", "Spine-neutral · gentle on lumbar"),
    ("Farmer Carry Intervals", "30 sec heavy carry / 30 sec rest × 4", "Spine-stable · brace and walk"),
    ("Dead Bug Variations", "30 sec × 3 rounds", "Anti-extension core · perfect for low-back"),
    ("Sled Push", "10 yd × 4-5 rounds · 45 sec rest", "Hip drive without spine load"),
]

SHOULDER_SAFE_FINISHERS = [
    ("Stationary Bike Intervals", "30 sec on / 60 sec off × 5", "Lower-body driven · shoulder rest"),
    ("Upright Bike Intervals", "30 sec on / 60 sec off × 5", "Quad-friendly · no shoulder load"),
    ("Sled Push", "10 yd × 4-5 rounds · 45 sec rest", "All hip · arms only stabilize"),
    ("Farmer Carry Intervals", "30 sec carry / 30 sec rest × 4", "Shoulder-neutral when bag depressed"),
    ("Dead Bug Variations", "30 sec × 3 rounds", "Anti-extension core · no shoulder load"),
]


def replacement_finisher_pool(normalized: dict) -> list:
    """If the filter wiped out the regular pool, return a safe replacement pool
    for the dominant limitation. Returns an empty list if no limits are flagged."""
    limits = set(normalized.get("limitations", []))
    if "shoulder_sensitive" in limits:
        return list(SHOULDER_SAFE_FINISHERS)
    if "low_back_sensitive" in limits:
        return list(LOW_BACK_SAFE_FINISHERS)
    if "knee_sensitive" in limits or "hip_sensitive" in limits:
        return list(KNEE_SAFE_FINISHERS)
    return []
