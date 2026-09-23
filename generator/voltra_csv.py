"""Parse Beyond+ VOLTRA rep-level CSV exports without assuming undocumented fields.

Vendor force/velocity/power columns are semicolon-separated sample arrays.
Keep their sign and source units; do not treat negative eccentric power as
invalid or interpret a sampled force trace as a single strength test.
"""
import csv
import io
import math

HEADER = (
    "Set Index", "Reps Index", "Base Weight (LBS)", "Eccentric Weight (LBS)",
    "Chains Weight (LBS)", "Range of Motion (M)", "Duration (S)",
    "Mean Velocity (M/S)", "Peak Velocity (M/S)", "Mean Power (W)",
    "Peak Power (W)", "Con. Force (LBS)", "Con. Velocity (M/S)",
    "Con. Power (W)", "Ecc. Force (LBS)", "Ecc Velocity (M/S)",
    "Ecc Power (W)",
)
TRACES = HEADER[11:]
NONNEGATIVE = HEADER[2:11]
MAX_ROWS = 10000
MAX_SAMPLES = 10000


class VoltraCSVError(ValueError):
    pass


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise VoltraCSVError(f"Invalid numeric value in {label}") from None
    if not math.isfinite(result):
        raise VoltraCSVError(f"Non-finite numeric value in {label}")
    return result


def parse_voltra_csv(source):
    """Return validated per-rep measurements and trace arrays, without PII.

    Input is CSV text (not a path). Exercise, session date, side and client
    identity are absent from this export and must be supplied by the coach.
    """
    if not isinstance(source, str) or len(source.encode("utf-8")) > 8_000_000:
        raise VoltraCSVError("CSV must be UTF-8 text no larger than 8 MB")
    reader = csv.DictReader(io.StringIO(source.lstrip("\ufeff"), newline=""))
    if not reader.fieldnames or tuple(reader.fieldnames) != HEADER:
        raise VoltraCSVError("Unrecognized VOLTRA CSV header")
    result = []
    seen = set()
    for row in reader:
        if len(result) >= MAX_ROWS:
            raise VoltraCSVError("Too many repetitions in CSV")
        if None in row or any(v is None for v in row.values()):
            raise VoltraCSVError("Malformed CSV row")
        if not any(str(v).strip() for v in row.values()):
            continue
        set_id = _number(row["Set Index"], "Set Index")
        rep_id = _number(row["Reps Index"], "Reps Index")
        if (set_id < 1 or rep_id < 1 or not set_id.is_integer()
                or not rep_id.is_integer()):
            raise VoltraCSVError("Set and rep indices must be positive integers")
        key = (int(set_id), int(rep_id))
        if key in seen:
            raise VoltraCSVError("Duplicate set and repetition index")
        seen.add(key)
        metrics = {}
        for field in NONNEGATIVE:
            value = _number(row[field], field)
            if value < 0:
                raise VoltraCSVError(f"Negative value in {field}")
            metrics[field] = value
        traces = {}
        for field in TRACES:
            raw = row[field].strip()
            values = [_number(x.strip(), field) for x in raw.split(";")] if raw else []
            if len(values) > MAX_SAMPLES:
                raise VoltraCSVError(f"Too many samples in {field}")
            traces[field] = values
        result.append({
            "set_index": key[0], "rep_index": key[1],
            "metrics": metrics, "traces": traces,
        })
    if not result:
        raise VoltraCSVError("CSV contains no repetitions")
    return {
        "source": "voltra_beyond_plus_csv",
        "units": {"load": "lb", "force": "lb", "rom": "m",
                  "duration": "s", "velocity": "m/s", "power": "W"},
        "repetitions": result,
        "requires_coach_context": ["client_id", "exercise", "session_date",
                                   "side", "training_mode"],
    }
