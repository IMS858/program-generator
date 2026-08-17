"""
IMS · ROM × force routing.

This is the cheapest high-value use of instrumented data, because it plugs
into the one subsystem that is already good: the joint-safety contraindication
router. It encodes a distinction a coach makes by hand every week ·

    can't reach that range because they are WEAK there
        vs
    can't reach that range because TISSUE won't let them

Quadrant · ROM axis × end-range force axis ·

  limited ROM  + weak force    → CAPACITY            → route toward loaded end-range work
  limited ROM  + normal force  → PASSIVE_RESTRICTION → route away from loading that joint,
                                                        flag for manual therapy
  full ROM     + weak force    → UNCONTROLLED_RANGE  → highest priority · controlled
                                                        end-range work BEFORE load
  full ROM     + normal force  → no signal

PRECEDENCE · these are ADVISORY ROUTES, NOT VETOES.

A measured signal may never override a safety reroute. Concretely ·

  * A hard contraindication on a joint suppresses any signal that would route
    work TOWARD loading that joint. The suppression is recorded, not silent.
  * A signal routing AWAY from loading is always kept · it only ever makes the
    program more conservative, so it can never fight the safety layer.
  * Nothing in this module returns a veto. Vetoes belong to
    Generator._violates_constraints and stay there.

``apply_precedence`` is the single place that enforces this, and it is proved
by test_objective_measures.TestPrecedence.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

from ims_contract import load_thresholds


# Quadrant ids
CAPACITY = "capacity"
PASSIVE_RESTRICTION = "passive_restriction"
UNCONTROLLED_RANGE = "uncontrolled_range"

# Routes
ROUTE_TOWARD_LOADED_END_RANGE = "toward_loaded_end_range"
ROUTE_AWAY_FROM_LOADING = "away_from_loading"
ROUTE_TOWARD_CONTROLLED_END_RANGE = "toward_controlled_end_range"

# Which routes push work TOWARD a joint · these are the ones a hard
# contraindication must be able to suppress.
_TOWARD_ROUTES = {ROUTE_TOWARD_LOADED_END_RANGE, ROUTE_TOWARD_CONTROLLED_END_RANGE}

_QUADRANT_PRIORITY = {
    UNCONTROLLED_RANGE: 1,   # highest
    PASSIVE_RESTRICTION: 2,
    CAPACITY: 3,
}

_QUADRANT_ROUTE = {
    CAPACITY: ROUTE_TOWARD_LOADED_END_RANGE,
    PASSIVE_RESTRICTION: ROUTE_AWAY_FROM_LOADING,
    UNCONTROLLED_RANGE: ROUTE_TOWARD_CONTROLLED_END_RANGE,
}

_QUADRANT_COACH_TEXT = {
    CAPACITY: ("Restricted range with weak end-range force · capacity problem. "
               "Load the end range progressively."),
    PASSIVE_RESTRICTION: ("Restricted range with intact end-range force · passive "
                          "restriction. Unload this joint and refer for manual therapy."),
    UNCONTROLLED_RANGE: ("Full range with weak end-range force · uncontrolled range. "
                         "Earn control at end range before adding load."),
}


@dataclass
class ForceSignal:
    """One advisory routing decision, with the measurement that caused it."""
    joint: str
    side: str
    motion: str
    quadrant: str
    route: str
    priority: int
    confidence: str                       # "high" | "low"
    rom_evidence: Optional[str] = None
    force_evidence: Optional[str] = None
    coach_note: str = ""
    flag_manual_therapy: bool = False
    suppressed_by: Optional[str] = None   # set by apply_precedence
    measured_on: Optional[str] = None

    @property
    def active(self) -> bool:
        return self.suppressed_by is None

    def evidence(self) -> str:
        bits = [b for b in (self.rom_evidence, self.force_evidence) if b]
        return " · ".join(bits)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = self.evidence()
        d["active"] = self.active
        return d


# ==========================================================
# AXIS CLASSIFICATION
# ==========================================================

def _classify_rom(rom, cfg: dict) -> Optional[str]:
    """'limited' | 'full' | None (indeterminate · no norm, or in the gap)."""
    norms = cfg.get("rom_norms", {})
    key = f"{rom.joint}_{rom.motion}"
    norm = norms.get(key)
    if not norm:
        return None
    if rom.degrees < float(norm["limited_below"]):
        return "limited"
    if rom.degrees >= float(norm["full_at_or_above"]):
        return "full"
    return None


def _classify_force(measure_set, joint: str, side: str, cfg: dict):
    """Classify end-range force for a joint/side.

    Returns (verdict, evidence, confidence) where verdict is
    'weak' | 'normal' | None.

    Three sources, in descending order of directness ·
      1. VOLTRA end-range / mid-range ratio on a pattern tagged to this joint.
         This is literally end-range force · use it when it exists.
      2. DynaMo peak isometric normalized to bodyweight.
      3. Contralateral asymmetry, when there is no bodyweight to normalize by.
         Marked low confidence.
    """
    # 1 · VOLTRA end-range vs mid-range
    er_cfg = cfg.get("end_range_force", {})
    for f in measure_set.forces:
        if f.device != "voltra" or f.position != "end_range":
            continue
        if f.joint and f.joint != joint:
            continue
        if f.side in ("L", "R") and side in ("L", "R") and f.side != side:
            continue
        mid = measure_set.force(f.test, f.side, "mid_range")
        if not mid or not mid.value_lb:
            continue
        ratio = f.value_lb / mid.value_lb
        ev = (f"VOLTRA {f.test.replace('_', ' ')} end-range "
              f"{int(round(f.value_lb))} lb vs mid-range "
              f"{int(round(mid.value_lb))} lb ({ratio:.0%})")
        if ratio < float(er_cfg.get("weak_below_ratio", 0.55)):
            return "weak", ev, "high"
        if ratio >= float(er_cfg.get("normal_at_or_above_ratio", 0.70)):
            return "normal", ev, "high"
        return None, ev, "high"

    # 2 · DynaMo peak isometric normalized to bodyweight
    candidates = [f for f in measure_set.forces
                  if f.device == "dynamo" and f.joint == joint
                  and (side not in ("L", "R") or f.side in (side, "bilateral"))]
    if not candidates:
        return None, None, "low"
    # Prefer a side-matched reading
    measure = next((f for f in candidates if f.side == side), candidates[0])

    bw = measure_set.bodyweight_lb
    norms = cfg.get("force_norms", {})
    norm = norms.get(measure.test) or norms.get("_default", {})
    if bw and norm:
        ratio = measure.value_lb / bw
        ev = (f"{measure.label()} {int(round(measure.value_lb))} lb "
              f"({ratio:.2f}× bodyweight)")
        if ratio < float(norm["weak_below_bw_ratio"]):
            return "weak", ev, "high"
        if ratio >= float(norm["normal_at_or_above_bw_ratio"]):
            return "normal", ev, "high"
        return None, ev, "high"

    # 3 · Asymmetry fallback · no bodyweight on file
    other = "R" if measure.side == "L" else "L"
    contra = measure_set.force(measure.test, other)
    if contra and contra.value_lb:
        stronger = max(measure.value_lb, contra.value_lb)
        gap = abs(measure.value_lb - contra.value_lb) / stronger * 100.0
        ev = (f"{measure.label()} {int(round(measure.value_lb))} lb vs "
              f"{other} {int(round(contra.value_lb))} lb ({gap:.0f}% gap)")
        gate = float(cfg.get("asymmetry", {}).get("weak_side_is_weak_at_pct", 15.0))
        if gap >= gate and measure.value_lb < contra.value_lb:
            return "weak", ev, "low"
        return "normal", ev, "low"

    return None, f"{measure.label()} {int(round(measure.value_lb))} lb", "low"


# ==========================================================
# QUADRANT
# ==========================================================

def build_signals(objective, cfg: dict = None) -> list:
    """Derive advisory routing signals from one ObjectiveMeasures.

    Only emits a signal where BOTH axes resolve · a joint with ROM but no
    force reading, or force but no ROM, produces nothing. That is deliberate:
    a half-measured joint is exactly where a confident-sounding route does
    the most damage.
    """
    if objective is None or not objective.has_data():
        return []
    cfg = cfg or load_thresholds()
    current = objective.current

    signals = []
    for rom in current.roms:
        rom_class = _classify_rom(rom, cfg)
        if rom_class is None:
            continue
        force_class, force_ev, confidence = _classify_force(
            current, rom.joint, rom.side, cfg)
        if force_class is None:
            continue

        if rom_class == "limited" and force_class == "weak":
            quadrant = CAPACITY
        elif rom_class == "limited" and force_class == "normal":
            quadrant = PASSIVE_RESTRICTION
        elif rom_class == "full" and force_class == "weak":
            quadrant = UNCONTROLLED_RANGE
        else:
            continue  # full + normal · no signal

        signals.append(ForceSignal(
            joint=rom.joint,
            side=rom.side,
            motion=rom.motion,
            quadrant=quadrant,
            route=_QUADRANT_ROUTE[quadrant],
            priority=_QUADRANT_PRIORITY[quadrant],
            confidence=confidence,
            rom_evidence=rom.evidence(),
            force_evidence=force_ev,
            coach_note=_QUADRANT_COACH_TEXT[quadrant],
            flag_manual_therapy=(quadrant == PASSIVE_RESTRICTION),
            measured_on=rom.measured_on or current.measured_on,
        ))

    signals.sort(key=lambda s: (s.priority, s.joint, s.side))
    return signals


# ==========================================================
# PRECEDENCE · SAFETY ALWAYS WINS
# ==========================================================

def apply_precedence(signals: list, contraindicated_joints) -> list:
    """Suppress any signal that would route work TOWARD a contraindicated joint.

    This is the whole safety contract of the feature, in one function ·

      * routes toward a joint  → suppressed when that joint is hard-blocked
      * routes away from a joint → always survive (they only add caution)
      * suppression is recorded on the signal, never silent

    A suppressed signal is still returned, so the coach plan can show that a
    measurement was seen and deliberately not acted on.
    """
    blocked = {str(j).lower() for j in (contraindicated_joints or []) if j}
    for s in signals:
        if s.route in _TOWARD_ROUTES and s.joint in blocked:
            s.suppressed_by = "hard_contraindication"
        else:
            s.suppressed_by = None
    return signals


# ==========================================================
# CONSUMER-FACING VIEWS
# ==========================================================

def joints_to_unload(signals: list) -> set:
    """Joints an ACTIVE signal says to route load away from (advisory)."""
    return {s.joint for s in signals
            if s.active and s.route == ROUTE_AWAY_FROM_LOADING}


def joints_needing_control_first(signals: list) -> set:
    """Full range, weak end-range · earn control before load."""
    return {s.joint for s in signals
            if s.active and s.route == ROUTE_TOWARD_CONTROLLED_END_RANGE}


def joints_for_loaded_end_range(signals: list) -> set:
    """Limited range, weak end-range · progressive loaded end-range work."""
    return {s.joint for s in signals
            if s.active and s.route == ROUTE_TOWARD_LOADED_END_RANGE}


def manual_therapy_flags(signals: list) -> list:
    """Coach-output referral flags · passive restriction, not a training problem."""
    out = []
    for s in signals:
        if s.active and s.flag_manual_therapy:
            side = f" {s.side}" if s.side in ("L", "R") else ""
            out.append({
                "joint": s.joint,
                "side": s.side,
                "text": (f"{s.joint.title()} {s.motion}{side} · passive restriction. "
                         f"Refer for manual therapy · loading will not resolve this."),
                "evidence": s.evidence(),
                "measured_on": s.measured_on,
            })
    return out
