"""
IMS · load prescribed off measured isometric force.

Every gym estimates 1RM from population rep-max formulas. This sets load from
*that client's* directly measured force, taken a few weeks ago on a DynaMo or
VOLTRA.

Where it applies · ONLY where a tested strength anchor does not resolve today.
The existing anchor resolver stays the first choice; a measured isometric value
is the fallback anchor, not a replacement. One mechanism writes load at a time.

The load path has a history (a legacy _fill_load duplicate that had to be
deleted), so this module carries a hard guard: any computed load must be
plausible for the exercise's equipment type, and an implausible combination
raises rather than prints. A wrong number on a client's PDF is worse than a
failed generation.

Every returned prescription carries the source measurement and its date so the
coach can see exactly what the number came from.
"""

from dataclasses import dataclass
from typing import Optional

from ims_contract import load_thresholds
from joint_taxonomy import joints_loaded_by
from objective_measures import days_between


class ImplausibleLoadError(ValueError):
    """A computed load is not physically sensible for the equipment.

    Deliberately loud. Callers must not swallow this · it means the force data,
    the config, or the equipment tagging is wrong, and any of the three needs a
    human before a client sees a number.
    """


@dataclass
class ForceAnchor:
    """A measured isometric value standing in for a tested anchor."""
    test: str
    joint: str
    side: str
    value_lb: float
    device: str
    measured_on: Optional[str]
    position: Optional[str] = None

    def label(self) -> str:
        side = f" {self.side}" if self.side in ("L", "R") else ""
        pos = f" {self.position.replace('_', '-')}" if self.position else ""
        return f"{self.test.replace('_', ' ')}{pos}{side}"

    def evidence(self) -> str:
        d = f", {self.measured_on}" if self.measured_on else ""
        return f"{self.device.upper()} {self.label()} {int(round(self.value_lb))} lb{d}"


# ── equipment normalization ────────────────────────────────
# The library's equipment field is free text and sometimes a list, sometimes a
# string, sometimes None. Normalize to the plausibility keys in the config.

_EQUIPMENT_KEYWORDS = [
    ("trap_bar", ("trap bar", "trap_bar", "hex bar")),
    ("barbell", ("barbell", "bar ", "straight bar", "landmine", "rack")),
    ("dumbbell", ("dumbbell", "dumbell", "db ")),
    ("kettlebell", ("kettlebell", "kb ")),
    ("cable", ("cable", "pulley", "trx", "suspension", "functional trainer")),
    ("machine", ("machine", "leg press", "pulldown", "selectorized", "smith")),
    ("band", ("band", "mini band", "loop")),
    ("sandbag", ("sandbag", "sand bag")),
    ("medicine_ball", ("medball", "medicine ball", "med ball", "slam ball")),
    ("sled", ("sled", "prowler")),
    ("voltra", ("voltra", "digital resistance")),
    ("bodyweight", ("mat", "bodyweight", "body weight", "floor", "bench only")),
]


def equipment_class(entry) -> str:
    """Normalize a library entry's equipment field to a plausibility key.

    Keys off the EQUIPMENT FIELD ONLY. An empty or missing equipment list means
    bodyweight · that is what it means throughout the library, and inferring
    equipment from the exercise NAME would be guessing about the one thing this
    module must not guess about.
    """
    if isinstance(entry, dict):
        raw = entry.get("equipment")
    else:
        raw = entry
    if isinstance(raw, (list, tuple, set)):
        text = " ".join(str(x) for x in raw)
    else:
        text = str(raw or "")
    blob = text.strip().lower()
    if not blob or blob in ("none", "null", "[]"):
        return "bodyweight"
    for key, needles in _EQUIPMENT_KEYWORDS:
        if any(n in blob for n in needles):
            return key
    return "_default"


def check_plausible(load_lb: float, eq_class: str, exercise_name: str,
                    cfg: dict = None) -> float:
    """Raise ImplausibleLoadError unless the load fits the equipment."""
    cfg = cfg or load_thresholds()
    bounds = cfg.get("plausibility", {})
    band = bounds.get(eq_class) or bounds.get("_default", {})
    lo = float(band.get("min_lb", 0))
    hi = float(band.get("max_lb", 0))
    if hi <= 0:
        raise ImplausibleLoadError(
            f"{exercise_name}: equipment '{eq_class}' takes no external load, "
            f"but {load_lb:.0f} lb was computed")
    if not (lo <= load_lb <= hi):
        raise ImplausibleLoadError(
            f"{exercise_name}: {load_lb:.0f} lb is outside the plausible "
            f"{lo:.0f}–{hi:.0f} lb range for {eq_class}")
    return load_lb


# ── anchor selection ───────────────────────────────────────

def find_force_anchor(exercise_entry, objective, cfg: dict = None,
                      exercise_name: str = "") -> Optional[ForceAnchor]:
    """Pick the measured value that best anchors this exercise.

    Preference order ·
      1. A VOLTRA compound reading whose pattern name appears in the exercise
         name · same movement, same client, directly comparable.
      2. The WEAKEST side of a DynaMo test on a joint the exercise loads. The
         weak side sets the load; loading to the strong side is how people get
         hurt.

    Returns None when nothing matches · that is the normal case.
    """
    if objective is None or not objective.has_data():
        return None
    cfg = cfg or load_thresholds()
    current = objective.current

    stale_reject = int(cfg.get("load_from_force", {}).get("staleness_days_reject", 180))

    def fresh(m) -> bool:
        if not m.measured_on:
            return True
        # Compare against the newest date we hold, not "today" · the generator
        # must be reproducible, and wall-clock time would break that.
        age = days_between(current.measured_on, m.measured_on)
        return age is None or age <= stale_reject

    name_l = (exercise_name or "").lower()

    # 1 · VOLTRA pattern match on the exercise name
    for f in current.forces:
        if f.device != "voltra" or f.position != "mid_range":
            continue
        pattern_words = [w for w in f.test.split("_") if len(w) > 3]
        if pattern_words and all(w in name_l for w in pattern_words) and fresh(f):
            return ForceAnchor(test=f.test, joint=f.joint or "", side=f.side,
                               value_lb=f.value_lb, device="voltra",
                               measured_on=f.measured_on, position=f.position)

    # 2 · DynaMo on the joint this exercise loads · weakest side
    #
    # SCOPE GUARD · a DynaMo reading is a single-joint isometric measurement.
    # It can anchor single-joint work. It cannot anchor a compound: a 14 lb
    # shoulder ER reading has no business setting the load on a trap bar
    # deadlift just because both involve the shoulder girdle. So a DynaMo
    # anchor is only offered when the exercise loads exactly ONE canonical
    # joint and that joint is the one that was tested.
    #
    # Compounds get a measured load from VOLTRA (step 1) or from a tested
    # anchor, or they get RIR. That is the correct answer, not a limitation.
    joints = joints_loaded_by(exercise_entry) if exercise_entry else set()
    if len(joints) != 1:
        return None
    joint = next(iter(joints))
    candidates = [f for f in current.forces
                  if f.device == "dynamo" and f.joint == joint and fresh(f)]
    if not candidates:
        return None
    weakest = min(candidates, key=lambda f: f.value_lb)
    return ForceAnchor(test=weakest.test, joint=weakest.joint or "",
                       side=weakest.side, value_lb=weakest.value_lb,
                       device="dynamo", measured_on=weakest.measured_on)


# ── prescription ───────────────────────────────────────────

def load_for_week(anchor: ForceAnchor, week: int, cfg: dict = None) -> float:
    cfg = cfg or load_thresholds()
    lf = cfg.get("load_from_force", {})
    pct_table = lf.get("percent_of_isometric_by_week", {})
    pct = float(pct_table.get(str(week), pct_table.get(str(1), 0.40)))
    pct = min(pct, float(lf.get("max_percent_of_isometric", 0.70)))
    return anchor.value_lb * pct


def build_force_prescriptions(exercise_name: str, exercise_entry,
                              anchor: ForceAnchor, ladder,
                              cfg: dict = None) -> Optional[list]:
    """Build the 4-week prescription list from a measured force anchor.

    ``ladder`` is the sets/reps/RPE ladder for this client (see
    progression_profile) · force data sets the LOAD, the progression profile
    sets the VOLUME. They are independent dimensions and stay that way.

    Raises ImplausibleLoadError rather than printing a nonsense number.
    """
    cfg = cfg or load_thresholds()
    lf = cfg.get("load_from_force", {})
    eq = equipment_class(exercise_entry)

    # No-external-load equipment never gets a force-derived number. Not an
    # error · just not applicable.
    band = cfg.get("plausibility", {}).get(eq) or {}
    if float(band.get("max_lb", 0)) <= 0:
        return None

    try:
        from strength_math import round_load
    except Exception:                       # pragma: no cover · import guard
        round_load = lambda w, e, l: round(w / 5.0) * 5.0  # noqa: E731

    min_lb = float(lf.get("min_prescribable_lb", 5))
    weeks = []
    for tpl in ladder:
        raw = load_for_week(anchor, tpl["week"], cfg)
        rounded = float(round_load(raw, eq, None))
        if rounded < min_lb:
            # Below the smallest sensible increment · fall back to RIR rather
            # than printing "@ 2 lb" on a plan.
            return None
        check_plausible(rounded, eq, exercise_name, cfg)
        weeks.append({
            "week": tpl["week"],
            "sets": tpl["sets"],
            "reps": tpl["reps"],
            "weight": rounded,
            "weight_unit": "lb",
            "weight_note": "/side" if anchor.side in ("L", "R") else "",
            "rpe": tpl.get("rpe", ""),
            "intent_label": tpl.get("intent", ""),
            "tempo_note": tpl.get("tempo", ""),
            "fallback_text": None,
            "display_dose": "",
            "load_source": "measured_isometric_force",
            "load_source_detail": anchor.evidence(),
            "load_source_date": anchor.measured_on,
            "load_source_pct": round(
                float(lf.get("percent_of_isometric_by_week", {})
                      .get(str(tpl["week"]), 0.40)) * 100),
        })

    for w in weeks:
        unit = f" {w['weight_unit']}" if w["weight"] is not None else ""
        note = f" {w['weight_note']}" if w["weight_note"] else ""
        wt = int(w["weight"]) if w["weight"] == int(w["weight"]) else round(w["weight"], 1)
        bits = [f"{w['sets']} × {w['reps']}", f"@ {wt}{unit}{note}"]
        if w["tempo_note"]:
            bits.append(w["tempo_note"])
        if w["rpe"]:
            bits.append(f"RPE {w['rpe']}")
        w["display_dose"] = " · ".join(bits)

    return weeks


def staleness_note(objective, cfg: dict = None) -> Optional[str]:
    """Warn the coach when the assessment driving load is getting old."""
    if objective is None or not objective.has_data():
        return None
    cfg = cfg or load_thresholds()
    warn = int(cfg.get("load_from_force", {}).get("staleness_days_warn", 75))
    age = days_between(objective.current_date, objective.previous_date)
    if age is None:
        return None
    if age > warn:
        return (f"Assessment interval was {age} days · longer than the "
                f"{warn}-day target. Retest before the next block.")
    return None
