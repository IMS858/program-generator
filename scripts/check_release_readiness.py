"""Strict IMS production-release gate; intentionally separate from development CI.

Usage: python scripts/check_release_readiness.py path/to/exercise_crosswalk_audit.json
Never treat fuzzy suggestions or skipped PDF tests as coach approvals.
"""
import json
import sys
from pathlib import Path


def evaluate(rows, legacy_pdf_tests_restored=False):
    pending = [r for r in rows if r.get("match_status") != "exact_normalized"
               or not r.get("safety_approved", False)]
    issues = []
    if pending:
        issues.append(f"{len(pending)} canonical exercises lack exact mapping and/or explicit safety approval")
    if not legacy_pdf_tests_restored:
        issues.append("Post-surgical four-week client/coach/full PDF regression suites are quarantined")
    return issues


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/check_release_readiness.py exercise_crosswalk_audit.json")
    rows = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    issues = evaluate(rows)
    if issues:
        print("RELEASE BLOCKED:")
        for issue in issues:
            print(f" - {issue}")
        raise SystemExit(1)
    print("Machine checks passed; qualified coach sign-off and deployment approval still required.")


if __name__ == "__main__":
    main()
