import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reconcile_exercise_ids import reconcile


class TestCrosswalk(unittest.TestCase):
    def test_matches_names_without_approving_or_inventing_ids(self):
        db = {"exercises": {
            "DB-1": {"id": "DB-1", "name": "Ankle Dorsiflexion Lift-Off"},
            "DB-2": {"id": "DB-2", "name": "Hip CARs"},
        }}
        rows = [
            {"exercise_id": "EX-0001", "canonical_name": "ankle dorsiflexion lift off"},
            {"exercise_id": "EX-0002", "canonical_name": "Missing Movement"},
        ]
        result = reconcile(rows, db)
        self.assertEqual([r["match_status"] for r in result],
                         ["exact_normalized", "unmatched"])
        self.assertEqual(result[0]["canonical_id"], "EX-0001")
        self.assertEqual(result[0]["candidates"][0]["generator_id"], "DB-1")
        self.assertFalse(result[0]["safety_approved"])
        self.assertEqual(result[1]["candidates"], [])

    def test_duplicate_normalized_names_are_ambiguous(self):
        db = {"exercises": {
            "a": {"id": "a", "name": "Hip CARs"},
            "b": {"id": "b", "name": "Hip-CARs"},
        }}
        result = reconcile([{"exercise_id": "EX-1", "name": "Hip CARs"}], db)
        self.assertEqual(result[0]["match_status"], "ambiguous")
        self.assertEqual(len(result[0]["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
