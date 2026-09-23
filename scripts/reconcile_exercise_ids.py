"""Reconcile an IMS canonical name/ID CSV against the 604-entry generator library.

Usage: python scripts/reconcile_exercise_ids.py path/to/canonical.csv --output audit.json
Read-only; does not assign IDs, merge aliases, or approve safety tags.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


def normalize(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold()).strip()


def reconcile(rows, database):
    index = defaultdict(list)
    for key, exercise in database["exercises"].items():
        name = exercise.get("name", "")
        if name:
            index[normalize(name)].append({"generator_key": key,
                                            "generator_id": exercise.get("id"),
                                            "generator_name": name})
    output = []
    for row in rows:
        canonical = row.get("canonical_name") or row.get("name") or ""
        candidates = index.get(normalize(canonical), [])
        output.append({
            "canonical_id": row.get("exercise_id") or row.get("id") or "",
            "canonical_name": canonical,
            "match_status": "exact_normalized" if len(candidates) == 1 else
                            "ambiguous" if candidates else "unmatched",
            "candidates": candidates,
            "safety_approved": False,
        })
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical_csv", type=Path)
    parser.add_argument("--database", type=Path,
                        default=Path(__file__).resolve().parents[1] /
                        "libraries/exercise_database.json")
    parser.add_argument("--output", type=Path, default=Path("exercise_crosswalk_audit.json"))
    args = parser.parse_args()
    with args.canonical_csv.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    database = json.loads(args.database.read_text(encoding="utf-8"))
    result = reconcile(rows, database)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    summary = {key: sum(row["match_status"] == key for row in result)
               for key in ("exact_normalized", "ambiguous", "unmatched")}
    print(json.dumps({"canonical_rows": len(rows), **summary,
                      "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
