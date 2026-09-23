"""Strict parsing of synthetic ActivForce measurements."""
import unittest
from objective_measures import _to_float, parse_objective_measures


class TestObjectiveInputSafety(unittest.TestCase):
    def test_numeric_parser_rejects_concatenation_and_nonfinite_values(self):
        for bad in ("45/60", "50 lb + 20 lb", "about 45", "1e309", "NaN",
                    float("inf"), float("-inf"), float("nan"), True, {}, []):
            with self.subTest(value=bad):
                self.assertIsNone(_to_float(bad))

    def test_explicit_numeric_units_are_accepted(self):
        for value in (45, 45.0, "45", "45 lb", "45kg", "45 N", "45 degrees"):
            with self.subTest(value=value):
                self.assertEqual(_to_float(value), 45)

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
