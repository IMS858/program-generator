"""Safety gate contracts: synthetic examples, never real client data."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator"))
from exercise_safety_gate import assess_candidate, restricted_joints


class TestSafetyGate(unittest.TestCase):
    def test_active_statuses_block_and_cleared_does_not(self):
        rows = [
            {"key": "bad_knee", "status": "active_flare_up"},
            {"key": "si_joint", "status": "post_surgery"},
            {"key": "shoulder", "status": "avoid_loading"},
            {"key": "hip", "status": "cleared"},
        ]
        self.assertEqual(restricted_joints(rows), {"knee", "lumbar", "shoulder"})

    def test_missing_or_unapproved_tags_require_review(self):
        for entry in (None, {"name": "Hip CARs"},
                      {"name": "Hip CARs", "primary_joints": ["hip"],
                       "secondary_joints": []}):
            with self.subTest(entry=entry):
                decision = assess_candidate(entry, {"hip"})
                self.assertFalse(decision.allowed)
                self.assertTrue(decision.requires_coach_review)

    def test_mobility_label_never_clears_active_surgery(self):
        entry = {"name": "Hip CARs", "pattern": "cars",
                 "primary_joints": ["hip"], "secondary_joints": [],
                 "safety_review_approved": True}
        self.assertFalse(assess_candidate(entry, {"hip"}).allowed)

    def test_spine_exclusions_catch_variants(self):
        for name in ("Back Squat", "Front Squat", "Conventional Deadlift",
                     "Trap Bar Deadlift High Handle", "KB Swing"):
            with self.subTest(name=name):
                entry = {"name": name, "primary_joints": ["hip"],
                         "secondary_joints": [], "safety_review_approved": True}
                self.assertFalse(assess_candidate(entry, set(), spine_red_flag=True).allowed)

    def test_only_reviewed_nonoverlapping_exercise_can_pass(self):
        entry = {"name": "Seated Wrist Extension", "primary_joints": ["wrist"],
                 "secondary_joints": [], "safety_review_approved": True}
        self.assertTrue(assess_candidate(entry, {"knee"}).allowed)
        self.assertFalse(assess_candidate(entry, {"wrist"}).allowed)

    def test_generator_holds_rich_active_restrictions_before_strength_selection(self):
        from generator import Generator
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[1]
        g = Generator(libraries_path=str(root / "libraries"))
        for status in ("active_flare_up", "post_surgery", "avoid_loading"):
            with self.subTest(status=status):
                assessment = SimpleNamespace(
                    constraints_rich=[{"key": "knee", "status": status}],
                    concerns=[], constraints=[]
                )
                with self.assertRaisesRegex(ValueError, "coach review required"):
                    g._pick_strength_exercise("squat", [], assessment=assessment)

    def test_unknown_restriction_holds_every_candidate(self):
        entry = {"name": "Seated Wrist Extension", "primary_joints": ["wrist"],
                 "secondary_joints": [], "safety_review_approved": True}
        self.assertFalse(assess_candidate(entry, restricted_joints([
            {"status": "post_surgery"}])).allowed)


if __name__ == "__main__":
    unittest.main()
