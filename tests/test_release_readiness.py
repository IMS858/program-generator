import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_release_readiness import CANONICAL_COUNT, evaluate


def synthetic_approved_rows():
    # Purely fictional release-gate fixtures; not actual exercise approvals.
    return [
        {
            "canonical_id": f"EX-{index:04d}",
            "matched_exercise_id": f"exercise-{index:04d}",
            "mapping_status": "coach_confirmed",
            "safety_approved": True,
            "reviewed_by": "synthetic-staff-test",
            "review_notes": "Fictional test mapping rationale only",
        }
        for index in range(1, CANONICAL_COUNT + 1)
    ]


class TestReleaseReadiness(unittest.TestCase):
    def test_empty_crosswalk_can_never_approve_release(self):
        issues = evaluate([], legacy_pdf_tests_restored=True)
        self.assertTrue(any("Expected 423" in x for x in issues))

    def test_unverified_pdf_suite_blocks_even_if_every_mapping_is_approved(self):
        issues = evaluate(synthetic_approved_rows())
        self.assertEqual(len(issues), 1)
        self.assertIn("PDF regression suite", issues[0])

    def test_exact_name_suggestion_is_not_coach_approval(self):
        rows = synthetic_approved_rows()
        rows[0] = {
            "canonical_id": "EX-0001", "match_status": "exact_normalized",
            "safety_approved": True, "matched_exercise_id": "exercise-0001",
            "reviewed_by": "synthetic", "review_notes": "Fictional rationale",
        }
        issues = evaluate(rows, legacy_pdf_tests_restored=True)
        self.assertTrue(any("1 canonical exercises" in x for x in issues))

    def test_unsigned_mapping_or_absent_safety_approval_blocks(self):
        rows = synthetic_approved_rows()
        rows[5]["reviewed_by"] = ""
        rows[6]["safety_approved"] = False
        issues = evaluate(rows, legacy_pdf_tests_restored=True)
        self.assertTrue(any("2 canonical exercises" in x for x in issues))

    def test_duplicate_or_missing_canonical_rows_block(self):
        rows = synthetic_approved_rows()
        rows[-1]["canonical_id"] = "EX-0001"
        issues = evaluate(rows, legacy_pdf_tests_restored=True)
        self.assertTrue(any("Duplicate canonical IDs" in x for x in issues))
        missing = evaluate(rows[:12], legacy_pdf_tests_restored=True)
        self.assertTrue(any("Expected 423" in x for x in missing))

    def test_synthetic_complete_fixture_only_passes_machine_checks(self):
        self.assertEqual(evaluate(synthetic_approved_rows(), legacy_pdf_tests_restored=True), [])


if __name__ == "__main__":
    unittest.main()
