"""Conservative pre-selection gate for exercise candidates with active joint restrictions.

This gate does not diagnose, clear, or prescribe rehabilitation. An unknown
exercise load profile must never be treated as safe for a flagged joint.
"""
from dataclasses import dataclass
from typing import Mapping, Sequence

ACTIVE_STATUSES = frozenset({"active_flare_up", "post_surgery", "avoid_loading"})
JOINT_ALIASES = {
    "back": "lumbar", "lower_back": "lumbar", "low_back": "lumbar",
    "lumbar_spine": "lumbar", "si_joint": "lumbar", "spine": "lumbar",
    "bad_knee": "knee", "bad_shoulder": "shoulder", "bad_hip": "hip",
    "bad_wrist": "wrist", "bad_ankle": "ankle", "bad_elbow": "elbow",
    "neck_cervical": "cervical", "neck": "cervical",
    "t_spine": "thoracic", "si_joint_sensitivity": "lumbar",
}
SPINE_EXCLUSIONS = frozenset({
    "back squat", "front squat", "conventional deadlift", "trap bar deadlift",
    "trap-bar deadlift", "kettlebell swing", "kb swing",
})


def normalize_joint(value: object) -> str:
    raw = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if raw.startswith(("left_", "right_")):
        raw = raw.split("_", 1)[1]
    return JOINT_ALIASES.get(raw, raw.removeprefix("bad_"))


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    requires_coach_review: bool


def restricted_joints(constraints_rich: Sequence[Mapping] | None) -> set[str]:
    blocked = set()
    for row in constraints_rich or ():
        if not isinstance(row, Mapping):
            continue
        if str(row.get("status") or "").strip().casefold() not in ACTIVE_STATUSES:
            continue
        joint = normalize_joint(row.get("key") or row.get("display_name"))
        if joint:
            blocked.add(joint)
        else:
            blocked.add("unknown")
    return blocked


def assess_candidate(entry: Mapping | None, blocked_joints: set[str],
                     *, spine_red_flag: bool = False) -> SafetyDecision:
    """Return HOLD for unknown data or any overlapping active restriction.

    A coach must separately review held candidates; this function has no
    clearance override and is intentionally independent of mobility pattern.
    """
    blocked = {normalize_joint(j) for j in blocked_joints}
    if spine_red_flag:
        blocked.add("lumbar")
    if not blocked:
        return SafetyDecision(True, "no active restriction supplied", False)
    if not entry:
        return SafetyDecision(False, "exercise absent from audited library", True)
    name = str(entry.get("name") or "").strip().casefold()
    if "lumbar" in blocked and any(x in name for x in SPINE_EXCLUSIONS):
        return SafetyDecision(False, "spine red-flag exclusion", True)
    if "unknown" in blocked:
        return SafetyDecision(False, "restriction joint not identified", True)
    joints = entry.get("primary_joints")
    if not isinstance(joints, (list, tuple)) or not joints:
        return SafetyDecision(False, "primary joint load not reviewed", True)
    secondary = entry.get("secondary_joints")
    if not isinstance(secondary, (list, tuple)):
        return SafetyDecision(False, "secondary joint load not reviewed", True)
    affected = {normalize_joint(j) for j in (*joints, *secondary)}
    if affected & blocked:
        return SafetyDecision(False, "active restriction overlaps loaded joint", True)
    if not entry.get("safety_review_approved"):
        return SafetyDecision(False, "exercise safety tags not coach-approved", True)
    return SafetyDecision(True, "approved non-overlapping joint load", False)
