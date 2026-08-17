"""
Strength anchor resolver tests · cover the spec scenarios.

  Test 1 · 3 Point Row anchor + Single Arm Dumbbell Row exercise → alias match
  Test 2 · DB Row anchor + Single Arm Dumbbell Row exercise → alias match
  Test 3 · 8 anchors entered, all preserved, all reach resolution
  Test 4 · Anchor for a category → picker prefers the anchored name
  Test 5 · No anchor → generic RIR is fine (no false matches)

Plus integration tests that the program PDF actually shows calculated weekly
loads instead of generic RIR when an anchor is in scope.
"""
import os
import sys
import unittest
import io
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "generator"))


class T:
    """Mock StrengthTest · matches the duck-typed interface used by the resolver."""
    def __init__(self, name=None, cat=None, **kw):
        self.exercise_name = name
        self.movement_category = cat
        self.load_unit = kw.get("load_unit", "lb")
        self.load_style = kw.get("load_style")
        for r in (3, 5, 6, 8, 10, 12):
            setattr(self, f"tested_{r}rm", kw.get(f"tested_{r}rm"))


class TestNormalize(unittest.TestCase):
    def test_lowercase_and_punct(self):
        from strength_anchor_resolver import normalize_exercise_name
        self.assertEqual(normalize_exercise_name("3-Point Row"), "3 point row")
        self.assertEqual(normalize_exercise_name("DB Bench Press"), "dumbbell bench press")
        self.assertEqual(normalize_exercise_name("SL RDL (Bench Supported)"),
                         "single leg romanian deadlift bench supported")

    def test_abbreviation_expansion(self):
        from strength_anchor_resolver import normalize_exercise_name
        self.assertIn("dumbbell", normalize_exercise_name("DB Row"))
        self.assertIn("single arm", normalize_exercise_name("SA Press"))
        self.assertIn("single leg", normalize_exercise_name("SL Squat"))
        self.assertIn("romanian deadlift", normalize_exercise_name("RDL"))
        self.assertIn("kettlebell", normalize_exercise_name("KB Swing"))

    def test_typo_normalization(self):
        from strength_anchor_resolver import normalize_exercise_name
        self.assertIn("pull up", normalize_exercise_name("Pulllups"))
        self.assertIn("pull up", normalize_exercise_name("Pullups"))


class TestResolver(unittest.TestCase):
    def test_three_point_row_matches_single_arm_db_row(self):
        """The exact bug from the audit · 3 Point Row anchor must alias-match
        Single Arm Dumbbell Row."""
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [T("3 Point Row", "pull_horizontal", tested_3rm=35)]
        match, method = resolve_anchor_for_exercise("Single Arm Dumbbell Row", tests)
        self.assertIsNotNone(match)
        self.assertEqual(method, "alias")
        self.assertEqual(match.exercise_name, "3 Point Row")

    def test_db_row_matches_single_arm_db_row(self):
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [T("DB Row", "pull_horizontal", tested_3rm=35)]
        match, method = resolve_anchor_for_exercise("Single Arm Dumbbell Row", tests)
        self.assertIsNotNone(match)
        self.assertIn(method, ("alias", "exact"))

    def test_hip_thrust_matches_bridge_variant(self):
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [T("Hip Thrust", "hinge", tested_3rm=235)]
        match, method = resolve_anchor_for_exercise("Bridge (Single & Double Leg)", tests)
        self.assertIsNotNone(match)
        self.assertEqual(method, "alias")

    def test_incline_bench_matches_db_bench(self):
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [T("Incline Bench Press", "press_horizontal", tested_5rm=30)]
        match, method = resolve_anchor_for_exercise("Dumbbell Bench Press", tests)
        self.assertIsNotNone(match)
        self.assertEqual(method, "alias")

    def test_no_match_returns_none(self):
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [T("Hip Thrust", "hinge", tested_3rm=200)]
        match, method = resolve_anchor_for_exercise("Front Squat", tests)
        # Front Squat is in squat group, hip thrust is in hip_extension. No alias.
        # Could still hit category if Hip Thrust's category were squat, but it's hinge.
        self.assertIsNone(match)

    def test_exact_match_wins_over_alias(self):
        """If both an exact and alias match exist, exact wins."""
        from strength_anchor_resolver import resolve_anchor_for_exercise
        tests = [
            T("DB Row", "pull_horizontal", tested_3rm=35),
            T("Single Arm Dumbbell Row", "pull_horizontal", tested_5rm=40),
        ]
        match, method = resolve_anchor_for_exercise("Single Arm Dumbbell Row", tests)
        self.assertIsNotNone(match)
        self.assertEqual(method, "exact")
        self.assertEqual(match.exercise_name, "Single Arm Dumbbell Row")


class TestEightAnchors(unittest.TestCase):
    """Spec test 3 · 8 anchors must all be preserved + reach resolution."""

    def test_all_eight_resolve_or_unused(self):
        from strength_anchor_resolver import resolve_anchor_for_exercise, AnchorUsageTracker
        tests = [
            T("Incline Bench Press", "press_horizontal", tested_5rm=30),
            T("Hip Thrust", "hinge", tested_3rm=235),
            T("3 Point Row", "pull_horizontal", tested_3rm=35),
            T("SL RDL Bench Supported", "hinge", tested_8rm=25),
            T("Trap Bar Deadlift", "hinge", tested_3rm=185),
            T("Pull-ups", "pull_vertical", tested_5rm=0),
            T("Goblet Squat", "squat", tested_8rm=50),
            T("Landmine Press", "press_vertical", tested_5rm=40),
        ]
        # Match each against typical pool picks
        program_picks = [
            "Single Arm Dumbbell Row",
            "Bridge (Single & Double Leg)",
            "Goblet Squat",
            "Bench-Supported Single Leg RDL",
            "Trap Bar Deadlift",
            "Lat Pulldown",
            "Dumbbell Bench Press",
            "Single Arm Landmine Press",
        ]
        tracker = AnchorUsageTracker(tests)
        for ex in program_picks:
            match, method = resolve_anchor_for_exercise(ex, tests)
            if match:
                tracker.record_match(match, ex, method)

        used = tracker.used()
        unused = tracker.unused()
        # All 8 either applied or accounted for
        self.assertEqual(len(used) + len(unused), 8)
        # At minimum, the major categories should match
        used_names = {u["test_name"] for u in used}
        # Hip Thrust must match Bridge variant
        self.assertIn("Hip Thrust", used_names)
        # 3 Point Row must match Single Arm DB Row
        self.assertIn("3 Point Row", used_names)
        # Trap Bar Deadlift must exact-match
        self.assertIn("Trap Bar Deadlift", used_names)
        # Goblet Squat must exact-match
        self.assertIn("Goblet Squat", used_names)


class TestPickerPrefersAnchored(unittest.TestCase):
    """Spec test 4 · if a tested anchor exists for a movement category,
    the picker should USE the anchored exercise name in the program."""

    def test_picker_returns_tested_name_via_alias(self):
        from generator import Generator
        # Build a fake assessment with the 3 Point Row anchor
        class A: pass
        a = A()
        a.strength_marker_tests = [T("3 Point Row", "pull_horizontal", tested_3rm=35)]

        g = Generator.__new__(Generator)  # bypass init
        # Reproduce the call site · candidates = a typical pull_horizontal pool
        candidates = ["Single Arm Dumbbell Row", "Cable Row", "Bench-Supported Row"]
        result = g._match_pattern_to_tested_exercise("pull_horizontal", candidates, a)
        # Should return the tested name, not the canonical pool name
        self.assertEqual(result, "3 Point Row")


class TestPDFIntegration(unittest.TestCase):
    """End-to-end · the strength table actually shows calculated weekly loads
    when an anchor matches via alias."""

    @classmethod
    def setUpClass(cls):
        from app import build_program_pdf
        form = {
            "client_name": "Anchor Test", "age_range": "early 50s", "sex": "F",
            "background": "general", "training_frequency": 3,
            "strength_days": 3, "cardio_days": 0,
            "primary_goal": "Get stronger",
            "fra_priorities": ["Hip IR L+R"],
            "mobility_map": [
                {"joint": "hip", "direction": "IR", "side": "L", "rating": "yellow"},
            ],
            "strength_markers": [], "strength_marker_results": {},
            "strength_marker_tests": [
                {"exercise_name": "3 Point Row", "movement_category": "pull_horizontal",
                 "load_style": "per_hand", "tested_3rm": 35, "form_quality": "clean"},
                {"exercise_name": "Hip Thrust", "movement_category": "hinge",
                 "load_style": "total_load", "tested_3rm": 235, "form_quality": "clean"},
                {"exercise_name": "Incline Bench Press", "movement_category": "press_horizontal",
                 "load_style": "per_hand", "tested_5rm": 30, "form_quality": "clean"},
            ],
            "constraints": [], "concerns": [], "body_comp": {},
            "nutrition_strategy": "maintenance", "activity_factor": 1.4,
            "pdf_mode": "full",
        }
        with contextlib.redirect_stdout(io.StringIO()):
            cls.pdf, _ = build_program_pdf(form)

        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(cls.pdf))
        cls.text = "\n".join((p.extract_text() or "") for p in r.pages)

    def test_pdf_generates(self):
        self.assertGreater(len(self.pdf), 50000)

    def test_used_anchors_section_present(self):
        self.assertIn("USED STRENGTH ANCHORS", self.text.upper())

    def test_three_anchors_appear_as_used(self):
        # All three anchors should be listed as USED in the appendix
        for name in ("3 Point Row", "Hip Thrust", "Incline Bench Press"):
            self.assertIn(name, self.text,
                           f"Anchor {name} should be listed as used")

    def test_calculated_weights_appear_in_strength_table(self):
        """The actual user-facing strength table should show calculated weights,
        not generic RIR. This is the bug from the audit."""
        # Each of these anchors was provided · expect calculated weights
        # to appear somewhere in the strength tables.
        text = self.text.lower()
        # 3 Point Row at 35 lb 3RM → ~25 lb working in W1 (per-hand)
        self.assertIn("@ 25 lb /hand", text,
                       "3 Point Row should show calculated W1 load (~25 lb /hand)")
        # Incline Bench Press at 30 lb 5RM → ~22.5 lb working in W1
        self.assertIn("@ 22.5 lb /hand", text,
                       "Incline Bench Press should show calculated W1 load (~22.5 lb /hand)")
        # Hip Thrust at 235 lb 3RM → ~170 lb working in W1 (total load)
        self.assertIn("@ 170 lb", text,
                       "Hip Thrust should show calculated W1 load (~170 lb)")

    def test_appendix_shows_match_method_and_loads_status(self):
        """The coach appendix should surface match method + loads status."""
        self.assertIn("match: exact", self.text.lower())
        # "loads ✓" or "loads ✗" · pdftotext sometimes drops the unicode mark · accept either
        text_low = self.text.lower()
        self.assertTrue("loads" in text_low and ("loads ✓" in self.text
                                                    or "loads ✗" in self.text
                                                    or "rep scheme only" in text_low),
                         "Appendix should show loads status")

    def test_appendix_walks_actual_program_objects(self):
        """If anchor metadata survives JSON, the appendix shouldn't say 'none matched'
        when 3 anchors are clearly being applied."""
        self.assertNotIn("(none of the anchors matched", self.text.lower())


class TestFullPathEightAnchors(unittest.TestCase):
    """Spec test · 8 anchors entered, all preserved, applied where alias-match
    fits, listed as unused otherwise. No silent fallback."""

    @classmethod
    def setUpClass(cls):
        from app import build_program_pdf
        cls.eight_anchors = [
            {"exercise_name": "Incline Bench Press", "movement_category": "press_horizontal",
             "load_style": "per_hand", "tested_5rm": 30, "form_quality": "clean"},
            {"exercise_name": "Hip Thrust", "movement_category": "hinge",
             "load_style": "total_load", "tested_3rm": 235, "form_quality": "clean"},
            {"exercise_name": "3 Point Row", "movement_category": "pull_horizontal",
             "load_style": "per_hand", "tested_3rm": 35, "form_quality": "clean"},
            {"exercise_name": "SL RDL Bench Supported", "movement_category": "hinge",
             "load_style": "per_hand", "tested_8rm": 25, "form_quality": "clean"},
            {"exercise_name": "Trap Bar Deadlift", "movement_category": "hinge",
             "load_style": "total_load", "tested_3rm": 185, "form_quality": "moderate"},
            {"exercise_name": "Pull-ups", "movement_category": "pull_vertical",
             "load_style": "bodyweight_added", "tested_5rm": 0, "form_quality": "moderate"},
            {"exercise_name": "Goblet Squat", "movement_category": "squat",
             "load_style": "total_load", "tested_8rm": 50, "form_quality": "clean"},
            {"exercise_name": "Landmine Press", "movement_category": "press_vertical",
             "load_style": "per_hand", "tested_5rm": 40, "form_quality": "clean"},
        ]
        form = {
            "client_name": "Eight Anchors", "age_range": "40s", "sex": "M",
            "background": "general", "training_frequency": 3,
            "strength_days": 3, "cardio_days": 0,
            "primary_goal": "Get stronger",
            "fra_priorities": ["Hip flexion L+R"],
            "mobility_map": [
                {"joint": "hip", "direction": "flexion", "side": "L", "rating": "yellow"},
            ],
            "strength_markers": [], "strength_marker_results": {},
            "strength_marker_tests": cls.eight_anchors,
            "constraints": [], "concerns": [], "body_comp": {},
            "nutrition_strategy": "maintenance", "activity_factor": 1.4,
            "pdf_mode": "full",
        }
        with contextlib.redirect_stdout(io.StringIO()):
            cls.pdf, _ = build_program_pdf(form)
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(cls.pdf))
        cls.text = "\n".join((p.extract_text() or "") for p in r.pages)

    def test_all_eight_anchors_listed(self):
        """All 8 anchor names should appear somewhere in the PDF (in the math
        section + USED + UNUSED sections combined)."""
        for anchor in self.eight_anchors:
            self.assertIn(anchor["exercise_name"], self.text,
                           f"Anchor {anchor['exercise_name']} should appear in the PDF")

    def test_appendix_shows_no_truncation(self):
        """The strength math section used to cap at 6 entries · regression test
        that all 8 are visible there."""
        # Each anchor with non-zero tested_NRM should produce a math line
        # like "30 × 5RM" or "235 × 3RM"
        for anchor in self.eight_anchors:
            # Find the rep max line that should appear
            for r in (3, 5, 8):
                key = f"tested_{r}rm"
                if anchor.get(key):
                    expected = f"{int(anchor[key])} × {r}RM"
                    if expected.lower() in self.text.lower():
                        break
            else:
                # No rep-max line found · only fail if the anchor had a non-zero rep max
                has_data = any(anchor.get(f"tested_{r}rm") for r in (3, 5, 8, 10, 12))
                if has_data:
                    self.fail(f"No rep-max line found for {anchor['exercise_name']}")





if __name__ == "__main__":
    unittest.main(verbosity=2)
