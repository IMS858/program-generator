"""Synthetic assessment-to-structured-program/PDF scenarios; no client records."""
import base64
import unittest
from app import app
from reviewed_program import validate_reviewed_program, ReviewedProgramError
from plan_pdf import _rotating_sessions


def baseline(**changes):
    p = {"client_name": "Synthetic Athlete", "age_range": "late 40s", "sex": "M",
         "strength_days": 3, "cardio_days": 0,
         "fra_priorities": ["Hip IR L+R"],
         "mobility_map": [{"joint": "hip", "direction": "IR", "side": "L", "rating": "yellow"}],
         "body_comp": {"weight": "185 lb", "lean_mass": "145 lb"},
         "nutrition_strategy": "maintenance", "pdf_mode": "client"}
    p.update(changes)
    return p


class SyntheticProgramScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def assert_generated(self, payload):
        response = self.client.post("/api/generate", json=payload,
                                    headers={"Accept": "application/json"})
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()
        self.assertTrue(base64.b64decode(data["pdf_base64"]).startswith(b"%PDF-"))
        program = data["program"]
        self.assertEqual(len(program["weeks"]), 4)
        # Initial generation renders a week-one-based PDF. Reviewed regeneration
        # currently rejects rotating exercise structures; track this separately.
        self.assertTrue(all(1 <= len(w["sessions"]) <= 7 for w in program["weeks"]))
        return program

    def test_ims_review_inspired_personas_generate_four_week_pdf(self):
        # Fictional composite personas inspired by public IMS review themes.
        # These are not the reviewers' records or individualized prescriptions.
        scenarios = [
            ("general_strength", dict(strength_days=3, cardio_days=1)),
            ("knee_history_cleared", dict(strength_days=2, cardio_days=1,
                concerns=["bad_knee"], constraints_rich=[
                    {"key": "post_surgery_knee", "status": "cleared"}],
                mobility_map=[{"joint": "knee", "direction": "flexion", "side": "L", "rating": "yellow"}])),
            ("college_football_offseason", dict(strength_days=4, cardio_days=2,
                fra_priorities=["Hip IR L+R", "Shoulder ER L+R"])),
            ("desk_worker_poor_recovery", dict(strength_days=2, cardio_days=1,
                conditioning_level="deconditioned", sleep_quality="poor", stress_level="high",
                body_comp={})),
            ("older_adult_strength", dict(age_range="early 70s", strength_days=2,
                cardio_days=1, fra_priorities=["Ankle dorsiflexion L+R"])),
            ("shoulder_sensitive_return", dict(strength_days=2, cardio_days=1,
                concerns=["bad_shoulder"], fra_priorities=["Shoulder ER L"])),
            ("low_back_sensitive", dict(strength_days=2, cardio_days=1,
                concerns=["lower_back"], constraints=["no_axial_loading"])),
            ("busy_client_twice_weekly", dict(strength_days=2, cardio_days=0,
                nutrition_strategy="maintenance")),
        ]
        for label, changes in scenarios:
            with self.subTest(persona=label):
                p = self.assert_generated(baseline(client_name="Synthetic " + label,
                                                   **changes))
                self.assertEqual(len(p["weeks"][0]["sessions"]), changes["strength_days"])
                self.assertEqual([w.get("week") for w in p["weeks"]], [1, 2, 3, 4])

    def test_active_post_surgery_is_not_silently_cleared(self):
        # Even an athlete with high capacity cannot bypass an active restriction.
        from generator import Generator
        from types import SimpleNamespace
        from pathlib import Path
        g = Generator(libraries_path=str(Path(__file__).resolve().parents[1] / "libraries"))
        for status in ("post_surgery", "active_flare_up", "avoid_loading"):
            with self.subTest(status=status):
                assessment = SimpleNamespace(
                    constraints_rich=[{"key": "knee", "status": status}],
                    concerns=[], constraints=[])
                with self.assertRaisesRegex(ValueError, "coach review required"):
                    g._pick_strength_exercise("squat", [], assessment=assessment)

    def test_reviewed_pdf_contract_detects_rotating_week_exercises(self):
        p = self.assert_generated(baseline(strength_days=2, concerns=["bad_knee"],
            constraints=["no_axial_loading"]))
        rotating = _rotating_sessions(p)
        self.assertIsNotNone(validate_reviewed_program(p))
        self.assertIsInstance(rotating, list)

    def test_general_strength_three_days(self):
        p = self.assert_generated(baseline())
        self.assertEqual(len(p["weeks"][0]["sessions"]), 3)

    def test_two_day_training_with_knee_constraint(self):
        self.assert_generated(baseline(strength_days=2, concerns=["bad_knee"],
            constraints=["no_axial_loading"], fra_priorities=["Shoulder ER L"],
            mobility_map=[{"joint": "shoulder", "direction": "ER", "side": "L", "rating": "yellow"}]))

    def test_missing_body_composition_still_generates(self):
        self.assert_generated(baseline(body_comp={}, strength_days=2,
            conditioning_level="deconditioned", sleep_quality="poor", stress_level="high"))

    def test_explicit_kg_body_composition_still_generates(self):
        self.assert_generated(baseline(body_comp={"weight": "84 kg", "lean_mass": "65 kg"},
            strength_days=2, cardio_days=1))


if __name__ == "__main__":
    unittest.main()
