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
    training_frequency: int             # Total days/week (strength + cardio). Kept for back-compat.
    primary_goal: str
    fra_priorities: list[FRAPriority]
    strength_markers: list[str]         # IDs from marker library
    constraints: list[str]              # e.g. ["SI_joint_sensitivity", "no_axial_loading"]
    mobility_map: list[MobilityRating]
    body_comp: dict = field(default_factory=dict)
    progression_mode: str = "autoregulated"  # or "volume_cycle"
    strength_marker_results: dict = field(default_factory=dict)  # legacy {marker_id: value_str}
    strength_days: int = 0              # Explicit strength days/week (preferred over training_frequency)
    cardio_days: int = 0                # Explicit cardio days/week
    # NEW · richer per-marker test data (StrengthTest objects from strength_testing.py)
    # Optional · empty list means we fall back to legacy strength_marker_results.
    strength_marker_tests: list = field(default_factory=list)
    # NEW · client concerns · checkbox-driven joint flags + free-text nuance
    # concerns examples · ["bad_knee", "bad_shoulder", "lower_back", "hip", "neck", "wrist", "elbow", "ankle"]
    # concern_notes · "Right meniscus repair 2019, still touchy on deep flexion"
    concerns: list = field(default_factory=list)
    concern_notes: str = ""
    # Examples (legacy strength_marker_results) ·
    #   {"inverted_rows": "18 reps (30s)", "lat_pulldown": "140x3",
    #    "landmine_sa_press": "6 x 40 lbs"}

    @classmethod
    def from_json(cls, path: str) -> "Assessment":
        data = json.loads(Path(path).read_text())
        data["fra_priorities"] = [FRAPriority(**p) for p in data["fra_priorities"]]
        data["mobility_map"] = [MobilityRating(**r) for r in data["mobility_map"]]
        # Hydrate strength_marker_tests if present
        if data.get("strength_marker_tests"):
            from strength_testing import StrengthTest
            data["strength_marker_tests"] = [StrengthTest.from_dict(t) for t in data["strength_marker_tests"]]
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
    # NEW · Per-week prescriptions from strength_math (when test data exists).
    # List of dicts · [{week, sets, reps, weight, weight_unit, weight_note,
    #                   rpe, intent_label, tempo_note, fallback_text}, ...]
    # Empty list = use default dose strings (legacy behavior).
    week_prescriptions: list = field(default_factory=list)


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
        """Build a 4-week program for one client (IMS Block 1 structure)."""
        # Step 1 · assign priorities to training days
        day_assignments = self._assign_priorities(assessment)

        # Step 2 · build each week (4-week block)
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

        Uses explicit strength_days + cardio_days if set; otherwise falls back
        to training_frequency with legacy defaults.

        Rules ·
          Strength days alternate LB → UB → LB → UB (up to 4)
          If only 1 strength day · picks the region matching top FRA priority
          Cardio days go AFTER all strength days in the weekly order
        """
        lb_priorities = [p for p in assessment.fra_priorities if p.region == "lower_body"]
        ub_priorities = [p for p in assessment.fra_priorities if p.region == "upper_body"]
        spine_priorities = [p for p in assessment.fra_priorities if p.region == "spine"]

        # Read explicit counts · fall back to legacy training_frequency if unset
        sd = getattr(assessment, 'strength_days', 0) or 0
        cd = getattr(assessment, 'cardio_days', 0) or 0
        if sd == 0 and cd == 0:
            # Legacy path · use training_frequency
            freq = assessment.training_frequency
            if freq <= 2:
                sd, cd = 2, 0
            elif freq == 3:
                sd, cd = 2, 1
            else:
                sd, cd = 3, 1

        # Clamp sanity
        sd = max(1, min(sd, 4))
        cd = max(0, min(cd, 2))

        assignments = {}
        day_idx = 1

        # Strength days · alternate LB / UB starting with LB
        # Focus priorities:
        #   Day 1 (LB): LB priorities + a spine secondary if present
        #   Day 2 (UB): UB priorities + a spine secondary if present
        #   Day 3 (LB): LB priorities (rotated) + remaining UB secondary
        #   Day 4 (UB): UB priorities (rotated) + remaining LB secondary
        for i in range(sd):
            is_lb_day = (i % 2 == 0)
            day_type = "strength_lb" if is_lb_day else "strength_ub"

            if is_lb_day:
                # LB day · LB priorities first, then maybe 1 UB as integration
                focus = list(lb_priorities)
                if ub_priorities and len(focus) < 3:
                    focus.append(ub_priorities[-1])
                # Attach a spine priority if we have one and there's room
                if spine_priorities and len(focus) < 3:
                    focus.append(spine_priorities[0])
            else:
                # UB day
                focus = list(ub_priorities)
                if lb_priorities and len(focus) < 3:
                    focus.append(lb_priorities[-1])
                if spine_priorities and len(focus) < 3:
                    spine_pick = spine_priorities[-1] if len(spine_priorities) > 1 else spine_priorities[0]
                    focus.append(spine_pick)

            # If client has priorities on one side only and this is their "weak" day,
            # still give them at least one priority (the top overall)
            if not focus and assessment.fra_priorities:
                focus = [assessment.fra_priorities[0]]

            assignments[f"day_{day_idx}"] = {
                "day_type": day_type,
                "focus_priorities": focus[:3],
            }
            day_idx += 1

        # Cardio days · after all strength days
        for i in range(cd):
            assignments[f"day_{day_idx}"] = {
                "day_type": "cardio",
                "focus_priorities": [],
            }
            day_idx += 1

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
            1: "Base Volume · 3 × 12 · build tolerance and groove the pattern",
            2: "Tempo Control · 3 × 10 with 3-sec eccentrics · own the descent",
            3: "Strength Build · 4 × 8 · push the working weight",
            4: "Performance Week · 4 × 6 · top-end strength · or retest 10RM",
        }.get(wk_num, "Unscheduled week")

    def _week_progression_notes(self, wk_num: int) -> list[str]:
        return {
            1: ["Base Volume week. Three sets of twelve at moderate load (RPE 7).",
                "Goal · move clean reps. Stop with 2-3 reps in reserve.",
                "If form breaks down before rep 12, drop the weight."],
            2: ["Tempo Control. Same sets, drop reps to ten, control the eccentric.",
                "Three seconds down on every rep · feel the muscle work.",
                "Weight stays similar to Week 1, RPE climbs to 7-8 from the tempo."],
            3: ["Strength Build. Four sets of eight at the prescribed working weight.",
                "Standard tempo returns. RPE 8 · the last rep should feel hard.",
                "This is the first real strength push of the block."],
            4: ["Performance Week. Four sets of six at top-end load · RPE 8-9.",
                "OR · retest 10RM if coach approves · directly compare to baseline.",
                "Either way, this is the load benchmark for next block."],
        }.get(wk_num, [])

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
        ]
        # Joint Care · only included when client has flagged concerns
        joint_care = self._build_joint_care(assessment)
        if joint_care:
            blocks.append(joint_care)
        blocks.extend([
            self._build_mobility_prep(priorities, assessment.constraints,
                                       wk_num=wk_num, assessment=assessment),
            self._build_strength_a(day_type, assessment, wk_num, day_num=day_num),
            self._build_strength_b(day_type, priorities, assessment, wk_num),
            self._build_hiit_finisher(assessment, context="strength"),
            self._build_decompression_cooldown(priorities),
            self._build_coach_finisher(priorities),
        ])

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
    # BLOCK BUILDER · JOINT CARE (red-flag joints, gentle drills)
    # ------------------------------------------------------

    def _build_joint_care(self, assessment: Assessment) -> Block | None:
        """Build a Joint Care block for any flagged client concerns.

        Returns None if there are no concerns to address (block won't appear).

        For each flagged joint, prescribes 2 gentle defaults ·
          - Passive CARs · low-load joint exploration
          - Light Flexibility Hold · pain-free range only
        Coach can swap or expand once they review the plan.

        Dose stays gentle and CONSTANT across all 4 weeks. No progression
        until the joint is cleared (yellow/green).
        """
        concerns = getattr(assessment, "concerns", None) or []
        if not concerns:
            return None

        # Map concern keywords to canonical joint names + drill labels
        # The drill labels are constructed to be unambiguous on the PDF
        # so the coach SEES exactly which joint was flagged
        joint_drills = []  # list of (joint_label, drills)

        for concern in concerns:
            concern_norm = str(concern).lower().replace(" ", "_").replace("-", "_")
            joint = self._concern_to_joint(concern_norm)
            if joint is None:
                continue

            joint_label = self._joint_display_name(joint)
            drills = [
                Exercise(
                    name=f"{joint_label} Passive CARs",
                    library="external_training",
                    dose="2-3 reps/direction · gentle · stop at any pinch",
                    rationale=f"Joint exploration without load · respects {joint_label.lower()} flag",
                ),
                Exercise(
                    name=f"{joint_label} Light Flexibility Hold",
                    library="external_training",
                    dose="30 sec · short of any restriction · NO pain",
                    rationale=f"Tissue prep · pain-free range only",
                ),
            ]
            joint_drills.append((joint_label, drills))

        if not joint_drills:
            return None

        # Flatten · Joint Care contains all drills across all flagged joints
        all_exercises = []
        for joint_label, drills in joint_drills:
            all_exercises.extend(drills)

        # Build the duration note that tells the coach what's happening
        flagged_joints = ", ".join(jl for jl, _ in joint_drills)
        return Block(
            name="Joint Care",
            exercises=all_exercises,
            duration_note=f"Working AROUND · {flagged_joints} · gentle · same dose all 4 weeks until cleared",
        )

    def _joint_display_name(self, canonical_joint: str) -> str:
        """Convert canonical joint key to a readable display label."""
        return {
            "knee": "Knee",
            "shoulder": "Shoulder",
            "lumbar": "Lower Back",
            "hip": "Hip",
            "cervical": "Neck",
            "wrist": "Wrist",
            "elbow": "Elbow",
            "ankle": "Ankle",
        }.get(canonical_joint, canonical_joint.title())

    # ------------------------------------------------------
    # BLOCK BUILDERS · MOBILITY PREP (RAILs-based)
    # ------------------------------------------------------

    def _build_mobility_prep(self, priorities: list[FRAPriority],
                             constraints: list[str],
                             wk_num: int = 1,
                             assessment: Assessment = None) -> Block:
        """RAILs-based mobility prep · constraint-aware progression.

        Dose progression rules ·
          - GREEN-rated joint (Optimal Control) · push hardest · time + rounds ramp aggressively
          - YELLOW-rated joint (Moderate Control) · moderate ramp
          - RED-rated joint (Limited Control) · gentle, conservative ramp
          - Unknown / no rating · default (yellow) progression

        Pattern per priority ·
          priority 1 · Lift-Off + Hover OR ERR
          priority 2 · Lift-Off only
          priority 3 · Lift-Off only
        """
        exercises = []
        for i, priority in enumerate(priorities[:3]):
            rating = self._rating_for_priority(priority, assessment)

            lift_off = self._pick_lift_off_for_priority(priority, constraints,
                                                        wk_num=wk_num, rating=rating)
            exercises.append(lift_off)

            if i == 0:
                slow_control = self._pick_slow_control_for_priority(priority, constraints,
                                                                     wk_num=wk_num, rating=rating)
                exercises.append(slow_control)

        return Block(
            name="Mobility Prep (RAILs-Based)",
            exercises=exercises,
            duration_note="Lift-Offs primary · Hover/ERR for slow-twitch control"
        )

    def _rating_for_priority(self, priority: FRAPriority,
                              assessment: Assessment) -> str:
        """Look up the worst rating in the mobility_map for joints/directions
        in this priority. Returns one of 'green' / 'yellow' / 'red'.

        If the assessment has no map or no match for this priority, default to
        'yellow' (moderate · conservative middle ground).
        """
        if assessment is None or not getattr(assessment, "mobility_map", None):
            return "yellow"

        priority_joints = set((j or "").lower() for j in (priority.joints or []))
        priority_dirs = set((d or "").lower() for d in (priority.directions or []))

        worst_score = 999  # green=2 yellow=1 red=0 · we want the smallest
        rating_map = {"green": 2, "yellow": 1, "red": 0,
                      "optimal": 2, "moderate": 1, "limited": 0}
        score_to_rating = {2: "green", 1: "yellow", 0: "red"}

        for entry in assessment.mobility_map:
            joint = (getattr(entry, "joint", "") or "").lower()
            direction = (getattr(entry, "direction", "") or "").lower()
            rating = (getattr(entry, "rating", "") or "").lower()

            joint_match = (not priority_joints or joint in priority_joints)
            dir_match = (not priority_dirs or direction in priority_dirs)
            if joint_match and dir_match and rating in rating_map:
                score = rating_map[rating]
                if score < worst_score:
                    worst_score = score

        if worst_score == 999:
            return "yellow"  # no match · safe default
        return score_to_rating[worst_score]

    def _mobility_dose(self, drill_type: str, wk_num: int, rating: str,
                        is_unilateral: bool = True) -> str:
        """Compute the per-week dose for a mobility drill · constraint-aware.

        drill_type · 'lift_off' | 'err' | 'hover'

        Progression model · TIME + ROUNDS + CONSTRAINT-MODULATED
          GREEN (Optimal)   · most aggressive · longer holds, more rounds
          YELLOW (Moderate) · moderate ramp · the default for most clients
          RED (Limited)     · steady · low rounds, modest hold ramp · safety first

        Returns dose string like "3×8/side · 15s hold" or "2×6/side · 10s hold".
        """
        side = "/side" if is_unilateral else ""

        # Per-week multipliers indexed by [rating][wk_num]
        # Each entry · (sets, reps, hold_seconds)
        TABLES = {
            "lift_off": {
                "green":  {1: (2, 6, 5),  2: (2, 8, 8),  3: (3, 6, 10), 4: (3, 8, 12)},
                "yellow": {1: (2, 6, 5),  2: (2, 6, 8),  3: (2, 8, 8),  4: (3, 6, 10)},
                "red":    {1: (2, 5, 3),  2: (2, 6, 5),  3: (2, 6, 5),  4: (2, 6, 5)},
            },
            "err": {
                # ERR is a slow eccentric ROM drill · lower reps, longer "slow" cue
                "green":  {1: (2, 4, 0), 2: (2, 5, 0), 3: (3, 4, 0), 4: (3, 5, 0)},
                "yellow": {1: (2, 3, 0), 2: (2, 4, 0), 3: (2, 5, 0), 4: (3, 4, 0)},
                "red":    {1: (2, 3, 0), 2: (2, 3, 0), 3: (2, 4, 0), 4: (2, 4, 0)},
            },
            "hover": {
                # Hover is a hold · time-dominant
                "green":  {1: (1, 5, 10), 2: (2, 4, 12), 3: (2, 5, 15), 4: (3, 4, 20)},
                "yellow": {1: (1, 5, 8),  2: (1, 5, 10), 3: (2, 4, 12), 4: (2, 5, 15)},
                "red":    {1: (1, 5, 5),  2: (1, 5, 8),  3: (2, 4, 8),  4: (2, 4, 10)},
            },
        }

        table = TABLES.get(drill_type, TABLES["lift_off"])
        rating_data = table.get(rating, table["yellow"])
        sets, reps, hold = rating_data.get(wk_num, rating_data[1])

        if drill_type == "err":
            return f"{sets}×{reps}{side} · slow"
        if drill_type == "hover":
            if hold > 0:
                return f"{sets}×{reps}{side} · {hold}s hold"
            return f"{sets}×{reps}{side}"
        # lift_off
        if hold > 0:
            return f"{sets}×{reps}{side} · {hold}s pause at end range"
        return f"{sets}×{reps}{side}"

    def _pick_lift_off_for_priority(self, priority: FRAPriority,
                                     constraints: list[str],
                                     wk_num: int = 1,
                                     rating: str = "yellow") -> Exercise:
        """Build a Lift-Off exercise · dose progresses by week + rating."""
        joint = priority.joints[0].title() if priority.joints else "General"
        direction = priority.directions[0] if priority.directions else ""
        direction_label = self._direction_label(direction)

        name = f"{joint} {direction_label} Lift-Offs".replace("  ", " ").strip()
        dose = self._mobility_dose("lift_off", wk_num, rating, is_unilateral=True)

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
                    dose=dose,
                    rationale=f"Targets {priority.description} · {rating} rating · W{wk_num} ramp"
                )

        return Exercise(
            name=name,
            library="end_range",
            dose=dose,
            rationale=f"Lift-Off activation · {rating} rating · W{wk_num} dose"
        )

    def _pick_slow_control_for_priority(self, priority: FRAPriority,
                                         constraints: list[str],
                                         wk_num: int = 1,
                                         rating: str = "yellow") -> Exercise:
        """Pick a Hover OR ERR · dose progresses by week + rating."""
        joint = priority.joints[0].title() if priority.joints else "General"
        direction = priority.directions[0] if priority.directions else ""
        direction_label = self._direction_label(direction)

        is_rotation = direction.lower() in ["ir", "er"]

        if is_rotation:
            name = f"{joint} {direction_label} ERRs".replace("  ", " ").strip()
            dose = self._mobility_dose("err", wk_num, rating, is_unilateral=True)
            return Exercise(
                name=name,
                library="end_range",
                dose=dose,
                rationale=f"Rotational slow-twitch · {rating} rating · W{wk_num}"
            )
        else:
            name = f"{joint} Hovers".strip()
            dose = self._mobility_dose("hover", wk_num, rating, is_unilateral=True)
            return Exercise(
                name=name,
                library="end_range",
                dose=dose,
                rationale=f"Slow-twitch hold · {rating} rating · W{wk_num}"
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

    def _build_strength_a(self, day_type: str, assessment: Assessment, wk_num: int,
                            day_num: int = 1) -> Block:
        if day_type == "strength_lb":
            patterns = self._pick_lb_patterns(assessment.constraints, day_num=day_num,
                                                wk_num=wk_num,
                                                concerns=getattr(assessment, "concerns", None))
        else:
            patterns = ["push_horizontal", "pull_horizontal"]  # default UB

        exercises = []
        for pattern in patterns:
            ex = self._pick_strength_exercise(pattern, assessment.constraints,
                                               assessment=assessment,
                                               day_type=day_type,
                                               day_num=day_num)
            ex.dose = self._strength_dose(wk_num, exercise_type="compound", pattern=pattern)
            ex.progression_note = self._progression_note(wk_num, "compound")
            ex = self._apply_week_progression(ex, wk_num, "compound")
            ex = self._fill_load(ex, assessment)
            ex = self._attach_week_prescriptions(ex, assessment)
            exercises.append(ex)

        return Block(
            name=f"Strength A",
            exercises=exercises,
            duration_note="Compound lifts · prioritize form over load"
        )

    def _find_matching_strength_test(self, exercise_name: str, assessment: Assessment):
        """Find a StrengthTest whose exercise_name matches this exercise.

        Matching is fuzzy · case-insensitive substring or token overlap.
        Returns None if no match (caller falls back to default dose strings).
        """
        tests = getattr(assessment, "strength_marker_tests", None) or []
        if not tests:
            return None

        target = (exercise_name or "").strip().lower()
        if not target:
            return None
        target_tokens = set(target.replace("(", " ").replace(")", " ").split())

        best = None
        best_score = 0
        for t in tests:
            test_name = (getattr(t, "exercise_name", None) or "").strip().lower()
            if not test_name:
                continue
            # Exact substring match · score 100
            if target == test_name or target in test_name or test_name in target:
                return t
            # Token overlap score
            test_tokens = set(test_name.replace("(", " ").replace(")", " ").split())
            overlap = len(target_tokens & test_tokens)
            if overlap > best_score and overlap >= 2:
                # Need at least 2 token overlap to count · avoids "Squat" matching
                # everything that has "squat" in it
                best_score = overlap
                best = t
        return best

    def _attach_week_prescriptions(self, ex: Exercise, assessment: Assessment) -> Exercise:
        """If strength test data matches this exercise, attach 4-week prescriptions.

        Stores them as a list of dicts on ex.week_prescriptions for the PDF
        renderer to read. Falls back gracefully (empty list) if no match.
        """
        try:
            test = self._find_matching_strength_test(ex.name, assessment)
        except Exception:
            return ex
        if test is None:
            return ex

        try:
            from strength_math import generate_4_week_progression
            prog = generate_4_week_progression(test, ex.name)
        except Exception:
            return ex

        # Convert WeekPrescription dataclasses → plain dicts for JSON-serialization
        weeks_as_dicts = []
        for w in prog.get("weeks", []):
            weeks_as_dicts.append({
                "week": w.week,
                "sets": w.sets,
                "reps": w.reps,
                "weight": w.weight,
                "weight_unit": w.weight_unit,
                "weight_note": w.weight_note,
                "rpe": w.rpe,
                "intent_label": w.intent_label,
                "tempo_note": w.tempo_note,
                "fallback_text": w.fallback_text,
                "display_dose": w.display_dose(),
            })

        ex.week_prescriptions = weeks_as_dicts
        return ex

    def _pick_lb_patterns(self, constraints: list[str], day_num: int = 1,
                            wk_num: int = 1, concerns: list = None) -> list[str]:
        """Pick lower body patterns, respecting constraints AND concerns.

        IMS convention for spine-constrained clients on LB day 1 ·
          Strength A · unilateral knee-dominant + hip-extension teaching
          Strength A is where the client learns hip extension cleanly before loading it.

        Spine triggers · formal SI/disc/lumbar flags · OR free-text "lower_back" concern.
        Knee triggers · formal flag · OR "bad_knee" concern → unilateral knee + hip extension.
        """
        has_spine = self._has_spine_constraint(constraints) or self._has_concern(concerns, "lower_back")
        has_knee = self._has_concern(concerns, "bad_knee") or self._has_concern(concerns, "knee")

        if has_spine:
            # Strength A · knee-dominant unilateral + hip extension teaching
            return ["squat_unilateral", "hip_extension_teaching"]
        if has_knee:
            # Bad knee · keep loaded squats off the menu · use unilateral hip-dominant work
            return ["squat_unilateral", "hinge_unilateral"]
        # Default · knee-dominant + hip-dominant
        return ["squat", "hinge"]

    def _has_spine_constraint(self, constraints: list[str]) -> bool:
        flags = {"si_joint_sensitivity", "no_axial_loading", "lumbar_issue", "disc_issue"}
        return any(c.lower().replace(" ", "_") in flags for c in (constraints or []))

    def _has_concern(self, concerns: list, *keywords) -> bool:
        """True if any concern entry contains any of the keywords (case-insensitive)."""
        if not concerns:
            return False
        normalized = [str(c).lower().replace(" ", "_").replace("-", "_") for c in concerns]
        for kw in keywords:
            kw_lower = kw.lower().replace(" ", "_").replace("-", "_")
            for n in normalized:
                if kw_lower in n:
                    return True
        return False

    def _pick_strength_exercise(self, pattern: str, constraints: list[str],
                                  assessment=None, day_type: str = None,
                                  day_num: int = 1) -> Exercise:
        """Select a strength exercise matching the pattern, filtered by constraints.

        Picker priority ·
          1. If client has a strength_marker_test for an exercise in this pattern's
             pool, USE that exercise. Coach tested it · they probably want it.
          2. Otherwise pick from the pool, varying by day_type so LB Day 1 and
             LB Day 4 don't always get the same pick.
          3. Constraint-safe variants always rise to the top.
        """
        # ─── POOLS · each pattern has multiple candidates ───
        # Order within each list = preference order for typical client.
        # Constraint filtering below then reorders.
        pools = {
            # SQUAT family · axial vs non-axial
            "squat":                  ["Goblet Squat", "Landmine Goblet Squat", "Barbell Front Squat", "Barbell Back Squat"],
            "squat_axial_safe":       ["Goblet Squat", "Landmine Goblet Squat", "Wide Stance Kettlebell Lateral Squat (Cossack)"],
            # Knee-friendly squat-pattern alternatives · emphasize hip, minimize knee shear
            # Used when client has bad_knee concern · loads the posterior chain instead
            "squat_knee_friendly":    ["Bridge (Single & Double Leg)", "Hip Thrust",
                                       "Kettlebell Deadlift", "Step Up",
                                       "Bench-Supported Single Leg RDL",
                                       "Dumbbell RDL (Straight Leg Deadlift)"],
            "squat_unilateral":       ["Rear Foot Elevated Split Squat", "Front Foot Elevated Split Squat",
                                       "Split Squat", "TRX Assisted Split Squat",
                                       "Step Up", "Step Down",
                                       "Slide Board Reverse Lunge", "Landmine Reverse Lunge",
                                       "Around the World Lunge",
                                       "Single Leg Squat (Pistol or Assisted)",
                                       "Wide Stance Kettlebell Lateral Squat (Cossack)"],
            "squat_lateral":          ["Lateral Lunge",
                                       "Slide Board Lateral Lunge",
                                       "Wide Stance Kettlebell Lateral Squat (Cossack)"],

            # HINGE family
            "hinge":                  ["Trap Bar Deadlift", "Dumbbell RDL (Straight Leg Deadlift)",
                                       "Barbell RDL (Straight Leg Deadlift)", "Kettlebell Deadlift",
                                       "Landmine Deadlift", "Landmine RDL", "Barbell Deadlift"],
            "hinge_teach":            ["TRX Double-Leg Hinge", "Dowel Hip Hinge", "Kettlebell Deadlift",
                                       "Bridge (Single & Double Leg)"],
            "hinge_axial_safe":       ["Kettlebell Deadlift", "TRX Double-Leg Hinge",
                                       "Landmine Deadlift", "Landmine RDL",
                                       "Dumbbell RDL (Straight Leg Deadlift)"],
            "hinge_unilateral":       ["Bench-Supported Single Leg RDL",
                                       "TRX Bodyweight Single Leg RDL",
                                       "TRX Split-Stance Hinge",
                                       "Dumbbell Single Leg RDL",
                                       "Kettlebell Single Leg RDL",
                                       "Landmine Single Leg RDL",
                                       "Single Leg RDL (weighted or unweighted)",
                                       "Single Leg Deadlift (reaching or kettlebell)"],

            # HAMSTRING CURL (new category)
            "hamstring_curl":         ["Physioball Hamstring Curl", "Slide Board Hamstring Curls"],

            # TEACHING / ACTIVATION (hip extension)
            "hip_extension_teaching": ["Double-Leg Hip Bridge", "Frog Pump", "Banded Hip Bridge",
                                       "Bridge (Single & Double Leg)", "Kettlebell Deadlift", "Dowel Hip Hinge"],

            # HIP BRIDGE PROGRESSION (used for Strength B accessory)
            "hip_bridge":             ["Double-Leg Hip Bridge", "Frog Pump", "Banded Hip Bridge",
                                       "Single-Leg Hip Bridge", "Foot-Elevated Hip Bridge",
                                       "Foot-Elevated Single-Leg Hip Bridge",
                                       "Dumbbell Hip Bridge", "Barbell Hip Bridge"],
            "hip_bridge_axial_safe":  ["Double-Leg Hip Bridge", "Frog Pump", "Banded Hip Bridge",
                                       "Single-Leg Hip Bridge", "Foot-Elevated Hip Bridge",
                                       "Dumbbell Hip Bridge"],

            # PRESSING · horizontal
            "push_horizontal":        ["Dumbbell Bench Press (Single or Double Arm)",
                                       "Dumbbell Floor Press (Single or Double Arm)",
                                       "Pushup (Full, Eccentric, Isometric)",
                                       "Barbell Bench Press", "Cable Press (Single or Double Arm)"],
            # Shoulder-friendly push · floor press, landmine, neutral grip · less impingement risk
            "push_horizontal_shoulder_friendly": [
                                       "Dumbbell Floor Press (Single or Double Arm)",
                                       "Half-Kneeling Landmine Press", "Cable Press (Single or Double Arm)",
                                       "Pushup (Full, Eccentric, Isometric)"],

            # PRESSING · vertical (shoulder)
            "push_vertical":          ["Half Kneeling Overhead Press", "Seated Overhead Press (Single or Double Arm)",
                                       "Half-Kneeling Landmine Press", "Standing Landmine Press",
                                       "Front Foot Elevated Overhead Press", "Standing Overhead Press"],
            "push_vertical_axial_safe": ["Half-Kneeling Landmine Press", "Half Kneeling Overhead Press",
                                         "Seated Overhead Press (Single or Double Arm)"],
            # Shoulder-friendly vertical push · landmine angle, less direct overhead
            "push_vertical_shoulder_friendly": [
                                       "Half-Kneeling Landmine Press", "Standing Landmine Press"],

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

            # CORE (new dedicated pool)
            "core_antiextension":     ["Deadbug (Training Table)", "Pilates Roll-Down (Training Table)",
                                       "Physioball Saw (Plank)", "Slide Board Plank Saws",
                                       "Hollow Hold", "Dead Bug", "Front Plank"],
            "core_antirotation":      ["Bird Dog (Training Table)", "Physioball Circles (Plank)",
                                       "Pallof Press (Standing Anti-Rotation)", "Suitcase March"],
            "core_dynamic":           ["Slide Board Mountain Climbers", "Physioball Saw (Plank)",
                                       "Ab Wheel / Barbell Rollout"],

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

        # Pick the pool · concerns and constraints both shape this
        # Spine-safe routing fires for formal flags OR a lower_back concern
        client_concerns_for_check = (getattr(assessment, "concerns", None) if assessment else None) or []
        spine_constrained = (self._has_spine_constraint(constraints)
                             or self._has_concern(client_concerns_for_check, "lower_back", "back"))
        rationale = None

        # Pull concerns from the assessment if available
        client_concerns = []
        if assessment is not None:
            client_concerns = [str(c).lower().replace(" ", "_").replace("-", "_")
                               for c in (getattr(assessment, "concerns", None) or [])]

        has_knee_concern = any("knee" in c for c in client_concerns)
        has_shoulder_concern = any("shoulder" in c for c in client_concerns)

        # ── CONCERN-DRIVEN POOL ROUTING (highest priority) ──
        # Bad knee · all squat/lunge patterns route to knee-friendly hip-emphasis pool
        if has_knee_concern and pattern in ("squat", "squat_unilateral", "squat_lateral"):
            candidates = pools.get("squat_knee_friendly", pools["squat"])
            rationale = "Knee-friendly · hip-emphasis pattern (knee concern noted)"
        # Bad shoulder · pressing patterns route to shoulder-friendly variants
        elif has_shoulder_concern and pattern == "push_horizontal":
            candidates = pools.get("push_horizontal_shoulder_friendly", pools["push_horizontal"])
            rationale = "Shoulder-friendly press · neutral grip / floor-supported (shoulder concern noted)"
        elif has_shoulder_concern and pattern == "push_vertical":
            candidates = pools.get("push_vertical_shoulder_friendly", pools["push_vertical"])
            rationale = "Landmine angle · reduces direct overhead load (shoulder concern noted)"
        # ── SPINE CONSTRAINT ROUTING (existing behavior) ──
        elif spine_constrained and f"{pattern}_axial_safe" in pools:
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
        # ── PICK ORDER ──
        # 1) prefer an exercise the coach actually tested (in strength_marker_tests)
        #    that matches this pattern · if you tested Front Squat, you get Front Squat
        # 2) rotate the pool by day_type so Day 1 ≠ Day 4 in the same week
        # 3) fall back to first valid pool candidate
        name = None

        # 1 · Test-match preference
        if assessment is not None:
            tested_match = self._match_pattern_to_tested_exercise(pattern, candidates, assessment)
            if tested_match:
                name = tested_match
                if not rationale:
                    rationale = "Pattern picked from your tested exercises"

        # 2 · Day-based rotation through the pool
        # Concerns (bad knee, bad shoulder etc.) come from the assessment if available
        client_concerns = getattr(assessment, "concerns", None) if assessment else None
        if name is None and day_type:
            rotated = self._rotate_pool(candidates, day_type, pattern, day_num=day_num)
            name = self._first_valid_candidate(rotated, constraints, concerns=client_concerns)

        # 3 · Default
        if name is None:
            name = self._first_valid_candidate(candidates, constraints,
                                                 concerns=client_concerns) or candidates[0]

        # If concerns drove a non-default pick, surface that in the rationale
        if client_concerns and not rationale:
            rationale = f"Selected with care for · {', '.join(client_concerns)}"

        if "unilateral" in pattern and spine_constrained and not rationale:
            rationale = "Unilateral variant selected due to spine-loading constraint"
        if pattern == "hip_extension_teaching" and not rationale:
            rationale = "Hip extension pattern without spine load · clean teaching exercise"

        return Exercise(name=name, library="external_training", rationale=rationale)

    def _match_pattern_to_tested_exercise(self, pattern: str,
                                            candidates: list[str],
                                            assessment) -> str | None:
        """Find a tested exercise whose name matches one of the pool candidates
        for this pattern. Returns the canonical pool name (so we use the
        library version), not the raw test entry name.

        Matching is fuzzy · case-insensitive substring + token overlap.
        """
        tests = getattr(assessment, "strength_marker_tests", None) or []
        if not tests:
            return None

        for t in tests:
            test_name = (getattr(t, "exercise_name", None) or "").strip().lower()
            if not test_name:
                continue
            test_tokens = set(test_name.replace("(", " ").replace(")", " ").split())

            # Look for a pool candidate whose name overlaps with the tested name
            for cand in candidates:
                cand_lower = cand.lower()
                cand_tokens = set(cand_lower.replace("(", " ").replace(")", " ").split())

                # Direct substring · highest confidence
                if test_name in cand_lower or cand_lower in test_name:
                    return cand
                # Token overlap · need at least 2 meaningful tokens shared
                # (avoids "Squat" matching everything with squat in it)
                shared = test_tokens & cand_tokens
                # Strip common short words that don't carry meaning
                shared -= {"the", "a", "of", "or", "and", "with"}
                if len(shared) >= 2:
                    return cand
        return None

    def _rotate_pool(self, candidates: list[str], day_type: str,
                      pattern: str, day_num: int = 1) -> list[str]:
        """Rotate the pool order so different days don't always pick the same
        exercise. Same client + same day_num always gets the same pick (stable),
        but Day 1 and Day 4 differ.

        Mechanism · take a per-pattern base offset (so different patterns start
        at different points in their pool), then ADD day_num so each day rotates
        one further than the last.
        """
        if not candidates:
            return candidates
        if len(candidates) <= 1:
            return list(candidates)

        import hashlib
        # Per-pattern base offset · stable across deploys
        digest = hashlib.md5(pattern.encode("utf-8")).digest()
        base = digest[0]
        # Combine with day_num so each day rotates +1 (or +2 etc)
        seed = (base + day_num) % len(candidates)
        return list(candidates[seed:]) + list(candidates[:seed])

    def _first_valid_candidate(self, candidates: list[str], constraints: list[str],
                                concerns: list[str] = None) -> str | None:
        """Return the first candidate whose contraindications don't clash with
        constraints OR client concerns (bad knee, bad shoulder, etc.)."""
        for name in candidates:
            entry = self._find_entry_by_name(name)
            if entry is None:
                # If we can't find it · allow it (PDF still renders the name)
                # but only when we have NO concerns to check (otherwise risky)
                if not concerns:
                    return name
                continue
            if not self._violates_constraints(entry, constraints, concerns=concerns):
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
        """4-week straight-set dose generator (IMS Block 1).

        Compound (Strength A) ·
          W1 · 3 × 12   · Base Volume
          W2 · 3 × 10   · Tempo Control
          W3 · 4 × 8    · Strength Build
          W4 · 4 × 6    · Performance Week

        Accessory (Strength B) ·
          W1 · 3 × 12
          W2 · 3 × 10
          W3 · 4 × 10
          W4 · 4 × 8

        Corrective · stays steady at 3 × 12 throughout (low intensity, high quality).

        NOTE · this is the BASELINE dose. If client has strength_marker_tests,
        the PDF renderer overlays personalized loading on top of these reps/sets.
        """
        is_side = pattern and ("unilateral" in pattern or "teaching" in pattern)
        side = "/side" if is_side else ""

        if exercise_type == "compound":
            if wk_num == 1:
                return f"3 × 12{side}"
            if wk_num == 2:
                return f"3 × 10{side}"
            if wk_num == 3:
                return f"4 × 8{side}"
            if wk_num == 4:
                return f"4 × 6{side}"

        if exercise_type == "accessory":
            if wk_num == 1:
                return f"3 × 12{side}"
            if wk_num == 2:
                return f"3 × 10{side}"
            if wk_num == 3:
                return f"4 × 10{side}"
            if wk_num == 4:
                return f"4 × 8{side}"

        if exercise_type == "corrective":
            return f"3 × 12{side}"

        return "3 × 10"

    def _progression_note(self, wk_num: int, exercise_type: str) -> str:
        """One-line note · what changes this week for this exercise type.

        4-week IMS Block 1 ·
          W1 · Base Volume        · 3 × 12 · groove the pattern
          W2 · Tempo Control      · 3 × 10 · 3-sec eccentric
          W3 · Strength Build     · 4 × 8  · push load
          W4 · Performance Week   · 4 × 6  · top-end strength

        Returns None when no modification is needed.
        """
        if wk_num == 1:
            return None

        if exercise_type == "compound":
            if wk_num == 2:
                return "Three sets of ten · 3-sec eccentric · same load family as W1."
            if wk_num == 3:
                return "Four sets of eight · standard tempo · push the working weight."
            if wk_num == 4:
                return "Four sets of six · top-end strength · or retest 10RM if coach approves."

        if exercise_type == "accessory":
            if wk_num == 2:
                return "Drop reps to 10 · 3-sec eccentric on every rep."
            if wk_num == 3:
                return "Add a fourth set · keep the rep target at 10."
            if wk_num == 4:
                return "Drop reps to 8 · push the load."

        if exercise_type == "corrective":
            if wk_num == 2:
                return "Add a 2-sec iso hold at end range."
            if wk_num == 3:
                return "Extend iso to 3 sec if tolerated."
            if wk_num == 4:
                return "Same dose · push effort and end-range control."

        return None

    def _apply_week_progression(self, ex: Exercise, wk_num: int, exercise_type: str) -> Exercise:
        """Apply IMS Block 1 (4-week straight-set) progression levers.

        For compounds and accessories, the sets/reps are already set by
        _strength_dose. This method ONLY adds tempo notes where appropriate.
        Personalized loads (when test data exists) are layered on later by
        the PDF renderer using the strength_math module.

        Week 1 · base dose, standard tempo
        Week 2 · same sets, fewer reps, 3-sec eccentric tempo note
        Week 3 · 4 sets of 8, standard tempo, RPE 8
        Week 4 · 4 sets of 6, RPE 8-9 (or retest)
        """
        if wk_num == 1:
            return ex

        if wk_num == 2:
            if exercise_type in ("compound", "accessory"):
                ex.tempo = "3-sec eccentric"
            elif exercise_type == "corrective":
                ex.tempo = "2-sec iso at end range"
            return ex

        if wk_num == 3:
            if exercise_type == "corrective":
                ex.tempo = "3-sec iso at end range"
            # Compounds and accessories use standard tempo · no mutation needed
            return ex

        if wk_num == 4:
            # No mutation · the dose is already 4 × 6 (compound) / 4 × 8 (accessory)
            # The "or retest 10RM" note is added by the PDF renderer
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

        # 1 · Core accessory · rotate from the antiextension pool
        # New clients or red-heavy profiles get the simpler variants first
        tier = self._infer_client_tier(assessment)
        core_candidates = [
            "Deadbug (Training Table)",       # teaching
            "Dead Bug",                       # classic
            "Bird Dog (Training Table)",      # antirotation (alt)
            "Pilates Roll-Down (Training Table)",  # spinal articulation
            "Hollow Hold",                    # intermediate
            "Physioball Saw (Plank)",         # dynamic
        ]
        # Advanced clients can rotate in the slide board / physioball work
        if tier == "advanced":
            core_candidates = [
                "Slide Board Plank Saws",
                "Physioball Saw (Plank)",
                "Ab Wheel / Barbell Rollout",
                "Physioball Circles (Plank)",
            ] + core_candidates

        # Pick by week number for variety across the block
        core_name = core_candidates[(wk_num - 1) % len(core_candidates)]
        core_entry = self._find_entry_by_name(core_name)
        core_dose = (core_entry or {}).get("dose") or "3 × 10"
        core_ex = Exercise(
            name=core_name,
            library="external_training",
            dose=core_dose,
            progression_note=self._progression_note(wk_num, "accessory"),
        )
        core_ex = self._apply_week_progression(core_ex, wk_num, "accessory")
        exercises.append(core_ex)

        # 2 · Pattern complement
        has_spine = self._has_spine_constraint(assessment.constraints)
        if day_type == "strength_lb":
            # LB Strength B #2 · rotate through the hip-bridge progression
            # Spine-safe clients get the non-axial picks; others can rotate to loaded
            bridge_pool = "hip_bridge_axial_safe" if has_spine else "hip_bridge"
            bridge_candidates = {
                "hip_bridge": [
                    "Single-Leg Hip Bridge", "Foot-Elevated Hip Bridge",
                    "Dumbbell Hip Bridge", "Banded Hip Bridge",
                    "Barbell Hip Bridge", "Foot-Elevated Single-Leg Hip Bridge",
                ],
                "hip_bridge_axial_safe": [
                    "Single-Leg Hip Bridge", "Foot-Elevated Hip Bridge",
                    "Dumbbell Hip Bridge", "Banded Hip Bridge", "Frog Pump",
                ],
            }[bridge_pool]
            bridge_name = bridge_candidates[(wk_num - 1) % len(bridge_candidates)]
            second_ex = Exercise(
                name=bridge_name,
                library="external_training",
                dose="3 × 10/side" if "Single" in bridge_name else "3 × 10",
                progression_note=self._progression_note(wk_num, "accessory"),
                rationale="Hip extension volume · progression rotated weekly",
            )
        else:
            # UB day · keep Landmine SA Press as vertical-press volume default
            second_ex = Exercise(
                name="Landmine SA Press",
                library="external_training",
                dose="3 × 6/side",
                progression_note=self._progression_note(wk_num, "accessory"),
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
        """Cardio day · progresses through zones across the 4-week block.

        IMS Block 1 cardio arc ·
          W1 · Zone 2 Base       · 15-20 min nasal breathing · build aerobic base
          W2 · Zone 2 Extended   · 25 min steady · capacity build
          W3 · Z2 → Z3 Bridge    · 10 min Z2 + 15 min Z3 · first tempo exposure
          W4 · Z3-Z4 Intervals   · alternating intervals · performance week
        """
        prescriptions = {
            1: {
                "focus": "Week 1 · Zone 2 Base",
                "main": "15-20 min steady state · RPE 4-5 · nasal breathing only",
                "rationale": "Build aerobic base. If you can't nasal breathe, slow down.",
            },
            2: {
                "focus": "Week 2 · Zone 2 Extended",
                "main": "25 min steady state · RPE 4-5 · nasal breathing",
                "rationale": "Same zone, longer duration. Capacity build.",
            },
            3: {
                "focus": "Week 3 · Zone 2 → Zone 3 Bridge",
                "main": "10 min Z2 warmup + 15 min Z3 (RPE 6-7) + 5 min Z2 cooldown",
                "rationale": "First tempo exposure. Breathing deeper but sustainable.",
            },
            4: {
                "focus": "Week 4 · Z3-Z4 Intervals",
                "main": "5 min Z2 warmup · 4 rounds (3 min Z3 / 1 min Z4) · 5 min cooldown",
                "rationale": "Performance week · alternate tempo and threshold work.",
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
            blocks.append(self._build_mobility_prep([focus_priority], assessment.constraints,
                                                     wk_num=wk_num, assessment=assessment))

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

    def _violates_constraints(self, ex: dict, constraints: list[str],
                                concerns: list[str] = None) -> bool:
        """Check if an exercise is contraindicated by any client constraint
        OR by a concern flag (bad knee, bad shoulder, etc.).

        Constraints · formal flags from the assessment (SI joint, disc, etc.)
        Concerns · checkbox-driven joint warnings (bad_knee, bad_shoulder, etc.)
        """
        contras = ex.get("contraindications", []) or []
        if not isinstance(contras, list):
            contras = [contras]
        contras_lower = [str(c).lower() for c in contras]

        # 1 · Direct constraint match (existing behavior)
        for constraint in (constraints or []):
            c_lower = constraint.lower().replace(" ", "_")
            if any(c_lower in con for con in contras_lower):
                return True

        # 2 · Concerns-based filtering · check joint of exercise vs bad joints
        if concerns:
            ex_joint = str(ex.get("joint", "")).lower()
            ex_secondary = [str(j).lower() for j in (ex.get("secondary_joints") or [])]
            ex_pattern = str(ex.get("pattern", "")).lower()
            ex_tier = str(ex.get("tier", "")).lower()

            for concern in concerns:
                concern_lower = concern.lower().replace(" ", "_").replace("-", "_")
                bad_joint = self._concern_to_joint(concern_lower)
                if bad_joint is None:
                    continue

                # Heavy-loading patterns through that joint · veto
                if self._is_heavy_load_for_joint(ex_pattern, ex_joint,
                                                   ex_secondary, ex_tier, bad_joint):
                    return True

        return False

    def _concern_to_joint(self, concern: str) -> str | None:
        """Map a checkbox concern flag to the joint it implies.

        Returns canonical joint name or None if not a joint concern.
        """
        mapping = {
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
        return mapping.get(concern)

    def _is_heavy_load_for_joint(self, pattern: str, joint: str,
                                   secondary: list, tier: str,
                                   bad_joint: str) -> bool:
        """Decide if an exercise heavily loads the bad_joint.

        Rules · err on the side of safety
          - Mobility / CARs / hover / lift-off · never heavy · always OK
          - All other patterns · if bad joint is primary, secondary, OR
            implied by pattern → veto
        """
        # Direct joint match · primary or secondary
        joints_loaded = [joint] + list(secondary)

        # Pattern-based joint mapping · catches things like "squat" → knee
        # even when the entry's joint field doesn't list knee explicitly
        pattern_joint_map = {
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
        if pattern in pattern_joint_map:
            joints_loaded.extend(pattern_joint_map[pattern])

        if bad_joint not in joints_loaded:
            return False  # exercise doesn't touch the bad joint · safe

        # Pure mobility patterns through the bad joint are still OK
        # (CARs, hovers, lift-offs, segmented rolldowns, etc.)
        safe_patterns = {
            "cars", "spinal_articulation", "lift_off", "hover", "err",
            "antiextension", "isometric", "breathing",
        }
        if pattern in safe_patterns:
            return False

        # Anything else loaded through the bad joint = veto
        return True

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
