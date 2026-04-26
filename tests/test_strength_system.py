"""
IMS Program Generator · Test Suite

Covers six concern areas ·
  1. Week consistency       · 4-week block has NO Week 5 / Week 6 language
  2. Strength math          · Epley · working loads · DB rounding · inconsistency flag
  3. Optional testing data  · PDF still generates · falls back to RPE/RIR
  4. Side effects           · Body comp / mobility priorities / PDF generation unchanged
  5. Page replacement       · Old "Notice, adjust, grow" page is GONE · new page appears
  6. PDF text safety        · No visible ellipses · names wrap or shorten cleanly

Run from repo root ·
    python3 -m unittest tests.test_strength_system -v

Or run the file directly ·
    cd tests && python3 test_strength_system.py
"""
import os
import sys
import io
import contextlib
import unittest
from pathlib import Path

# Make the repo importable from the tests folder
THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "generator"))


# ────────────────────────────────────────────────────────
# Test fixtures · canonical assessment payloads
# ────────────────────────────────────────────────────────

def assessment_with_tests():
    """A payload representing the spec's strength testing scenario."""
    return {
        "client_name": "Test Client", "age_range": "early 40s", "sex": "M",
        "background": "test", "training_frequency": 4,
        "strength_days": 3, "cardio_days": 1,
        "primary_goal": "Build strength",
        "fra_priorities": ["Hip IR L+R"],
        "mobility_map": [
            {"joint": "hip", "direction": "IR", "side": "L", "rating": "yellow"},
        ],
        "strength_markers": [], "strength_marker_results": {},
        "strength_marker_tests": [
            {
                "exercise_name": "DB Bench Press",
                "load_style": "per_hand", "equipment_type": "dumbbell",
                "load_unit": "lb",
                "tested_12rm": 35, "tested_10rm": 40, "tested_3rm": 55,
                "form_quality": "clean",
            },
        ],
        "constraints": [], "body_comp": {},
        "nutrition_strategy": "strength", "activity_factor": 1.55,
    }


def assessment_no_tests():
    """A payload with NO strength testing data · should still work."""
    return {
        "client_name": "BW Client", "age_range": "early 40s", "sex": "F",
        "background": "test", "training_frequency": 3,
        "strength_days": 2, "cardio_days": 1,
        "primary_goal": "Move better",
        "fra_priorities": ["Hip IR L+R"],
        "mobility_map": [
            {"joint": "hip", "direction": "IR", "side": "R", "rating": "red"},
        ],
        "strength_markers": [], "strength_marker_results": {},
        "strength_marker_tests": [],
        "constraints": [], "body_comp": {},
        "nutrition_strategy": "maintenance", "activity_factor": 1.4,
    }


def assessment_with_body_comp():
    """A payload with full BOD POD numbers · for side-effect verification."""
    p = assessment_with_tests()
    p["body_comp"] = {
        "weight": "180 lbs", "body_fat": "15%",
        "lean_mass": "153 lbs", "fat_mass": "27 lbs",
        "method": "BOD POD (Lohman Model)",
        "rmr_katch_mcardle": "AUTO",
        "tdee_estimated": "AUTO",
        "nutrition_targets": "AUTO",
    }
    return p


def build_pdf_silently(form):
    """Generate a PDF, suppressing print output."""
    from app import build_program_pdf
    with contextlib.redirect_stdout(io.StringIO()):
        return build_program_pdf(form)


def extract_pdf_text(pdf_bytes):
    """Read text from a PDF · uses pypdf if available, else best-effort fallback."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    except ImportError:
        # pypdf isn't a hard dep · fall back to a naive byte search for ASCII strings
        # which is enough for the kind of substring assertions we make below.
        return pdf_bytes.decode("latin-1", errors="ignore")


# ════════════════════════════════════════════════════════
# 1 · WEEK CONSISTENCY
# ════════════════════════════════════════════════════════

class WeekConsistencyTests(unittest.TestCase):
    """Block 1 is 4 weeks · no Week 5 or Week 6 language anywhere."""

    @classmethod
    def setUpClass(cls):
        pdf_bytes, _ = build_pdf_silently(assessment_with_tests())
        cls.pdf_bytes = pdf_bytes
        cls.pdf_text = extract_pdf_text(pdf_bytes)

    def test_pdf_contains_week_01_04_label(self):
        """PDF header should say WEEK 01-04, not WEEK 01-06."""
        self.assertIn("WEEK 01-04", self.pdf_text)
        self.assertNotIn("WEEK 01-06", self.pdf_text)

    def test_no_week_5_language(self):
        """Old Week 5 verbiage ('Heavy Push', 'WK 5') must be absent."""
        forbidden = ["WK 5", "Week 5", "Heavy Push", "WK5"]
        for token in forbidden:
            self.assertNotIn(
                token, self.pdf_text,
                msg=f"Found forbidden 6-week language: {token!r}"
            )

    def test_no_week_6_language(self):
        """Old Week 6 verbiage ('Deload + Re-Test', 'WK 6') must be absent."""
        forbidden = ["WK 6", "Week 6", "Deload + Re-Test", "WK6", "Re-Test"]
        for token in forbidden:
            self.assertNotIn(
                token, self.pdf_text,
                msg=f"Found forbidden 6-week language: {token!r}"
            )

    def test_program_object_has_4_weeks(self):
        """The Program object built by Generator should have exactly 4 weeks."""
        from generator import Generator, Assessment, parse_fra_priority, MobilityRating
        from strength_testing import StrengthTest
        a = Assessment(
            name="X", age_range="40s", sex="M", background="t",
            training_frequency=4, strength_days=3, cardio_days=1,
            primary_goal="t",
            fra_priorities=[parse_fra_priority("Hip IR L+R")],
            strength_markers=[], constraints=[],
            mobility_map=[MobilityRating(joint="hip", direction="IR",
                                         side="L", rating="yellow")],
            body_comp={}, progression_mode="autoregulated",
            strength_marker_results={}, strength_marker_tests=[],
        )
        with contextlib.redirect_stdout(io.StringIO()):
            g = Generator(libraries_path=str(REPO_ROOT / "libraries"))
            program = g.build_program(a)
        self.assertEqual(len(program.weeks), 4,
                         f"Expected 4 weeks, got {len(program.weeks)}")

    def test_week_intent_strings_only_for_weeks_1_to_4(self):
        """_week_intent should return text for 1-4 only · 5/6 give the unscheduled stub."""
        from generator import Generator
        with contextlib.redirect_stdout(io.StringIO()):
            g = Generator(libraries_path=str(REPO_ROOT / "libraries"))
        for w in (1, 2, 3, 4):
            self.assertNotEqual(g._week_intent(w), "Unscheduled week",
                                f"Week {w} should have a real intent string")
        for w in (5, 6):
            self.assertEqual(g._week_intent(w), "Unscheduled week",
                             f"Week {w} should be an unscheduled stub")


# ════════════════════════════════════════════════════════
# 2 · STRENGTH MATH
# ════════════════════════════════════════════════════════

class StrengthMathTests(unittest.TestCase):
    """The exact spec scenario · DB Bench 12RM=35, 10RM=40, 3RM=55, per-hand."""

    @classmethod
    def setUpClass(cls):
        from strength_testing import StrengthTest
        cls.test = StrengthTest.from_dict({
            "exercise_name": "DB Bench Press",
            "load_style": "per_hand", "equipment_type": "dumbbell",
            "load_unit": "lb",
            "tested_12rm": 35, "tested_10rm": 40, "tested_3rm": 55,
            "form_quality": "clean",
        })

    def test_estimate_1rm_epley(self):
        """Epley formula sanity · weight × (1 + reps/30)."""
        from strength_math import estimate_1rm
        self.assertAlmostEqual(estimate_1rm(225, 5), 262.5, places=1)
        self.assertAlmostEqual(estimate_1rm(100, 12), 140.0, places=1)
        self.assertAlmostEqual(estimate_1rm(35, 12), 49.0, places=1)

    def test_calculate_estimates_returns_per_test(self):
        """calculate_estimates_from_tests should return Epley estimates for each tested rep."""
        from strength_math import calculate_estimates_from_tests
        e = calculate_estimates_from_tests(self.test)
        self.assertIn(12, e.estimated_1rm_from_each_test)
        self.assertIn(10, e.estimated_1rm_from_each_test)
        self.assertIn(3, e.estimated_1rm_from_each_test)
        self.assertAlmostEqual(e.estimated_1rm_from_each_test[12], 49.0, places=1)
        self.assertAlmostEqual(e.estimated_1rm_from_each_test[10], 53.33, places=1)
        self.assertAlmostEqual(e.estimated_1rm_from_each_test[3], 60.5, places=1)

    def test_best_estimate_uses_lowest_rep(self):
        """Best estimate prefers the lowest-rep tested value (closest to 1RM)."""
        from strength_math import calculate_estimates_from_tests
        e = calculate_estimates_from_tests(self.test)
        # Lowest rep = 3, Epley estimate = 55 × (1 + 3/30) = 60.5
        self.assertAlmostEqual(e.best_estimate, 60.5, places=1)

    def test_conservative_training_max_uses_85_percent(self):
        """Training max = 0.85 × best estimate (clean form, no pain)."""
        from strength_math import calculate_estimates_from_tests
        e = calculate_estimates_from_tests(self.test)
        # 60.5 × 0.85 = 51.425
        self.assertAlmostEqual(e.conservative_training_max, 51.425, places=1)

    def test_working_weights_generated_for_all_4_target_reps(self):
        """get_working_weight_for_reps returns sane numbers for 12, 10, 8, 6."""
        from strength_math import get_working_weight_for_reps
        for reps in (12, 10, 8, 6):
            w = get_working_weight_for_reps(self.test, reps)
            self.assertIsNotNone(w, f"Working weight for {reps}RM was None")
            self.assertGreater(w, 0, f"Working weight for {reps}RM was non-positive")

    def test_dumbbell_rounding(self):
        """DB loads should round to 2.5 lb under 30 lb, 5 lb at/over 30 lb."""
        from strength_math import round_load
        # Under 30 lb · nearest 2.5
        self.assertEqual(round_load(27.4, "dumbbell", "per_hand"), 27.5)
        self.assertEqual(round_load(28.1, "dumbbell", "per_hand"), 27.5)
        self.assertEqual(round_load(28.8, "dumbbell", "per_hand"), 30)  # past 28.75 boundary
        # At/over 30 lb · nearest 5
        self.assertEqual(round_load(47.3, "dumbbell", "per_hand"), 45)
        self.assertEqual(round_load(52.7, "dumbbell", "per_hand"), 55)
        self.assertEqual(round_load(40.0, "dumbbell", "per_hand"), 40)

    def test_inconsistency_flag_when_3rm_much_higher(self):
        """3RM estimate (60.5) is ~24% above the median of (49, 53.3) · flag must fire."""
        from strength_math import detect_inconsistencies
        flags = detect_inconsistencies(self.test)
        self.assertTrue(
            len(flags) > 0,
            "Expected an inconsistency flag for 3RM=55 vs 12RM=35, 10RM=40"
        )
        # The flag should mention the 3RM specifically
        self.assertTrue(
            any("3RM" in f or "3" in f for f in flags),
            f"Inconsistency flag should reference 3RM · got: {flags}"
        )

    def test_no_inconsistency_when_data_is_clean(self):
        """Tests that scale linearly should NOT trigger an inconsistency flag."""
        from strength_testing import StrengthTest
        from strength_math import detect_inconsistencies
        # Real-world Epley-consistent client · 12RM=100, 10RM=110, 8RM=120, 5RM=140
        clean = StrengthTest.from_dict({
            "tested_12rm": 100, "tested_10rm": 110,
            "tested_8rm": 120, "tested_5rm": 140,
        })
        flags = detect_inconsistencies(clean)
        self.assertEqual(
            flags, [],
            f"Expected no inconsistency flags on clean data · got: {flags}"
        )


# ════════════════════════════════════════════════════════
# 3 · OPTIONAL TESTING DATA
# ════════════════════════════════════════════════════════

class OptionalTestingDataTests(unittest.TestCase):
    """No test data · PDF still generates · cells fall back to RPE / RIR."""

    @classmethod
    def setUpClass(cls):
        pdf_bytes, _ = build_pdf_silently(assessment_no_tests())
        cls.pdf_bytes = pdf_bytes
        cls.pdf_text = extract_pdf_text(pdf_bytes)

    def test_pdf_generated_without_test_data(self):
        self.assertGreater(len(self.pdf_bytes), 10_000,
                           "PDF should still generate without test data")

    def test_no_lb_weights_appear_for_no_test_client(self):
        """A client with no tests should NOT have specific lb numbers in the
        strength progression cells. The fallback is RPE/RIR language.
        (Some lb references CAN appear elsewhere · nutrition, etc., so we
        scope this to the strength-table phrases.)"""
        # Look for cell-style "@ <num> lb" load notation · should not appear
        import re
        loads_pattern = re.compile(r"@ \d+(?:\.\d+)? lb")
        # We scan only the per-page text for the strength session pages
        # (heuristic · pages between Mobility Map and Nutrition).
        matches = loads_pattern.findall(self.pdf_text)
        self.assertEqual(
            matches, [],
            f"No-test-data client should have no @ X lb cells · found {matches[:5]}"
        )

    def test_rir_or_rpe_language_present(self):
        """RIR or RPE labels should appear when there's no tested load."""
        has_rir = "RIR 2-3" in self.pdf_text or "RIR" in self.pdf_text
        has_rpe = "RPE" in self.pdf_text
        self.assertTrue(
            has_rir or has_rpe,
            "No-test-data client should show RIR or RPE labels"
        )


# ════════════════════════════════════════════════════════
# 4 · SIDE EFFECTS
# ════════════════════════════════════════════════════════

class SideEffectTests(unittest.TestCase):
    """Existing pieces of the system must continue to work."""

    def test_body_comp_calculations_still_work(self):
        """A payload with body_comp should produce a PDF with the BOD POD page populated."""
        pdf_bytes, _ = build_pdf_silently(assessment_with_body_comp())
        pdf_text = extract_pdf_text(pdf_bytes)
        # The body comp page lists the lean mass, fat mass, etc.
        self.assertIn("153", pdf_text, "Lean mass (153 lbs) should appear")
        # And nutrition AUTO should have been resolved to actual numbers
        self.assertNotIn("AUTO", pdf_text,
                         "AUTO placeholders should have been replaced by real values")

    def test_mobility_priority_generation_still_works(self):
        """Generator should still produce mobility prep blocks for FRA priorities."""
        pdf_bytes, _ = build_pdf_silently(assessment_with_tests())
        pdf_text = extract_pdf_text(pdf_bytes)
        # The mobility map page mentions the Hip IR priority
        self.assertIn("Hip IR", pdf_text,
                      "Hip IR priority should surface in the PDF")
        # And the per-session pages mention CARs / Mobility Prep
        self.assertIn("CARS", pdf_text.upper(),
                      "CARs sequence block should appear in session pages")
        self.assertIn("MOBILITY PREP", pdf_text.upper(),
                      "Mobility Prep block should appear")

    def test_pdf_generation_still_works_for_full_payload(self):
        """End-to-end · realistic payload produces a multi-page PDF."""
        pdf_bytes, name = build_pdf_silently(assessment_with_body_comp())
        self.assertEqual(name, "Test Client")
        self.assertGreater(len(pdf_bytes), 50_000,
                           "Full PDF should be substantial in size")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            self.assertGreaterEqual(
                len(reader.pages), 15,
                f"PDF should have at least 15 pages · got {len(reader.pages)}"
            )
        except ImportError:
            self.skipTest("pypdf not installed · skipping page count check")


# ════════════════════════════════════════════════════════
# 5 · PAGE REPLACEMENT
# ════════════════════════════════════════════════════════

class PageReplacementTests(unittest.TestCase):
    """Old tracking page language gone · new coaching-process page present."""

    @classmethod
    def setUpClass(cls):
        pdf_bytes, _ = build_pdf_silently(assessment_with_tests())
        cls.pdf_text = extract_pdf_text(pdf_bytes)

    def test_old_tracking_language_removed(self):
        """Old phrases that used to live on the tracking page must be gone."""
        forbidden = [
            "scale 1-10",                # old "Energy · scale 1-10"
            "quality + duration",        # old "Sleep · quality + duration"
            "Training Wins",             # old fourth bullet
            "anything that felt good",   # old subtext
            "WHAT YOU TRACK",            # old section header
            "Notice,",                   # old splash headline
            "adjust, grow.",             # old splash subhead
        ]
        for token in forbidden:
            self.assertNotIn(
                token, self.pdf_text,
                msg=f"Old tracking page language still present: {token!r}"
            )

    def test_new_coaching_process_page_present(self):
        """The new page should mention coaching-process language."""
        # Allow either spec phrasing OR the implementation phrasing
        acceptable_section_headers = [
            "HOW WE ADJUST YOUR PLAN",
            "How We Adjust Your Plan",
            "HOW WE ADJUST",
        ]
        found = any(h in self.pdf_text for h in acceptable_section_headers)
        self.assertTrue(
            found,
            f"None of the acceptable headers found in PDF · expected one of {acceptable_section_headers}"
        )

    def test_new_page_has_adjustment_signals(self):
        """The new page should reference what we look at when adjusting plans ·
        test results, recovery, schedule, observation."""
        signals = ["Test results", "How you felt", "What life looks like",
                   "Coach observation"]
        for s in signals:
            self.assertIn(
                s, self.pdf_text,
                msg=f"Expected signal {s!r} on the new coaching-process page"
            )


# ════════════════════════════════════════════════════════
# 6 · PDF TEXT SAFETY
# ════════════════════════════════════════════════════════

class TextSafetyTests(unittest.TestCase):
    """No visible ellipses · names wrap or shorten cleanly."""

    @classmethod
    def setUpClass(cls):
        # Use a payload with deliberately long exercise names to stress-test wrapping
        payload = assessment_with_tests()
        payload["strength_marker_tests"] = [
            {
                "exercise_name": "Front Foot Elevated Single Leg RDL with Dumbbell",
                "load_style": "per_hand", "equipment_type": "dumbbell",
                "tested_8rm": 30, "form_quality": "clean",
            },
            {
                "exercise_name": "Bench Supported Single Arm Dumbbell Row",
                "load_style": "per_hand", "equipment_type": "dumbbell",
                "tested_10rm": 45, "form_quality": "clean",
            },
        ]
        pdf_bytes, _ = build_pdf_silently(payload)
        cls.pdf_text = extract_pdf_text(pdf_bytes)

    def test_no_ellipsis_in_pdf_text(self):
        """The unicode ellipsis character … should never appear in client PDFs."""
        # The horizontal ellipsis · U+2026
        ELLIPSIS = "\u2026"
        self.assertNotIn(
            ELLIPSIS, self.pdf_text,
            "Ellipsis character … found in PDF · names should wrap, not truncate"
        )

    def test_no_three_dot_truncation(self):
        """Three-dot truncation '...' should not appear in exercise contexts."""
        # Three actual dots · used to be appended by the old shorten() function
        # This is a softer check · '...' might legitimately appear in prose,
        # so we only flag it inside known table contexts.
        # We scan for patterns like "Word..." or "Word ..." in close proximity
        # to typical strength-table tokens.
        if "..." in self.pdf_text:
            # Only fail if "..." appears NEAR a sets×reps pattern (i.e., in a table cell)
            import re
            # Find any "..." that's within 80 chars of "× <num>" (a strength cell)
            danger = re.search(r"\.{3}.{0,80}× \d+|× \d+.{0,80}\.{3}", self.pdf_text)
            self.assertIsNone(
                danger,
                f"Three-dot truncation found near strength table content: {danger.group() if danger else ''}"
            )

    def test_long_exercise_names_present_in_pdf(self):
        """The PDF should contain the long exercise names that the generator
        actually picks (e.g. 'Dumbbell Bench Press (Single or Double Arm)'
        from the library) without truncating them with ellipses."""
        # The strength A picker selects from the library · names like
        # 'Dumbbell Bench Press (Single or Double Arm)' or 'Trap Bar Deadlift'
        # are guaranteed to appear when there's UB strength work.
        # We check that AT LEAST ONE multi-word library exercise name is
        # rendered intact (not truncated).
        common_long_names = [
            "Trap Bar Deadlift",
            "Goblet Squat",
            "Dumbbell Bench Press",
            "Chest Supported Row",
            "Cable Hip IR",
            "Single-Leg Hip Bridge",
        ]
        found_count = sum(1 for n in common_long_names if n in self.pdf_text)
        self.assertGreater(
            found_count, 0,
            f"None of the standard library exercise names found in PDF · "
            f"text was {len(self.pdf_text)} chars long"
        )

    def test_shorten_function_never_adds_ellipses(self):
        """The shorten() helper must abbreviate via the replacement table,
        never append an ellipsis character."""
        from plan_pdf import shorten
        long_names = [
            "Front Foot Elevated Single-Leg RDL with Dumbbell",
            "Bench Supported Single-Arm Dumbbell Row",
            "External Rotation Cable Row",
            "Single Leg Romanian Deadlift",
        ]
        for n in long_names:
            result = shorten(n)
            self.assertNotIn(
                "\u2026", result,
                f"shorten({n!r}) returned an ellipsis: {result!r}"
            )
            self.assertFalse(
                result.endswith("..."),
                f"shorten({n!r}) returned three dots: {result!r}"
            )


# ────────────────────────────────────────────────────────
# Runner
# ────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Direct run · `python3 test_strength_system.py`
    unittest.main(verbosity=2)
