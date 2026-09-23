"""Read-only inventory of the canonical generator exercise library.

Runs in CI so the 1.17 MB source is audited in place, never copied into a
second manually maintained list. This is an inventory, not coach approval.
"""
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "libraries" / "exercise_database.json"


class TestExerciseLibraryInventory(unittest.TestCase):
    def test_inventory_and_report_schema(self):
        data = json.loads(LIBRARY.read_text(encoding="utf-8"))
        print("\nEXERCISE_AUDIT top_level_type=", type(data).__name__, flush=True)
        if isinstance(data, dict):
            print("EXERCISE_AUDIT top_level_keys=", sorted(data.keys())[:35], flush=True)
            candidates = [(key, value) for key, value in data.items()
                          if isinstance(value, list)]
            for key, value in candidates:
                print("EXERCISE_AUDIT list=", key, "count=", len(value), flush=True)
            rows = max(candidates, key=lambda item: len(item[1]))[1] if candidates else []
        elif isinstance(data, list):
            rows = data
        else:
            self.fail("Exercise database must be a JSON object or array")
        print("EXERCISE_AUDIT primary_row_count=", len(rows), flush=True)
        if rows and isinstance(rows[0], dict):
            print("EXERCISE_AUDIT sample_field_names=", sorted(rows[0].keys()), flush=True)
            for field in ("exercise_id", "id", "name", "canonical_name", "status",
                          "contraindications", "safety_tags", "primary_joints",
                          "equipment", "aliases"):
                present = sum(isinstance(row, dict) and row.get(field) not in
                              (None, "", [], {}) for row in rows)
                print("EXERCISE_AUDIT field=", field, "populated=", present, flush=True)
            for field in ("exercise_id", "id", "name", "canonical_name"):
                values = [str(row[field]).strip().casefold() for row in rows
                          if isinstance(row, dict) and row.get(field)]
                duplicate_count = sum(n - 1 for n in Counter(values).values() if n > 1)
                print("EXERCISE_AUDIT field=", field, "duplicates=", duplicate_count, flush=True)
        self.assertTrue(rows, "Exercise database contains no exercise rows")


if __name__ == "__main__":
    unittest.main()
