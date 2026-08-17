"""
IMS · server-side payload validation.

Before this existed, /api/generate accepted anything and coerced it. A typo in
a Coach OS field name produced a plan silently missing that input, which is the
worst possible failure mode for a document a client trains off.

Rules ·
  * WRONG TYPE or OUT OF RANGE  → hard error, HTTP 400, nothing is generated.
  * UNKNOWN FIELD               → warning, request proceeds. Coach OS ships
                                  ahead of the generator sometimes and a new
                                  field should not take the studio down.
  * MISSING OPTIONAL FIELD      → silent. Most of the payload is optional and
                                  that is by design.

Also the contract gate · a payload may declare contract_version, and a major
this build does not accept is refused rather than half-understood.
"""

from ims_contract import ACCEPTED_CONTRACT_MAJORS, CONTRACT_VERSION, contract_major
from objective_measures import DYNAMO_TESTS, canonical_joint


class PayloadError(ValueError):
    """One or more hard validation failures. Carries every error at once."""

    def __init__(self, errors, warnings=None):
        self.errors = list(errors)
        self.warnings = list(warnings or [])
        super().__init__("; ".join(self.errors))

    def to_dict(self) -> dict:
        return {
            "error": "invalid_payload",
            "contract_version": CONTRACT_VERSION,
            "errors": self.errors,
            "warnings": self.warnings,
        }


KNOWN_FIELDS = {
    # identity + intake
    "client_name", "age_range", "sex", "background", "primary_goal",
    "assessment_date", "training_frequency", "strength_days", "cardio_days",
    "training_age_years", "conditioning_level",
    # assessment content
    "fra_priorities", "mobility_map", "strength_markers",
    "strength_marker_results", "strength_marker_tests",
    "constraints", "constraints_rich", "concerns", "concern_notes",
    "accessory_categories", "cardio_profile", "rom_degrees",
    # coach OS enrichment
    "sleep_quality", "sleep_hours", "stress_level", "desk_hours", "resting_hr",
    "posture", "pain_map", "red_flags", "coach_notes",
    # body comp / nutrition
    "body_comp", "nutrition_strategy", "activity_factor",
    # objective measurement
    "objective_measures",
    # meta
    "pdf_mode", "contract_version", "block_number",
}

_LIST_FIELDS = ("fra_priorities", "mobility_map", "strength_markers",
                "strength_marker_tests", "constraints", "constraints_rich",
                "concerns", "accessory_categories")
_DICT_FIELDS = ("strength_marker_results", "body_comp", "posture", "pain_map",
                "rom_degrees", "cardio_profile", "objective_measures")
_STR_FIELDS = ("client_name", "age_range", "sex", "background", "primary_goal",
               "concern_notes", "sleep_quality", "sleep_hours", "stress_level",
               "desk_hours", "resting_hr", "red_flags", "coach_notes",
               "nutrition_strategy", "pdf_mode", "assessment_date",
               "conditioning_level")

_ENUMS = {
    "pdf_mode": {"client", "coach", "full"},
    "sleep_quality": {"", "good", "fair", "poor"},
    "stress_level": {"", "low", "moderate", "high", "very_high"},
    "nutrition_strategy": {"", "maintenance", "fat_loss", "endurance", "strength"},
    "conditioning_level": {"", "deconditioned", "moderate", "well_conditioned"},
}

_RATINGS = {"red", "yellow", "green"}
_SIDES = {"", "l", "r", "left", "right", "bilateral", "both", "b", "n/a"}
_CONSTRAINT_STATUSES = {"", "active_flare_up", "history", "cleared",
                        "post_surgery", "avoid_loading"}
_FORCE_UNITS = {"", "lb", "lbs", "kg", "kgs", "n", "newton", "newtons"}


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _validate_objective_measures(raw, errors, warnings):
    if raw is None:
        return
    if not isinstance(raw, dict):
        errors.append("objective_measures must be an object")
        return

    sets = {}
    if "current" in raw or "previous" in raw:
        for which in ("current", "previous"):
            val = raw.get(which)
            if val is None:
                continue
            if not isinstance(val, dict):
                errors.append(f"objective_measures.{which} must be an object")
                continue
            sets[which] = val
    elif any(k in raw for k in ("dynamo", "voltra", "rom")):
        sets["current"] = raw
    else:
        errors.append("objective_measures must contain 'current' "
                      "(or dynamo/voltra/rom directly)")
        return

    for which, ms in sets.items():
        base = f"objective_measures.{which}"

        bw = ms.get("bodyweight_lb", ms.get("bodyweight"))
        if bw is not None:
            n = _num(bw)
            if n is None:
                errors.append(f"{base}.bodyweight must be a number")
            elif not (50 <= n <= 700):
                errors.append(f"{base}.bodyweight {n} is out of range (50–700 lb)")

        for key in ("dynamo", "force"):
            rows = ms.get(key)
            if rows is None:
                continue
            if not isinstance(rows, list):
                errors.append(f"{base}.{key} must be a list")
                continue
            for i, row in enumerate(rows):
                at = f"{base}.{key}[{i}]"
                if not isinstance(row, dict):
                    errors.append(f"{at} must be an object")
                    continue
                test = str(row.get("test") or row.get("name") or "").strip().lower()
                test = test.replace(" ", "_").replace("-", "_")
                if not test:
                    errors.append(f"{at} is missing 'test'")
                elif test not in DYNAMO_TESTS:
                    errors.append(f"{at} unknown test '{test}' · known tests: "
                                  + ", ".join(sorted(DYNAMO_TESTS)))
                val = _num(row.get("value", row.get("peak_force")))
                if val is None:
                    errors.append(f"{at} is missing a numeric 'value'")
                elif val <= 0 or val > 1000:
                    errors.append(f"{at} value {val} is out of range (0–1000)")
                if str(row.get("unit") or "").strip().lower() not in _FORCE_UNITS:
                    errors.append(f"{at} unit '{row.get('unit')}' is not lb, kg or N")
                if str(row.get("side") or "").strip().lower() not in _SIDES:
                    errors.append(f"{at} side '{row.get('side')}' is not L, R or bilateral")

        rows = ms.get("voltra")
        if rows is not None:
            if not isinstance(rows, list):
                errors.append(f"{base}.voltra must be a list")
            else:
                for i, row in enumerate(rows):
                    at = f"{base}.voltra[{i}]"
                    if not isinstance(row, dict):
                        errors.append(f"{at} must be an object")
                        continue
                    if not str(row.get("pattern") or row.get("test") or "").strip():
                        errors.append(f"{at} is missing 'pattern'")
                    pos = str(row.get("position") or "").strip().lower().replace("-", "_")
                    if pos not in ("mid_range", "end_range", "mid", "end",
                                   "midrange", "endrange"):
                        errors.append(f"{at} position must be mid_range or end_range")
                    val = _num(row.get("value", row.get("peak_force")))
                    if val is None:
                        errors.append(f"{at} is missing a numeric 'value'")
                    elif val <= 0 or val > 2000:
                        errors.append(f"{at} value {val} is out of range")

        rows = ms.get("rom", ms.get("rom_degrees"))
        if rows is not None and not isinstance(rows, dict):
            if not isinstance(rows, list):
                errors.append(f"{base}.rom must be a list or an object")
            else:
                for i, row in enumerate(rows):
                    at = f"{base}.rom[{i}]"
                    if not isinstance(row, dict):
                        errors.append(f"{at} must be an object")
                        continue
                    if canonical_joint(row.get("joint")) is None:
                        errors.append(f"{at} joint '{row.get('joint')}' is not a "
                                      f"known joint")
                    if not str(row.get("motion") or row.get("direction") or "").strip():
                        errors.append(f"{at} is missing 'motion'")
                    deg = _num(row.get("degrees", row.get("value")))
                    if deg is None:
                        errors.append(f"{at} is missing numeric 'degrees'")
                    elif not (-30 <= deg <= 200):
                        errors.append(f"{at} degrees {deg} is out of range (-30–200)")

    cur = sets.get("current") or {}
    prev = sets.get("previous")
    if prev and cur.get("date") and prev.get("date"):
        if str(prev["date"]) > str(cur["date"]):
            warnings.append("objective_measures.previous is dated after current · "
                            "deltas will be skipped")


def validate_payload(form_data) -> dict:
    """Validate an /api/generate payload. Raises PayloadError on any hard failure.

    Returns {"warnings": [...]} on success.
    """
    errors, warnings = [], []

    if not isinstance(form_data, dict):
        raise PayloadError([f"payload must be a JSON object, got "
                            f"{type(form_data).__name__}"])

    declared = form_data.get("contract_version")
    if declared:
        major = contract_major(declared)
        if major not in ACCEPTED_CONTRACT_MAJORS:
            raise PayloadError([
                f"contract_version {declared} is not supported by this "
                f"generator (accepts major {sorted(ACCEPTED_CONTRACT_MAJORS)}, "
                f"current {CONTRACT_VERSION})"])

    for key in form_data:
        if key not in KNOWN_FIELDS and not str(key).startswith("_"):
            warnings.append(f"unknown field '{key}' ignored")

    for f in _LIST_FIELDS:
        if f in form_data and form_data[f] is not None and not isinstance(form_data[f], list):
            errors.append(f"{f} must be a list")
    for f in _DICT_FIELDS:
        if f in form_data and form_data[f] is not None and not isinstance(form_data[f], dict):
            errors.append(f"{f} must be an object")
    for f in _STR_FIELDS:
        v = form_data.get(f)
        if v is not None and isinstance(v, (list, dict)):
            errors.append(f"{f} must be a string")

    for f, allowed in _ENUMS.items():
        v = form_data.get(f)
        if v is None:
            continue
        if isinstance(v, str) and v.strip().lower() not in allowed:
            errors.append(f"{f} '{v}' must be one of: "
                          + ", ".join(sorted(a for a in allowed if a)))

    if not str(form_data.get("client_name") or "").strip():
        warnings.append("client_name is empty · the plan will read 'Client'")

    for f, lo, hi in (("strength_days", 0, 7), ("cardio_days", 0, 7),
                      ("training_frequency", 0, 14), ("block_number", 1, 52)):
        if form_data.get(f) in (None, ""):
            continue
        n = _num(form_data[f])
        if n is None:
            errors.append(f"{f} must be a number")
        elif not (lo <= n <= hi):
            errors.append(f"{f} must be between {lo} and {hi} (got {form_data[f]})")

    sd, cd = _num(form_data.get("strength_days") or 0), _num(form_data.get("cardio_days") or 0)
    if sd is not None and cd is not None and (sd + cd) > 7:
        errors.append(f"strength_days + cardio_days is {int(sd + cd)} · "
                      f"more than 7 days in a week")

    af = form_data.get("activity_factor")
    if af not in (None, ""):
        n = _num(af)
        if n is None:
            errors.append("activity_factor must be a number")
        elif not (1.0 <= n <= 2.5):
            errors.append(f"activity_factor {af} is outside 1.0–2.5")

    if "training_age_years" in form_data and form_data["training_age_years"] not in (None, ""):
        n = _num(form_data["training_age_years"])
        if n is None:
            errors.append("training_age_years must be a number")
        elif not (0 <= n <= 70):
            errors.append(f"training_age_years {n} is outside 0–70")

    for i, row in enumerate(form_data.get("mobility_map") or []):
        if not isinstance(row, dict):
            errors.append(f"mobility_map[{i}] must be an object")
            continue
        rating = str(row.get("rating") or "").strip().lower()
        if rating and rating not in _RATINGS:
            errors.append(f"mobility_map[{i}] rating '{row.get('rating')}' must be "
                          f"red, yellow or green")
        if str(row.get("side") or "").strip().lower() not in _SIDES:
            errors.append(f"mobility_map[{i}] side '{row.get('side')}' is not "
                          f"L, R or bilateral")

    for i, row in enumerate(form_data.get("constraints_rich") or []):
        if not isinstance(row, dict):
            errors.append(f"constraints_rich[{i}] must be an object")
            continue
        st = str(row.get("status") or "").strip().lower()
        if st and st not in _CONSTRAINT_STATUSES:
            errors.append(f"constraints_rich[{i}] status '{row.get('status')}' "
                          f"is not a known status")
        pl = row.get("pain_level")
        if pl not in (None, ""):
            n = _num(pl)
            if n is None or not (0 <= n <= 10):
                errors.append(f"constraints_rich[{i}] pain_level must be 0–10")

    pm = form_data.get("pain_map")
    if isinstance(pm, dict):
        for area, entry in pm.items():
            if not isinstance(entry, dict):
                errors.append(f"pain_map['{area}'] must be an object")
                continue
            sev = entry.get("severity")
            if sev not in (None, ""):
                n = _num(sev)
                if n is None or not (0 <= n <= 10):
                    errors.append(f"pain_map['{area}'].severity must be 0–10")

    _validate_objective_measures(form_data.get("objective_measures"), errors, warnings)

    if errors:
        raise PayloadError(errors, warnings)
    return {"warnings": warnings}
