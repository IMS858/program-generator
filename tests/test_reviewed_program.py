import unittest
from reviewed_program import validate_reviewed_program, ReviewedProgramError


def plan():
    return {"client_name": "Synthetic Client", "assessment": {}, "weeks": [
        {"sessions": [{"day_type": "strength_lb", "blocks": [
            {"name": "Strength A", "exercises": [{"name": "Goblet squat", "dose": "3x8"}]}
        ]}]} for _ in range(4)
    ]}


class ReviewedProgramTests(unittest.TestCase):
    def test_valid_four_week_program(self):
        self.assertIsNotNone(validate_reviewed_program(plan()))

    def test_different_week_structure_is_rejected(self):
        p = plan()
        p["weeks"][2]["sessions"][0]["day_type"] = "cardio"
        with self.assertRaises(ReviewedProgramError):
            validate_reviewed_program(p)

    def test_different_exercise_in_later_week_is_rejected(self):
        p = plan()
        p["weeks"][2]["sessions"][0]["blocks"][0]["exercises"][0]["name"] = "Split squat"
        with self.assertRaisesRegex(ReviewedProgramError, "exercise"):
            validate_reviewed_program(p)

    def test_different_block_name_in_later_week_is_rejected(self):
        p = plan()
        p["weeks"][1]["sessions"][0]["blocks"][0]["name"] = "Strength B"
        with self.assertRaisesRegex(ReviewedProgramError, "block"):
            validate_reviewed_program(p)

    def test_week_specific_dose_changes_are_allowed(self):
        p = plan()
        p["weeks"][2]["sessions"][0]["blocks"][0]["exercises"][0]["dose"] = "4x6"
        self.assertIsNotNone(validate_reviewed_program(p))

    def test_unbounded_exercise_note_is_rejected(self):
        p = plan()
        p["weeks"][0]["sessions"][0]["blocks"][0]["exercises"][0]["progression_note"] = "x" * 2001
        with self.assertRaises(ReviewedProgramError):
            validate_reviewed_program(p)

    def test_missing_exercise_name_is_rejected(self):
        p = plan()
        p["weeks"][0]["sessions"][0]["blocks"][0]["exercises"][0]["name"] = ""
        with self.assertRaises(ReviewedProgramError):
            validate_reviewed_program(p)


if __name__ == "__main__":
    unittest.main()
