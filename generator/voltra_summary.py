"""Coach-reviewable VOLTRA workout summary from validated Beyond+ CSV data.

Descriptive performance only: do not convert device readings into a 1RM,
clinical diagnosis, or automatic progression without coach approval.
"""
from statistics import mean
from voltra_csv import parse_voltra_csv, VoltraCSVError


def summarize_voltra_csv(csv_text, *, exercise, session_date, side,
                         training_mode, client_id):
    context = dict(exercise=exercise, session_date=session_date, side=side,
                   training_mode=training_mode, client_id=client_id)
    for field, value in context.items():
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise VoltraCSVError(f"{field} is required and must be 1-200 characters")
    if side not in ("left", "right", "bilateral", "unspecified"):
        raise VoltraCSVError("side must be left, right, bilateral or unspecified")
    from datetime import date
    try:
        date.fromisoformat(session_date)
    except ValueError:
        raise VoltraCSVError("session_date must be YYYY-MM-DD") from None
    parsed = parse_voltra_csv(csv_text)
    groups = {}
    for rep in parsed["repetitions"]:
        groups.setdefault(rep["set_index"], []).append(rep)
    sets = []
    for index, reps in sorted(groups.items()):
        reps.sort(key=lambda r: r["rep_index"])
        metrics = [r["metrics"] for r in reps]
        loads = {m["Base Weight (LBS)"] for m in metrics}
        # Variable resistance is valid; report range, never imply a fixed load.
        sets.append({
            "set_index": index, "repetitions": len(reps),
            "base_load_lb_min": min(loads),
            "base_load_lb_max": max(loads),
            "mean_velocity_m_s": round(mean(m["Mean Velocity (M/S)"] for m in metrics), 3),
            "peak_velocity_m_s": max(m["Peak Velocity (M/S)"] for m in metrics),
            "mean_power_w": round(mean(m["Mean Power (W)"] for m in metrics), 1),
            "peak_power_w": max(m["Peak Power (W)"] for m in metrics),
            "mean_rom_m": round(mean(m["Range of Motion (M)"] for m in metrics), 3),
            "total_duration_s": round(sum(m["Duration (S)"] for m in metrics), 2),
        })
    return {
        "source": parsed["source"], "client_id": client_id,
        "exercise": exercise.strip(), "session_date": session_date,
        "side": side, "training_mode": training_mode.strip(),
        "sets": sets, "total_repetitions": len(parsed["repetitions"]),
        "units": parsed["units"], "review_status": "requires_coach_review",
        "notes": [
            "CSV contains no exercise, date, side or client identity; context was supplied manually.",
            "Results are descriptive. Compare sessions only with matching exercise, mode and setup.",
            "Do not infer maximum strength or automatically prescribe load from this export.",
        ],
    }
