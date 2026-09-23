import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_release_readiness import evaluate


class TestReleaseReadiness(unittest.TestCase):
    def test_exact_mapping_without_safety_approval_blocks_release(self):
        rows = [{"match_status": "exact_normalized", "safety_approved": False}]
        issues = evaluate(rows, legacy_pdf_tests_restored=True)
        self.assertEqual(len(issues), 1)
        self.assertIn("1 canonical exercises", issues[0])

    def test_unmatched_suggestion_cannot_be_auto_approved(self):
        rows = [{"match_status": "unmatched", "safety_approved": True,
                 "suggestions_for_coach_review": [{"generator_name": "Similar"}]}]
        self.assertTrue(evaluate(rows, legacy_pdf_tests_restored=True))

    def test_quarantined_pdf_tests_always_block_release(self):
        rows = [{"match_status": "exact_normalized", "safety_approved": True}]
        self.assertEqual(len(evaluate(rows)), 1)
        self.assertEqual(evaluate(rows, legacy_pdf_tests_restored=True), [])


if __name__ == "__main__":
    unittest.main()
