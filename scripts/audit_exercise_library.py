"""Deterministic structural audit of the IMS exercise library.

This audits catalog integrity and identifies missing contraindication DATA. It does
not certify exercises medically safe or replace IMS coach sign-off. The separate
review ledger deliberately starts every executable entry as unreviewed.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "libraries" / "exercise_database.json"
REVIEW_COLUMNS = (
    "review_priority", "legacy_id", "name", "library", "modality",
    "primary_joint", "secondary_joints", "pattern",
    "contraindications", "legacy_contraindicated_if",
    "canonical_exercise_id", "review_status", "reviewer", "reviewed_at",
    "coach_review_notes",
)
REFERENCE_ONLY = frozenset({"playbook"})


class CatalogIntegrityError(ValueError):
    pass


def normalized_name(value):
    """Matching aid for COLLISION DETECTION, never automatic exercise aliasing."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", "", text)


def audit_catalog(catalog):
    if not isinstance(catalog, dict) or not isinstance(catalog.get("exercises"), dict):
        raise CatalogIntegrityError("expected catalog.exercises as an ID-keyed object")
    records = catalog["exercises"]
    errors, warnings, seen_names = [], [], {}
    by_library = Counter()
    by_modality = Counter()
    missing_tags = []
    for key, entry in records.items():
        if not isinstance(entry, dict):
            errors.append(f"{key}: exercise entry is not an object")
            continue
        if entry.get("id") != key or not re.fullmatch(r"[a-z0-9_-]+", key):
            errors.append(f"{key}: invalid or mismatched ID")
        name = entry.get("name")
        norm = normalized_name(name)
        if not norm:
            errors.append(f"{key}: missing or invalid name")
        elif norm in seen_names:
            errors.append(f"{key}: normalized name collides with {seen_names[norm]}")
        else:
            seen_names[norm] = key
        library = entry.get("library")
        modality = entry.get("modality")
        if not isinstance(library, str) or not library:
            errors.append(f"{key}: missing library")
        if not isinstance(modality, str) or not modality:
            errors.append(f"{key}: missing modality")
        by_library[library] += 1
        by_modality[modality] += 1
        for field in ("contraindications", "contraindicated_if"):
            value = entry.get(field, [])
            if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
                errors.append(f"{key}: {field} must be a list of nonblank strings")
        if library not in REFERENCE_ONLY and not entry.get("contraindications"):
            missing_tags.append(key)
        legacy = entry.get("contraindicated_if", [])
        if legacy and set(legacy) != set(entry.get("contraindications", [])):
            warnings.append(f"{key}: legacy and unified exclusion tags differ")
    indexes = catalog.get("indexes")
    if not isinstance(indexes, dict):
        errors.append("indexes must be an object")
    else:
        for index_name, field in (("by_library", "library"), ("by_modality", "modality")):
            index = indexes.get(index_name)
            if not isinstance(index, dict):
                errors.append(f"{index_name}: missing index")
                continue
            found = []
            for bucket, ids in index.items():
                if not isinstance(ids, list):
                    errors.append(f"{index_name}/{bucket}: not an array")
                    continue
                for exercise_id in ids:
                    found.append(exercise_id)
                    if exercise_id not in records:
                        errors.append(f"{index_name}: dangling ID {exercise_id}")
                    elif records[exercise_id].get(field) != bucket:
                        errors.append(f"{index_name}: {exercise_id} in wrong bucket {bucket}")
            if len(found) != len(set(found)) or set(found) != set(records):
                errors.append(f"{index_name}: duplicate or unindexed records")
        # Other indexes may validly omit exercises, while by_input is many-to-many.
        for index_name, buckets in indexes.items():
            if not isinstance(buckets, dict):
                errors.append(f"{index_name}: invalid buckets")
                continue
            for bucket, ids in buckets.items():
                if not isinstance(ids, list):
                    errors.append(f"{index_name}/{bucket}: not an array")
                else:
                    for exercise_id in ids:
                        if exercise_id not in records:
                            errors.append(f"{index_name}/{bucket}: dangling ID {exercise_id}")
    meta = catalog.get("meta") or {}
    if meta.get("total_exercises") != len(records):
        errors.append("meta.total_exercises differs from the record count")
    library_count_drift = {}
    for source in meta.get("libraries_merged", []):
        expected = source.get("count")
        actual = by_library[source.get("library")]
        if actual != expected:
            library_count_drift[source.get("library")] = {"declared": expected, "actual": actual}
    if library_count_drift:
        warnings.append("library count metadata is stale; update after source review")
    return {
        "total_records": len(records),
        "executable_records": sum(n for library, n in by_library.items() if library not in REFERENCE_ONLY),
        "reference_only_records": sum(by_library[k] for k in REFERENCE_ONLY),
        "missing_contraindication_ids": sorted(missing_tags),
        "missing_contraindication_count": len(missing_tags),
        "by_library": dict(sorted(by_library.items())),
        "library_count_drift": library_count_drift,
        "errors": errors,
        "warnings": warnings,
    }


def review_rows(catalog):
    records = catalog["exercises"]
    rows = []
    for exercise_id, entry in records.items():
        if entry["library"] in REFERENCE_ONLY:
            continue
        missing = not entry.get("contraindications")
        rows.append({
            "review_priority": "P0_missing_tags" if missing else "P1_verify_existing_tags",
            "legacy_id": exercise_id,
            "name": entry["name"],
            "library": entry["library"],
            "modality": entry.get("modality", ""),
            "primary_joint": entry.get("joint") or "",
            "secondary_joints": " | ".join(entry.get("secondary_joints") or []),
            "pattern": entry.get("pattern") or "",
            "contraindications": " | ".join(entry.get("contraindications") or []),
            "legacy_contraindicated_if": " | ".join(entry.get("contraindicated_if") or []),
            "canonical_exercise_id": "",  # Requires the separate 423-ID workbook.
            "review_status": "unreviewed",  # Metadata from prior AI drafts is NOT approval.
            "reviewer": "",
            "reviewed_at": "",
            "coach_review_notes": "",
        })
    return sorted(rows, key=lambda r: (r["review_priority"], r["library"], r["name"].casefold(), r["legacy_id"]))


def write_review_queue(path, catalog):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows(catalog))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--queue", type=Path, help="write an all-exercise review CSV (no clinical approval inferred)")
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    report = audit_catalog(catalog)
    if args.queue:
        write_review_queue(args.queue, catalog)
    print(json.dumps(report, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
