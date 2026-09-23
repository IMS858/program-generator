"""Strict parsing of synthetic ActivForce measurements."""
import unittest
from objective_measures import _to_float, parse_objective_measures
from force_load import find_force_anchor
from weakest_link import rank_joints, asymmetries


class TestObjectiveInputSafety(unittest.TestCase):
    def test_numeric_parser_rejects_concatenation_and_nonfinite_values(self):
        for bad in ("45/60", "50 lb + 20 lb", "about 45", "1e309", "NaN",
                    float("inf"), float("-inf"), float("nan"), True, {}, []):
            with self.subTest(value=bad):
                self.assertIsNone(_to_float(bad))

    def test_explicit_numeric_units_are_accepted(self):
        for value in (45, 45.0, "45", " 45 ", "45.0"):
            with self.subTest(value=value):
                self.assertEqual(_to_float(value), 45)

    def test_embedded_units_never_silently_override_explicit_unit(self):
        for value in ("45 lb", "45kg", "45 N", "45 degrees", "35°"):
            with self.subTest(value=value):
                self.assertIsNone(_to_float(value))
        payload = {"current": {"date": "2026-09-20", "dynamo": [
            {"test": "hip_ir", "side": "L", "value": "45kg", "unit": "lb",
             "source": "activforce_2_manual"},
            {"test": "hip_ir", "side": "R", "value": 45, "unit": "kg",
             "source": "activforce_2_manual"}]}}
        result = parse_objective_measures(payload)
        self.assertEqual(len(result.current.forces), 1)
        self.assertEqual(result.current.forces[0].side, "R")
        self.assertAlmostEqual(result.current.forces[0].value_lb, 99.208, places=2)
        self.assertTrue(result.warnings)

    def test_activforce_requires_explicit_rom_mode_side_and_date(self):
        payload = {"current": {"date": "2026-09-20", "rom": [
            {"joint": "hip", "motion": "ir", "side": "L", "degrees": 32,
             "source": "activforce_2_manual"},
            {"joint": "hip", "motion": "ir", "side": "R", "degrees": 36,
             "mode": "active", "source": "activforce_2_manual"},
            {"joint": "hip", "motion": "er", "degrees": 45,
             "mode": "passive", "source": "activforce_2_manual"}]}}
        result = parse_objective_measures(payload)
        self.assertEqual(len(result.current.roms), 1)
        self.assertEqual(result.current.roms[0].mode, "active")
        self.assertEqual(result.current.roms[0].side, "R")
        self.assertEqual(len(result.warnings), 2)

    def test_activforce_force_requires_side_and_plausible_load(self):
        payload = {"current": {"date": "2026-09-20", "dynamo": [
            {"test": "knee_extension", "value": 50,
             "source": "activforce_2_manual"},
            {"test": "knee_extension", "side": "L", "value": 900,
             "source": "activforce_2_manual"},
            {"test": "knee_extension", "side": "R", "value": 500,
             "unit": "N", "source": "activforce_2_manual"}]}}
        result = parse_objective_measures(payload)
        self.assertEqual(len(result.current.forces), 1)
        self.assertEqual(result.current.forces[0].device, "activforce_2")
        self.assertAlmostEqual(result.current.forces[0].value_lb, 112.40447, places=3)
        self.assertEqual(len(result.warnings), 2)

    def test_activforce_measurements_reach_prescription_and_asymmetry(self):
        payload = {"current": {"date": "2026-09-20", "bodyweight_lb": 185,
            "dynamo": [
                {"test": "knee_extension", "side": "L", "value": 60,
                 "source": "activforce_2_manual"},
                {"test": "knee_extension", "side": "R", "value": 90,
                 "source": "activforce_2_manual"},
                {"test": "hip_abduction", "side": "L", "value": 45,
                 "source": "activforce_2_manual"},
                {"test": "shoulder_er", "side": "L", "value": 18,
                 "source": "activforce_2_manual"}]}}
        objective = parse_objective_measures(payload)
        anchor = find_force_anchor(
            {"name": "Leg Extension", "joint": "knee", "pattern": "isolation",
             "equipment": ["machine"]}, objective, exercise_name="Leg Extension")
        self.assertIsNotNone(anchor)
        self.assertEqual(anchor.device, "activforce_2")
        self.assertEqual(anchor.side, "L")
        self.assertEqual(anchor.value_lb, 60)
        self.assertTrue(rank_joints(objective))
        gaps = asymmetries(objective)
        self.assertTrue(any(x["test"] == "knee_extension" and x["weak_side"] == "L"
                            for x in gaps))

    def test_activforce_does_not_anchor_compound_lift(self):
        payload = {"current": {"date": "2026-09-20", "dynamo": [
            {"test": "knee_extension", "side": "L", "value": 80,
             "source": "activforce_2_manual"}]}}
        objective = parse_objective_measures(payload)
        anchor = find_force_anchor(
            {"name": "Barbell Back Squat", "joint": "knee", "pattern": "squat",
             "equipment": ["barbell"]}, objective, exercise_name="Barbell Back Squat")
        self.assertIsNone(anchor)

    def test_invalid_force_and_rom_are_dropped(self):
        payload = {"current": {"date": "2026-09-20",
            "dynamo": [{"test": "hip_abduction", "side": "L", "value": "50/60", "unit": "lb"},
                       {"test": "hip_abduction", "side": "R", "value": 55, "unit": "lb"}],
            "rom": [{"joint": "hip", "motion": "ir", "side": "L", "degrees": "35/40"},
                    {"joint": "hip", "motion": "ir", "side": "R", "degrees": 35}]}}
        parsed = parse_objective_measures(payload)
        self.assertEqual(len(parsed.current.forces), 1)
        self.assertEqual(parsed.current.forces[0].side, "R")
        self.assertEqual(len(parsed.current.roms), 1)
        self.assertEqual(parsed.current.roms[0].side, "R")
        self.assertGreaterEqual(len(parsed.warnings), 2)


if __name__ == "__main__":
    unittest.main()
