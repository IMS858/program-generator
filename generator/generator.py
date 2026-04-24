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
        """Build a 6-week program for one client (IMS v2 block structure)."""
        # Step 1 · assign priorities to training days
        day_assignments = self._assign_priorities(assessment)

        # Step 2 · build each week (6-week block)
        weeks = []
        for wk_num in range(1, 7):
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
            2: "Tempo Push · Slow eccentrics and iso holds at same weight",
            3: "Load Push · Add +5-10 lbs, keep scheme and tempo",
            4: "Volume Push · Add a set (4 × 12-10-8-6)",
            5: "Heavy Push · One final load bump · last hard week",
            6: "Deload + Re-Test · Cut volume 30-40%, re-test strength markers + FRA priorities"
        }[wk_num]

    def _week_progression_notes(self, wk_num: int) -> list[str]:
        return {
            1: ["Client learns the movement. Moderate load (RPE 6-7).",
                "Rep scheme · 3 × 12-10-8 for Strength A compounds.",
                "Pattern > load always in Week 1."],
            2: ["Same weight as Week 1. Primary lever · TEMPO.",
                "Slow eccentrics (3-sec lowering) OR iso hold at hardest point.",
                "Builds tissue tolerance before we add load."],
            3: ["Standard tempo returns. Primary lever · LOAD.",
                "Add +5-10 lbs to Strength A compounds. Rep scheme stays 3 × 12-10-8.",
                "This is the first real strength push of the block."],
            4: ["Volume week. Rep scheme expands to 4 × 12-10-8-6.",
                "Add a set to Strength A compounds. Top set drops reps to 6.",
                "Can be similar weight to Week 3 or slightly heavier top set."],
            5: ["Final hard week. Keep 4 × 12-10-8-6 scheme.",
                "Push load on the top set of Strength A.",
                "Client should feel this one. Watch form · cut if breakdown."],
            6: ["Deload + Re-test. Volume cut 30-40% (2 sets instead of 3-4).",
                "Re-test all strength markers as their own block (Day 1 OR Day 2).",
                "Re-screen FRA priorities. Mobility Prep + Coach Finisher stay full volume."]
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

        # Strength days (LB or UB) · Jason's 8-block IMS v2 flow
        blocks = [
            self._build_cars_sequence(priorities, assessment),
            self._build_dynamic_warmup(assessment, priorities),
            self._build_mobility_prep(priorities, assessment.constraints),
            self._build_strength_a(day_type, assessment, wk_num),
            self._build_strength_b(day_type, priorities, assessment, wk_num),
            self._build_hiit_finisher(assessment, context="strength"),
            self._build_decompression_cooldown(priorities),
            self._build_coach_finisher(priorities),
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
    # BLOCK BUILDERS · CARs SEQUENCE (pre-session)
    # ------------------------------------------------------

    def _build_cars_sequence(self, priorities: list[FRAPriority], assessment: Assessment) -> Block:
        """Jason's CARs opener · joint-by-joint controlled articular rotations.

        Sequence order (fixed) · neck → scap → shoulder → T-spine → cat-cow →
        thoracic twist → supine hip capsule CARs.

        Intensity ramps based on:
          - Client tier (new client starts 20-40%; advanced works up to 80-90%)
          - Day's hardest work (heavy LB day = higher hip CARs intensity)

        Reps scale too · 2-3 for new clients, 3-5 for advanced.
        """
        # Determine intensity tier
        tier = self._infer_client_tier(assessment)
        intensity = self._cars_intensity_for_day(tier, priorities)

        # Reps scale with tier
        reps = "2-3 reps/direction" if tier == "new" else "3-5 reps/direction"

        sequence = [
            Exercise(
                name="Neck CARs",
                library="cars",
                dose=reps,
                rationale=f"Start light · {intensity} effort",
            ),
            Exercise(
                name="Scapular CARs",
                library="cars",
                dose=reps,
                rationale=f"{intensity} effort",
            ),
            Exercise(
                name="Shoulder CARs (both arms)",
                library="cars",
                dose=reps,
                rationale=f"{intensity} effort",
            ),
            Exercise(
                name="T-Spine CARs (quadruped rotation)",
                library="cars",
                dose=reps,
                rationale=f"{intensity} effort",
            ),
            Exercise(
                name="Cat / Cow",
                library="cars",
                dose="5-8 reps",
                rationale="Spinal segmentation",
            ),
            Exercise(
                name="Thoracic Twist (open-book)",
                library="cars",
                dose="5 reps/side",
                rationale="T-spine rotation",
            ),
            Exercise(
                name="Supine Hip Capsule CARs",
                library="cars",
                dose=reps,
                rationale=f"{intensity} effort · ramps to match today's work",
            ),
        ]

        return Block(
            name="CARs Sequence",
            exercises=sequence,
            duration_note=f"Always first · {intensity} effort today",
        )

    def _infer_client_tier(self, assessment: Assessment) -> str:
        """Infer client tier (new / intermediate / advanced) from the assessment.

        Heuristic · if MORE THAN 3 mobility joints are rated 'red', the client
        has significant restrictions and is treated as new. If no reds AND some
        greens, they're advanced. Otherwise intermediate.
        """
        reds = sum(1 for r in assessment.mobility_map if r.rating == "red")
        greens = sum(1 for r in assessment.mobility_map if r.rating == "green")
        total = len(assessment.mobility_map) or 1

        if reds / total > 0.4:
            return "new"
        if greens / total > 0.4 and reds == 0:
            return "advanced"
        return "intermediate"

    def _cars_intensity_for_day(self, tier: str, priorities: list[FRAPriority]) -> str:
        """Pick the effort % for CARs today.

        Rule (hybrid) ·
          tier sets the CEILING · new = 20-40%, intermediate = 40-60%, advanced = 70-90%
          day's hardest work sets WITHIN that range
        """
        # For now we treat every strength day as "medium-hard" since we always pair
        # LB + UB compounds. Cardio day would use lower intensity but cardio has
        # its own warmup.
        if tier == "new":
            return "20-40%"
        if tier == "advanced":
            return "70-90%"
        return "40-60%"

    # ------------------------------------------------------
    # BLOCK BUILDERS · DYNAMIC WARMUP (autoregulated)
    # ------------------------------------------------------

    def _build_dynamic_warmup(self, assessment: Assessment, priorities: list[FRAPriority]) -> Block:
        """Jason's dynamic warmup · meets the client where they are.

        Dose is a RANGE · 5-15 min based on how the client moves that day.
        Core elements · hip flexor rockers → groin rockers → World's Greatest Stretch →
        in-place or walking dynamic. Athletes can add heavier dynamic.
        """
        tier = self._infer_client_tier(assessment)

        flow = [
            Exercise(
                name="Hip Flexor Rockers",
                library="external_training",
                dose="8-10 reps/side",
                rationale="Open front of hip",
            ),
            Exercise(
                name="Groin Rockers",
                library="external_training",
                dose="8-10 reps",
                rationale="Adductor + inner hip prep",
            ),
            Exercise(
                name="World's Greatest Stretch",
                library="external_training",
                dose="5 reps/side",
                rationale="Full-body movement prep",
            ),
        ]

        # Athlete / advanced client · add a dynamic gait element
        if tier == "advanced":
            flow.append(Exercise(
                name="Dynamic Walking Flow (high knees, skips, cariocas)",
                library="external_training",
                dose="10 yards × 2-3 rounds",
                rationale="Athlete-tier warmup",
            ))
        else:
            flow.append(Exercise(
                name="In-Place Dynamic Flow (high knees, butt kicks, lateral shuffle)",
                library="external_training",
                dose="20 sec × 3",
                rationale="Movement prep",
            ))

        return Block(
            name="Dynamic Warmup",
            exercises=flow,
            duration_note="5-15 min · match the client's day",
        )

    # ------------------------------------------------------
    # BLOCK BUILDERS · COACH FINISHER (table work)
    # ------------------------------------------------------

    def _build_coach_finisher(self, priorities: list[FRAPriority]) -> Block:
        """Jason's signature end-of-session table work · 5 min passive mobility.

        Standard flow · supine foot traction → hip ER/IR rotation (add PAIL/RAIL
        if tight side) → patella glides → knee rotations → shoulder ER/IR →
        flip prone → Hypervolt lumbar→cervical 2 min each side → optional calves.

        This is coach-delivered and always present on strength days.
        """
        # Pick the tight-side hip call-out (if priorities indicate)
        hip_side_note = ""
        for p in priorities:
            d = p.description.lower()
            if "hip" in d and ("ir" in d or "er" in d):
                hip_side_note = f" · emphasize {p.description}"
                break

        flow = [
            Exercise(
                name="Supine Foot Traction Pull",
                library="manual",
                dose="30-60 sec",
                rationale="Open the posterior chain",
            ),
            Exercise(
                name="Hip Rotation Mobilization (ER / IR)",
                library="manual",
                dose="1-2 min/side",
                rationale=f"Rotate into tight side{hip_side_note} · add PAIL/RAIL if severe",
            ),
            Exercise(
                name="Patella Glides",
                library="manual",
                dose="30 sec/side",
                rationale="Kneecap mobility",
            ),
            Exercise(
                name="Supine Knee Rotations",
                library="manual",
                dose="30 sec/side",
                rationale="Tibio-femoral rotation",
            ),
            Exercise(
                name="Supine Shoulder ER/IR Passive Range",
                library="manual",
                dose="30-45 sec/side",
                rationale="Capsule work",
            ),
            Exercise(
                name="Prone Hypervolt · Lumbar → Cervical",
                library="manual",
                dose="2 min/side",
                rationale="Soft-tissue flush along the spine",
            ),
            Exercise(
                name="Calves (optional)",
                library="manual",
                dose="30-60 sec/side if tight",
                rationale="Only if calves feel tight today",
            ),
        ]

        return Block(
            name="Coach Finisher",
            exercises=flow,
            duration_note="~5 min table work · coach-delivered",
        )

    # ------------------------------------------------------
    # BLOCK BUILDERS · HIIT FINISHER (optional · tier-matched)
    # ------------------------------------------------------

    def _build_hiit_finisher(self, assessment, context: str = "strength", week_num: int = None) -> Block:
        """Optional HIIT finisher · 3-5 min · tier-matched to client.

        Three tiers ·
          T1 Joint-Friendly  · sled, carries, bike sprints, battle rope (no impact)
          T2 Mid             · KB swings, jump rope, step-ups, med ball slams
          T3 Plyo/Athletic   · box jumps, broad jumps, burpees, skater bounds

        Tier selection · inferred from client_tier (new=T1, intermediate=T2, advanced=T3)
        or from constraints (post-surgery / chronic-anything → T1 always).
        """
        # Pick tier
        if assessment is None:
            # Cardio day context · default to T2, coach can substitute
            tier = "mid"
            rationale_prefix = "Cardio day finisher"
        else:
            client_tier = self._infer_client_tier(assessment)
            tier = self._hiit_tier_for_client(assessment, client_tier)
            rationale_prefix = f"{client_tier.title()} client"

        # Tier libraries
        TIER_1_JOINT_FRIENDLY = [
            ("Sled Push", "10 yd × 4-5 rounds · 45 sec rest", "No impact, all-hip drive"),
            ("Sled Drag (backward)", "10 yd × 4 rounds · 45 sec rest", "Quad and knee friendly"),
            ("Farmer Carry Intervals", "30 sec heavy carry / 30 sec rest × 4", "Grip + core + posture"),
            ("Bike Sprints (Assault / Air Bike)", "20 sec sprint / 40 sec easy × 6", "All-out, zero impact"),
            ("Rower Sprints", "250m × 4 rounds · 60 sec rest", "Full-body pull pattern"),
            ("Battle Rope Slams", "30 sec on / 30 sec off × 5", "Standing or half-kneeling · no jumping"),
        ]
        TIER_2_MID = [
            ("Jump Rope Intervals", "30 sec on / 30 sec off × 5", "Low-grade plyo · stiffness drill"),
            ("Kettlebell Swings", "20 sec on / 40 sec off × 6", "Hinge ballistic · hip power"),
            ("Step-Ups with Knee Drive", "30 sec/side × 3 rounds", "Unilateral · hip extension"),
            ("Med Ball Slams", "10 reps × 4 rounds", "Full-body rotational power"),
            ("Lateral Bounds (controlled)", "5/side × 4 rounds · focus on stick", "Single-leg power, controlled"),
            ("Alternating Reverse Lunges", "45 sec × 3 rounds", "Split-stance conditioning"),
        ]
        TIER_3_PLYO = [
            ("Box Jumps", "5 reps × 4 rounds · full rest", "Max concentric, step down"),
            ("Broad Jumps + Stick", "5 reps × 4 rounds", "Horizontal power"),
            ("Depth Jumps", "5 reps × 3 rounds · 90 sec rest", "Reactive strength · advanced only"),
            ("Lateral Hops (continuous)", "30 sec on / 30 sec off × 5", "Ankle stiffness + frontal plane"),
            ("Burpees", "30 sec on / 30 sec off × 5", "Full-body conditioning classic"),
            ("Skater Bounds", "30 sec × 4 rounds", "Lateral power · single-leg stick"),
            ("Plyo Push-Ups", "5 reps × 4 rounds", "Upper-body power · advanced"),
        ]

        # Build block · offer 2-3 options, coach/client picks
        if tier == "joint_friendly":
            pool = TIER_1_JOINT_FRIENDLY
            tier_label = "Joint-Friendly"
        elif tier == "plyo":
            pool = TIER_3_PLYO
            tier_label = "Plyo / Athletic"
        else:
            pool = TIER_2_MID
            tier_label = "Mid-Intensity"

        # Deterministic but varied · pick 3 options based on week number
        import random
        seed = (week_num or 1) * 17 + hash(context) % 100
        rng = random.Random(seed)
        picks = rng.sample(pool, min(3, len(pool)))

        exercises = [
            Exercise(
                name=name,
                library="external_training",
                dose=dose,
                rationale=f"{rationale_prefix} · {note}",
            )
            for name, dose, note in picks
        ]

        return Block(
            name=f"HIIT Finisher (optional · {tier_label})",
            exercises=exercises,
            duration_note="3-5 min · skip if table-work priority that day",
        )

    def _hiit_tier_for_client(self, assessment, client_tier: str) -> str:
        """Pick HIIT tier from client profile.

        Constraint-driven downgrade rules ·
          Any post-surgery / chronic-anything / pregnancy → T1 joint-friendly always
          Otherwise client_tier maps · new→T1, intermediate→T2, advanced→T3
        """
        constraints = [c.lower() for c in (assessment.constraints or [])]
        downgrade_flags = [
            "post_surgery", "chronic", "pregnancy", "si_joint", "knee", "hip", "shoulder"
        ]
        for c in constraints:
            if any(f in c for f in downgrade_flags):
                return "joint_friendly"

        if client_tier == "new":
            return "joint_friendly"
        if client_tier == "advanced":
            return "plyo"
        return "mid"

    # ------------------------------------------------------
    # BLOCK BUILDERS · DECOMPRESSION COOL DOWN (optional · self-led)
    # ------------------------------------------------------

    def _build_decompression_cooldown(self, priorities: list[FRAPriority]) -> Block:
        """Optional self-led decompression flow · passive holds client can do alone.

        Shows up as an optional block before the Coach Finisher · if the client
        trains alone or has extra time, they work through these holds. If Jason
        is coaching, this folds into the Coach Finisher table work instead.
        """
        flow = [
            Exercise(
                name="Supine 90/90 Decompression",
                library="base_positions",
                dose="1-2 min",
                rationale="Neutral spine · hip flexor lengthen",
            ),
            Exercise(
                name="Child's Pose with Arm Reach",
                library="base_positions",
                dose="1 min · breathe into lats",
                rationale="T-spine + lat decompression",
            ),
            Exercise(
                name="Supine Hip Capsule Lean (side-lying)",
                library="base_positions",
                dose="45 sec/side",
                rationale="Passive hip IR / ER hold",
            ),
        ]

        # Priority-specific addition
        if priorities:
            primary = priorities[0]
            d = primary.description.lower()
            if "shoulder" in d:
                flow.append(Exercise(
                    name="Doorway Pec Stretch",
                    library="base_positions",
                    dose="45 sec/side",
                    rationale=f"Opens front shoulder · supports {primary.description}",
                ))
            elif "thoracic" in d or "t-spine" in d:
                flow.append(Exercise(
                    name="Foam Roller Thoracic Extension",
                    library="base_positions",
                    dose="5 slow breath cycles",
                    rationale="Passive T-spine decompression",
                ))
            elif "ankle" in d:
                flow.append(Exercise(
                    name="Deep Squat Hold",
                    library="base_positions",
                    dose="45 sec · hold railing if needed",
                    rationale="Ankle + hip decompression hold",
                ))

        return Block(
            name="Decompression Cool Down (optional)",
            exercises=flow,
            duration_note="2-4 min · self-led · skip if Coach Finisher replaces it",
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
        """Select a strength exercise matching the pattern, filtered by constraints.

        Each pattern now maps to a POOL of exercises. Constraint-safe picks rise to
        the top · e.g. spine-sensitive clients get non-axial variants first.
        """
        # ─── POOLS · each pattern has multiple candidates ───
        # Order within each list = preference order for typical client.
        # Constraint filtering below then reorders.
        pools = {
            # SQUAT family · axial vs non-axial
            "squat":                  ["Goblet Squat", "Landmine Goblet Squat", "Barbell Front Squat", "Barbell Back Squat"],
            "squat_axial_safe":       ["Goblet Squat", "Landmine Goblet Squat", "Wide Stance Kettlebell Lateral Squat (Cossack)"],
            "squat_unilateral":       ["Rear Foot Elevated Split Squat", "Split Squat", "Single Leg Squat (Pistol or Assisted)",
                                       "Wide Stance Kettlebell Lateral Squat (Cossack)", "Landmine Reverse Lunge"],

            # HINGE family
            "hinge":                  ["Trap Bar Deadlift", "Dumbbell RDL (Straight Leg Deadlift)",
                                       "Barbell RDL (Straight Leg Deadlift)", "Kettlebell Deadlift",
                                       "Landmine Deadlift", "Landmine RDL", "Barbell Deadlift"],
            "hinge_axial_safe":       ["Kettlebell Deadlift", "Landmine Deadlift", "Landmine RDL",
                                       "Dumbbell RDL (Straight Leg Deadlift)"],
            "hinge_unilateral":       ["Single Leg RDL (weighted or unweighted)",
                                       "Single Leg Deadlift (reaching or kettlebell)",
                                       "Landmine RDL"],

            # TEACHING / ACTIVATION
            "hip_extension_teaching": ["Bridge (Single & Double Leg)", "Kettlebell Deadlift", "Dowel Hip Hinge"],

            # PRESSING · horizontal
            "push_horizontal":        ["Dumbbell Bench Press (Single or Double Arm)",
                                       "Dumbbell Floor Press (Single or Double Arm)",
                                       "Pushup (Full, Eccentric, Isometric)",
                                       "Barbell Bench Press", "Cable Press (Single or Double Arm)"],

            # PRESSING · vertical (shoulder)
            "push_vertical":          ["Half Kneeling Overhead Press", "Seated Overhead Press (Single or Double Arm)",
                                       "Half-Kneeling Landmine Press", "Standing Landmine Press",
                                       "Front Foot Elevated Overhead Press", "Standing Overhead Press"],
            "push_vertical_axial_safe": ["Half-Kneeling Landmine Press", "Half Kneeling Overhead Press",
                                         "Seated Overhead Press (Single or Double Arm)"],

            # PULLING · horizontal
            "pull_horizontal":        ["Chest Supported Row", "Single Arm Dumbbell Row",
                                       "Inverted Row", "TRX Row", "Landmine Chest-Supported Row",
                                       "Landmine (Meadows) Row", "Landmine T-Bar Row"],

            # PULLING · vertical
            "pull_vertical":          ["Lat Pulldown (Close and Wide Grip)", "Single Arm Cable Pulldown",
                                       "Cable X Pulldown", "Chin-up", "Pull-up (Pronated)"],

            # ROTATION (thoracic-dominant)
            "rotation":               ["Half Kneeling Chops", "Half Kneeling Lifts", "Standing Chops",
                                       "Standing Lifts", "Pulley Rotation (Bottom-Up, Horizontal, Top-Down)",
                                       "Landmine Rotation (Rainbow)", "Standing Cable Core Rotation"],

            # CARRY
            "carry":                  ["Farmer Carry", "Suitcase Carry", "Front Rack Carry",
                                       "Overhead Carry", "Bottoms-Up Kettlebell Carry"],
        }

        # Legacy single-name mapping (keeps old callers working)
        legacy_fallback = {
            "squat": "Goblet Squat",
            "squat_unilateral": "Rear Foot Elevated Split Squat",
            "hinge": "Trap Bar Deadlift",
            "hinge_unilateral": "Single Leg RDL (weighted or unweighted)",
            "hip_extension_teaching": "Bridge (Single & Double Leg)",
            "push_horizontal": "Pushup (Full, Eccentric, Isometric)",
            "push_vertical": "Half-Kneeling Landmine Press",
            "pull_horizontal": "Chest Supported Row",
            "pull_vertical": "Lat Pulldown (Close and Wide Grip)",
        }

        # Pick the pool · map to axial-safe variant if spine constraint applies
        spine_constrained = self._has_spine_constraint(constraints)
        rationale = None

        if spine_constrained and f"{pattern}_axial_safe" in pools:
            candidates = pools[f"{pattern}_axial_safe"]
            rationale = "Non-axial variant selected · spine-safe pattern"
        elif spine_constrained and pattern == "squat":
            candidates = pools.get("squat_axial_safe", pools["squat"])
            rationale = "Non-axial squat · protects spine"
        elif spine_constrained and pattern == "hinge":
            candidates = pools.get("hinge_axial_safe", pools["hinge"])
            rationale = "Non-axial hinge · protects spine"
        elif spine_constrained and pattern == "push_vertical":
            candidates = pools.get("push_vertical_axial_safe", pools["push_vertical"])
            rationale = "Half-kneeling / seated press · no axial load"
        elif pattern in pools:
            candidates = pools[pattern]
        else:
            candidates = [legacy_fallback.get(pattern, "Goblet Squat")]

        # Filter out any candidate whose DB entry violates constraints
        name = self._first_valid_candidate(candidates, constraints) or candidates[0]

        if "unilateral" in pattern and spine_constrained and not rationale:
            rationale = "Unilateral variant selected due to spine-loading constraint"
        if pattern == "hip_extension_teaching" and not rationale:
            rationale = "Hip extension pattern without spine load · clean teaching exercise"

        return Exercise(name=name, library="external_training", rationale=rationale)

    def _first_valid_candidate(self, candidates: list[str], constraints: list[str]) -> str | None:
        """Return the first candidate whose contraindications don't clash with constraints."""
        for name in candidates:
            entry = self._find_entry_by_name(name)
            if entry is None:
                # If we can't find it, allow it (the PDF can still render the name)
                return name
            if not self._violates_constraints(entry, constraints):
                return name
        return None

    def _find_entry_by_name(self, name: str) -> dict | None:
        """Look up an exercise entry in the unified DB by its canonical name."""
        entries = self.db.get('exercises', {})
        if isinstance(entries, dict):
            for eid, entry in entries.items():
                if entry.get('name') == name:
                    return entry
        elif isinstance(entries, list):
            for entry in entries:
                if entry.get('name') == name:
                    return entry
        return None

    def _strength_dose(self, wk_num: int, exercise_type: str, pattern: str = None) -> str:
        """Jason's descending pyramid · weight climbs each set.

        Compound (Strength A) ·
          W1-3 · 3 × 12-10-8
          W4-5 · 4 × 12-10-8-6 (add a set, top set drops reps)
          W6   · 2 × 12-10 (deload)

        Accessory (Strength B) ·
          W1-3 · 3 × 12 or 3 × 10
          W4-5 · 4 × 10 (add a set)
          W6   · 2 × 12 (deload)

        Corrective · stays steady · 3 × 12 throughout (no deload)
        """
        is_side = pattern and ("unilateral" in pattern or "teaching" in pattern)
        side = "/side" if is_side else ""

        if exercise_type == "compound":
            if wk_num in (1, 2, 3):
                return f"3 × 12-10-8{side}"
            if wk_num in (4, 5):
                return f"4 × 12-10-8-6{side}"
            if wk_num == 6:
                return f"2 × 12-10{side}  (deload)"

        if exercise_type == "accessory":
            if wk_num in (1, 2, 3):
                return f"3 × 10{side}"
            if wk_num in (4, 5):
                return f"4 × 10{side}"
            if wk_num == 6:
                return f"2 × 12{side}  (deload)"

        if exercise_type == "corrective":
            return f"3 × 12{side}"

        # Safe default
        return "3 × 10"

    def _progression_note(self, wk_num: int, exercise_type: str) -> str:
        """What changes this week for this exercise type (Jason's method)."""
        if wk_num == 1:
            return None  # Establish · no note needed

        if exercise_type == "compound":
            if wk_num == 2:
                return "Same weight. Slow the eccentric to 3 sec OR iso hold at hardest point."
            if wk_num == 3:
                return "Standard tempo. +5-10 lbs from Week 1."
            if wk_num == 4:
                return "Add a 4th set (12-10-8-6). Top set drops to 6 reps."
            if wk_num == 5:
                return "Push the top set heavy. Last hard week before deload."
            if wk_num == 6:
                return "Deload · 2 sets, ~60% of Week 5 weight. Re-test markers this week."

        if exercise_type == "accessory":
            if wk_num == 2:
                return "Slow eccentric (3 sec) OR pause at hardest point."
            if wk_num == 3:
                return "Standard tempo. Push load if possible."
            if wk_num in (4, 5):
                return "Add a set. Same reps."
            if wk_num == 6:
                return "Deload · 2 sets."

        if exercise_type == "corrective":
            if wk_num == 2:
                return "Add 2-sec iso hold at end range."
            if wk_num == 3:
                return "Extend iso to 3 sec if tolerated."
            if wk_num in (4, 5):
                return "Same dose. Push effort · end-range control."
            if wk_num == 6:
                return "Keep full volume · correctives don't deload."

        return None

    def _apply_week_progression(self, ex: Exercise, wk_num: int, exercise_type: str) -> Exercise:
        """Apply Jason's W1-W6 progression levers to an exercise.

        Week 1 · Establish · base dose, standard tempo
        Week 2 · Tempo     · same dose, slow eccentric or iso hold
        Week 3 · Load      · base dose, +5-10 lbs, standard tempo
        Week 4 · Volume    · add a set (compound 12-10-8-6; accessory 4x)
        Week 5 · Heavy     · W4 scheme, push weight on top set
        Week 6 · Deload    · 2 sets, -30-40% load, re-test markers
        """
        # Week 1 · no modification
        if wk_num == 1:
            return ex

        # Week 2 · TEMPO lever (same dose, add slow eccentric or iso)
        if wk_num == 2:
            if exercise_type == "compound":
                ex.tempo = "3-sec eccentric"
                ex.dose = f"{ex.dose}  · tempo {ex.tempo}"
            elif exercise_type == "accessory":
                ex.tempo = "3-sec eccentric"
                ex.dose = f"{ex.dose}  · tempo {ex.tempo}"
            elif exercise_type == "corrective":
                ex.tempo = "2-sec iso at end range"
                ex.dose = f"{ex.dose}  · {ex.tempo}"
            return ex

        # Week 3 · LOAD lever (standard tempo, add weight)
        if wk_num == 3:
            if exercise_type == "compound":
                ex.dose = f"{ex.dose}  · +5-10 lbs from Wk 1"
            elif exercise_type == "accessory":
                ex.dose = f"{ex.dose}  · push load"
            elif exercise_type == "corrective":
                ex.tempo = "3-sec iso at end range"
                ex.dose = f"{ex.dose}  · {ex.tempo}"
            return ex

        # Week 4 · VOLUME (dose is already 4 sets from _strength_dose)
        if wk_num == 4:
            if exercise_type == "compound":
                ex.dose = f"{ex.dose}  · same weight as Wk 3, extra set"
            elif exercise_type == "accessory":
                ex.dose = f"{ex.dose}  · added set"
            return ex

        # Week 5 · HEAVY (push weight on the top set)
        if wk_num == 5:
            if exercise_type == "compound":
                ex.dose = f"{ex.dose}  · push top set heavy"
            elif exercise_type == "accessory":
                ex.dose = f"{ex.dose}  · push load"
            return ex

        # Week 6 · DELOAD (dose is already reduced from _strength_dose)
        if wk_num == 6:
            if exercise_type in ("compound", "accessory"):
                ex.dose = f"{ex.dose}  · ~60% of Wk 5 weight"
                ex.tempo = None
            # Correctives stay full volume (already set in _strength_dose)
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
        """Cardio day · progresses through zones across the 6-week block.

        Jason's arc ·
          W1 · Zone 2 base · 15-20 min nasal breathing
          W2 · Zone 2 longer · 25-30 min
          W3 · Add Zone 3 · 10 min Z2 + 15 min Z3
          W4 · Z3-Z4 intervals · 4x(3min Z3 / 1min Z4)
          W5 · Z4-Z5 push · 6x(30sec Z5 / 90sec recovery)
          W6 · Back to Zone 2 · recovery / capacity re-consolidation
        """
        # Pick the prescription for this week
        prescriptions = {
            1: {
                "focus": "Week 1 · Zone 2 Base",
                "main": "15-20 min steady state · RPE 4-5 · nasal breathing only",
                "rationale": "Build aerobic base. If you can't nasal breathe, slow down.",
            },
            2: {
                "focus": "Week 2 · Zone 2 Extended",
                "main": "25-30 min steady state · RPE 4-5 · nasal breathing",
                "rationale": "Same zone, longer duration. Capacity build.",
            },
            3: {
                "focus": "Week 3 · Introducing Zone 3",
                "main": "10 min Z2 warmup + 15 min Z3 (RPE 6-7) + 5 min Z2 cooldown",
                "rationale": "First tempo exposure. Breathing noticeably deeper but sustainable.",
            },
            4: {
                "focus": "Week 4 · Z3-Z4 Intervals",
                "main": "5 min Z2 warmup · 4 rounds (3 min Z3 / 1 min Z4) · 5 min cooldown",
                "rationale": "Alternate tempo and threshold work.",
            },
            5: {
                "focus": "Week 5 · Z4-Z5 Push",
                "main": "8 min Z2 warmup · 6 rounds (30 sec Z5 / 90 sec Z1 recovery) · 10 min Z2 cooldown",
                "rationale": "Peak cardio week. Max intervals short and sharp.",
            },
            6: {
                "focus": "Week 6 · Re-Consolidation",
                "main": "20-30 min Zone 2 · nasal breathing",
                "rationale": "Deload week · back to base. Let the high-intensity work consolidate.",
            },
        }
        prescription = prescriptions.get(wk_num, prescriptions[1])

        # Warmup (fixed)
        warmup = Block(
            name="Cardio Warmup (10 min)",
            exercises=[
                Exercise(
                    name="Easy Aerobic Ramp",
                    library="external_training",
                    dose="5 min Zone 1 · nasal breathing",
                    rationale="Wake up the aerobic system",
                ),
                Exercise(
                    name="Dynamic Joint Prep",
                    library="external_training",
                    dose="5 min · leg swings, hip openers, thoracic rotations",
                    rationale="Prep joints for sustained cyclic movement",
                ),
            ],
        )

        # Main conditioning (weekly prescription)
        conditioning = Block(
            name=prescription["focus"],
            exercises=[
                Exercise(
                    name="Primary Modality (Elliptical, Arc Trainer, Bike, or Rower)",
                    library="external_training",
                    dose=prescription["main"],
                    rationale=prescription["rationale"],
                ),
            ],
            duration_note="Client picks modality · rotate to distribute load",
        )

        # Post-cardio reset (FRC-inspired flow)
        reset = Block(
            name="Post-Cardio Reset",
            exercises=[
                Exercise(
                    name="Hip Abducted Rock Backs",
                    library="base_positions",
                    dose="1x10 slow",
                    rationale="Open posterior hip",
                ),
                Exercise(
                    name="Hip Flexion Rocking (Quadruped)",
                    library="base_positions",
                    dose="1x8/side",
                ),
                Exercise(
                    name="90/90 Transitions",
                    library="base_positions",
                    dose="1x6/side",
                ),
                Exercise(
                    name="Shoulder IR + Scapular CARs",
                    library="cars",
                    dose="2x5 each direction",
                ),
            ],
            duration_note="~5 min",
        )

        return Session(
            day_number=day_num,
            day_type="cardio",
            focus=f"Cardio · {prescription['focus']}",
            blocks=[
                warmup,
                conditioning,
                self._build_hiit_finisher(None, context="cardio", week_num=wk_num),
                reset,
                self._build_coach_finisher([]),
            ],
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
