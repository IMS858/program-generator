"""Strict validation of coach-reviewed programs before PDF rendering.

This is a document contract, not an exercise-prescription validator: the coach
can edit prescriptions, but the renderer must receive a bounded, consistent
four-week document instead of silently printing only week one's sessions.
"""
class ReviewedProgramError(ValueError):
    pass


def validate_reviewed_program(program):
    def fail(message):
        raise ReviewedProgramError(message)

    if not isinstance(program, dict):
        fail("program must be an object")
    name = program.get("client_name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        fail("client_name must be 1-200 characters")
    if not isinstance(program.get("assessment"), dict):
        fail("assessment must be an object")
    weeks = program.get("weeks")
    if not isinstance(weeks, list) or not 1 <= len(weeks) <= 8:
        fail("weeks must contain 1-8 entries")
    expected_days = None
    total_exercises = 0
    for wi, week in enumerate(weeks):
        if not isinstance(week, dict) or not isinstance(week.get("sessions"), list):
            fail(f"weeks[{wi}].sessions must be a list")
        sessions = week["sessions"]
        if not 1 <= len(sessions) <= 7:
            fail(f"weeks[{wi}] must have 1-7 sessions")
        day_types = []
        for si, session in enumerate(sessions):
            if not isinstance(session, dict) or not isinstance(session.get("blocks"), list):
                fail(f"weeks[{wi}].sessions[{si}].blocks must be a list")
            day_types.append(session.get("day_type"))
            blocks = session["blocks"]
            if not 1 <= len(blocks) <= 16:
                fail(f"weeks[{wi}].sessions[{si}] must have 1-16 blocks")
            for bi, block in enumerate(blocks):
                if not isinstance(block, dict) or not isinstance(block.get("exercises"), list):
                    fail(f"weeks[{wi}].sessions[{si}].blocks[{bi}].exercises must be a list")
                if len(block["exercises"]) > 30:
                    fail("too many exercises in a block")
                for exercise in block["exercises"]:
                    if not isinstance(exercise, dict):
                        fail("exercise must be an object")
                    if not isinstance(exercise.get("name"), str) or not exercise["name"].strip():
                        fail("exercise name is required")
                    for key in ("name", "dose", "tempo", "rationale", "progression_note"):
                        value = exercise.get(key)
                        if value is not None and (not isinstance(value, str) or len(value) > 2000):
                            fail(f"exercise {key} must be text no longer than 2000 characters")
                    if exercise.get("coach_override_dose") not in (None, True, False):
                        fail("coach_override_dose must be boolean")
                    total_exercises += 1
                    if total_exercises > 2000:
                        fail("program contains too many exercises")
        # The current client PDF draws detailed sessions from week one.
        # Reject different day structures rather than misrepresenting later weeks.
        if expected_days is None:
            expected_days = day_types
        elif day_types != expected_days:
            fail("session structure differs between weeks; PDF cannot safely represent it")
    return program
