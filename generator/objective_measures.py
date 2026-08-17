"""
IMS · objective measurement ingest.

Coach OS captures an instrumented assessment roughly every two months ·

  VALD DynaMo   · peak isometric force, each side independently
                  (grip, shoulder IR/ER, hip abduction, knee extension)
  Passive ROM   · degrees (shoulder flexion, hip IR, and anything else the
                  coach records)
  VOLTRA        · isometric force on a compound pattern at mid-range and
                  end-range

Those arrive in an OPTIONAL ``objective_measures`` object carrying the current
assessment, the previous one when it exists, and both dates.

Design rules that are not negotiable ·

1. Graceful degradation is the FIRST requirement. Absent or partial data must
   produce byte-identical output to a build with no objective data at all.
   Nothing in this module may raise into the generator · malformed entries are
   dropped and recorded as warnings. Loud failure happens at the API boundary
   (see validation.py), not mid-generation.
2. Everything is normalized once, here · force to lb, ROM to degrees, joints to
   the same canonical vocabulary the contraindication router already uses.
3. Every derived value keeps a pointer back to the measurement and the date
   that produced it, so the coach output can say where a number came from.
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

from ims_contract import load_thresholds


# ==========================================================
# CANONICAL VOCABULARY
# ==========================================================

# Canonical joints are the SAME names the contraindication router uses
# (see Generator._concern_to_joint / _is_heavy_load_for_joint):
#   knee · shoulder · hip · lumbar · cervical · wrist · elbow · ankle
CANONICAL_JOINTS = {
    "knee", "shoulder", "hip", "lumbar", "cervical", "wrist", "elbow", "ankle",
}

# DynaMo test id → (canonical joint, motion)
DYNAMO_TESTS = {
    "grip": ("wrist", "grip"),
    "hand_grip": ("wrist", "grip"),
    "shoulder_ir": ("shoulder", "ir"),
    "shoulder_er": ("shoulder", "er"),
    "shoulder_abduction": ("shoulder", "abduction"),
    "shoulder_flexion": ("shoulder", "flexion"),
    "hip_abduction": ("hip", "abduction"),
    "hip_adduction": ("hip", "adduction"),
    "hip_ir": ("hip", "ir"),
    "hip_er": ("hip", "er"),
    "hip_extension": ("hip", "extension"),
    "knee_extension": ("knee", "extension"),
    "knee_flexion": ("knee", "flexion"),
    "ankle_dorsiflexion": ("ankle", "dorsiflexion"),
    "ankle_plantarflexion": ("ankle", "plantarflexion"),
    "elbow_flexion": ("elbow", "flexion"),
    "elbow_extension": ("elbow", "extension"),
}

_JOINT_ALIASES = {
    "shoulders": "shoulder", "gh": "shoulder", "glenohumeral": "shoulder",
    "knees": "knee",
    "hips": "hip",
    "low_back": "lumbar", "lower_back": "lumbar", "back": "lumbar",
    "lumbar_spine": "lumbar", "spine": "lumbar",
    "neck": "cervical", "cervical_spine": "cervical",
    "hand": "wrist", "grip": "wrist",
    "ankles": "ankle", "foot": "ankle",
}

_SIDE_ALIASES = {
    "l": "L", "left": "L", "lt": "L",
    "r": "R", "right": "R", "rt": "R",
    "b": "bilateral", "bi": "bilateral", "both": "bilateral",
    "bilateral": "bilateral", "": "bilateral", "n/a": "bilateral",
}


def canonical_joint(raw) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        return None
    s = _JOINT_ALIASES.get(s, s)
    return s if s in CANONICAL_JOINTS else None


def canonical_side(raw) -> str:
    s = str(raw or "").strip().lower()
    return _SIDE_ALIASES.get(s, "bilateral")


def canonical_motion(raw) -> str:
    s = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "internal_rotation": "ir", "int_rotation": "ir", "internal_rot": "ir",
        "external_rotation": "er", "ext_rotation": "er", "external_rot": "er",
        "abd": "abduction", "add": "adduction",
        "flex": "flexion", "ext": "extension",
        "dorsiflexion": "dorsiflexion", "df": "dorsiflexion",
    }
    return aliases.get(s, s)


def _to_float(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_lb(value: float, unit, cfg: dict) -> Optional[float]:
    if value is None:
        return None
    u = str(unit or "lb").strip().lower()
    units = cfg.get("units", {})
    if u in ("lb", "lbs", "pound", "pounds", ""):
        return float(value)
    if u in ("kg", "kgs", "kilogram", "kilograms"):
        return float(value) * float(units.get("kg_to_lb", 2.2046226218))
    if u in ("n", "newton", "newtons"):
        return float(value) * float(units.get("newton_to_lb", 0.2248089431))
    return None


def _parse_date(raw) -> Optional[str]:
    """Return an ISO date string, or None. Never raises."""
    if not raw:
        return None
    if isinstance(raw, (date, datetime)):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def days_between(later_iso, earlier_iso) -> Optional[int]:
    if not later_iso or not earlier_iso:
        return None
    try:
        a = datetime.strptime(later_iso, "%Y-%m-%d")
        b = datetime.strptime(earlier_iso, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return (a - b).days


# ==========================================================
# DATA MODELS
# ==========================================================

@dataclass
class ForceMeasure:
    """One peak isometric force reading."""
    test: str                       # canonical DynaMo test id, or a VOLTRA pattern
    joint: Optional[str]            # canonical joint, or None for a VOLTRA pattern
    motion: str
    side: str                       # "L" | "R" | "bilateral"
    value_lb: float
    device: str = "dynamo"          # "dynamo" | "voltra"
    position: Optional[str] = None  # VOLTRA only · "mid_range" | "end_range"
    raw_value: Optional[float] = None
    raw_unit: Optional[str] = None
    measured_on: Optional[str] = None

    @property
    def key(self) -> str:
        pos = f"_{self.position}" if self.position else ""
        return f"{self.test}_{self.side}{pos}".lower()

    def label(self) -> str:
        parts = [self.test.replace("_", " ")]
        if self.position:
            parts.append(self.position.replace("_", "-"))
        if self.side in ("L", "R"):
            parts.append(self.side)
        return " · ".join(parts)

    def evidence(self) -> str:
        v = int(round(self.value_lb))
        d = f", {self.measured_on}" if self.measured_on else ""
        return f"{self.label()} {v} lb{d}"


@dataclass
class RomMeasure:
    """One passive range-of-motion reading, in degrees."""
    joint: str
    motion: str
    side: str
    degrees: float
    mode: str = "passive"
    measured_on: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.joint}_{self.motion}_{self.side}".lower()

    def label(self) -> str:
        side = f" {self.side}" if self.side in ("L", "R") else ""
        return f"{self.joint} {self.motion}{side}".replace("_", " ")

    def evidence(self) -> str:
        d = f", {self.measured_on}" if self.measured_on else ""
        return f"{self.label()} {int(round(self.degrees))}°{d}"


@dataclass
class MeasureSet:
    """One instrumented assessment."""
    measured_on: Optional[str] = None
    bodyweight_lb: Optional[float] = None
    forces: list = field(default_factory=list)   # list[ForceMeasure]
    roms: list = field(default_factory=list)     # list[RomMeasure]
    notes: str = ""

    def is_empty(self) -> bool:
        return not self.forces and not self.roms

    def force(self, test: str, side: str = None, position: str = None):
        for f in self.forces:
            if f.test != test:
                continue
            if side and f.side != side:
                continue
            if position and f.position != position:
                continue
            if position is None and f.position not in (None, "peak"):
                continue
            return f
        return None

    def forces_for_joint(self, joint: str) -> list:
        return [f for f in self.forces if f.joint == joint]

    def rom(self, joint: str, motion: str, side: str = None):
        for r in self.roms:
            if r.joint == joint and r.motion == motion:
                if side and r.side != side:
                    continue
                return r
        return None

    def tested_joints(self) -> list:
        seen = []
        for f in self.forces:
            if f.joint and f.joint not in seen:
                seen.append(f.joint)
        return seen


@dataclass
class ObjectiveMeasures:
    """The full optional payload · current, previous, and both dates."""
    current: MeasureSet
    previous: Optional[MeasureSet] = None
    warnings: list = field(default_factory=list)

    @property
    def current_date(self):
        return self.current.measured_on if self.current else None

    @property
    def previous_date(self):
        return self.previous.measured_on if self.previous else None

    def has_data(self) -> bool:
        return self.current is not None and not self.current.is_empty()

    def has_previous(self) -> bool:
        return self.previous is not None and not self.previous.is_empty()

    def age_days(self) -> Optional[int]:
        return days_between(self.current_date, self.previous_date)

    def deltas(self, cfg: dict = None) -> list:
        """Force + ROM change since the previous assessment.

        Returns a list of plain dicts · safe to serialize straight into the
        coach plan. Empty when there is no previous assessment.
        """
        if not self.has_previous():
            return []
        cfg = cfg or load_thresholds()
        pct_gate = float(cfg.get("delta", {}).get("meaningful_change_pct", 8.0))
        deg_gate = float(cfg.get("delta", {}).get("meaningful_rom_change_deg", 5))

        out = []
        for f in self.current.forces:
            prev = self.previous.force(f.test, f.side, f.position)
            if prev is None or not prev.value_lb:
                continue
            delta = f.value_lb - prev.value_lb
            pct = (delta / prev.value_lb) * 100.0
            out.append({
                "kind": "force",
                "label": f.label(),
                "previous": round(prev.value_lb, 1),
                "current": round(f.value_lb, 1),
                "unit": "lb",
                "delta": round(delta, 1),
                "delta_pct": round(pct, 1),
                "meaningful": abs(pct) >= pct_gate,
                "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
                "previous_date": self.previous_date,
                "current_date": self.current_date,
            })
        for r in self.current.roms:
            prev = self.previous.rom(r.joint, r.motion, r.side)
            if prev is None:
                continue
            delta = r.degrees - prev.degrees
            out.append({
                "kind": "rom",
                "label": r.label(),
                "previous": round(prev.degrees, 1),
                "current": round(r.degrees, 1),
                "unit": "deg",
                "delta": round(delta, 1),
                "delta_pct": (round((delta / prev.degrees) * 100.0, 1)
                              if prev.degrees else None),
                "meaningful": abs(delta) >= deg_gate,
                "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
                "previous_date": self.previous_date,
                "current_date": self.current_date,
            })
        return out

    def measure_table(self) -> list:
        """Flat table of every current measurement · for the coach plan."""
        rows = []
        for f in self.current.forces:
            rows.append({
                "kind": "force",
                "device": f.device,
                "test": f.test,
                "position": f.position,
                "side": f.side,
                "value": round(f.value_lb, 1),
                "unit": "lb",
                "measured_on": f.measured_on,
            })
        for r in self.current.roms:
            rows.append({
                "kind": "rom",
                "device": "goniometry",
                "test": f"{r.joint}_{r.motion}",
                "position": r.mode,
                "side": r.side,
                "value": round(r.degrees, 1),
                "unit": "deg",
                "measured_on": r.measured_on,
            })
        return rows

    def to_dict(self) -> dict:
        return {
            "current_date": self.current_date,
            "previous_date": self.previous_date,
            "bodyweight_lb": self.current.bodyweight_lb if self.current else None,
            "measures": self.measure_table(),
            "warnings": list(self.warnings),
        }


# ==========================================================
# PARSING
# ==========================================================

def _parse_measure_set(raw, cfg: dict, warnings: list, which: str,
                       fallback_date=None) -> Optional[MeasureSet]:
    if not isinstance(raw, dict):
        if raw not in (None, {}, []):
            warnings.append(f"objective_measures.{which} ignored · expected an object")
        return None

    measured_on = _parse_date(raw.get("date") or raw.get("measured_on") or fallback_date)
    bw = _to_float(raw.get("bodyweight_lb") or raw.get("bodyweight"))
    if bw is not None and raw.get("bodyweight_unit"):
        bw = _to_lb(bw, raw.get("bodyweight_unit"), cfg)
    if bw is not None and not (50 <= bw <= 700):
        warnings.append(f"objective_measures.{which}.bodyweight {bw} out of range · ignored")
        bw = None

    ms = MeasureSet(measured_on=measured_on, bodyweight_lb=bw,
                    notes=str(raw.get("notes") or ""))

    # ── DynaMo peak isometric force ──
    for i, entry in enumerate(raw.get("dynamo") or raw.get("force") or []):
        if not isinstance(entry, dict):
            warnings.append(f"{which}.dynamo[{i}] ignored · not an object")
            continue
        test = str(entry.get("test") or entry.get("name") or "").strip().lower()
        test = test.replace(" ", "_").replace("-", "_")
        if test not in DYNAMO_TESTS:
            warnings.append(f"{which}.dynamo[{i}] ignored · unknown test '{test}'")
            continue
        val = _to_float(entry.get("value") if entry.get("value") is not None
                        else entry.get("peak_force"))
        lb = _to_lb(val, entry.get("unit"), cfg)
        if lb is None or lb <= 0:
            warnings.append(f"{which}.dynamo[{i}] ({test}) ignored · unreadable value")
            continue
        joint, motion = DYNAMO_TESTS[test]
        ms.forces.append(ForceMeasure(
            test=test, joint=joint, motion=motion,
            side=canonical_side(entry.get("side")),
            value_lb=lb, device="dynamo",
            raw_value=val, raw_unit=str(entry.get("unit") or "lb"),
            measured_on=measured_on,
        ))

    # ── VOLTRA compound isometric, mid-range vs end-range ──
    for i, entry in enumerate(raw.get("voltra") or []):
        if not isinstance(entry, dict):
            warnings.append(f"{which}.voltra[{i}] ignored · not an object")
            continue
        pattern = str(entry.get("pattern") or entry.get("test") or "").strip().lower()
        pattern = pattern.replace(" ", "_").replace("-", "_")
        position = str(entry.get("position") or "").strip().lower().replace("-", "_")
        if position in ("mid", "midrange"):
            position = "mid_range"
        if position in ("end", "endrange"):
            position = "end_range"
        if not pattern or position not in ("mid_range", "end_range"):
            warnings.append(f"{which}.voltra[{i}] ignored · needs pattern + mid_range/end_range")
            continue
        val = _to_float(entry.get("value") if entry.get("value") is not None
                        else entry.get("peak_force"))
        lb = _to_lb(val, entry.get("unit"), cfg)
        if lb is None or lb <= 0:
            warnings.append(f"{which}.voltra[{i}] ignored · unreadable value")
            continue
        ms.forces.append(ForceMeasure(
            test=pattern,
            joint=canonical_joint(entry.get("joint")),
            motion=canonical_motion(entry.get("motion") or "compound"),
            side=canonical_side(entry.get("side")),
            value_lb=lb, device="voltra", position=position,
            raw_value=val, raw_unit=str(entry.get("unit") or "lb"),
            measured_on=measured_on,
        ))

    # ── Passive ROM ──
    rom_raw = raw.get("rom") or raw.get("rom_degrees") or []
    if isinstance(rom_raw, dict):
        # Tolerate the flat Coach OS shape · {"shoulder_flexion_L": "148"}
        converted = []
        for k, v in rom_raw.items():
            parts = str(k).split("_")
            side = parts[-1] if parts and parts[-1].lower() in ("l", "r") else None
            core = parts[:-1] if side else parts
            if len(core) < 2:
                continue
            converted.append({"joint": core[0], "motion": "_".join(core[1:]),
                              "side": side, "degrees": v})
        rom_raw = converted
    for i, entry in enumerate(rom_raw or []):
        if not isinstance(entry, dict):
            warnings.append(f"{which}.rom[{i}] ignored · not an object")
            continue
        joint = canonical_joint(entry.get("joint"))
        motion = canonical_motion(entry.get("motion") or entry.get("direction"))
        deg = _to_float(entry.get("degrees") if entry.get("degrees") is not None
                        else entry.get("value"))
        if not joint or not motion or deg is None:
            warnings.append(f"{which}.rom[{i}] ignored · needs joint, motion and degrees")
            continue
        if not (-30 <= deg <= 200):
            warnings.append(f"{which}.rom[{i}] ignored · {deg}° out of plausible range")
            continue
        ms.roms.append(RomMeasure(
            joint=joint, motion=motion, side=canonical_side(entry.get("side")),
            degrees=deg, mode=str(entry.get("mode") or "passive"),
            measured_on=measured_on,
        ))

    return ms


def parse_objective_measures(raw, cfg: dict = None) -> Optional[ObjectiveMeasures]:
    """Parse the optional ``objective_measures`` object.

    Returns None when there is nothing usable · that is the common case and it
    must cost the caller nothing. Never raises.
    """
    if not raw:
        return None
    try:
        cfg = cfg or load_thresholds()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None

    warnings = []
    current_raw = raw.get("current")
    if current_raw is None and ("dynamo" in raw or "rom" in raw or "voltra" in raw):
        current_raw = raw  # tolerate a bare single assessment
    current = _parse_measure_set(current_raw, cfg, warnings, "current",
                                 fallback_date=raw.get("current_date"))
    if current is None or current.is_empty():
        return None

    previous = _parse_measure_set(raw.get("previous"), cfg, warnings, "previous",
                                  fallback_date=raw.get("previous_date"))
    if previous is not None and previous.is_empty():
        previous = None

    # A previous set dated after the current one is a data-entry error · drop it
    # rather than computing backwards deltas.
    if previous is not None and current.measured_on and previous.measured_on:
        if previous.measured_on > current.measured_on:
            warnings.append("previous assessment is dated after the current one · deltas skipped")
            previous = None

    if previous is not None and previous.bodyweight_lb is None:
        previous.bodyweight_lb = current.bodyweight_lb

    return ObjectiveMeasures(current=current, previous=previous, warnings=warnings)
