"""Fail-closed IMS exercise release gate, independent of development CI.

Input must be a **coach-confirmed** canonical mapping export, not the
read-only reconciliation suggestions file. No public/client release
without separately verified regression suites and owner clinical sign-off.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

CANONICAL_COUNT = 423


def evaluate(rows, legacy_pdf_tests_restored=False):
    issues = []
    if not isinstance(rows, list):
        return ["Canonical mapping export must be a list of review records"]
    if len(rows) != CANONICAL_COUNT:
        issues.append(f"Expected {CANONICAL_COUNT} canonical review records; found {len(rows)}")
    ids = [r.get("canonical_id") for r in rows if isinstance(r, dict)]
    missing = sum(not cid for cid in ids)
    duplicates = [key for key, count in Counter(ids).items() if key and count > 1]
    if missing or len(ids) != len(rows):
        issues.append("Canonical IDs are missing or some review rows are malformed")
    if duplicates:
        issues.append(f"Duplicate canonical IDs: {len(duplicates)}")
    # Suggestions and exact name matches do not establish exercise identity.
    pending = [r for r in rows if not isinstance(r, dict) or
        r.get("mapping_status") != "coach_confirmed" or
        not r.get("matched_exercise_id") or
        not r.get("safety_approved", False) or
        not r.get("reviewed_by") or
        len(str(r.get("review_notes") or "").strip()) < 15]
    if pending:
        issues.append(f"{len(pending)} canonical exercises lack signed coach-confirmed mapping and safety approval")
    if not legacy_pdf_tests_restored:
        issues.append("Required post-surgical client/coach/full PDF regression suite not verified")
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crosswalk", type=Path, help="Coach-confirmed 423-row review export")
    parser.add_argument("--pdf-suite-verified", action="store_true",
                        help="Required PDF suite was run and passed in the release candidate CI")
    args = parser.parse_args()
    try:
        rows = json.loads(args.crosswalk.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise SystemExit(f"RELEASE BLOCKED: unreadable crosswalk export ({type(exc).__name__})")
    issues = evaluate(rows, legacy_pdf_tests_restored=args.pdf_suite_verified)
    if issues:
        print("RELEASE BLOCKED:")
        for issue in issues:
            print(f" - {issue}")
        raise SystemExit(1)
    print("Machine release checks passed; qualified IMS coach and owner sign-off still required.")


if __name__ == "__main__":
    main()
