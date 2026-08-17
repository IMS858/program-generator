"""
Cardio Capacity & Machine Tolerance · structured profile for cardio prescription.

This module holds all the fields collected by the cardio assessment section
of the form, with bulletproof parsing that drops bad values silently rather
than crashing.

Used by the generator to ·
  - Pick a primary cardio modality the client can actually tolerate
  - Avoid modalities flagged as caution
  - Filter HIIT finishers when joint limitations are present
  - Decide whether to prescribe intervals (only if cleared_for_intervals)
  - Tune Zone 2 duration based on conditioning level
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ─── ENUM-LIKE CONSTANTS ─────────────────────────────────────

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

LIMITATIONS = {
    "knee_sensitive", "hip_sensitive", "low_back_sensitive",
    "shoulder_sensitive", "wrist_sensitive",
    "conditioning_beginner", "deconditioned",
    "high_stress_poor_recovery",
    "cleared_for_intervals", "not_cleared_for_intervals",
}


# ─── HELPER PARSERS ──────────────────────────────────────────

def _clean_str(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _modality_or_none(v) -> Optional[str]:
    s = _clean_str(v)
    if not s:
        return None
    norm = s.lower().replace(" ", "_").replace("-", "_")
    return norm if norm in MODALITIES else None


def _modality_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        m = _modality_or_none(item)
        if m and m not in out:
            out.append(m)
    return out


def _limitation_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        s = _clean_str(item)
        if not s:
            continue
        norm = s.lower().replace(" ", "_").replace("-", "_")
        if norm in LIMITATIONS and norm not in out:
            out.append(norm)
    return out


def _nonneg_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return f if f >= 0 else None
    except (TypeError, ValueError):
        return None


def _nonneg_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        i = int(float(v))
        return i if i >= 0 else None
    except (TypeError, ValueError):
        return None


def _clamp_float(v, lo, hi) -> Optional[float]:
    f = _nonneg_float(v)
    if f is None:
        return None
    return max(lo, min(hi, f))


# ─── DATA CLASSES ────────────────────────────────────────────

@dataclass
class Z2BaselineTest:
    """The 10-minute Zone 2 baseline test the coach ran in studio."""
    machine: Optional[str] = None
    duration_minutes: Optional[float] = None
    avg_hr: Optional[int] = None
    peak_hr: Optional[int] = None
    rpe: Optional[float] = None
    distance: Optional[str] = None       # e.g. "2.4 mi" / "1500 m"
    calories: Optional[int] = None
    avg_watts: Optional[int] = None
    resistance_level: Optional[str] = None
    notes: Optional[str] = None
    joint_tolerance_notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Z2BaselineTest":
        if not isinstance(data, dict):
            return cls()
        return cls(
            machine=_modality_or_none(data.get("machine")),
            duration_minutes=_nonneg_float(data.get("duration_minutes")),
            avg_hr=_nonneg_int(data.get("avg_hr")),
            peak_hr=_nonneg_int(data.get("peak_hr")),
            rpe=_clamp_float(data.get("rpe"), 0, 10),
            distance=_clean_str(data.get("distance")),
            calories=_nonneg_int(data.get("calories")),
            avg_watts=_nonneg_int(data.get("avg_watts")),
            resistance_level=_clean_str(data.get("resistance_level")),
            notes=_clean_str(data.get("notes")),
            joint_tolerance_notes=_clean_str(data.get("joint_tolerance_notes")),
        )

    def has_data(self) -> bool:
        return any(v is not None for v in asdict(self).values())


@dataclass
class IntervalTest:
    """Optional interval tolerance test · only meaningful if cleared_for_intervals."""
    machine: Optional[str] = None
    protocol: Optional[str] = None       # e.g. "20s on / 70s off · 6 rounds"
    work_seconds: Optional[int] = None
    rest_seconds: Optional[int] = None
    rounds: Optional[int] = None
    peak_watts: Optional[int] = None
    avg_watts: Optional[int] = None
    peak_hr: Optional[int] = None
    ending_rpe: Optional[float] = None
    joint_tolerance_notes: Optional[str] = None
    recovery_notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "IntervalTest":
        if not isinstance(data, dict):
            return cls()
        return cls(
            machine=_modality_or_none(data.get("machine")),
            protocol=_clean_str(data.get("protocol")),
            work_seconds=_nonneg_int(data.get("work_seconds")),
            rest_seconds=_nonneg_int(data.get("rest_seconds")),
            rounds=_nonneg_int(data.get("rounds")),
            peak_watts=_nonneg_int(data.get("peak_watts")),
            avg_watts=_nonneg_int(data.get("avg_watts")),
            peak_hr=_nonneg_int(data.get("peak_hr")),
            ending_rpe=_clamp_float(data.get("ending_rpe"), 0, 10),
            joint_tolerance_notes=_clean_str(data.get("joint_tolerance_notes")),
            recovery_notes=_clean_str(data.get("recovery_notes")),
        )

    def has_data(self) -> bool:
        return any(v is not None for v in asdict(self).values())


@dataclass
class HRRecovery:
    """Heart rate recovery snapshot · how fast the client comes back down."""
    end_hr: Optional[int] = None
    one_min_hr: Optional[int] = None
    drop_one_min: Optional[int] = None       # auto-computed if both above set

    @classmethod
    def from_dict(cls, data: dict) -> "HRRecovery":
        if not isinstance(data, dict):
            return cls()
        end_hr = _nonneg_int(data.get("end_hr"))
        one_min_hr = _nonneg_int(data.get("one_min_hr"))
        drop = _nonneg_int(data.get("drop_one_min"))
        # Auto-compute drop if not provided
        if drop is None and end_hr is not None and one_min_hr is not None:
            drop = max(0, end_hr - one_min_hr)
        return cls(end_hr=end_hr, one_min_hr=one_min_hr, drop_one_min=drop)

    def has_data(self) -> bool:
        return any(v is not None for v in (self.end_hr, self.one_min_hr, self.drop_one_min))

    def quality(self) -> Optional[str]:
        """Categorize HR recovery quality · returns 'strong' / 'normal' / 'poor' / None."""
        if self.drop_one_min is None:
            return None
        if self.drop_one_min >= 18:
            return "strong"
        if self.drop_one_min >= 12:
            return "normal"
        return "poor"


@dataclass
class CardioProfile:
    """Complete cardio capacity & machine tolerance assessment."""
    primary_modality: Optional[str] = None
    secondary_modalities: list[str] = field(default_factory=list)
    avoid_modalities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    z2_baseline: Z2BaselineTest = field(default_factory=Z2BaselineTest)
    interval_test: IntervalTest = field(default_factory=IntervalTest)
    hr_recovery: HRRecovery = field(default_factory=HRRecovery)

    @classmethod
    def from_dict(cls, data: dict) -> "CardioProfile":
        if not isinstance(data, dict):
            return cls()
        return cls(
            primary_modality=_modality_or_none(data.get("primary_modality")),
            secondary_modalities=_modality_list(data.get("secondary_modalities")),
            avoid_modalities=_modality_list(data.get("avoid_modalities")),
            limitations=_limitation_list(data.get("limitations")),
            z2_baseline=Z2BaselineTest.from_dict(data.get("z2_baseline")),
            interval_test=IntervalTest.from_dict(data.get("interval_test")),
            hr_recovery=HRRecovery.from_dict(data.get("hr_recovery")),
        )

    # ── Decision helpers · used by the generator ─────────────

    def has_limitation(self, *names: str) -> bool:
        return any(n in self.limitations for n in names)

    def cleared_for_intervals(self) -> bool:
        # Explicit not_cleared overrides everything
        if "not_cleared_for_intervals" in self.limitations:
            return False
        return "cleared_for_intervals" in self.limitations

    def is_deconditioned(self) -> bool:
        return self.has_limitation("conditioning_beginner", "deconditioned")

    def has_data(self) -> bool:
        return (self.primary_modality is not None
                or bool(self.secondary_modalities)
                or bool(self.avoid_modalities)
                or bool(self.limitations)
                or self.z2_baseline.has_data()
                or self.interval_test.has_data()
                or self.hr_recovery.has_data())

    def to_dict(self) -> dict:
        return {
            "primary_modality": self.primary_modality,
            "secondary_modalities": list(self.secondary_modalities),
            "avoid_modalities": list(self.avoid_modalities),
            "limitations": list(self.limitations),
            "z2_baseline": asdict(self.z2_baseline),
            "interval_test": asdict(self.interval_test),
            "hr_recovery": asdict(self.hr_recovery),
        }


def parse_cardio_profile(data) -> CardioProfile:
    """Public entry point · safe parser that always returns a CardioProfile."""
    try:
        return CardioProfile.from_dict(data)
    except Exception:
        return CardioProfile()
