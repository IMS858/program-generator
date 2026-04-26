"""
IMS Strength Math · Personalized Loading

Converts tested rep maxes from a StrengthTest object into personalized
weekly training loads for the IMS 4-week block.

Philosophy ·
  Use a CONSERVATIVE training max (0.85 × estimated 1RM, not a true 1RM).
  This is "Technical Training Max" · the load you can move with clean reps,
  not the load you grind out at competition.

Adjustments stacked on top ·
  form_quality = poor       → ×0.85 (15% reduction)
  form_quality = moderate   → ×0.93 (7% reduction)
  form_quality = clean      → ×1.00 (no change)
  pain_or_compensation_notes present → ×0.90 (10% reduction, plus coach flag)

The 4-week IMS block ·
  Week 1 · Base Volume      · 3 × 12 @ ~12RM weight · RPE 7
  Week 2 · Tempo Control    · 3 × 10 @ ~10RM weight · 3-sec eccentric · RPE 7-8
  Week 3 · Strength Build   · 4 × 8  @ ~8RM weight  · RPE 8
  Week 4 · Performance Week · 4 × 6  @ ~6RM weight  · RPE 8-9 (or retest 10RM)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ─── Tunables · easy to find at the top ─────────────────────

TRAINING_MAX_MULTIPLIER = 0.85          # IMS Technical Training Max · 0.85 of est. 1RM

FORM_QUALITY_MULTIPLIERS = {
    "clean":    1.00,
    "moderate": 0.93,                   # ~7% reduction
    "poor":     0.85,                   # 15% reduction
}

PAIN_NOTES_REDUCTION = 0.90             # 10% off if any pain/compensation noted

INCONSISTENCY_THRESHOLD = 0.12          # 12% above the median triggers a flag

# Per-week percent-of-1RM targets · used when tested RM at that rep range is missing
WEEK_PCT_OF_1RM = {
    1: 0.65,                            # 12-rep work · ~65% 1RM
    2: 0.72,                            # 10-rep work · ~72% 1RM
    3: 0.78,                            # 8-rep work · ~78% 1RM
    4: 0.83,                            # 6-rep work · ~83% 1RM
}


# ─── Output dataclasses ────────────────────────────────────

@dataclass
class WeekPrescription:
    """One week's prescription for one exercise."""
    week: int
    sets: int
    reps: int
    weight: Optional[float] = None
    weight_unit: str = "lb"
    weight_note: str = ""               # e.g. "/hand" or "added"
    rpe: str = ""
    intent_label: str = ""
    tempo_note: str = ""
    coach_note: str = ""
    fallback_text: Optional[str] = None

    def display_dose(self) -> str:
        """Client-facing one-line dose string for the PDF cell."""
        bits = [f"{self.sets} × {self.reps}"]
        if self.weight is not None:
            wt = int(self.weight) if self.weight == int(self.weight) else round(self.weight, 1)
            unit = f" {self.weight_unit}" if self.weight_unit else ""
            note = f" {self.weight_note}" if self.weight_note else ""
            bits.append(f"@ {wt}{unit}{note}")
        elif self.fallback_text:
            bits.append(f"@ {self.fallback_text}")
        if self.tempo_note:
            bits.append(self.tempo_note)
        if self.rpe:
            bits.append(f"RPE {self.rpe}")
        return " · ".join(bits)


@dataclass
class Estimates:
    """Output of calculate_estimates_from_tests."""
    estimated_1rm_from_each_test: dict = field(default_factory=dict)
    best_estimate: Optional[float] = None
    conservative_training_max: Optional[float] = None
    flags: list = field(default_factory=list)


# ─── 1 · estimate_1rm ──────────────────────────────────────

def estimate_1rm(weight: float, reps: int) -> float:
    """Epley · estimated_1rm = weight × (1 + reps/30)."""
    return float(weight) * (1.0 + float(reps) / 30.0)


# ─── 2 · calculate_estimates_from_tests ────────────────────

def calculate_estimates_from_tests(strength_test) -> Estimates:
    """Read a StrengthTest object, return Estimates."""
    if strength_test is None:
        return Estimates()

    rep_to_field = [
        (1, "tested_1rm"),
        (3, "tested_3rm"),
        (5, "tested_5rm"),
        (6, "tested_6rm"),
        (8, "tested_8rm"),
        (10, "tested_10rm"),
        (12, "tested_12rm"),
    ]

    per_test = {}
    for reps, fld in rep_to_field:
        v = getattr(strength_test, fld, None)
        if v is None or v < 0:
            continue
        per_test[reps] = float(v) if reps == 1 else estimate_1rm(v, reps)

    if not per_test:
        return Estimates()

    best_reps = min(per_test.keys())
    best = per_test[best_reps]

    tm = best * TRAINING_MAX_MULTIPLIER

    fq = getattr(strength_test, "form_quality", None) or "clean"
    fq_mult = FORM_QUALITY_MULTIPLIERS.get(fq, 1.00)
    tm *= fq_mult

    pain_present = bool(getattr(strength_test, "pain_or_compensation_notes", None))
    if pain_present:
        tm *= PAIN_NOTES_REDUCTION

    flags = list(detect_inconsistencies(strength_test))
    if fq == "poor":
        flags.append("Form quality marked POOR · loads reduced 15%.")
    elif fq == "moderate":
        flags.append("Form quality marked moderate · loads reduced 7%.")
    if pain_present:
        flags.append("Pain or compensation noted · loads reduced 10% · monitor at first session.")

    return Estimates(
        estimated_1rm_from_each_test=per_test,
        best_estimate=best,
        conservative_training_max=tm,
        flags=flags,
    )


# ─── 3 · detect_inconsistencies ────────────────────────────

def detect_inconsistencies(strength_test) -> list:
    """Flag if one rep range produces a much higher estimate than others."""
    if strength_test is None:
        return []

    rep_to_field = [
        (3, "tested_3rm"),
        (5, "tested_5rm"),
        (6, "tested_6rm"),
        (8, "tested_8rm"),
        (10, "tested_10rm"),
        (12, "tested_12rm"),
    ]

    estimates = {}
    for reps, fld in rep_to_field:
        v = getattr(strength_test, fld, None)
        if v is None or v < 0:
            continue
        estimates[reps] = estimate_1rm(v, reps)

    if len(estimates) < 2:
        return []

    sorted_vals = sorted(estimates.values())
    n = len(sorted_vals)
    med = (sorted_vals[n // 2] if n % 2 == 1
           else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2)

    flags = []
    for reps, est in estimates.items():
        if med > 0 and (est - med) / med >= INCONSISTENCY_THRESHOLD:
            pct = (est - med) / med * 100
            flags.append(
                f"{reps}RM estimate ({est:.0f} lb) is {pct:.0f}% above the median "
                f"({med:.0f} lb) · possible strength-endurance gap or inconsistent "
                f"testing. Use conservative loading."
            )
            break

    return flags


# ─── 4 · get_working_weight_for_reps ───────────────────────

def get_working_weight_for_reps(strength_test, target_reps: int,
                                 estimates: Optional[Estimates] = None) -> Optional[float]:
    """Return working weight for a target rep count, or None if no data."""
    if strength_test is None:
        return None

    field_name = f"tested_{target_reps}rm"
    direct = getattr(strength_test, field_name, None)
    if direct is not None and direct >= 0:
        fq_mult = FORM_QUALITY_MULTIPLIERS.get(
            getattr(strength_test, "form_quality", None) or "clean", 1.00)
        pain_mult = (PAIN_NOTES_REDUCTION
                     if getattr(strength_test, "pain_or_compensation_notes", None)
                     else 1.00)
        return float(direct) * fq_mult * pain_mult

    if estimates is None:
        estimates = calculate_estimates_from_tests(strength_test)
    if estimates.conservative_training_max is None:
        return None

    pct = WEEK_PCT_OF_1RM.get(_week_for_reps(target_reps))
    if pct is None:
        return None

    implied_1rm = estimates.conservative_training_max / TRAINING_MAX_MULTIPLIER
    return implied_1rm * pct


def _week_for_reps(reps: int) -> Optional[int]:
    return {12: 1, 10: 2, 8: 3, 6: 4}.get(reps)


# ─── 5 · round_load ────────────────────────────────────────

def round_load(weight: float, equipment_type: Optional[str],
               load_style: Optional[str]) -> float:
    """Round to a sensible gym increment."""
    if weight is None or weight < 0:
        return weight

    eq = (equipment_type or "").lower()
    ls = (load_style or "").lower()

    if eq == "dumbbell" or ls == "per_hand":
        return _round_to(weight, 2.5) if weight < 30 else _round_to(weight, 5)
    if eq in ("barbell", "trap_bar") or ls == "total_load":
        return _round_to(weight, 5)
    if eq == "kettlebell":
        return _round_to(weight, 4)
    if ls == "cable_stack":
        return _round_to(weight, 5)
    if ls == "machine_number":
        return float(round(weight))
    if ls == "bodyweight_added":
        return _round_to(weight, 2.5)
    if ls == "bodyweight_assisted":
        return _round_to(weight, 5)
    return _round_to(weight, 5)


def _round_to(weight: float, increment: float) -> float:
    return round(weight / increment) * increment


# ─── 6 · generate_4_week_progression ───────────────────────

WEEK_TEMPLATES = [
    {"week": 1, "sets": 3, "reps": 12, "intent": "Base Volume",
     "rpe": "7", "tempo": ""},
    {"week": 2, "sets": 3, "reps": 10, "intent": "Tempo Control",
     "rpe": "7-8", "tempo": "3-sec eccentric"},
    {"week": 3, "sets": 4, "reps": 8, "intent": "Strength Build",
     "rpe": "8", "tempo": ""},
    {"week": 4, "sets": 4, "reps": 6, "intent": "Performance Week",
     "rpe": "8-9", "tempo": ""},
]


def generate_4_week_progression(strength_test, exercise_name: Optional[str] = None) -> dict:
    """Build a 4-week progression for one exercise."""
    estimates = calculate_estimates_from_tests(strength_test)
    has_data = estimates.conservative_training_max is not None

    weeks = []
    for tpl in WEEK_TEMPLATES:
        week_num = tpl["week"]
        target_reps = tpl["reps"]

        weight = None
        weight_note = ""
        unit = "lb"
        fallback = None

        if has_data:
            raw = get_working_weight_for_reps(strength_test, target_reps,
                                               estimates=estimates)
            if raw is not None:
                weight = round_load(
                    raw,
                    getattr(strength_test, "equipment_type", None),
                    getattr(strength_test, "load_style", None),
                )
                unit = getattr(strength_test, "load_unit", "lb") or "lb"
                ls = getattr(strength_test, "load_style", None)
                if ls == "per_hand":
                    weight_note = "/hand"
                elif ls == "bodyweight_added":
                    weight_note = "added"
                elif ls == "bodyweight_assisted":
                    weight_note = "assist"
                elif ls == "cable_stack":
                    weight_note = "(stack)"
                    unit = ""
                elif ls == "machine_number":
                    weight_note = "(setting)"
                    unit = ""
        if weight is None:
            fallback = "load that leaves 2-3 reps in reserve"

        coach_note = "Or · retest 10RM if coach approves." if week_num == 4 else ""

        weeks.append(WeekPrescription(
            week=week_num,
            sets=tpl["sets"],
            reps=target_reps,
            weight=weight,
            weight_unit=unit,
            weight_note=weight_note,
            rpe=tpl["rpe"],
            intent_label=tpl["intent"],
            tempo_note=tpl["tempo"],
            coach_note=coach_note,
            fallback_text=fallback,
        ))

    client_lines = []
    coach_lines = []
    for w in weeks:
        title = f"Week {w.week} · {w.intent_label}"
        line = w.display_dose()
        client_lines.append({"title": title, "dose": line})
        coach_line = {"title": title, "dose": line}
        if w.coach_note:
            coach_line["note"] = w.coach_note
        coach_lines.append(coach_line)

    return {
        "exercise_name": exercise_name or getattr(strength_test, "exercise_name", None),
        "has_test_data": has_data,
        "weeks": weeks,
        "client": client_lines,
        "coach": coach_lines,
        "flags": estimates.flags,
        "training_max": estimates.conservative_training_max,
        "estimated_1rm": estimates.best_estimate,
    }
