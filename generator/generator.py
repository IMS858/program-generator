"""
IMS PROGRAM GENERATOR v1.0
==========================
Takes a filled assessment → outputs a 4-week structured program.

Usage ·
    from ims_generator import Assessment, Generator
    assessment = Assessment.from_json("matt_assessment.json")
    generator = Generator()
    program = generator.build_program(assessment)
    program.to_json("matt_program.json")

Design principles ·
- Never ships a contraindicated exercise
- Never adds load to a RED-scored joint
- Coach can override any generator decision
- Defaults match the IMS methodology; overrides use coach judgment
"""

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ==========================================================
# DATA MODELS
# ==========================================================

@dataclass
class MobilityRating:
    """Traffic light per joint direction."""
    joint: str           # e.g. "hip"
    direction: str       # e.g. "IR" or "flexion"
    side: str            # "L", "R", or "bilateral"
    rating: str          # "red", "yellow", "green"

    @property
    def key(self) -> str:
        return f"{self.joint}_{self.direction}_{self.side}".lower()


@dataclass
class FRAPriority:
    """One joint + direction requiring focused attention."""
    description: str     # e.g. "Hip IR L+R"
    joints: list[str]    # parsed from description · ["hip"]
    directions: list[str]  # ["IR"]
    sides: list[str]     # ["L", "R"]
    region: str          # "lower_body" or "upper_body" or "spine"


@dataclass
class Assessment:
    """The complete assessment input for one client."""
    name: str
    age_range: str                      # "late 40s"
    sex: str
    background: str                     # "ex-military"
    training_frequency: int             # 2, 3, or 4
    primary_goal: str
    fra_priorities: list[FRAPriority]
    strength_markers: list[str]         # IDs from marker library
    constraints: list[str]              # e.g. ["SI_joint_sensitivity", "no_axial_loading"]
    mobility_map: list[MobilityRating]
    body_comp: dict = field(default_factory=dict)
    progression_mode: str = "autoregulated"  # or "volume_cycle"
    strength_marker_results: dict = field(default_factory=dict)  # {marker_id: value_str}
    # Examples ·
    #   {"inverted_rows": "18 reps (30s)", "lat_pulldown": "140x3",
    #    "landmine_sa_press": "6 x 40 lbs"}

    @classmethod
    def from_json(cls, path: str) -> "Assessment":
        data = json.loads(Path(path).read_text())
        data["fra_priorities"] = [FRAPriority(**p) for p in data["fra_priorities"]]
        data["mobility_map"] = [MobilityRating(**r) for r in data["mobility_map"]]
        return cls(**data)

    def to_json(self, path: str):
        data = asdict(self)
        Path(path).write_text(json.dumps(data, indent=2))


@dataclass
class Exercise:
    """One exercise as it appears in a session."""
    name: str
    library: str                        # which library it was drawn from
    library_id: str | None = None       # entry ID in source library
    dose: str = ""                      # "3x8/side" or "2x5 @ 70%"
    tempo: str | None = None            # e.g. "3-sec eccentric"
    progression_note: str | None = None # week-to-week modifier
    rationale: str | None = None        # why this exercise for this client


@dataclass
class Block:
    """One block of a session (e.g. Mobility Prep, Strength A)."""
    name: str
    exercises: list[Exercise]
    duration_note: str = ""


@dataclass
class Session:
    """One training day."""
    day_number: int
    day_type: str                       # "strength_lb", "strength_ub", "cardio", "integration"
    focus: str                          # "Lower Body Strength + Left Shoulder ER"
    blocks: list[Block]


@dataclass
class Week:
    """One week of the program."""
    week_number: int
    intent: str                         # "Establish Tolerance" / "Push One Lever" / etc.
    sessions: list[Session]
    progression_notes: list[str] = field(default_factory=list)


@dataclass
class Program:
    """Complete 4-week program for one client."""
    client_name: str
    block_number: int                   # which 4-week block (1st, 2nd, etc.)
    weeks: list[Week]
    assessment: Assessment
    generator_version: str = "v1.0"

    def to_json(self, path: str):
        data = {
            "client_name": self.client_name,
            "block_number": self.block_number,
            "generator_version": self.generator_version,
            "weeks": [asdict(w) for w in self.weeks],
            "assessment": asdict(self.assessment)
        }
        Path(path).write_text(json.dumps(data, indent=2))


# ==========================================================
# THE GENERATOR
# ==========================================================

class Generator:
    """Builds a complete 4-week program from an assessment."""

    def __init__(self, libraries_path: str = None):
        if libraries_path is None:
            # Default: ../libraries relative to this file (for GitHub repo structure)
            libraries_path = str(Path(__file__).resolve().parent.parent / "libraries")
        self.lib_path = Path(libraries_path)
        self.db = self._load_unified_db()
        self.markers = self._load_markers()

    def _load_unified_db(self) -> dict:
        # Support both the new repo name and the legacy name
        for fname in ("exercise_database.json", "ims_unified_database_v2.json"):
            path = self.lib_path / fname
            if path.exists():
                return json.loads(path.read_text())
        raise FileNotFoundError(
            f"Could not find exercise database in {self.lib_path}. "
            f"Expected 'exercise_database.json' or 'ims_unified_database_v2.json'."
        )

    def _load_markers(self) -> dict:
        # Support both locations · generator folder + libraries folder
        candidates = [
            Path(__file__).resolve().parent / "strength_markers.json",
            self.lib_path / "strength_markers.json",
            self.lib_path / "ims_strength_markers_v1.json",
        ]
        for path in candidates:
            if path.exists():
                return json.loads(path.read_text())
        raise FileNotFoundError(
            f"Could not find strength_markers.json. Checked: {[str(p) for p in candidates]}"
        )

    # ------------------------------------------------------
    # MAIN ENTRY POINT
    # ------------------------------------------------------

    def build_program(self, assessment: Assessment, block_number: int = 1) -> Program:
        """Build a 4-week program for one client."""
        # Step 1 · assign priorities to training days
        day_assignments = self._assign_priorities(assessment)

        # Step 2 · build each week
        weeks = []
        for wk_num in range(1, 5):
            week = self._build_week(assessment, day_assignments, wk_num)
            weeks.append(week)

        return Program(
            client_name=assessment.name,
            block_number=block_number,
            weeks=weeks,
            assessment=assessment
        )

    # ------------------------------------------------------
    # STEP 1 · PRIORITY ROTATION
    # ------------------------------------------------------

    def _assign_priorities(self, assessment: Assessment) -> dict:
        """Distribute FRA priorities across training days.
        Rule · lower-body priorities → LB day; upper-body → UB day.
        Coach can override any assignment afterward.
        """
        freq = assessment.training_frequency
        lb_priorities = [p for p in assessment.fra_priorities if p.region == "lower_body"]
        ub_priorities = [p for p in assessment.fra_priorities if p.region == "upper_body"]
        spine_priorities = [p for p in assessment.fra_priorities if p.region == "spine"]

        assignments = {}

        if freq == 2:
            # Two days · top priority each day
            ordered = assessment.fra_priorities
            assignments["day_1"] = {
                "day_type": "strength_lb" if ordered[0].region == "lower_body" else "strength_ub",
                "focus_priorities": [ordered[0]] + spine_priorities[:1]
            }
            if len(ordered) >= 2:
                other_region = "strength_ub" if ordered[0].region == "lower_body" else "strength_lb"
                assignments["day_2"] = {
                    "day_type": other_region,
                    "focus_priorities": [ordered[1]] + spine_priorities[1:]
                }

        elif freq == 3:
            # Standard · LB day + UB day + cardio day
            assignments["day_1"] = {
                "day_type": "strength_lb",
                "focus_priorities": lb_priorities + ub_priorities[-1:]  # LB focus + 1 UB secondary
            }
            assignments["day_2"] = {
                "day_type": "strength_ub",
                "focus_priorities": ub_priorities + lb_priorities[-1:]  # UB focus + 1 LB secondary
            }
            assignments["day_3"] = {
                "day_type": "cardio",
                "focus_priorities": []
            }

        elif freq == 4:
            # Two strength days + cardio + integration
            assignments["day_1"] = {
                "day_type": "strength_lb",
                "focus_priorities": lb_priorities[:2]
            }
            assignments["day_2"] = {
                "day_type": "strength_ub",
                "focus_priorities": ub_priorities[:2]
            }
            assignments["day_3"] = {
                "day_type": "cardio",
                "focus_priorities": []
            }
            # Day 4 · integration for worst-scored joint
            worst = self._worst_joint(assessment)
            assignments["day_4"] = {
                "day_type": "integration",
                "focus_priorities": [p for p in assessment.fra_priorities
                                     if worst.joint.lower() in [j.lower() for j in p.joints]][:1]
            }

        return assignments

    def _worst_joint(self, assessment: Assessment) -> MobilityRating:
        """Return the mobility rating that's most restricted."""
        reds = [r for r in assessment.mobility_map if r.rating == "red"]
        if reds:
            return reds[0]
        yellows = [r for r in assessment.mobility_map if r.rating == "yellow"]
        return yellows[0] if yellows else assessment.mobility_map[0]

    # ------------------------------------------------------
    # STEP 2 · BUILD A WEEK
    # ------------------------------------------------------

    def _build_week(self, assessment: Assessment, day_assignments: dict, wk_num: int) -> Week:
        intent = self._week_intent(wk_num)
        sessions = []
        for day_key, config in day_assignments.items():
            day_num = int(day_key.split("_")[1])
            session = self._build_session(assessment, day_num, config, wk_num)
            sessions.append(session)

        return Week(
            week_number=wk_num,
            intent=intent,
            sessions=sessions,
            progression_notes=self._week_progression_notes(wk_num)
        )

    def _week_intent(self, wk_num: int) -> str:
        return {
            1: "Establish Tolerance · Pattern over load",
            2: "Push One Lever · Add +5lbs OR 1-2 reps OR 2-sec iso OR 3-sec eccentric per lift",
            3: "Peak the Lever · Extend the Week 2 progression OR add a second lever",
            4: "Deload + Re-Test · Volume reduced 30-40%; re-test strength markers and FRA priorities"
        }[wk_num]

    def _week_progression_notes(self, wk_num: int) -> list[str]:
        return {
            1: ["Client learns the movement. Load is conservative (RPE 6-7)."],
            2: ["Coach selects ONE progression lever per lift.",
                "Compound barbell/DB lifts → prefer linear load (+5 lbs).",
                "Bodyweight/cable work → prefer reps or eccentric.",
                "Single-joint correctives → prefer iso hold.",
                "Plyometric/power work → NEVER add eccentric or iso."],
            3: ["Peak week. Reduce if form breaks down.",
                "Same lever as Week 2, pushed one notch further.",
                "OR add a second lever if Week 2 lever is maxed."],
            4: ["DELOAD. 2 sets instead of 3 for Strength A + B.",
                "Mobility Prep and Cool Down stay full volume (clients need these).",
                "Re-test 4 strength markers as their own block (Day 1 OR Day 2).",
                "Schedule Integration Visit mid-week for full FRA re-screen."]
        }[wk_num]

    # ------------------------------------------------------
    # STEP 3 · BUILD A SESSION
    # ------------------------------------------------------

    def _build_session(self, assessment: Assessment, day_num: int,
                       config: dict, wk_num: int) -> Session:
        day_type = config["day_type"]
        priorities = config["focus_priorities"]

        if day_type == "cardio":
            return self._build_cardio_session(day_num, wk_num)

        if day_type == "integration":
            return self._build_integration_session(assessment, day_num, priorities, wk_num)

        # Strength days (LB or UB)
        blocks = [
            self._build_passive_stretch(priorities),
            self._build_mobility_prep(priorities, assessment.constraints),
            self._build_strength_a(day_type, assessment, wk_num),
            self._build_strength_b(day_type, priorities, assessment, wk_num),
            self._build_cool_down(priorities, wk_num)
        ]

        focus_labels = [p.description for p in priorities]
        focus_text = ("Lower Body Strength" if day_type == "strength_lb"
                      else "Upper Body Strength")
        if focus_labels:
            focus_text += " + " + " / ".join(focus_labels[:2]) + " Focus"

        return Session(
            day_number=day_num,
            day_type=day_type,
            focus=focus_text,
            blocks=blocks
        )

    # ------------------------------------------------------
    # BLOCK BUILDERS · PASSIVE STRETCH
    # ------------------------------------------------------

    def _build_passive_stretch(self, priorities: list[FRAPriority]) -> Block:
        if not priorities:
            return Block(name="Passive Stretch (2 min)",
                        exercises=[Exercise(name="General mobility breath work",
                                           library="manual",
                                           dose="2 min")])
        primary = priorities[0]
        # Pick a base position that targets this priority
        stretch_name = self._passive_stretch_for_priority(primary)
        return Block(
            name="Passive Stretch (2 min)",
            exercises=[Exercise(
                name=stretch_name,
                library="base_positions",
                dose="1 min/side" if "L+R" in primary.description or "bilateral" in primary.description.lower() else "2 min",
                rationale=f"Opens up {primary.description}"
            )]
        )

    def _passive_stretch_for_priority(self, priority: FRAPriority) -> str:
        """Map a priority to a matching base-position passive stretch."""
        joint = priority.joints[0].lower() if priority.joints else ""
        direction = priority.directions[0].lower() if priority.directions else ""

        mapping = {
            ("hip", "ir"): "90/90 Hip Hold",
            ("hip", "er"): "Pigeon Pose",
            ("hip", "flexion"): "Deep Squat Hold",
            ("hamstring", ""): "Hamstring Wall Stretch (Posterior Tilt Bias)",
            ("shoulder", "er"): "Child's Pose with Arm Reach",
            ("shoulder", "ir"): "Sleeper Stretch",
            ("ankle", "plantarflexion"): "Kneeling Ankle Stretch",
            ("ankle", "eversion"): "Tibialis Wall Stretch",
            ("thoracic", ""): "Prayer Stretch on Foam Roller",
            ("cervical", ""): "Supine Cervical Traction Hold",
            ("lumbar", ""): "Supine Knee-to-Chest",
        }
        key = (joint, direction)
        if key in mapping:
            return mapping[key]
        # Fallback
        for (j, _), val in mapping.items():
            if j == joint:
                return val
        return f"Targeted hold · {priority.description}"

    # ------------------------------------------------------
    # BLOCK BUILDERS · MOBILITY PREP (RAILs-based)
    # ------------------------------------------------------

    def _build_mobility_prep(self, priorities: list[FRAPriority],
                             constraints: list[str]) -> Block:
        """RAILs-based only · PRH, PRLO, Lift-Offs, Hovers, ERRs.
        NO PAIL/RAIL combos here (those go in cool-down).

        IMS style rule · Lift-Offs (PRLO) are the PRIMARY prep modality.
        Pattern per priority ·
          priority 1 · Lift-Off + Hover OR ERR
          priority 2 · Lift-Off only
          priority 3 · Lift-Off only
        Guarantees at least 1 slow-twitch control drill (Hover or ERR).
        """

        exercises = []
        for i, priority in enumerate(priorities[:3]):
            # Always prioritize a Lift-Off (PRLO) first
            lift_off = self._pick_lift_off_for_priority(priority, constraints)
            exercises.append(lift_off)

            # First priority also gets a slow-control drill (Hover or ERR)
            if i == 0:
                slow_control = self._pick_slow_control_for_priority(priority, constraints)
                exercises.append(slow_control)

        return Block(
            name="Mobility Prep (RAILs-Based)",
            exercises=exercises,
            duration_note="Lift-Offs primary · Hover/ERR for slow-twitch control"
        )

    def _pick_lift_off_for_priority(self, priority: FRAPriority,
                                     constraints: list[str]) -> Exercise:
        """Build a Lift-Off exercise name matching the priority."""
        joint = priority.joints[0].title() if priority.joints else "General"
        direction = priority.directions[0] if priority.directions else ""
        direction_label = self._direction_label(direction)

        name = f"{joint} {direction_label} Lift-Offs".replace("  ", " ").strip()

        # Search DB for a matching PRLO; fall back to constructed name if none found
        matches = self._search_library(library="end_range", priority=priority,
                                        constraints=constraints, limit=5)
        for m in matches:
            mod = str(m.get("modality", "")).lower()
            if "prlo" in mod or "lift" in mod:
                return Exercise(
                    name=m.get("name", name),
                    library="end_range",
                    library_id=m.get("id"),
                    dose="2x6/side",
                    rationale=f"Targets {priority.description}"
                )

        # Fallback · construct the exercise
        return Exercise(
            name=name,
            library="end_range",
            dose="2x6/side",
            rationale=f"Lift-Off activation for {priority.description}"
        )

    def _pick_slow_control_for_priority(self, priority: FRAPriority,
                                         constraints: list[str]) -> Exercise:
        """Pick a Hover OR ERR for the priority — coach's default is Hover,
        unless the priority is a rotation (then ERR is more targeted)."""
        joint = priority.joints[0].title() if priority.joints else "General"
        direction = priority.directions[0] if priority.directions else ""
        direction_label = self._direction_label(direction)

        is_rotation = direction.lower() in ["ir", "er"]

        if is_rotation:
            name = f"{joint} {direction_label} ERRs".replace("  ", " ").strip()
            return Exercise(
                name=name,
                library="end_range",
                dose="2x3/side (slow)",
                rationale=f"Rotational slow-twitch control for {priority.description}"
            )
        else:
            name = f"{joint} Hovers".strip()
            return Exercise(
                name=name,
                library="end_range",
                dose="1x5/side",
                rationale=f"Slow-twitch hold for {priority.description}"
            )

    def _direction_label(self, direction: str) -> str:
        """Human-friendly label for direction codes."""
        mapping = {
            "IR": "IR", "ER": "ER",
            "flexion": "Flexion", "extension": "Extension",
            "plantarflexion": "Plantarflexion", "dorsiflexion": "DF",
            "eversion": "Eversion", "inversion": "Inversion",
            "abduction": "Abduction", "adduction": "Adduction",
            "general": "", "restricted": ""
        }
        return mapping.get(direction, direction.title())

    # ------------------------------------------------------
    # BLOCK BUILDERS · STRENGTH A (compound lifts)
    # ------------------------------------------------------

    def _build_strength_a(self, day_type: str, assessment: Assessment, wk_num: int) -> Block:
        if day_type == "strength_lb":
            patterns = self._pick_lb_patterns(assessment.constraints, day_num=1, wk_num=wk_num)
        else:
            patterns = ["push_horizontal", "pull_horizontal"]  # default UB

        exercises = []
        for pattern in patterns:
            ex = self._pick_strength_exercise(pattern, assessment.constraints)
            ex.dose = self._strength_dose(wk_num, exercise_type="compound", pattern=pattern)
            ex.progression_note = self._progression_note(wk_num, "compound")
            # Apply week-specific dose modification
            ex = self._apply_week_progression(ex, wk_num, "compound")
            # Fill in load suggestion from strength markers (if matching)
            ex = self._fill_load(ex, assessment)
            exercises.append(ex)

        return Block(
            name=f"Strength A",
            exercises=exercises,
            duration_note="Compound lifts · prioritize form over load"
        )

    def _pick_lb_patterns(self, constraints: list[str], day_num: int = 1, wk_num: int = 1) -> list[str]:
        """Pick lower body patterns, respecting constraints.
        
        IMS convention for spine-constrained clients on LB day 1 ·
          Strength A · unilateral knee-dominant + hip-extension teaching (SL Glute Bridge)
          Strength A is where the client learns hip extension cleanly before loading it.
        """
        has_spine = self._has_spine_constraint(constraints)
        if has_spine:
            # Strength A · knee-dominant unilateral + hip extension teaching
            return ["squat_unilateral", "hip_extension_teaching"]
        # Default · knee-dominant + hip-dominant
        return ["squat", "hinge"]

    def _has_spine_constraint(self, constraints: list[str]) -> bool:
        flags = {"SI_joint_sensitivity", "no_axial_loading", "lumbar_issue", "disc_issue"}
        return any(c.lower().replace(" ", "_") in flags for c in constraints)

    def _pick_strength_exercise(self, pattern: str, constraints: list[str]) -> Exercise:
        """Select a strength exercise matching the pattern, filtered by constraints."""
        mapping = {
            "squat": ("Goblet Squat", "external_training"),
            "squat_unilateral": ("DB Front Foot Elevated Split Squat", "external_training"),
            "hinge": ("Trap Bar Deadlift", "external_training"),
            "hinge_unilateral": ("Assisted SL RDL (Landmine/TRX/Dowel)", "external_training"),
            "hip_extension_teaching": ("SL Glute Bridge", "external_training"),
            "push_horizontal": ("Incline Pushups", "external_training"),
            "push_vertical": ("Landmine SA Press", "external_training"),
            "pull_horizontal": ("Inverted Rows", "external_training"),
            "pull_vertical": ("Lat Pulldown", "external_training"),
        }
        name, lib = mapping.get(pattern, ("Goblet Squat", "external_training"))
        rationale = None
        if "unilateral" in pattern and self._has_spine_constraint(constraints):
            rationale = "Unilateral variant selected due to spine-loading constraint"
        if pattern == "hip_extension_teaching":
            rationale = "Hip extension pattern without spine load · clean teaching exercise"
        return Exercise(name=name, library=lib, rationale=rationale)

    def _strength_dose(self, wk_num: int, exercise_type: str, pattern: str = None) -> str:
        """Default doses by week and exercise type.
        Dose is the BASE · week-specific modifications applied by _apply_week_progression.
        """
        # Base reps by pattern
        if exercise_type == "compound":
            # Hip extension teaching is typically 3x10/side
            if pattern == "hip_extension_teaching":
                return "3x10/side"
            # Unilateral patterns default to /side
            if pattern and "unilateral" in pattern:
                return "3x8/side"
            return "3x8/side"
        elif exercise_type == "accessory":
            return "3x10"
        elif exercise_type == "corrective":
            return "3x12"
        return "3x8"

    def _progression_note(self, wk_num: int, exercise_type: str) -> str:
        """What changes this week for this type of exercise."""
        if wk_num == 1:
            return None
        if wk_num == 4:
            return "Deload · reduce volume, prepare for re-test"

        # Week 2 and 3 · propose a lever per exercise type
        if exercise_type == "compound":
            return "Week 2 · add +5 lbs if form is clean. Week 3 · +5 lbs again OR add 3-sec eccentric."
        if exercise_type == "accessory":
            return "Week 2 · add 1-2 reps OR slow the eccentric to 3 sec. Week 3 · push further."
        if exercise_type == "corrective":
            return "Week 2 · add 2-sec iso hold at hardest point. Week 3 · extend iso to 3 sec."
        return "Week 2 · push one lever. Week 3 · extend or add second lever."

    def _apply_week_progression(self, ex: Exercise, wk_num: int, exercise_type: str) -> Exercise:
        """Apply week-specific dose and tempo modifications to an exercise.

        Week 1 · base dose, no tempo modifier (client learns pattern)
        Week 2 · one progression lever picked by exercise type ·
                  compound       → +5 lbs (load modifier added)
                  accessory      → +1-2 reps (rep bumped in dose string)
                  corrective     → 2-sec iso at hardest point (tempo added)
        Week 3 · second notch of same lever ·
                  compound       → +10 lbs OR 3-sec eccentric
                  accessory      → +2-3 reps OR 3-sec eccentric
                  corrective     → 3-sec iso
        Week 4 · deload · -1 set, tempo stripped back to Week 1
        """
        # Week 1 · unchanged
        if wk_num == 1:
            return ex

        # Week 4 · deload · drop a set, strip tempos
        if wk_num == 4:
            # Reduce set count by 1
            new_dose = self._reduce_sets(ex.dose, by=1)
            ex.dose = f"{new_dose} (deload)"
            ex.tempo = None  # strip tempo
            return ex

        # Week 2 · first progression lever
        if wk_num == 2:
            if exercise_type == "compound":
                # Linear load · add load instruction
                ex.dose = f"{ex.dose}  +5 lbs from Wk 1"
            elif exercise_type == "accessory":
                # Add 1-2 reps
                ex.dose = self._bump_reps(ex.dose, by=2)
            elif exercise_type == "corrective":
                # Add 2-sec iso
                ex.tempo = "2-sec iso hold at hardest point"
                ex.dose = f"{ex.dose}  (with {ex.tempo})"
            return ex

        # Week 3 · second notch — prefer eccentric as default 2nd lever
        if wk_num == 3:
            if exercise_type == "compound":
                # +5 more lbs OR 3-sec eccentric
                ex.dose = f"{ex.dose}  +10 lbs from Wk 1"
                ex.tempo = "3-sec eccentric"
                ex.dose = f"{ex.dose}  (tempo · {ex.tempo})"
            elif exercise_type == "accessory":
                # More reps + eccentric
                ex.dose = self._bump_reps(ex.dose, by=3)
                ex.tempo = "3-sec eccentric"
                ex.dose = f"{ex.dose}  (tempo · {ex.tempo})"
            elif exercise_type == "corrective":
                # Extend iso
                ex.tempo = "3-sec iso hold"
                ex.dose = f"{ex.dose}  (with {ex.tempo})"
            return ex

        return ex

    def _bump_reps(self, dose: str, by: int) -> str:
        """Increase the rep count in a dose string.
        Handles '3x8', '3x8/side', '3x10', etc.
        """
        import re
        # Match NxM patterns · "3x8" → "3x10"
        def replace_rep(match):
            sets = match.group(1)
            reps = int(match.group(2))
            return f"{sets}x{reps + by}"
        # Only bump the FIRST occurrence (some doses have multiple)
        result = re.sub(r'(\d+)x(\d+)', replace_rep, dose, count=1)
        return result

    def _reduce_sets(self, dose: str, by: int) -> str:
        """Reduce the set count in a dose string for deload."""
        import re
        def replace_set(match):
            sets = int(match.group(1))
            reps = match.group(2)
            new_sets = max(sets - by, 1)  # never go below 1
            return f"{new_sets}x{reps}"
        result = re.sub(r'(\d+)x(\d+)', replace_set, dose, count=1)
        return result

    def _fill_load(self, ex: Exercise, assessment: Assessment) -> Exercise:
        """Fill in a starting load (for Week 1) based on assessment strength markers.
        Only applies if the exercise matches a tested marker.
        Week 1 · 60-70% of max tested load (client learns at moderate intensity).
        """
        if not assessment.strength_marker_results:
            return ex

        # Match exercise name to marker results
        name_lower = ex.name.lower()
        for marker_id, result in assessment.strength_marker_results.items():
            if marker_id.replace("_", " ") in name_lower:
                # Parse and back off to 60-70%
                suggested = self._suggest_starting_load(result)
                if suggested:
                    ex.dose = f"{ex.dose}  @ {suggested}"
                break

        return ex

    def _suggest_starting_load(self, marker_result: str) -> str | None:
        """From a strength marker result string like '140x3' or '6 x 40 lbs',
        suggest a Week 1 starting load · ~60-70% of tested max.
        """
        import re
        # Try to extract a weight in lbs
        match = re.search(r'(\d+)\s*(?:lbs?|x)', marker_result, re.IGNORECASE)
        if match:
            max_load = int(match.group(1))
            # Back off 30% for Week 1 starting load
            start_load = int(max_load * 0.70 / 5) * 5  # round to nearest 5 lbs
            if start_load >= 10:
                return f"~{start_load} lbs"
        # Rep-based marker · no load
        return None

    # ------------------------------------------------------
    # BLOCK BUILDERS · STRENGTH B (accessory + FRA-specific)
    # ------------------------------------------------------

    def _build_strength_b(self, day_type: str, priorities: list[FRAPriority],
                          assessment: Assessment, wk_num: int) -> Block:
        exercises = []

        # 1 · core/stability drill (always Deadbug + Band Pull-Apart as default)
        deadbug = Exercise(
            name="Deadbug + Band Pull-Apart",
            library="external_training",
            dose="3x6/side",
            progression_note=self._progression_note(wk_num, "accessory")
        )
        deadbug = self._apply_week_progression(deadbug, wk_num, "accessory")
        exercises.append(deadbug)

        # 2 · pattern complement
        # Matt-style · LB day 2nd accessory is Landmine SA Press (not SL Glute Bridge — that's now in Strength A)
        # UB day 2nd accessory is Landmine SA Press as vertical-push volume
        has_spine = self._has_spine_constraint(assessment.constraints)
        if day_type == "strength_lb" and has_spine:
            second_ex = Exercise(
                name="Landmine SA Press",
                library="external_training",
                dose="3x6/side",
                progression_note=self._progression_note(wk_num, "accessory"),
                rationale="Upper body press integration on LB day"
            )
        elif day_type == "strength_lb":
            second_ex = Exercise(
                name="SL Glute Bridge",
                library="external_training",
                dose="3x10/side",
                progression_note=self._progression_note(wk_num, "accessory")
            )
        else:
            second_ex = Exercise(
                name="Landmine SA Press",
                library="external_training",
                dose="3x6/side",
                progression_note=self._progression_note(wk_num, "accessory")
            )
        second_ex = self._apply_week_progression(second_ex, wk_num, "accessory")
        second_ex = self._fill_load(second_ex, assessment)
        exercises.append(second_ex)

        # 3 · FRA-specific corrective for the day's top priority
        if priorities:
            top = priorities[0]
            corrective = self._pick_corrective(top)
            if corrective:
                corrective.dose = self._strength_dose(wk_num, "corrective")
                corrective.progression_note = self._progression_note(wk_num, "corrective")
                corrective = self._apply_week_progression(corrective, wk_num, "corrective")
                exercises.append(corrective)

        return Block(
            name="Strength B",
            exercises=exercises,
            duration_note="Accessory work + FRA-specific corrective"
        )

    def _pick_corrective(self, priority: FRAPriority) -> Exercise | None:
        joint = priority.joints[0].lower() if priority.joints else ""
        direction = priority.directions[0].lower() if priority.directions else ""

        mapping = {
            ("shoulder", "er"): "Cable/Band Shoulder ER",
            ("shoulder", "ir"): "Cable/Band Shoulder IR",
            ("hip", "ir"): "Cable Hip IR (clamshell + band)",
            ("hip", "er"): "Banded Clamshell",
            ("ankle", "plantarflexion"): "Calf Raise (bilateral → unilateral)",
            ("ankle", "eversion"): "Banded Ankle Eversion",
            ("hamstring", ""): "Nordic Hamstring Curl (assisted)"
        }
        name = mapping.get((joint, direction))
        if not name:
            for (j, _), val in mapping.items():
                if j == joint:
                    name = val
                    break
        if not name:
            return None
        side_note = ""
        if "L+R" not in priority.description and len(priority.sides) == 1:
            side_note = f" ({priority.sides[0]} side)"
        return Exercise(
            name=name + side_note,
            library="external_training",
            rationale=f"Corrective for {priority.description}"
        )

    # ------------------------------------------------------
    # BLOCK BUILDERS · COOL DOWN
    # ------------------------------------------------------

    def _build_cool_down(self, priorities: list[FRAPriority], wk_num: int) -> Block:
        """Integration work. PAIL/RAIL combos allowed here."""
        exercises = []

        # 1 · CARs at the day's joint focus
        if priorities:
            joint = priorities[0].joints[0].title() if priorities[0].joints else "General"
            exercises.append(Exercise(
                name=f"Seated {joint} CARs",
                library="cars",
                dose="1x5/side",
                rationale="Integrate the day's priority at end-range control"
            ))

        # 2 · transition/flow drill
        exercises.append(Exercise(
            name="Modified 90/90 Windshield Wipers",
            library="base_positions",
            dose="1x6/side",
            rationale="Integrate hip rotation across positions"
        ))

        # 3 · OPTIONAL PAIL/RAIL combo (coach adds when target joint needs it)
        if priorities and self._priority_needs_pail_rail(priorities[0]):
            exercises.append(Exercise(
                name=f"{priorities[0].description} PAIL/RAIL Combo",
                library="pails_rails",
                dose="1 round · L1 effort",
                rationale="Capsular work at end of session (per IMS rule)"
            ))

        # 4 · low-intensity integration
        exercises.append(Exercise(
            name="Standing Arm Swings to Capsule End Range (Controlled)",
            library="end_range",
            dose="1x10",
            rationale="Gentle shoulder capsular finish"
        ))

        return Block(
            name="Dynamic Cool Down",
            exercises=exercises,
            duration_note="PAIL/RAIL combos allowed here (per IMS rule)"
        )

    def _priority_needs_pail_rail(self, priority: FRAPriority) -> bool:
        """Add PAIL/RAIL combo if priority is severe (red-rated)."""
        # Simple heuristic · could be enhanced with mobility_map lookup
        return True  # default to including for priority work

    # ------------------------------------------------------
    # BLOCK BUILDERS · CARDIO DAY
    # ------------------------------------------------------

    def _build_cardio_session(self, day_num: int, wk_num: int) -> Session:
        warmup = Block(
            name="Warm-Up (10 min)",
            exercises=[
                Exercise(name="Elliptical", library="external_training", dose="5 min · nasal breathing"),
                Exercise(name="Arc Trainer", library="external_training", dose="5 min · moderate incline")
            ]
        )

        conditioning = Block(
            name="Conditioning (pick one)",
            exercises=[
                Exercise(
                    name="Option A · Zone 2 Aerobic Base",
                    library="external_training",
                    dose="15 min Elliptical + 15-25 min Arc Trainer @ RPE 5-6"
                ),
                Exercise(
                    name="Option B · Aerobic Intervals",
                    library="external_training",
                    dose="5 rounds · 2 min Arc Trainer (mod/high) + 2 min Elliptical (recovery). Cooldown · 5-10 min walk."
                )
            ]
        )

        reset = Block(
            name="Post-Cardio Reset (FRC-inspired)",
            exercises=[
                Exercise(name="Hip Abducted Rock Backs", library="base_positions", dose="1x10 slow"),
                Exercise(name="Hip Flexion Rocking (Quadruped)", library="base_positions", dose="1x8/side"),
                Exercise(name="90/90 Transitions", library="base_positions", dose="1x6/side"),
                Exercise(name="Shoulder IR + Scapular CARs", library="cars", dose="2x5 each direction")
            ]
        )

        return Session(
            day_number=day_num,
            day_type="cardio",
            focus="Cardio & Recovery Conditioning",
            blocks=[warmup, conditioning, reset]
        )

    # ------------------------------------------------------
    # BLOCK BUILDERS · INTEGRATION DAY (4x/week)
    # ------------------------------------------------------

    def _build_integration_session(self, assessment: Assessment, day_num: int,
                                   priorities: list[FRAPriority], wk_num: int) -> Session:
        """Full-body integration · focus on worst-scoring joint."""
        worst = self._worst_joint(assessment)
        focus_priority = priorities[0] if priorities else None

        blocks = []

        # Extended mobility work
        if focus_priority:
            blocks.append(self._build_mobility_prep([focus_priority], assessment.constraints))

        # Light full-body strength
        blocks.append(Block(
            name="Integration Strength",
            exercises=[
                Exercise(name="Farmer Carry", library="external_training", dose="3x30m"),
                Exercise(name="SL Glute Bridge", library="external_training", dose="3x10/side"),
                Exercise(name="Dead Hang", library="external_training", dose="3x max hold")
            ],
            duration_note="Low intensity · focus on control and integration"
        ))

        # Extended cool-down with PAIL/RAIL
        blocks.append(Block(
            name="Extended Integration",
            exercises=[
                Exercise(name=f"{worst.joint.title()} PAIL/RAIL combo",
                        library="pails_rails", dose="2 rounds · L1 effort"),
                Exercise(name="Full-body CARs sequence", library="cars", dose="1 round all joints"),
                Exercise(name="Breath work · 5 min box breathing", library="manual", dose="5 min")
            ]
        ))

        focus_text = f"Integration · Full Body + {worst.joint.title()} {worst.direction} Focus"
        return Session(
            day_number=day_num,
            day_type="integration",
            focus=focus_text,
            blocks=blocks
        )

    # ------------------------------------------------------
    # LIBRARY SEARCH
    # ------------------------------------------------------

    def _search_library(self, library: str, priority: FRAPriority,
                        constraints: list[str], limit: int = 2) -> list[dict]:
        """Search the unified db for exercises matching a priority."""
        matches = []
        joint_needed = priority.joints[0].lower() if priority.joints else None
        direction_needed = priority.directions[0].lower() if priority.directions else None

        for ex_id, ex in self.db["exercises"].items():
            if ex.get("library") != library:
                continue
            ex_joint = str(ex.get("joint", "")).lower()
            if joint_needed and joint_needed not in ex_joint:
                continue
            # Direction match · check name / modality / setup
            if direction_needed:
                text = (str(ex.get("name", "")) + " " + str(ex.get("modality", "")) +
                        " " + str(ex.get("setup", ""))).lower()
                if direction_needed not in text:
                    continue
            # Constraints filter
            if self._violates_constraints(ex, constraints):
                continue
            matches.append(ex)
            if len(matches) >= limit:
                break

        return matches

    def _violates_constraints(self, ex: dict, constraints: list[str]) -> bool:
        """Check if an exercise is contraindicated by any client constraint."""
        contras = ex.get("contraindications", []) or []
        if not isinstance(contras, list):
            contras = [contras]
        contras_lower = [str(c).lower() for c in contras]
        for constraint in constraints:
            c_lower = constraint.lower().replace(" ", "_")
            if any(c_lower in con for con in contras_lower):
                return True
        return False

    def _exercise_from_db_entry(self, entry: dict, priority: FRAPriority) -> Exercise:
        """Convert a unified-db entry into an Exercise."""
        return Exercise(
            name=entry.get("name", "Unknown"),
            library=entry.get("library", "unknown"),
            library_id=entry.get("id"),
            rationale=f"Targets {priority.description}"
        )


# ==========================================================
# CONVENIENCE · PARSE FRA PRIORITY STRINGS
# ==========================================================

def parse_fra_priority(description: str) -> FRAPriority:
    """Parse strings like 'Hip IR L+R' or 'Left Shoulder External Rotation'."""
    desc = description.strip()
    lower = desc.lower()

    # Region detection
    lower_body_keywords = {"hip", "knee", "ankle", "foot", "toe", "hamstring", "quad", "glute", "calf"}
    upper_body_keywords = {"shoulder", "scapular", "elbow", "wrist", "hand"}
    spine_keywords = {"cervical", "thoracic", "lumbar", "spine", "neck", "back"}

    region = "unknown"
    joints = []
    for k in lower_body_keywords:
        if k in lower:
            region = "lower_body"
            joints.append(k)
    for k in upper_body_keywords:
        if k in lower:
            region = "upper_body"
            joints.append(k)
    for k in spine_keywords:
        if k in lower:
            region = "spine"
            joints.append(k)

    # Direction parsing
    directions = []
    if "ir" in lower or "internal rotation" in lower: directions.append("IR")
    if "er" in lower or "external rotation" in lower: directions.append("ER")
    if "flexion" in lower and "plantar" not in lower and "dorsi" not in lower:
        directions.append("flexion")
    if "extension" in lower: directions.append("extension")
    if "plantarflexion" in lower or "plantar" in lower: directions.append("plantarflexion")
    if "dorsiflexion" in lower: directions.append("dorsiflexion")
    if "eversion" in lower: directions.append("eversion")
    if "inversion" in lower: directions.append("inversion")
    if "abduction" in lower: directions.append("abduction")
    if "adduction" in lower: directions.append("adduction")
    if "restriction" in lower and not directions: directions.append("restricted")

    # Side parsing
    sides = []
    if "l+r" in lower or "bilateral" in lower or "both" in lower:
        sides = ["L", "R"]
    elif "left" in lower or lower.startswith("l "):
        sides = ["L"]
    elif "right" in lower or lower.startswith("r "):
        sides = ["R"]
    else:
        sides = ["bilateral"]

    return FRAPriority(
        description=description,
        joints=joints or ["unknown"],
        directions=directions or ["general"],
        sides=sides,
        region=region
    )


# ==========================================================
# MAIN · DEMO USING MATT'S ASSESSMENT
# ==========================================================

def build_matt_program():
    """Demo · build Matt's 4-week program from the assessment we have."""
    matt = Assessment(
        name="Matt",
        age_range="late 40s",
        sex="M",
        background="ex-military",
        training_frequency=3,
        primary_goal="Restore mobility, improve strength, optimize joint function, and build an aerobic base",
        fra_priorities=[
            parse_fra_priority("Hip Internal Rotation L+R"),
            parse_fra_priority("Left Shoulder External Rotation"),
            parse_fra_priority("Ankle Plantarflexion + Eversion"),
            parse_fra_priority("Bilateral Hamstring Restriction"),
        ],
        strength_markers=["inverted_rows", "incline_pushups", "lat_pulldown", "landmine_sa_press"],
        constraints=["SI_joint_sensitivity", "no_axial_loading"],
        mobility_map=[
            MobilityRating(joint="hip", direction="IR", side="L", rating="red"),
            MobilityRating(joint="hip", direction="IR", side="R", rating="red"),
            MobilityRating(joint="shoulder", direction="ER", side="L", rating="red"),
            MobilityRating(joint="ankle", direction="plantarflexion", side="bilateral", rating="yellow"),
            MobilityRating(joint="ankle", direction="eversion", side="bilateral", rating="yellow"),
            MobilityRating(joint="hamstring", direction="flexibility", side="bilateral", rating="red"),
        ],
        body_comp={},
        progression_mode="autoregulated",
        strength_marker_results={
            "inverted_rows": "18 reps (30s)",
            "incline_pushups": "22 reps (30s)",
            "lat_pulldown": "140x3",
            "landmine_sa_press": "6 x 40 lbs"
        }
    )

    generator = Generator()
    program = generator.build_program(matt, block_number=1)

    out_path = str(Path(__file__).resolve().parent.parent / "examples" / "matt_program.json")
    program.to_json(out_path)

    # Summary print
    print(f"Generated · {program.client_name} · Block {program.block_number}")
    print(f"Weeks · {len(program.weeks)}")
    for week in program.weeks:
        print(f"\n--- Week {week.week_number} · {week.intent} ---")
        for session in week.sessions:
            print(f"  Day {session.day_number} · {session.focus}")
            for block in session.blocks:
                print(f"    [{block.name}]  · {len(block.exercises)} exercises")
                for ex in block.exercises[:3]:
                    print(f"      · {ex.name} — {ex.dose}")

    print(f"\nProgram JSON written · {out_path}")
    return program


if __name__ == "__main__":
    build_matt_program()
