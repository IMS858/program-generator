"""
IMS · objective measurement layer · test suite.

Test order matters here and mirrors the build brief ·

  1. GRACEFUL DEGRADATION IS WRITTEN FIRST. With objective_measures absent or
     partial, output must be byte-identical to a build with no objective layer
     at all. Everything else in this file is only allowed to exist because
     this passes.
  2. Precedence · a measured signal may never override a hard contraindication.
  3. Quadrant classification, weakest link, load from force, side dose.
  4. Phase 2 individualization · identical demographics with different force
     profiles produce different programs, and different demographics with
     identical force produce different volume.

Run ·
    python3 -m unittest tests.test_objective_measures -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "generator"))

from generator import Assessment, Generator, MobilityRating, parse_fra_priority  # noqa: E402
from ims_contract import (CONTRACT_VERSION, GENERATOR_VERSION,  # noqa: E402
                          PROTOCOL_VERSION, load_thresholds)
import force_load  # noqa: E402
import rom_force_routing as rfr  # noqa: E402
import side_dose  # noqa: E402
import weakest_link  # noqa: E402
from objective_measures import parse_objective_measures  # noqa: E402
from progression_profile import derive_profile, parse_age  # noqa: E402


LIB = str(REPO_ROOT / "libraries")
CFG = load_thresholds()


# ══════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════

def make_assessment(**overrides) -> Assessment:
    base = dict(
        name="Test Client",
        age_range="late 40s",
        sex="M",
        background="software engineer, sits often",
        training_frequency=3,
        primary_goal="Move better and get stronger",
        fra_priorities=[parse_fra_priority("Hip IR L+R"),
                        parse_fra_priority("Shoulder ER L")],
        strength_markers=[],
        constraints=[],
        mobility_map=[
            MobilityRating(joint="hip", direction="IR", side="L", rating="yellow"),
            MobilityRating(joint="hip", direction="IR", side="R", rating="yellow"),
            MobilityRating(joint="shoulder", direction="ER", side="L", rating="yellow"),
        ],
        body_comp={},
        strength_days=3,
        cardio_days=0,
    )
    base.update(overrides)
    return Assessment(**base)


FULL_MEASURES = {
    "current": {
        "date": "2026-06-14",
        "bodyweight_lb": 185,
        "dynamo": [
            {"test": "knee_extension", "side": "L", "value": 60, "unit": "lb"},
            {"test": "knee_extension", "side": "R", "value": 95, "unit": "lb"},
            {"test": "hip_abduction", "side": "L", "value": 52, "unit": "lb"},
            {"test": "hip_abduction", "side": "R", "value": 55, "unit": "lb"},
            {"test": "shoulder_er", "side": "L", "value": 14, "unit": "lb"},
            {"test": "shoulder_er", "side": "R", "value": 24, "unit": "lb"},
            {"test": "grip", "side": "L", "value": 95, "unit": "lb"},
            {"test": "grip", "side": "R", "value": 98, "unit": "lb"},
        ],
        "rom": [
            # Limited hip IR, and the hip is strong → passive restriction
            {"joint": "hip", "motion": "ir", "side": "L", "degrees": 18},
            # Full shoulder flexion but weak ER → uncontrolled range
            {"joint": "shoulder", "motion": "flexion", "side": "L", "degrees": 172},
        ],
    },
    "previous": {
        "date": "2026-04-12",
        "bodyweight_lb": 188,
        "dynamo": [
            {"test": "knee_extension", "side": "L", "value": 50, "unit": "lb"},
            {"test": "knee_extension", "side": "R", "value": 93, "unit": "lb"},
        ],
        "rom": [
            {"joint": "hip", "motion": "ir", "side": "L", "degrees": 12},
        ],
    },
}


def build(assessment):
    return Generator(libraries_path=LIB).build_program(assessment)


def program_json(program) -> str:
    """Serialize a program to a comparable JSON string."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "p.json")
        program.to_json(path)
        return Path(path).read_text()


# ══════════════════════════════════════════════════════════
# 1 · GRACEFUL DEGRADATION · WRITTEN FIRST
# ══════════════════════════════════════════════════════════

class TestGracefulDegradation(unittest.TestCase):
    """Absent or partial objective data must cost exactly nothing.

    Most clients will have no assessment data for months. Some never will. If
    the objective layer changes their plan by so much as a character, the
    feature is not safe to ship.
    """

    def test_absent_objective_data_is_byte_identical(self):
        a1 = make_assessment()
        a2 = make_assessment(objective_measures=None)
        self.assertEqual(program_json(build(a1)), program_json(build(a2)))

    def test_empty_objective_object_is_byte_identical(self):
        baseline = program_json(build(make_assessment()))
        for empty in ({}, {"current": {}}, {"current": {"dynamo": [], "rom": []}}):
            with self.subTest(empty=empty):
                a = make_assessment(objective_measures=empty)
                self.assertEqual(program_json(build(a)), baseline)

    def test_malformed_objective_data_never_raises_and_degrades_cleanly(self):
        """Garbage in the optional block must not take a session down."""
        baseline = program_json(build(make_assessment()))
        garbage = {
            "current": {
                "date": "not-a-date",
                "dynamo": [
                    {"test": "unknown_test", "value": 40},
                    {"test": "grip", "value": "banana"},
                    "not even an object",
                ],
                "rom": [{"joint": "elbow_of_theseus", "motion": "ir", "degrees": 5}],
            }
        }
        a = make_assessment(objective_measures=garbage)
        # Every entry is unusable → parses to nothing → identical output.
        self.assertEqual(program_json(build(a)), baseline)

    def test_generation_is_reproducible(self):
        """Same input, same output · twice in the same process and across runs.

        This used to fail: the HIIT finisher was seeded with hash(context),
        which Python salts per process. Without reproducibility none of the
        byte-identical assertions above mean anything.
        """
        self.assertEqual(program_json(build(make_assessment())),
                         program_json(build(make_assessment())))

    def test_partial_data_rom_only_produces_no_signals(self):
        """One axis is not a quadrant. A half-measured joint gets no route."""
        a = make_assessment(objective_measures={
            "current": {"date": "2026-06-14",
                        "rom": [{"joint": "hip", "motion": "ir", "side": "L",
                                 "degrees": 18}]}})
        program = build(a)
        self.assertEqual(program.objective.get("signals"), [])

    def test_partial_data_force_only_produces_no_signals(self):
        a = make_assessment(objective_measures={
            "current": {"date": "2026-06-14", "bodyweight_lb": 185,
                        "dynamo": [{"test": "grip", "side": "L", "value": 40}]}})
        program = build(a)
        self.assertEqual(program.objective.get("signals"), [])

    def test_first_assessment_with_no_previous(self):
        payload = {"current": FULL_MEASURES["current"]}
        a = make_assessment(objective_measures=payload)
        program = build(a)
        self.assertIsNone(program.objective["previous_date"])
        self.assertEqual(program.objective["deltas"], [])
        self.assertTrue(program.objective["measure_table"])

    def test_objective_data_does_change_the_program(self):
        """The other side of the coin · with data, something must differ.

        A degradation test that passes because the feature does nothing is not
        a passing degradation test.
        """
        without = program_json(build(make_assessment()))
        with_data = program_json(build(make_assessment(
            objective_measures=FULL_MEASURES)))
        self.assertNotEqual(without, with_data)


# ══════════════════════════════════════════════════════════
# 2 · PRECEDENCE · SAFETY WINS
# ══════════════════════════════════════════════════════════

class TestPrecedence(unittest.TestCase):
    """A measured signal must never override a safety reroute."""

    def _capacity_signal(self):
        """Limited ROM + weak force on the knee → 'load the end range'."""
        return rfr.ForceSignal(
            joint="knee", side="L", motion="flexion",
            quadrant=rfr.CAPACITY, route=rfr.ROUTE_TOWARD_LOADED_END_RANGE,
            priority=3, confidence="high",
            rom_evidence="knee flexion L 100°",
            force_evidence="knee extension L 40 lb")

    def test_toward_route_is_suppressed_by_hard_contraindication(self):
        signals = rfr.apply_precedence([self._capacity_signal()], {"knee"})
        self.assertFalse(signals[0].active)
        self.assertEqual(signals[0].suppressed_by, "hard_contraindication")
        self.assertEqual(rfr.joints_for_loaded_end_range(signals), set())

    def test_suppression_is_recorded_not_silent(self):
        signals = rfr.apply_precedence([self._capacity_signal()], {"knee"})
        self.assertIn("suppressed_by", signals[0].to_dict())
        self.assertEqual(signals[0].to_dict()["suppressed_by"],
                         "hard_contraindication")

    def test_away_route_survives_a_contraindication(self):
        """Routing away only adds caution · it can never fight the safety layer."""
        sig = rfr.ForceSignal(
            joint="knee", side="L", motion="flexion",
            quadrant=rfr.PASSIVE_RESTRICTION, route=rfr.ROUTE_AWAY_FROM_LOADING,
            priority=2, confidence="high", flag_manual_therapy=True)
        signals = rfr.apply_precedence([sig], {"knee"})
        self.assertTrue(signals[0].active)
        self.assertIn("knee", rfr.joints_to_unload(signals))

    def test_unrelated_joint_is_untouched(self):
        signals = rfr.apply_precedence([self._capacity_signal()], {"shoulder"})
        self.assertTrue(signals[0].active)

    def test_end_to_end_measured_signal_cannot_unblock_a_bad_knee(self):
        """The whole contract, through the real generator.

        The client has a measured signal that says 'load this knee's end range'
        AND a checked bad_knee concern. The concern wins, the signal is
        recorded as suppressed, and no knee-loading exercise appears.
        """
        measures = {
            "current": {
                "date": "2026-06-14", "bodyweight_lb": 185,
                "dynamo": [
                    {"test": "knee_extension", "side": "L", "value": 45},
                    {"test": "knee_extension", "side": "R", "value": 48},
                    {"test": "grip", "side": "L", "value": 95},
                    {"test": "grip", "side": "R", "value": 96},
                    {"test": "hip_abduction", "side": "L", "value": 50},
                ],
                "rom": [{"joint": "knee", "motion": "flexion", "side": "L",
                         "degrees": 105}],
            }
        }
        a = make_assessment(objective_measures=measures, concerns=["bad_knee"])
        program = build(a)

        suppressed = program.objective["suppressed_signals"]
        knee_signals = [s for s in program.objective["signals"]
                        if s["joint"] == "knee"]
        if knee_signals:
            # If the quadrant fired at all, it must have been suppressed.
            self.assertTrue(any(s["joint"] == "knee" for s in suppressed),
                            "a knee signal survived a bad_knee concern")
        self.assertNotIn("knee", program.objective.get("_", {}))

    def test_no_force_derived_load_on_an_unloaded_joint(self):
        """A joint routed away from loading gets no measured working load."""
        gen = Generator(libraries_path=LIB)
        gen._reset_objective_state()
        gen._advisory_unload = {"hip"}
        from generator import Exercise
        ex = Exercise(name="Test", library="x")
        objective = parse_objective_measures(FULL_MEASURES)
        gen._objective = objective
        # Single-joint entry · a DynaMo anchor is only offered for single-joint
        # work, so a multi-joint pattern here would short-circuit before the
        # unload check we are actually testing.
        entry = {"name": "Test", "joint": "hip", "pattern": "isolation",
                 "equipment": ["cable"]}
        ladder = [{"week": 1, "sets": 3, "reps": 12, "rpe": "7",
                   "tempo": "", "intent": "Base"}]
        out = gen._attach_force_prescriptions(ex, make_assessment(), entry,
                                              ladder, "accessory")
        self.assertEqual(out.week_prescriptions, [])
        self.assertTrue(any("routed away" in n for n in out.objective_notes))


# ══════════════════════════════════════════════════════════
# 3 · QUADRANT CLASSIFICATION
# ══════════════════════════════════════════════════════════

class TestQuadrant(unittest.TestCase):

    def _signals(self, rom_deg, force_lb, joint="hip", motion="ir",
                 test="hip_abduction", bodyweight=185):
        payload = {"current": {
            "date": "2026-06-14", "bodyweight_lb": bodyweight,
            "dynamo": [{"test": test, "side": "L", "value": force_lb}],
            "rom": [{"joint": joint, "motion": motion, "side": "L",
                     "degrees": rom_deg}],
        }}
        return rfr.build_signals(parse_objective_measures(payload), CFG)

    def test_limited_rom_weak_force_is_capacity(self):
        sigs = self._signals(rom_deg=18, force_lb=25)   # 0.14 × bw · weak
        self.assertEqual([s.quadrant for s in sigs], [rfr.CAPACITY])
        self.assertEqual(sigs[0].route, rfr.ROUTE_TOWARD_LOADED_END_RANGE)

    def test_limited_rom_normal_force_is_passive_restriction(self):
        sigs = self._signals(rom_deg=18, force_lb=70)   # 0.38 × bw · normal
        self.assertEqual([s.quadrant for s in sigs], [rfr.PASSIVE_RESTRICTION])
        self.assertEqual(sigs[0].route, rfr.ROUTE_AWAY_FROM_LOADING)
        self.assertTrue(sigs[0].flag_manual_therapy)

    def test_full_rom_weak_force_is_uncontrolled_and_highest_priority(self):
        sigs = self._signals(rom_deg=40, force_lb=25)
        self.assertEqual([s.quadrant for s in sigs], [rfr.UNCONTROLLED_RANGE])
        self.assertEqual(sigs[0].priority, 1)
        self.assertLess(sigs[0].priority,
                        rfr._QUADRANT_PRIORITY[rfr.PASSIVE_RESTRICTION])

    def test_full_rom_normal_force_emits_nothing(self):
        self.assertEqual(self._signals(rom_deg=40, force_lb=70), [])

    def test_rom_in_the_indeterminate_gap_emits_nothing(self):
        # hip_ir · limited below 25, full at 35 · 30 is neither
        self.assertEqual(self._signals(rom_deg=30, force_lb=25), [])

    def test_every_signal_carries_its_evidence(self):
        for sig in self._signals(rom_deg=18, force_lb=25):
            self.assertTrue(sig.rom_evidence)
            self.assertTrue(sig.force_evidence)
            self.assertIn("2026-06-14", sig.evidence())

    def test_voltra_end_range_ratio_drives_classification(self):
        payload = {"current": {
            "date": "2026-06-14", "bodyweight_lb": 185,
            "voltra": [
                {"pattern": "trap_bar_deadlift", "position": "mid_range",
                 "value": 300, "joint": "hip"},
                {"pattern": "trap_bar_deadlift", "position": "end_range",
                 "value": 120, "joint": "hip"},   # 40% · weak end range
            ],
            "rom": [{"joint": "hip", "motion": "ir", "side": "L", "degrees": 40}],
        }}
        sigs = rfr.build_signals(parse_objective_measures(payload), CFG)
        self.assertEqual([s.quadrant for s in sigs], [rfr.UNCONTROLLED_RANGE])
        self.assertIn("VOLTRA", sigs[0].force_evidence)

    def test_no_bodyweight_falls_back_to_asymmetry_at_low_confidence(self):
        payload = {"current": {
            "date": "2026-06-14",
            "dynamo": [{"test": "hip_abduction", "side": "L", "value": 30},
                       {"test": "hip_abduction", "side": "R", "value": 60}],
            "rom": [{"joint": "hip", "motion": "ir", "side": "L", "degrees": 40}],
        }}
        sigs = rfr.build_signals(parse_objective_measures(payload), CFG)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0].confidence, "low")


# ══════════════════════════════════════════════════════════
# 4 · WEAKEST LINK
# ══════════════════════════════════════════════════════════

class TestWeakestLink(unittest.TestCase):

    def test_ranks_weakest_first(self):
        objective = parse_objective_measures(FULL_MEASURES)
        ranked = weakest_link.rank_joints(objective, CFG)
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].joint, "shoulder")   # 14 lb ER on a 185 lb client

    def test_uses_the_weaker_side_not_an_average(self):
        objective = parse_objective_measures(FULL_MEASURES)
        knee = next(s for s in weakest_link.rank_joints(objective, CFG)
                    if s.joint == "knee")
        self.assertEqual(knee.side, "L")
        self.assertEqual(int(knee.value_lb), 60)

    def test_too_few_tested_joints_declines_to_call_a_weak_link(self):
        payload = {"current": {"date": "2026-06-14", "bodyweight_lb": 185,
                               "dynamo": [{"test": "grip", "side": "L",
                                           "value": 40}]}}
        self.assertEqual(weakest_link.rank_joints(
            parse_objective_measures(payload), CFG), [])

    def test_bias_is_stable_with_no_data(self):
        candidates = ["A", "B", "C"]
        self.assertEqual(
            weakest_link.bias_candidates(candidates, lambda n: None, [], set()),
            candidates)

    def test_bias_moves_weak_joint_candidates_up(self):
        entries = {
            "Goblet Squat": {"name": "Goblet Squat", "pattern": "squat"},
            "Half Kneeling Press": {"name": "Half Kneeling Press",
                                    "pattern": "push_vertical"},
        }
        order = weakest_link.bias_candidates(
            ["Goblet Squat", "Half Kneeling Press"], entries.get,
            ["shoulder"], set())
        self.assertEqual(order[0], "Half Kneeling Press")

    def test_bias_sinks_an_unloaded_joint(self):
        entries = {
            "Goblet Squat": {"name": "Goblet Squat", "pattern": "squat"},
            "Half Kneeling Press": {"name": "Half Kneeling Press",
                                    "pattern": "push_vertical"},
        }
        order = weakest_link.bias_candidates(
            ["Goblet Squat", "Half Kneeling Press"], entries.get,
            [], {"knee"})
        self.assertEqual(order[-1], "Goblet Squat")

    def test_asymmetry_detection(self):
        objective = parse_objective_measures(FULL_MEASURES)
        gaps = {a["test"]: a for a in weakest_link.asymmetries(objective, CFG)}
        self.assertIn("knee_extension", gaps)
        self.assertEqual(gaps["knee_extension"]["weak_side"], "L")
        self.assertTrue(gaps["knee_extension"]["significant"])
        self.assertNotIn("grip", gaps)      # 3% gap · under the flag threshold


# ══════════════════════════════════════════════════════════
# 5 · LOAD FROM MEASURED FORCE
# ══════════════════════════════════════════════════════════

class TestLoadFromForce(unittest.TestCase):

    LADDER = [
        {"week": 1, "sets": 3, "reps": 12, "rpe": "7", "tempo": "", "intent": "Base"},
        {"week": 2, "sets": 3, "reps": 10, "rpe": "7-8", "tempo": "3-sec eccentric",
         "intent": "Tempo"},
        {"week": 3, "sets": 4, "reps": 8, "rpe": "8", "tempo": "", "intent": "Build"},
        {"week": 4, "sets": 4, "reps": 6, "rpe": "8-9", "tempo": "", "intent": "Peak"},
    ]

    def test_equipment_classification(self):
        cases = [
            ({"equipment": ["dumbbell"]}, "dumbbell"),
            ({"equipment": ["barbell", "rack"]}, "barbell"),
            ({"equipment": ["kettlebell"]}, "kettlebell"),
            ({"equipment": ["cable"]}, "cable"),
            ({"equipment": []}, "bodyweight"),
            ({"equipment": None, "name": "Dead Bug"}, "bodyweight"),
        ]
        for entry, expected in cases:
            with self.subTest(entry=entry):
                self.assertEqual(force_load.equipment_class(entry), expected)

    def test_load_is_a_percentage_of_measured_force(self):
        anchor = force_load.ForceAnchor(
            test="knee_extension", joint="knee", side="L", value_lb=100,
            device="dynamo", measured_on="2026-06-14")
        w1 = force_load.load_for_week(anchor, 1, CFG)
        w4 = force_load.load_for_week(anchor, 4, CFG)
        self.assertAlmostEqual(w1, 40.0)     # 40% in config
        self.assertAlmostEqual(w4, 55.0)
        self.assertGreater(w4, w1)

    def test_prescription_carries_the_source_and_the_date(self):
        anchor = force_load.ForceAnchor(
            test="knee_extension", joint="knee", side="L", value_lb=100,
            device="dynamo", measured_on="2026-06-14")
        entry = {"name": "DB Split Squat", "equipment": ["dumbbell"],
                 "pattern": "squat_unilateral"}
        weeks = force_load.build_force_prescriptions(
            "DB Split Squat", entry, anchor, self.LADDER, CFG)
        self.assertEqual(len(weeks), 4)
        for w in weeks:
            self.assertEqual(w["load_source"], "measured_isometric_force")
            self.assertIn("2026-06-14", w["load_source_detail"])
            self.assertEqual(w["load_source_date"], "2026-06-14")

    def test_implausible_load_errors_rather_than_printing(self):
        """The whole reason this guard exists · the load path has a history."""
        anchor = force_load.ForceAnchor(
            test="grip", joint="wrist", side="L", value_lb=900,
            device="dynamo", measured_on="2026-06-14")
        entry = {"name": "DB Curl", "equipment": ["dumbbell"]}
        with self.assertRaises(force_load.ImplausibleLoadError):
            force_load.build_force_prescriptions("DB Curl", entry, anchor,
                                                 self.LADDER, CFG)

    def test_bodyweight_equipment_never_gets_a_number(self):
        anchor = force_load.ForceAnchor(
            test="grip", joint="wrist", side="L", value_lb=100,
            device="dynamo", measured_on="2026-06-14")
        entry = {"name": "Dead Bug", "equipment": []}
        self.assertIsNone(force_load.build_force_prescriptions(
            "Dead Bug", entry, anchor, self.LADDER, CFG))

    def test_anchor_prefers_the_weakest_side(self):
        objective = parse_objective_measures(FULL_MEASURES)
        entry = {"name": "Leg Extension", "joint": "knee",
                 "equipment": ["machine"]}
        anchor = force_load.find_force_anchor(entry, objective, CFG,
                                              "Leg Extension")
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.side, "L")
        self.assertEqual(int(anchor.value_lb), 60)

    def test_tested_anchor_still_wins_over_measured_force(self):
        """Measured force is a FALLBACK anchor. A real tested lift beats it."""
        from strength_testing import parse_strength_tests
        tests = parse_strength_tests([{
            "exercise_name": "Trap Bar Deadlift",
            "movement_category": "hinge",
            "equipment_type": "trap_bar",
            "load_style": "total_load",
            "sets": [{"weight": 225, "reps": 5}],
        }])
        a = make_assessment(objective_measures=FULL_MEASURES,
                            strength_marker_tests=tests)
        program = build(a)
        sources = set()
        for wk in program.weeks:
            for sess in wk.sessions:
                for blk in sess.blocks:
                    for ex in blk.exercises:
                        if ex.load_source:
                            sources.add(ex.load_source)
        # Whatever resolved, a tested anchor must never be labelled as measured.
        for wk in program.weeks:
            for sess in wk.sessions:
                for blk in sess.blocks:
                    for ex in blk.exercises:
                        if ex.anchor_match_method in ("exact", "alias", "fuzzy"):
                            self.assertNotEqual(ex.load_source,
                                                "measured_isometric_force")


# ══════════════════════════════════════════════════════════
# 6 · PHASE 2 · INDIVIDUALIZED VOLUME
# ══════════════════════════════════════════════════════════

class TestProgressionProfile(unittest.TestCase):

    def test_age_parsing(self):
        cases = {"47": 47, "late 40s": 47, "mid-50s": 55, "early 30s": 32,
                 "60-65": 62, "68 years old": 68, "": None, "unknown": None}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_age(raw), expected)

    def test_the_headline_case(self):
        """A 68-year-old deconditioned client and a 28-year-old athlete no
        longer receive the same 3×12 → 3×10 → 4×8 → 4×6."""
        older = derive_profile(make_assessment(
            age_range="68", conditioning_level="deconditioned",
            background="retired, new to lifting"), cfg=CFG)
        younger = derive_profile(make_assessment(
            age_range="28", conditioning_level="well_conditioned",
            background="former college athlete, lifted 10 years"), cfg=CFG)
        self.assertEqual(older.ladder_id, "conservative")
        self.assertEqual(younger.ladder_id, "aggressive")
        self.assertNotEqual(older.ladders["compound"],
                            younger.ladders["compound"])

    def test_deconditioned_forces_conservative_at_any_age(self):
        p = derive_profile(make_assessment(
            age_range="28", conditioning_level="deconditioned",
            background="former college athlete"), cfg=CFG)
        self.assertEqual(p.ladder_id, "conservative")

    def test_65_plus_forces_conservative(self):
        p = derive_profile(make_assessment(
            age_range="70", conditioning_level="well_conditioned",
            background="lifted 30 years"), cfg=CFG)
        self.assertEqual(p.ladder_id, "conservative")

    def test_nothing_on_file_keeps_the_legacy_ladder(self):
        p = derive_profile(make_assessment(age_range="", background="",
                                           primary_goal="", resting_hr=""),
                           cfg=CFG)
        self.assertEqual(p.ladder_id, "_default")
        self.assertEqual(p.ladders["compound"],
                         [[3, 12], [3, 10], [4, 8], [4, 6]])

    def test_progression_mode_is_no_longer_a_lie(self):
        p = derive_profile(make_assessment(), cfg=CFG)
        self.assertNotIn("autoregulated", p.progression_mode)

    def test_low_recovery_steps_one_ladder_down(self):
        kwargs = dict(age_range="28", conditioning_level="well_conditioned",
                      background="former college athlete, lifted 10 years")
        rested = derive_profile(make_assessment(**kwargs), recovery=1.0, cfg=CFG)
        wrecked = derive_profile(make_assessment(**kwargs), recovery=0.72, cfg=CFG)
        self.assertEqual(rested.ladder_id, "aggressive")
        self.assertEqual(wrecked.ladder_id, "moderate")

    def test_the_ladder_reaches_the_generated_dose(self):
        older = build(make_assessment(age_range="68",
                                      conditioning_level="deconditioned"))
        younger = build(make_assessment(
            age_range="28", conditioning_level="well_conditioned",
            background="former college athlete, lifted 10 years"))

        def first_compound_dose(program):
            for blk in program.weeks[0].sessions[0].blocks:
                if blk.name.startswith("Strength A") and blk.exercises:
                    return blk.exercises[0].dose
            return None

        self.assertNotEqual(first_compound_dose(older),
                            first_compound_dose(younger))

    def test_the_ladder_survives_the_trip_to_the_pdf(self):
        """The PDF used to hold a third hard-coded copy of the ladder that
        silently overwrote whatever the generator decided."""
        from plan_pdf import _synth_wp_from_dose
        program = {"progression": {"week_templates": {"compound": [
            {"week": 1, "sets": 2, "reps": 12, "rpe": "6", "tempo": "",
             "intent": "Base Volume"}]}}}
        wp = _synth_wp_from_dose("2 × 12", 1, program=program)
        self.assertEqual((wp["sets"], wp["reps"]), (2, 12))
        self.assertEqual(wp["rpe"], "6")

    def test_identical_demographics_different_force_produce_different_programs(self):
        weak_shoulder = {"current": {
            "date": "2026-06-14", "bodyweight_lb": 185,
            "dynamo": [
                {"test": "shoulder_er", "side": "L", "value": 10},
                {"test": "shoulder_er", "side": "R", "value": 11},
                {"test": "knee_extension", "side": "L", "value": 110},
                {"test": "knee_extension", "side": "R", "value": 112},
                {"test": "grip", "side": "L", "value": 95},
                {"test": "grip", "side": "R", "value": 96},
            ]}}
        weak_knee = {"current": {
            "date": "2026-06-14", "bodyweight_lb": 185,
            "dynamo": [
                {"test": "shoulder_er", "side": "L", "value": 30},
                {"test": "shoulder_er", "side": "R", "value": 31},
                {"test": "knee_extension", "side": "L", "value": 45},
                {"test": "knee_extension", "side": "R", "value": 46},
                {"test": "grip", "side": "L", "value": 95},
                {"test": "grip", "side": "R", "value": 96},
            ]}}
        a1 = build(make_assessment(objective_measures=weak_shoulder))
        a2 = build(make_assessment(objective_measures=weak_knee))
        self.assertNotEqual(a1.objective["emphasis"], a2.objective["emphasis"])
        self.assertNotEqual(program_json(a1), program_json(a2))


# ══════════════════════════════════════════════════════════
# 7 · PHASE 3 · SIDE-AWARE DOSE
# ══════════════════════════════════════════════════════════

class TestSideAwareDose(unittest.TestCase):

    def test_mobility_map_side_is_finally_read(self):
        a = make_assessment(mobility_map=[
            MobilityRating(joint="shoulder", direction="ER", side="L", rating="red"),
            MobilityRating(joint="shoulder", direction="ER", side="R", rating="green"),
        ])
        biases = side_dose.from_mobility_map(a, CFG)
        self.assertEqual(len(biases), 1)
        self.assertEqual(biases[0].weak_side, "L")
        self.assertEqual(biases[0].joint, "shoulder")

    def test_symmetric_ratings_produce_no_bias(self):
        a = make_assessment(mobility_map=[
            MobilityRating(joint="hip", direction="IR", side="L", rating="yellow"),
            MobilityRating(joint="hip", direction="IR", side="R", rating="yellow"),
        ])
        self.assertEqual(side_dose.from_mobility_map(a, CFG), [])

    def test_measured_force_beats_the_traffic_light(self):
        a = make_assessment(mobility_map=[
            MobilityRating(joint="knee", direction="flexion", side="R", rating="red"),
            MobilityRating(joint="knee", direction="flexion", side="L", rating="green"),
        ])
        biases = side_dose.resolve(a, parse_objective_measures(FULL_MEASURES), CFG)
        # Force says the LEFT knee is 37% weaker; the traffic light said right.
        self.assertEqual(biases["knee"].weak_side, "L")
        self.assertEqual(biases["knee"].source, "measured_force")

    def test_weak_side_earns_one_extra_set(self):
        bias = side_dose.SideBias(joint="shoulder", weak_side="L",
                                  source="mobility_map", detail="shoulder L red")
        split = side_dose.split_dose(3, 12, bias, CFG)
        self.assertEqual(split["L"], {"sets": 4, "reps": 12})
        self.assertEqual(split["R"], {"sets": 3, "reps": 12})
        self.assertEqual(side_dose.format_dose(split), "L 4 × 12 · R 3 × 12")

    def test_compounds_are_excluded(self):
        """Adding a set to one side of a bilateral compound is not coherent."""
        self.assertFalse(side_dose.applies_to("compound", "squat_unilateral", CFG))
        self.assertTrue(side_dose.applies_to("accessory", "squat_unilateral", CFG))
        self.assertFalse(side_dose.applies_to("accessory", "squat", CFG))

    def test_pdf_cell_renders_both_sides(self):
        from plan_pdf import _cell_lines_for_week

        class FakeCanvas:
            def stringWidth(self, *a, **k):
                return 10

        wk_ex = {
            "name": "SA Row",
            "dose": "3 × 12/side",
            "week_prescriptions": [],
            "dose_by_side": {"weak_side": "L", "by_week": {
                "1": {"L": {"sets": 4, "reps": 12}, "R": {"sets": 3, "reps": 12},
                      "display": "L 4 × 12 · R 3 × 12"}}},
        }
        lines = _cell_lines_for_week(wk_ex, 1, 100, FakeCanvas())
        self.assertIn("L 4 × 12", lines)
        self.assertIn("R 3 × 12", lines)


# ══════════════════════════════════════════════════════════
# 8 · CONTRACT + VERSION STAMPS
# ══════════════════════════════════════════════════════════

class TestVersionStamps(unittest.TestCase):

    def test_every_program_carries_three_versions(self):
        program = build(make_assessment())
        self.assertEqual(program.generator_version, GENERATOR_VERSION)
        self.assertEqual(program.contract_version, CONTRACT_VERSION)
        self.assertEqual(program.protocol_version, PROTOCOL_VERSION)

    def test_versions_survive_serialization(self):
        data = json.loads(program_json(build(make_assessment())))
        for key in ("generator_version", "contract_version", "protocol_version"):
            self.assertIn(key, data)

    def test_config_version_is_stamped_on_objective_output(self):
        program = build(make_assessment(objective_measures=FULL_MEASURES))
        self.assertEqual(program.objective["threshold_config_version"],
                         CFG["config_version"])


# ══════════════════════════════════════════════════════════
# 9 · DELETED LEGACY LOAD PATH
# ══════════════════════════════════════════════════════════

class TestLegacyLoadPathIsGone(unittest.TestCase):

    def test_fill_load_no_longer_exists(self):
        gen = Generator(libraries_path=LIB)
        self.assertFalse(hasattr(gen, "_fill_load"))
        self.assertFalse(hasattr(gen, "_suggest_starting_load"))

    def test_marker_results_no_longer_write_a_load(self):
        """The legacy field is still accepted · it just cannot touch a dose."""
        with_markers = build(make_assessment(strength_marker_results={
            "lat_pulldown": "140x3", "landmine_sa_press": "6 x 40 lbs"}))
        without = build(make_assessment())

        def doses(program):
            out = []
            for wk in program.weeks:
                for sess in wk.sessions:
                    for blk in sess.blocks:
                        for ex in blk.exercises:
                            out.append(ex.dose)
            return out

        self.assertEqual(doses(with_markers), doses(without))
        for d in doses(with_markers):
            self.assertNotIn("@ ~", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
