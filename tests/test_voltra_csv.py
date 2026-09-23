import csv
import io
import unittest
from voltra_csv import HEADER, parse_voltra_csv, VoltraCSVError


def sample(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buf.getvalue()


def row(rep=1):
    return [1, rep, 180, 0, 0, 0.43, 1.15, 0.38, 0.77, 309, 629,
            "180.5;179.4;180.5", "0.18;0.14;0.17", "144;111;143",
            "179.4;179.5", "-0.32;-0.39", "-260;-317"]


class VoltraCSVTests(unittest.TestCase):
    def test_real_export_shape_and_signed_eccentric_traces(self):
        parsed = parse_voltra_csv(sample([row(1), row(2)]))
        self.assertEqual(len(parsed["repetitions"]), 2)
        self.assertEqual(parsed["repetitions"][0]["metrics"]["Base Weight (LBS)"], 180)
        self.assertEqual(parsed["repetitions"][0]["traces"]["Ecc. Power (W)"], [-260, -317])
        self.assertIn("session_date", parsed["requires_coach_context"])

    def test_rejects_duplicate_reps(self):
        with self.assertRaises(VoltraCSVError):
            parse_voltra_csv(sample([row(), row()]))

    def test_rejects_nonfinite_samples(self):
        bad = row()
        bad[-1] = "-260;nan"
        with self.assertRaises(VoltraCSVError):
            parse_voltra_csv(sample([bad]))

    def test_rejects_malformed_headers(self):
        with self.assertRaises(VoltraCSVError):
            parse_voltra_csv("Set Index,Reps Index\\n1,1")

    def test_rejects_negative_load(self):
        bad = row()
        bad[2] = -180
        with self.assertRaises(VoltraCSVError):
            parse_voltra_csv(sample([bad]))


if __name__ == "__main__":
    unittest.main()
