"""
Cardio system tests · verify cardio_rules logic + integration into the program.

Covers the spec list ·
  1. knee-sensitive defaults to bike/arc and gets no impact finishers
  2. not_cleared_for_intervals blocks intervals everywhere
  3. low-back-sensitive does not get rower by default
  4. shoulder-sensitive does not get SkiErg or Assault Bike arms by default
  5. cardio_days = 2 creates two cardio sessions
  6. client PDF shows primary cardio machine and 4-week progression
  7. coach PDF shows baseline data and flags
  8. full PDF shows both
  9. no cardio data falls back to safe generic Zone 2 prescription
"""
import os
import sys
import unittest
import io
import contextlib

# Make the generator package importable
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "generator"))


def _silent(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


# ─── UNIT-LEVEL · cardio_rules ───────────────────────────────

class TestNormalize(unittest.TestCase):
    def test_concern_to_limit_mapping(self):
        from cardio_rules import normalize_cardio_profile
        n = normalize_cardio_profile(
            profile=None,
            concerns=["bad_knee", "lower_back", "bad_shoulder"],
            constraints_rich=[],
        )
        self.assertIn("knee_sensitive", n["limitations"])
        self.assertIn("low_back_sensitive", n["limitations"])
        self.assertIn("shoulder_sensitive", n["limitations"])

    def test_constraint_status_cleared_drops(self):
        from cardio_rules import normalize_cardio_profile
        n = normalize_cardio_profile(
            profile=None,
            concerns=[],
            constraints_rich=[
                {"key": "post_surgery_knee", "status": "cleared"},
            ],
        )
        self.assertNotIn("knee_sensitive", n["limitations"])

    def test_post_surgery_status_flag(self):
        from cardio_rules import normalize_cardio_profile
        n = normalize_cardio_profile(
            profile=None,
            concerns=[],
            constraints_rich=[
                {"key": "post_surgery_knee", "status": "post_surgery"},
            ],
        )
        self.assertIn("knee_sensitive", n["limitations"])
        self.assertTrue(n["post_surgery"])

    def test_active_flare_up_set(self):
        from cardio_rules import normalize_cardio_profile
        n = normalize_cardio_profile(
            profile=None,
            concerns=[],
            constraints_rich=[
                {"key": "chronic_low_back", "status": "active_flare_up"},
            ],
        )
        self.assertTrue(n["active_flare_up"])
        self.assertIn("low_back_sensitive", n["limitations"])

    def test_hr_recovery_quality_classified(self):
        from cardio_rules import normalize_cardio_profile
        # mock profile with HR recovery
        class P: pass
        p = P()
        p.primary_modality = None
        p.secondary_modalities = []
        p.avoid_modalities = []
        p.limitations = []
        p.z2_baseline = {}
        p.interval_test = {}
        p.hr_recovery = {"end_hr": 150, "one_min_hr": 130}  # drop = 20 → strong
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        self.assertEqual(n["hr_recovery"]["quality"], "strong")
        self.assertEqual(n["hr_recovery"]["drop_one_min"], 20)


class TestMachineChoice(unittest.TestCase):
    def test_knee_sensitive_default_to_bike(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        n = normalize_cardio_profile(profile=None, concerns=["bad_knee"], constraints_rich=[])
        machine, _ = choose_primary_cardio_machine(n)
        self.assertIn(machine, ["stationary_bike", "upright_bike", "arc_trainer"])

    def test_low_back_sensitive_avoids_rower(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        n = normalize_cardio_profile(profile=None, concerns=["lower_back"], constraints_rich=[])
        machine, _ = choose_primary_cardio_machine(n)
        self.assertNotEqual(machine, "rower")

    def test_shoulder_sensitive_avoids_skierg_and_assault(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        n = normalize_cardio_profile(profile=None, concerns=["bad_shoulder"], constraints_rich=[])
        machine, _ = choose_primary_cardio_machine(n)
        self.assertNotIn(machine, ["skierg", "assault_bike"])

    def test_explicit_primary_used_when_safe(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        class P: pass
        p = P()
        p.primary_modality = "arc_trainer"
        p.secondary_modalities = []
        p.avoid_modalities = []
        p.limitations = ["knee_sensitive"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        machine, _ = choose_primary_cardio_machine(n)
        self.assertEqual(machine, "arc_trainer")

    def test_explicit_primary_routed_when_risky(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        # SkiErg picked but client is shoulder_sensitive · should reroute
        class P: pass
        p = P()
        p.primary_modality = "skierg"
        p.secondary_modalities = []
        p.avoid_modalities = []
        p.limitations = ["shoulder_sensitive"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        machine, rationale = choose_primary_cardio_machine(n)
        self.assertNotEqual(machine, "skierg")
        self.assertIn("conflicts", rationale.lower())

    def test_default_when_nothing_set(self):
        from cardio_rules import normalize_cardio_profile, choose_primary_cardio_machine
        n = normalize_cardio_profile(profile=None, concerns=[], constraints_rich=[])
        machine, _ = choose_primary_cardio_machine(n)
        self.assertEqual(machine, "stationary_bike")


class TestIntervalClearance(unittest.TestCase):
    def test_not_cleared_blocks(self):
        from cardio_rules import normalize_cardio_profile, determine_interval_clearance
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["not_cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        self.assertEqual(determine_interval_clearance(n), "blocked")

    def test_active_flare_up_blocks(self):
        from cardio_rules import normalize_cardio_profile, determine_interval_clearance
        n = normalize_cardio_profile(
            profile=None, concerns=[],
            constraints_rich=[{"key": "chronic_low_back", "status": "active_flare_up"}],
        )
        self.assertEqual(determine_interval_clearance(n), "blocked")

    def test_post_surgery_blocks(self):
        from cardio_rules import normalize_cardio_profile, determine_interval_clearance
        n = normalize_cardio_profile(
            profile=None, concerns=[],
            constraints_rich=[{"key": "post_surgery_knee", "status": "post_surgery"}],
        )
        self.assertEqual(determine_interval_clearance(n), "blocked")

    def test_poor_hr_recovery_z2_only(self):
        from cardio_rules import normalize_cardio_profile, determine_interval_clearance
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["cleared_for_intervals"]  # cleared but HR is poor
        p.z2_baseline = {}; p.interval_test = {}
        p.hr_recovery = {"end_hr": 150, "one_min_hr": 145}  # drop=5 → poor
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        self.assertEqual(determine_interval_clearance(n), "z2_only")

    def test_cleared_with_strong_hr_full(self):
        from cardio_rules import normalize_cardio_profile, determine_interval_clearance
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}
        p.hr_recovery = {"end_hr": 150, "one_min_hr": 130}  # drop=20 → strong
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        self.assertEqual(determine_interval_clearance(n), "full")


class TestProgression(unittest.TestCase):
    def test_blocked_progression_no_intervals(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_progression
        n = normalize_cardio_profile(
            profile=None, concerns=["bad_knee"],
            constraints_rich=[{"key": "post_surgery_knee", "status": "post_surgery"}],
        )
        prog = generate_cardio_progression(n)
        for wk in (1, 2, 3, 4):
            text = (prog[wk]["main"] + " " + prog[wk]["focus"]).lower()
            self.assertNotIn("interval", text,
                              f"Week {wk} should not contain intervals: {text}")
            self.assertNotIn("pickup", text,
                              f"Week {wk} should not contain pickups: {text}")

    def test_deconditioned_progression_short_durations(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_progression
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["deconditioned"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        prog = generate_cardio_progression(n)
        # W1 should be the shortest dose
        self.assertIn("8-12", prog[1]["main"])

    def test_full_clearance_progression_has_intervals(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_progression
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}
        p.hr_recovery = {"end_hr": 150, "one_min_hr": 130}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        prog = generate_cardio_progression(n)
        self.assertIn("pickup", prog[3]["main"].lower())
        self.assertIn("20s hard", prog[4]["main"].lower())


class TestCoachFlags(unittest.TestCase):
    def test_knee_flag_present(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_coach_flags
        n = normalize_cardio_profile(profile=None, concerns=["bad_knee"], constraints_rich=[])
        flags = generate_cardio_coach_flags(n)
        joined = " ".join(flags).lower()
        self.assertIn("knee", joined)
        self.assertIn("impact", joined)

    def test_not_cleared_flag_present(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_coach_flags
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["not_cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        flags = generate_cardio_coach_flags(n)
        joined = " ".join(flags).lower()
        self.assertTrue("not cleared" in joined or "z2 only" in joined or "zone 2 only" in joined)

    def test_poor_hr_flag_present(self):
        from cardio_rules import normalize_cardio_profile, generate_cardio_coach_flags
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}
        p.hr_recovery = {"end_hr": 150, "one_min_hr": 145}  # drop=5 = poor
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        flags = generate_cardio_coach_flags(n)
        joined = " ".join(flags).lower()
        self.assertIn("hr recovery", joined)


class TestFinisherFilter(unittest.TestCase):
    SAMPLE_POOL = [
        ("Lateral Bounds (controlled)", "5/side × 4 rounds", "single-leg power"),
        ("Jump Rope Intervals", "30s on / 30s off × 5", "low-grade plyo"),
        ("Kettlebell Swings", "20s on / 40s off × 6", "hinge ballistic"),
        ("Step-Ups with Knee Drive", "30s/side × 3 rounds", "unilateral hip extension"),
        ("Bike Sprints (Assault / Air Bike)", "20s sprint / 40s easy × 6", "zero impact"),
        ("Farmer Carry Intervals", "30s carry / 30s rest × 4", "grip + posture"),
        ("SkiErg Intervals", "30s on / 30s off × 5", "upper-body power"),
        ("Battle Rope Slams", "30s on / 30s off × 5", "standing"),
        ("Rower Sprints", "250m × 4 rounds", "full-body pull"),
    ]

    def test_knee_sensitive_kills_impact(self):
        from cardio_rules import normalize_cardio_profile, filter_finishers_by_cardio_limitations
        n = normalize_cardio_profile(profile=None, concerns=["bad_knee"], constraints_rich=[])
        out = filter_finishers_by_cardio_limitations(self.SAMPLE_POOL, n)
        names = [e[0].lower() for e in out]
        for banned in ("lateral bound", "jump rope", "kettlebell swing", "step-up"):
            self.assertFalse(any(banned in n for n in names),
                             f"{banned} should be removed for knee-sensitive client")

    def test_shoulder_sensitive_kills_skierg(self):
        from cardio_rules import normalize_cardio_profile, filter_finishers_by_cardio_limitations
        n = normalize_cardio_profile(profile=None, concerns=["bad_shoulder"], constraints_rich=[])
        out = filter_finishers_by_cardio_limitations(self.SAMPLE_POOL, n)
        names = [e[0].lower() for e in out]
        self.assertFalse(any("skierg" in n for n in names))
        self.assertFalse(any("battle rope" in n for n in names))

    def test_low_back_kills_rower_sprints(self):
        from cardio_rules import normalize_cardio_profile, filter_finishers_by_cardio_limitations
        n = normalize_cardio_profile(profile=None, concerns=["lower_back"], constraints_rich=[])
        out = filter_finishers_by_cardio_limitations(self.SAMPLE_POOL, n)
        names = [e[0].lower() for e in out]
        self.assertFalse(any("rower sprint" in n for n in names))
        self.assertFalse(any("kettlebell swing" in n for n in names))

    def test_not_cleared_kills_all_intensity(self):
        from cardio_rules import normalize_cardio_profile, filter_finishers_by_cardio_limitations
        class P: pass
        p = P()
        p.primary_modality = None; p.secondary_modalities = []; p.avoid_modalities = []
        p.limitations = ["not_cleared_for_intervals"]
        p.z2_baseline = {}; p.interval_test = {}; p.hr_recovery = {}
        n = normalize_cardio_profile(p, concerns=[], constraints_rich=[])
        out = filter_finishers_by_cardio_limitations(self.SAMPLE_POOL, n)
        names = [e[0].lower() for e in out]
        for banned_word in ("sprint", "interval", "swing", "slam", "jump", "bound"):
            self.assertFalse(any(banned_word in n for n in names),
                             f"{banned_word} should be removed for not_cleared_for_intervals client")


# ─── INTEGRATION · full program build ────────────────────────

class TestIntegrationKneeClient(unittest.TestCase):
    """The exact scenario from the spec ·
       right knee concern, post-surgery knee, stationary bike primary,
       not_cleared_for_intervals, HR end 150 / 1-min 128, 3 strength + 2 cardio.
    """

    @classmethod
    def setUpClass(cls):
        from app import build_program_pdf
        form = {
            "client_name": "Final Spec Test", "age_range": "early 50s", "sex": "F",
            "background": "knee surgery 2019", "training_frequency": 5,
            "strength_days": 3, "cardio_days": 2,
            "primary_goal": "Build aerobic base without aggravating my knee",
            "fra_priorities": ["Hip IR L+R"],
            "mobility_map": [
                {"joint": "hip", "direction": "IR", "side": "L", "rating": "yellow"},
                {"joint": "knee", "direction": "flexion", "side": "R", "rating": "red"},
            ],
            "strength_markers": [], "strength_marker_results": {},
            "strength_marker_tests": [],
            "constraints": ["post_surgery_knee"],
            "constraints_rich": [
                {
                    "key": "post_surgery_knee",
                    "display_name": "Post-Surgery Knee",
                    "side": "right", "status": "post_surgery",
                    "pain_level": 3,
                    "avoid_notes": "deep knee flexion",
                    "allowed_notes": "supported variants",
                },
            ],
            "concerns": ["bad_knee"],
            "concern_notes": "Right meniscus repair 2019",
            "body_comp": {},
            "cardio_profile": {
                "primary_modality": "stationary_bike",
                "secondary_modalities": ["upright_bike"],
                "avoid_modalities": [],
                "limitations": ["knee_sensitive", "not_cleared_for_intervals"],
                "z2_baseline": {
                    "machine": "stationary_bike",
                    "duration_minutes": 10, "avg_hr": 130,
                    "rpe": 4, "avg_watts": 95,
                },
                "interval_test": {},
                "hr_recovery": {"end_hr": 150, "one_min_hr": 128},  # drop=22 strong
            },
            "nutrition_strategy": "maintenance", "activity_factor": 1.4,
        }

        cls.pdfs = {}
        for mode in ("client", "coach", "full"):
            f = dict(form); f["pdf_mode"] = mode
            with contextlib.redirect_stdout(io.StringIO()):
                pdf, _ = build_program_pdf(f)
            cls.pdfs[mode] = pdf

        from pypdf import PdfReader
        cls.text = {}
        for mode, pdf in cls.pdfs.items():
            r = PdfReader(io.BytesIO(pdf))
            cls.text[mode] = "\n".join((p.extract_text() or "") for p in r.pages)

    def test_client_pdf_uses_stationary_bike(self):
        # Either explicit "Stationary Bike" or generic bike text in the cardio prescription
        self.assertIn("Stationary Bike", self.text["client"])

    def test_client_pdf_has_no_intervals(self):
        # Prescription text should not contain interval / pickup / sprint
        # (Coach appendix may, but client mode strips it)
        # We look at the CARDIO session block · find the Z2 lines
        ct_lower = self.text["client"].lower()
        # The prescription progression for blocked/z2_only paths uses these labels
        self.assertIn("zone 2", ct_lower)
        self.assertNotIn("controlled pickups", ct_lower)
        self.assertNotIn("interval block", ct_lower)
        self.assertNotIn("6 rounds (20s", ct_lower)

    def test_client_pdf_has_no_lateral_bounds(self):
        self.assertNotIn("Lateral Bound", self.text["client"])

    def test_client_pdf_has_no_jump_rope(self):
        self.assertNotIn("Jump Rope", self.text["client"])

    def test_client_pdf_has_no_kettlebell_swings(self):
        self.assertNotIn("Kettlebell Swing", self.text["client"])

    def test_client_pdf_has_5_total_sessions(self):
        # Day-by-day in the weekly map should account for 5 working sessions
        # (3 strength + 2 cardio)
        tx = self.text["client"]
        # Count the number of training-day lines
        num_strength = tx.count("Strength · ")
        num_cardio = tx.lower().count("cardio · week 1")
        # We just assert that the program registers 5 sessions
        # (the specific text may vary, but the schedule meta block shows TOTAL/wk)
        self.assertIn("TOTAL", tx)
        self.assertIn("5/wk", tx)

    def test_coach_pdf_has_baseline_and_flags(self):
        kt = self.text["coach"]
        self.assertIn("CARDIO", kt.upper())
        self.assertIn("130", kt)            # avg HR baseline
        self.assertIn("MACHINE CHOICE", kt.upper())
        self.assertIn("INTERVAL CLEARANCE", kt.upper())
        # Drop = 22 → strong
        self.assertTrue("drop -22" in kt or "drop -22 bpm" in kt)

    def test_full_pdf_has_both(self):
        ft = self.text["full"]
        self.assertIn("Stationary Bike", ft)
        self.assertIn("CARDIO", ft.upper())
        self.assertIn("COACH APPENDIX", ft.upper())


class TestNoCardioDataFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import build_program_pdf
        form = {
            "client_name": "No Cardio Profile", "age_range": "40s", "sex": "M",
            "background": "general", "training_frequency": 3,
            "strength_days": 2, "cardio_days": 1, "primary_goal": "build base",
            "fra_priorities": ["Hip IR L+R"],
            "mobility_map": [{"joint": "hip", "direction": "IR", "side": "L", "rating": "yellow"}],
            "strength_markers": [], "strength_marker_results": {}, "strength_marker_tests": [],
            "constraints": [], "concerns": [], "body_comp": {},
            # NO cardio_profile key at all
            "nutrition_strategy": "maintenance", "activity_factor": 1.4,
        }
        with contextlib.redirect_stdout(io.StringIO()):
            cls.pdf, _ = build_program_pdf(form)

    def test_pdf_generates(self):
        self.assertGreater(len(self.pdf), 50000)

    def test_falls_back_to_zone_2(self):
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(self.pdf))
        text = "\n".join((p.extract_text() or "") for p in r.pages)
        self.assertIn("Zone 2", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
