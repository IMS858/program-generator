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
            exercises = data.get("exercises")
            if isinstance(exercises, dict):
                rows = list(exercises.values())
                keys = list(exercises)
                print("EXERCISE_AUDIT exercise_map_count=", len(keys), flush=True)
                print("EXERCISE_AUDIT duplicate_map_keys= JSON parsing cannot detect duplicates", flush=True)
            elif isinstance(exercises, list):
                rows = exercises
            else:
                self.fail("Missing exercises array or object in unified database")
        elif isinstance(data, list):
            rows = data
        else:
            self.fail("Exercise database must be a JSON object or array")
        if isinstance(data, dict):
            indexes = data.get("indexes") or {}
            print("EXERCISE_AUDIT index_names=", sorted(indexes) if isinstance(indexes, dict) else type(indexes).__name__, flush=True)
            if isinstance(indexes, dict):
                for key, value in indexes.items():
                    if isinstance(value, (dict, list)):
                        print("EXERCISE_AUDIT index=", key, "entries=", len(value), flush=True)
            meta = data.get("meta") or {}
            if isinstance(meta, dict):
                print("EXERCISE_AUDIT meta_keys=", sorted(meta), flush=True)
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
