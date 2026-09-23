"""Synthetic assessment-to-structured-program/PDF scenarios; no client records."""
import base64
import unittest
from app import app
from reviewed_program import validate_reviewed_program


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
        self.assertIsNotNone(validate_reviewed_program(program))
        return program

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
