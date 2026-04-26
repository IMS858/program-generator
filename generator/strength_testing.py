"""
IMS Strength Testing · Data Model

Canonical schema for tested-weight strength markers. Every field is optional
to preserve backwards compatibility · existing assessments without test data
must continue to work.

Used by ·
  - web/index.html (JS uses the same field names + load_style enum)
  - app.py · parses incoming form data into StrengthTest objects
  - generator/generator.py · Assessment dataclass references these
  - generator/plan_pdf.py (later) · renders test results on Page 23

LOAD STYLE explainer · the most subtle field
  per_hand          · dumbbell · "40 lbs" means 40 each hand (80 total bodyweight)
  total_load        · barbell, trap bar · "225 lbs" means the whole bar's weight
  cable_stack       · cable machines with a numbered stack · "10" means 10th pin
  machine_number    · selectorized machines without weight · "5" = setting 5
  bodyweight_added  · weighted pull-up, weighted dip · "+45 lbs ON TOP of bodyweight"
  bodyweight_assisted · band-assisted pull-up · "-30 lbs subtracted from bodyweight"
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


# ────────────────────────────────────────────────────────────
# ENUMS · valid values for constrained fields
# ────────────────────────────────────────────────────────────

LOAD_UNITS = ("lb", "kg")

LOAD_STYLES = (
    "per_hand",
    "total_load",
    "cable_stack",
    "machine_number",
    "bodyweight_added",
    "bodyweight_assisted",
)

FORM_QUALITIES = ("clean", "moderate", "poor")

MOVEMENT_CATEGORIES = (
    "squat",
    "hinge",
    "press_horizontal",
    "press_vertical",
    "pull_horizontal",
    "pull_vertical",
    "lunge",
    "carry",
    "rotation",
    "core",
    "isometric_hold",
    "other",
)

EQUIPMENT_TYPES = (
    "dumbbell",
    "barbell",
    "trap_bar",
    "kettlebell",
    "cable",
    "machine",
    "bodyweight",
    "trx",
    "landmine",
    "band",
    "sled",
    "other",
)


# ────────────────────────────────────────────────────────────
# Dataclass
# ────────────────────────────────────────────────────────────

@dataclass
class StrengthTest:
    """One tested strength marker · captures everything the coach measured.

    All fields optional. Use `from_dict` to parse forgivingly · invalid
    values get coerced to None or defaults rather than raising.
    """

    # ── Identification ─────────────────────────────────────
    exercise_name: Optional[str] = None
    movement_category: Optional[str] = None        # one of MOVEMENT_CATEGORIES
    equipment_type: Optional[str] = None           # one of EQUIPMENT_TYPES

    # ── Load convention ────────────────────────────────────
    load_unit: str = "lb"                          # "lb" or "kg"
    load_style: Optional[str] = None               # one of LOAD_STYLES

    # ── Tested rep maxes (any subset; all weights non-negative) ──
    tested_12rm: Optional[float] = None
    tested_10rm: Optional[float] = None
    tested_8rm: Optional[float] = None
    tested_6rm: Optional[float] = None
    tested_5rm: Optional[float] = None
    tested_3rm: Optional[float] = None
    tested_1rm: Optional[float] = None              # tested or estimated

    rm_1_estimated: bool = False                    # True if 1RM was calculated, not lifted

    # ── Performance quality ────────────────────────────────
    form_quality: Optional[str] = None              # "clean" / "moderate" / "poor"
    rpe: Optional[float] = None                     # Rate of Perceived Exertion · 1-10
    rir: Optional[int] = None                       # Reps in Reserve · 0-5
    pain_or_compensation_notes: Optional[str] = None
    test_notes: Optional[str] = None
    coach_notes: Optional[str] = None               # Internal · not shown to client

    # ── Source metadata ────────────────────────────────────
    test_date: Optional[str] = None                 # ISO-ish · "Apr 25, 2026"

    # ──────────────────────────────────────────────────────
    # Construction
    # ──────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "StrengthTest":
        """Parse a dict (from JSON) forgivingly. Bad values silently dropped.

        Validation rules (silent · don't raise) ·
          - All weight fields must be >= 0 if present, else dropped
          - load_unit defaults to 'lb' if missing or invalid
          - load_style must be in LOAD_STYLES, else None
          - movement_category, equipment_type, form_quality enum-checked
          - rpe clamped to 0-10
          - rir clamped to 0-5
        """
        if not isinstance(data, dict):
            return cls()

        # Identification
        name = _clean_str(data.get("exercise_name"))
        cat = _enum_or_none(data.get("movement_category"), MOVEMENT_CATEGORIES)
        equip = _enum_or_none(data.get("equipment_type"), EQUIPMENT_TYPES)

        # Load convention
        unit = data.get("load_unit", "lb")
        if unit not in LOAD_UNITS:
            unit = "lb"
        style = _enum_or_none(data.get("load_style"), LOAD_STYLES)

        # Tested RMs · coerce to non-negative float, drop if invalid
        tests = {}
        for fld in ("tested_12rm", "tested_10rm", "tested_8rm", "tested_6rm",
                    "tested_5rm", "tested_3rm", "tested_1rm"):
            tests[fld] = _nonneg_float(data.get(fld))

        rm1_est = bool(data.get("rm_1_estimated", False))

        # Quality
        form = _enum_or_none(data.get("form_quality"), FORM_QUALITIES)
        rpe = _clamp_float(data.get("rpe"), 0.0, 10.0)
        rir = _clamp_int(data.get("rir"), 0, 5)

        notes_pain = _clean_str(data.get("pain_or_compensation_notes"))
        notes_test = _clean_str(data.get("test_notes"))
        notes_coach = _clean_str(data.get("coach_notes"))
        test_date = _clean_str(data.get("test_date"))

        return cls(
            exercise_name=name,
            movement_category=cat,
            equipment_type=equip,
            load_unit=unit,
            load_style=style,
            **tests,
            rm_1_estimated=rm1_est,
            form_quality=form,
            rpe=rpe,
            rir=rir,
            pain_or_compensation_notes=notes_pain,
            test_notes=notes_test,
            coach_notes=notes_coach,
            test_date=test_date,
        )

    def to_dict(self) -> dict:
        """Return a JSON-friendly dict · drops None values for compactness."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}

    # ──────────────────────────────────────────────────────
    # Convenience accessors · used by the generator + PDF renderer
    # ──────────────────────────────────────────────────────

    def has_any_data(self) -> bool:
        """True if at least one tested weight is set."""
        return any(getattr(self, f) is not None for f in (
            "tested_12rm", "tested_10rm", "tested_8rm", "tested_6rm",
            "tested_5rm", "tested_3rm", "tested_1rm",
        ))

    def best_rm(self) -> Optional[tuple[int, float]]:
        """Return (reps, weight) for the heaviest tested RM, or None.

        Useful for picking a starting weight when the program asks for a
        compound lift starting load.
        """
        for reps, fld in [(1, "tested_1rm"), (3, "tested_3rm"), (5, "tested_5rm"),
                          (6, "tested_6rm"), (8, "tested_8rm"), (10, "tested_10rm"),
                          (12, "tested_12rm")]:
            v = getattr(self, fld)
            if v is not None:
                return (reps, v)
        return None

    def estimated_1rm(self) -> Optional[float]:
        """Return tested 1RM if lifted; otherwise estimate from highest RM tested.

        Uses the Epley formula · 1RM ≈ weight × (1 + reps / 30)
        Conservative · we use whichever tested RM has the lowest reps (closest to 1RM).
        """
        if self.tested_1rm is not None:
            return self.tested_1rm
        best = self.best_rm()
        if best is None:
            return None
        reps, weight = best
        return round(weight * (1 + reps / 30.0), 1)

    def display_label(self) -> str:
        """Short readable string · 'DB Bench Press · 40 lb (per hand)'."""
        parts = []
        if self.exercise_name:
            parts.append(self.exercise_name)
        best = self.best_rm()
        if best:
            reps, weight = best
            unit = self.load_unit
            style_suffix = ""
            if self.load_style == "per_hand":
                style_suffix = " (per hand)"
            elif self.load_style == "bodyweight_added":
                style_suffix = " added"
            elif self.load_style == "bodyweight_assisted":
                style_suffix = " assisted"
            parts.append(f"{int(weight) if weight == int(weight) else weight} {unit}{style_suffix} × {reps}")
        return " · ".join(parts) if parts else "(empty test)"

    def total_load_lbs(self) -> Optional[float]:
        """Return total weight moved in pounds, accounting for load_style.

        For per_hand dumbbells, a '40 lb' entry means 80 lbs total.
        For bodyweight_added, returns the added weight (caller adds bodyweight).
        For bodyweight_assisted, returns negative · caller subtracts from bodyweight.
        Returns None if no weights tested or if it's a stack/machine number (not real lbs).
        """
        best = self.best_rm()
        if best is None:
            return None
        _, weight = best

        # Convert kg → lbs if needed (for downstream comparisons)
        if self.load_unit == "kg":
            weight = weight * 2.20462

        if self.load_style == "per_hand":
            return weight * 2  # both hands
        if self.load_style == "cable_stack" or self.load_style == "machine_number":
            return None  # can't meaningfully convert · these are equipment-specific
        if self.load_style == "bodyweight_assisted":
            return -weight  # subtractive
        # total_load OR bodyweight_added OR None
        return weight


# ────────────────────────────────────────────────────────────
# Coercion helpers · forgive, don't raise
# ────────────────────────────────────────────────────────────

def _clean_str(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _enum_or_none(v, allowed: tuple[str, ...]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if s in allowed else None


def _nonneg_float(v) -> Optional[float]:
    """Return a non-negative float, or None if invalid/negative/missing."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _clamp_float(v, lo: float, hi: float) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, f))


def _clamp_int(v, lo: int, hi: int) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        i = int(v)
    except (TypeError, ValueError):
        try:
            i = int(float(v))
        except (TypeError, ValueError):
            return None
    return max(lo, min(hi, i))


# ────────────────────────────────────────────────────────────
# Collection helper · parse a list of test entries from a payload
# ────────────────────────────────────────────────────────────

def parse_strength_tests(raw_list) -> list[StrengthTest]:
    """Parse `strength_marker_tests` list from incoming form data.

    Always returns a list (possibly empty). Entries with no useful data
    are dropped silently.
    """
    if not isinstance(raw_list, list):
        return []
    out = []
    for item in raw_list:
        test = StrengthTest.from_dict(item) if isinstance(item, dict) else StrengthTest()
        # Keep entry only if it has at least an exercise name or any test result
        if test.exercise_name or test.has_any_data():
            out.append(test)
    return out
