import csv
import io
import unittest
from voltra_csv import HEADER, VoltraCSVError
from voltra_summary import summarize_voltra_csv


def fixture():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADER)
    for rep, vel, power in [(1, .38, 309), (2, .47, 374), (3, .50, 399)]:
        writer.writerow([1, rep, 180, 0, 0, .43, 1.0, vel, .9, power,
                         700, "180;181", ".3;.4", "100;200",
                         "180;180", "-.3;-.4", "-200;-300"])
    return output.getvalue()


CONTEXT = dict(exercise="Cable row", session_date="2026-09-22",
               side="bilateral", training_mode="weight training",
               client_id="synthetic-test-client")


class VoltraSummaryTests(unittest.TestCase):
    def test_summarizes_actual_vendor_schema(self):
        result = summarize_voltra_csv(fixture(), **CONTEXT)
        self.assertEqual(result["total_repetitions"], 3)
        self.assertEqual(result["sets"][0]["base_load_lb_min"], 180)
        self.assertEqual(result["sets"][0]["mean_velocity_m_s"], .45)
        self.assertEqual(result["sets"][0]["peak_power_w"], 700)
        self.assertEqual(result["review_status"], "requires_coach_review")
        self.assertNotIn("estimated_1rm", result)

    def test_requires_workout_context(self):
        with self.assertRaises(VoltraCSVError):
            summarize_voltra_csv(fixture(), **dict(CONTEXT, exercise=""))

    def test_rejects_bad_date(self):
        with self.assertRaises(VoltraCSVError):
            summarize_voltra_csv(fixture(), **dict(CONTEXT, session_date="yesterday"))

    def test_rejects_unknown_side(self):
        with self.assertRaises(VoltraCSVError):
            summarize_voltra_csv(fixture(), **dict(CONTEXT, side="dominant"))


if __name__ == "__main__":
    unittest.main()
