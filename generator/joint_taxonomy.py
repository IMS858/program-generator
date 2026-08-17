"""
IMS · the one joint taxonomy.

WHAT THE CONTRAINDICATION ROUTER ACTUALLY USES (reported before reuse, as
required by the build brief). Before this module existed, the tagging lived
inline in Generator._is_heavy_load_for_joint and Generator._concern_to_joint.
It is three sources, unioned ·

  1. entry["joint"]             · the primary joint string on a library entry,
                                  matched case-insensitively by substring
  2. entry["secondary_joints"]  · an optional list on the entry
  3. PATTERN_JOINT_MAP[pattern] · a hard-coded map from movement pattern to the
                                  joints that pattern loads, which exists
                                  because plenty of entries have a pattern but
                                  an incomplete joint field ("squat" with no
                                  "knee")

plus SAFE_PATTERNS, an escape hatch: pure mobility patterns through a bad
joint are not vetoed.

Canonical joint vocabulary · knee, shoulder, hip, lumbar, cervical, wrist,
elbow, ankle. Note "lower_back"/"low_back" collapse to lumbar and "neck" to
cervical; there is no thoracic entry in the veto map even though thoracic
appears elsewhere in the codebase as an FRA priority region.

Everything that needs to reason about which joints an exercise touches imports
from here. No parallel taxonomy.
"""

CANONICAL_JOINTS = (
    "knee", "shoulder", "hip", "lumbar", "cervical", "wrist", "elbow", "ankle",
)

# Checkbox concern flag → canonical joint.
CONCERN_TO_JOINT = {
    "bad_knee": "knee", "knee": "knee", "knee_pain": "knee",
    "bad_shoulder": "shoulder", "shoulder": "shoulder", "shoulder_pain": "shoulder",
    "lower_back": "lumbar", "low_back": "lumbar", "back": "lumbar",
    "lumbar": "lumbar", "back_pain": "lumbar",
    "hip": "hip", "bad_hip": "hip", "hip_pain": "hip",
    "neck": "cervical", "neck_pain": "cervical", "cervical": "cervical",
    "wrist": "wrist", "bad_wrist": "wrist", "wrist_pain": "wrist",
    "elbow": "elbow", "bad_elbow": "elbow", "elbow_pain": "elbow",
    "ankle": "ankle", "bad_ankle": "ankle", "ankle_pain": "ankle",
}

# Movement pattern → joints that pattern loads.
PATTERN_JOINT_MAP = {
    "squat": ["knee", "hip"],
    "squat_unilateral": ["knee", "hip"],
    "squat_lateral": ["knee", "hip"],
    "squat_axial_safe": ["knee", "hip"],
    "lunge": ["knee", "hip"],
    "lunge_lateral": ["knee", "hip"],
    "lunge_unilateral": ["knee", "hip"],
    "hinge": ["lumbar", "hip"],
    "hinge_unilateral": ["hip"],
    "hinge_axial_safe": ["lumbar", "hip"],
    "press": ["shoulder", "elbow"],
    "push_horizontal": ["shoulder", "elbow"],
    "push_vertical": ["shoulder", "elbow", "lumbar"],
    "push_vertical_axial_safe": ["shoulder", "elbow"],
    "pull_horizontal": ["shoulder", "elbow"],
    "pull_vertical": ["shoulder", "elbow"],
    "carry": ["shoulder", "wrist", "lumbar"],
    "hip_extension_teaching": ["hip", "lumbar"],
}

# Patterns that never count as "loading" a joint.
SAFE_PATTERNS = {
    "cars", "spinal_articulation", "lift_off", "hover", "err",
    "antiextension", "isometric", "breathing",
}


def concern_to_joint(concern: str):
    """Map a checkbox concern flag to a canonical joint, or None."""
    if not concern:
        return None
    key = str(concern).lower().replace(" ", "_").replace("-", "_")
    return CONCERN_TO_JOINT.get(key)


def joints_loaded_by(entry: dict) -> set:
    """Every canonical joint a library entry loads.

    Union of the three sources described at the top of this module. Substring
    matching on the primary joint field mirrors the router's behaviour, so an
    entry tagged "hip / lumbar" resolves to both.
    """
    if not isinstance(entry, dict):
        return set()

    found = set()
    primary = str(entry.get("joint", "") or "").lower()
    for j in CANONICAL_JOINTS:
        if j in primary:
            found.add(j)
    for j in (entry.get("secondary_joints") or []):
        s = str(j).lower()
        for canon in CANONICAL_JOINTS:
            if canon in s:
                found.add(canon)

    pattern = str(entry.get("pattern", "") or "").lower()
    for j in PATTERN_JOINT_MAP.get(pattern, []):
        found.add(j)

    return found


def is_safe_pattern(pattern) -> bool:
    return str(pattern or "").lower() in SAFE_PATTERNS


# Words that name a canonical joint in plain exercise-name English. Used ONLY
# to build a shim entry for exercises that live in the accessory / corrective
# libraries and therefore have no unified-DB entry to read a joint off. This is
# the same canonical vocabulary, not a second one · it just reads it out of a
# name instead of a field.
_NAME_JOINT_WORDS = {
    "knee": "knee", "quad": "knee", "hamstring": "knee",
    "shoulder": "shoulder", "delt": "shoulder", "scap": "shoulder",
    "rotator": "shoulder", "lat ": "shoulder", "press": "shoulder",
    "row": "shoulder", "pull": "shoulder",
    "hip": "hip", "glute": "hip", "clamshell": "hip", "thrust": "hip",
    "bridge": "hip",
    "lumbar": "lumbar", "back": "lumbar", "spine": "lumbar", "plank": "lumbar",
    "dead bug": "lumbar", "deadbug": "lumbar",
    "neck": "cervical", "cervical": "cervical", "chin tuck": "cervical",
    "wrist": "wrist", "grip": "wrist", "carry": "wrist",
    "elbow": "elbow", "bicep": "elbow", "tricep": "elbow", "curl": "elbow",
    "ankle": "ankle", "calf": "ankle", "tibialis": "ankle",
}

_UNILATERAL_MARKERS = (
    "unilateral", "single arm", "single-arm", "one arm", "one-arm",
    "single leg", "single-leg", "sa ", " sa", "split squat", "lunge",
    "step up", "step-up", "b-stance", "staggered", "half kneeling",
    "half-kneeling", "side plank", "/side", "per side", "teaching",
)


def shim_entry_for_name(name: str) -> dict:
    """A minimal entry for an exercise with no unified-DB record.

    The accessory and corrective libraries carry exercises the unified DB has
    never heard of, so anything reasoning about joints would silently skip
    them. This reads the canonical joint out of the name instead. Conservative
    by design · it only fires on an explicit joint word, and it returns an
    empty joint rather than guessing.
    """
    n = f" {str(name or '').lower()} "
    joints = []
    for word, joint in _NAME_JOINT_WORDS.items():
        if word in n and joint not in joints:
            joints.append(joint)
    return {
        "name": name,
        "joint": joints[0] if joints else "",
        "secondary_joints": joints[1:],
        "pattern": "",
        "equipment": None,
        "_shim": True,
    }


def is_unilateral(name: str = "", pattern: str = "", dose: str = "") -> bool:
    """Is this exercise trained one side at a time?

    Checks the pattern, the name and the dose string · plenty of library
    entries carry pattern "row" while the name says "Single Arm", and per-side
    dosing has to key off what the exercise actually is, not off how the
    pattern happens to be spelled.
    """
    blob = f" {str(name or '').lower()} {str(pattern or '').lower()} {str(dose or '').lower()} "
    explicit = ("unilateral" in blob or "single arm" in blob
                or "single-arm" in blob or "single leg" in blob
                or "single-leg" in blob)
    if "bilateral" in blob and not explicit:
        # A "/side" dose on an exercise the library calls bilateral is about
        # alternating sides within a set, not a per-side prescription.
        return False
    return any(m in blob for m in _UNILATERAL_MARKERS)
