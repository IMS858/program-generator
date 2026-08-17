"""
IMS · side-aware dose (Phase 3).

The plumbing item. Until now MobilityRating.side was captured on every row of
the mobility map and never read: a client with a red left shoulder and a green
right shoulder got the identical prescription on both sides.

What changed to make this possible ·
  * _strength_dose() takes the assessment and a side
  * the dose string can express a per-side prescription
  * the PDF cell renderer understands it

Scope, deliberately narrow · unilateral ACCESSORY and CORRECTIVE work only.
Adding a set to one side of a bilateral compound is not a coherent
prescription, so compounds are excluded in config, not in code.

Two independent triggers, either is enough ·
  1. mobility map · one side rated red, or red/yellow against a green
  2. measured force asymmetry above the configured percentage

The weaker side earns one extra set. That is the whole intervention · it is
deliberately small, because the honest state of the evidence is that nobody
knows the right number and a bigger asymmetry correction is a guess wearing a
lab coat.
"""

from dataclasses import dataclass, asdict
from typing import Optional

from ims_contract import load_thresholds
from joint_taxonomy import joints_loaded_by


_RATING_RANK = {"red": 3, "yellow": 2, "green": 1}


@dataclass
class SideBias:
    joint: str
    weak_side: str            # "L" | "R"
    source: str               # "mobility_map" | "measured_force"
    detail: str
    magnitude_pct: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_side(raw) -> Optional[str]:
    s = str(raw or "").strip().lower()
    if s in ("l", "left"):
        return "L"
    if s in ("r", "right"):
        return "R"
    return None


def from_mobility_map(assessment, cfg: dict = None) -> list:
    """Side bias from the traffic-light map · reads MobilityRating.side."""
    cfg = cfg or load_thresholds()
    scfg = cfg.get("side_aware_dose", {})
    if not scfg.get("enabled", True):
        return []

    by_joint = {}
    for r in (getattr(assessment, "mobility_map", None) or []):
        side = _norm_side(getattr(r, "side", None))
        if side is None:
            continue
        joint = str(getattr(r, "joint", "") or "").strip().lower()
        rating = str(getattr(r, "rating", "") or "").strip().lower()
        if not joint or rating not in _RATING_RANK:
            continue
        slot = by_joint.setdefault(joint, {})
        # Worst rating per side wins.
        if _RATING_RANK[rating] > _RATING_RANK.get(slot.get(side, "green"), 0):
            slot[side] = rating

    out = []
    for joint, sides in by_joint.items():
        left, right = sides.get("L"), sides.get("R")
        if not left or not right:
            # Only one side rated · a single red side is still a signal.
            lone_side = "L" if left else ("R" if right else None)
            lone = left or right
            if lone_side and lone == "red" and scfg.get("trigger_on_red_rating", True):
                out.append(SideBias(joint=joint, weak_side=lone_side,
                                    source="mobility_map",
                                    detail=f"{joint} {lone_side} rated red"))
            continue
        gap = _RATING_RANK[left] - _RATING_RANK[right]
        if gap == 0:
            continue
        weak = "L" if gap > 0 else "R"
        worse = left if gap > 0 else right
        better = right if gap > 0 else left
        if worse == "red" and scfg.get("trigger_on_red_rating", True):
            out.append(SideBias(joint=joint, weak_side=weak, source="mobility_map",
                                detail=f"{joint} {weak} {worse} vs {better}"))
        elif abs(gap) >= 1 and scfg.get("trigger_on_yellow_gap", True):
            out.append(SideBias(joint=joint, weak_side=weak, source="mobility_map",
                                detail=f"{joint} {weak} {worse} vs {better}"))
    return out


def from_force(objective, cfg: dict = None) -> list:
    """Side bias from measured asymmetry."""
    if objective is None or not objective.has_data():
        return []
    cfg = cfg or load_thresholds()
    scfg = cfg.get("side_aware_dose", {})
    if not scfg.get("enabled", True):
        return []
    gate = float(scfg.get("trigger_asymmetry_pct", 15.0))

    from weakest_link import asymmetries
    out = []
    for a in asymmetries(objective, cfg):
        if a["gap_pct"] < gate or not a.get("joint"):
            continue
        out.append(SideBias(joint=a["joint"], weak_side=a["weak_side"],
                            source="measured_force",
                            detail=f"{a['evidence']} · {a['gap_pct']:.0f}% gap",
                            magnitude_pct=a["gap_pct"]))
    return out


def resolve(assessment, objective=None, cfg: dict = None) -> dict:
    """{joint: SideBias} · measured force wins over the traffic light."""
    cfg = cfg or load_thresholds()
    merged = {}
    for b in from_mobility_map(assessment, cfg):
        merged[b.joint] = b
    for b in from_force(objective, cfg):
        merged[b.joint] = b        # measured beats subjective
    return merged


def bias_for_exercise(exercise_entry, biases: dict) -> Optional[SideBias]:
    """The side bias that applies to one exercise, if any.

    Joint tagging comes from joint_taxonomy · the router's own taxonomy.
    """
    if not biases or not exercise_entry:
        return None
    joints = joints_loaded_by(exercise_entry)
    if not joints:
        return None
    candidates = [b for j, b in biases.items() if j in joints]
    if not candidates:
        return None
    # Prefer a measured bias over a subjective one.
    candidates.sort(key=lambda b: 0 if b.source == "measured_force" else 1)
    return candidates[0]


def applies_to(exercise_type: str, pattern: str, cfg: dict = None,
               name: str = "", dose: str = "") -> bool:
    """Is per-side dosing coherent for this exercise?

    Two gates · the exercise type must be one config allows (accessory and
    corrective, never compounds), and the exercise must actually be trained one
    side at a time. Unilateral detection is shared with joint_taxonomy so the
    name, the pattern and the dose string all count · a library entry with
    pattern "row" and the name "Single Arm Dumbbell Row" is unilateral no
    matter what the pattern field says.
    """
    cfg = cfg or load_thresholds()
    scfg = cfg.get("side_aware_dose", {})
    if not scfg.get("enabled", True):
        return False
    if exercise_type not in (scfg.get("applies_to_exercise_types") or []):
        return False
    from joint_taxonomy import is_unilateral
    return is_unilateral(name=name, pattern=pattern, dose=dose)


def split_dose(sets: int, reps: int, bias: SideBias, cfg: dict = None) -> dict:
    """Per-side sets/reps. The weak side earns the extra set."""
    cfg = cfg or load_thresholds()
    scfg = cfg.get("side_aware_dose", {})
    extra = min(int(scfg.get("extra_sets_weak_side", 1)),
                int(scfg.get("max_extra_sets", 1)))
    weak, strong = bias.weak_side, ("R" if bias.weak_side == "L" else "L")
    return {
        weak: {"sets": int(sets) + extra, "reps": int(reps)},
        strong: {"sets": int(sets), "reps": int(reps)},
        "_weak_side": weak,
        "_reason": f"{bias.detail} ({bias.source.replace('_', ' ')})",
    }


def format_dose(split: dict) -> str:
    """'L 4 × 12 · R 3 × 12' · the dose string format gained a per-side form."""
    left = split.get("L")
    right = split.get("R")
    if not left or not right:
        return ""
    return (f"L {left['sets']} × {left['reps']} · "
            f"R {right['sets']} × {right['reps']}")
