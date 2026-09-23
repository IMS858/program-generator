"""Nutrition parsing regression tests; synthetic data only."""
import unittest
from app import _mass_lb, calculate_nutrition


class NutritionSafetyTests(unittest.TestCase):
    def test_explicit_kg_and_lb_equivalent(self):
        a = calculate_nutrition({"weight": "90.718 kg", "lean_mass": "70 kg"}, 1.45, "maintenance")
        b = calculate_nutrition({"weight": "200 lb", "lean_mass": "154.324 lb"}, 1.45, "maintenance")
        self.assertEqual(a["rmr_katch_mcardle"], b["rmr_katch_mcardle"])
        self.assertEqual(a["tdee_estimated"], b["tdee_estimated"])

    def test_numeric_legacy_pounds(self):
        self.assertAlmostEqual(_mass_lb(185), 185)
        result = calculate_nutrition({"weight": 185, "lean_mass": 145}, 1.45, "strength")
        self.assertIn("nutrition_targets", result)

    def test_reject_ambiguous_or_corrupted_mass(self):
        for mass in ("185lb/84kg", "about 185", "1e9", -10, True, [], "NaN"):
            with self.subTest(mass=mass):
                self.assertIsNone(_mass_lb(mass))

    def test_lean_mass_cannot_exceed_weight(self):
        bc = {"weight": "180 lb", "lean_mass": "195 lb"}
        self.assertNotIn("nutrition_targets", calculate_nutrition(bc, 1.45, "fat_loss"))

    def test_reject_implausible_mass_and_activity(self):
        for weight, lean, factor in [("40 lb", "35 lb", 1.45), ("800 lb", "150 lb", 1.45),
                                     ("200 lb", "140 lb", 4), ("200 lb", "140 lb", float('nan'))]:
            with self.subTest(weight=weight, factor=factor):
                self.assertNotIn("nutrition_targets", calculate_nutrition(
                    {"weight": weight, "lean_mass": lean}, factor, "maintenance"))


if __name__ == "__main__":
    unittest.main()
