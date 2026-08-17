"""
IMS · VALD DynaMo mapping · test suite.

The fixtures below are the example payloads from VALD's own External DynaMo API
documentation, used verbatim. If VALD changes the schema, these break, which is
exactly what should happen.
"""

import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "generator"))

from objective_measures import DYNAMO_TESTS, parse_objective_measures  # noqa: E402
from validation import PayloadError, validate_payload  # noqa: E402
from vald_mapping import (VALD_ROM_MAP, VALD_TEST_MAP,  # noqa: E402
                          build_objective_measures, transform_tests,
                          unmapped_tests)


# ── fixtures · straight from the VALD API docs ────────────

STRENGTH_TEST = {
    "id": "4984c8fa-636d-4745-b7eb-199c6c217d53",
    "athleteId": "eec1c134-f278-4a77-9161-3cb29b1ec381",
    "testCategory": "Strength",
    "bodyRegion": "Knee",
    "movement": "Flexion",
    "position": "Seated",
    "laterality": "LeftThenRight",
    "startTimeUTC": "2024-09-04T05:01:48.60773Z",
    "repetitionTypeSummaries": [
        {"movement": "Flexion", "laterality": "LeftSide", "repCount": 1,
         "maxForceNewtons": 84, "avgForceNewtons": 84,
         "maxRateOfForceDevelopmentNewtonsPerSecond": 341.44718819712114,
         "maxRangeOfMotionDegrees": 0,
         "avgTimeToPeakForceSeconds": 0.5599440000000007},
        {"movement": "Flexion", "laterality": "RightSide", "repCount": 1,
         "maxForceNewtons": 73.10000000000001,
         "maxRateOfForceDevelopmentNewtonsPerSecond": 285.6807419872497,
         "maxRangeOfMotionDegrees": 0,
         "avgTimeToPeakForceSeconds": 0.8976880000000003},
    ],
    "asymmetries": [{"movement": "Flexion", "valuePercentage": -13}],
}

ROM_TEST = {
    "id": "053f8417-0671-49ae-9bbd-7fb927a036f2",
    "testCategory": "RangeofMotion",
    "bodyRegion": "Knee",
    "movement": "Extension",
    "position": "Seated",
    "laterality": "LeftSide",
    "startTimeUTC": "2024-07-19T04:45:03.657123Z",
    "repetitionTypeSummaries": [
        {"movement": "Extension", "laterality": "LeftSide", "repCount": 1,
         "maxForceNewtons": 0,
         "maxRangeOfMotionDegrees": -32.0392012157334},
    ],
}

SHOULDER_TEST = {
    "id": "d23a4754-37bc-43dd-ac7f-395592119b49",
    "testCategory": "Strength",
    "bodyRegion": "Shoulder",
    "movement": "ExternalRotation",
    "position": "Standing",
    "laterality": "LeftThenRight",
    "startTimeUTC": "2026-06-14T01:36:33Z",
    "repetitionTypeSummaries": [
        {"laterality": "LeftSide", "maxForceNewtons": 62},
        {"laterality": "RightSide", "maxForceNewtons": 107},
    ],
}

IMTP_TEST = {
    "id": "eaf124a3-88fd-4ccf-9b51-460ba58571d6",
    "testCategory": "Strength",
    "bodyRegion": "Hip",
    "movement": "IsometricMidThighPull",
    "position": "MidThigh",
    "laterality": "None",
    "startTimeUTC": "2026-06-14T00:37:21.823469Z",
    "repetitionTypeSummaries": [
        {"laterality": "None", "maxForceNewtons": 185,
         "maxRateOfForceDevelopmentNewtonsPerSecond": 496.0661950730271},
    ],
}


class TestMappingTable(unittest.TestCase):

    def test_every_mapped_id_is_known_to_the_generator(self):
        """The whole reason the table lives in this repo · no drift."""
        for key, test_id in VALD_TEST_MAP.items():
            with self.subTest(key=key):
                self.assertIn(test_id, DYNAMO_TESTS,
                              f"{key} maps to '{test_id}', which the server "
                              f"would 400 on")

    def test_rom_map_targets_are_canonical(self):
        from objective_measures import canonical_joint
        for key, (joint, _motion) in VALD_ROM_MAP.items():
            with self.subTest(key=key):
                self.assertIsNotNone(canonical_joint(joint))


class TestStrengthTransform(unittest.TestCase):

    def test_bilateral_test_splits_into_two_sides(self):
        out = transform_tests([STRENGTH_TEST])
        sides = sorted(d["side"] for d in out["dynamo"])
        self.assertEqual(sides, ["L", "R"])

    def test_force_stays_in_newtons_and_is_converted_downstream(self):
        out = transform_tests([STRENGTH_TEST])
        left = next(d for d in out["dynamo"] if d["side"] == "L")
        self.assertEqual(left["unit"], "N")
        self.assertEqual(left["value"], 84.0)

        objective = parse_objective_measures({"current": out})
        measure = objective.current.force("knee_flexion", "L")
        # 84 N is about 18.9 lb
        self.assertAlmostEqual(measure.value_lb, 18.9, places=1)

    def test_rfd_comes_through_free(self):
        """RFD does NOT need force-trace parsing · it is on the same payload.

        The original plan assumed this was gated behind a later ingest phase.
        It is not.
        """
        out = transform_tests([STRENGTH_TEST])
        left = next(d for d in out["dynamo"] if d["side"] == "L")
        self.assertAlmostEqual(left["metrics"]["rfd_n_per_s"], 341.45, places=1)
        self.assertIn("time_to_peak_s", left["metrics"])

    def test_provenance_is_recorded(self):
        out = transform_tests([STRENGTH_TEST])
        for d in out["dynamo"]:
            self.assertEqual(d["source"], "vald_api")
            self.assertEqual(d["source_id"], STRENGTH_TEST["id"])

    def test_provenance_survives_into_the_measure_table(self):
        objective = parse_objective_measures(
            {"current": transform_tests([STRENGTH_TEST])})
        rows = objective.measure_table()
        self.assertTrue(all(r["source"] == "vald_api" for r in rows))
        self.assertEqual(objective.to_dict()["sources"], ["vald_api"])

    def test_unlateralised_test_becomes_bilateral(self):
        out = transform_tests([IMTP_TEST])
        self.assertEqual(len(out["dynamo"]), 1)
        self.assertEqual(out["dynamo"][0]["side"], "bilateral")
        self.assertEqual(out["dynamo"][0]["test"], "imtp")

    def test_movement_naming_variants_all_resolve(self):
        for movement in ("ExternalRotation", "External Rotation",
                         "external_rotation"):
            with self.subTest(movement=movement):
                test = dict(SHOULDER_TEST, movement=movement)
                out = transform_tests([test])
                self.assertEqual(out["dynamo"][0]["test"], "shoulder_er")


class TestRomTransform(unittest.TestCase):

    def test_rom_arrives_in_degrees_not_quaternions(self):
        """Correcting an earlier assumption.

        Quaternions are in the raw trace. The test-level payload carries
        maxRangeOfMotionDegrees directly, so ROM imports cleanly and does not
        have to stay manual.
        """
        out = transform_tests([ROM_TEST])
        self.assertEqual(len(out["rom"]), 1)
        self.assertEqual(out["rom"][0]["joint"], "knee")
        self.assertEqual(out["rom"][0]["motion"], "extension")

    def test_negative_rom_survives_validation(self):
        """An extension deficit is negative. VALD's own example is -32 degrees,
        which the first cut of the validator would have rejected."""
        out = transform_tests([ROM_TEST])
        self.assertEqual(out["rom"][0]["degrees"], -32.0)
        validate_payload({"objective_measures": {"current": out}})

    def test_dynamo_rom_is_marked_active_not_passive(self):
        """The client drives a DynaMo ROM test. Calling it passive would be a
        quiet clinical lie on the coach page."""
        out = transform_tests([ROM_TEST])
        self.assertEqual(out["rom"][0]["mode"], "active")


class TestFailureModes(unittest.TestCase):

    def test_unmapped_test_warns_and_skips_rather_than_failing(self):
        """One novel movement must not fail a whole assessment sync."""
        novel = dict(STRENGTH_TEST, bodyRegion="Thumb", movement="Opposition")
        warnings = []
        out = transform_tests([STRENGTH_TEST, novel], warnings)
        self.assertEqual(len(out["dynamo"]), 2)      # the knee test survived
        self.assertTrue(any("Thumb" in w for w in warnings))

    def test_unmapped_report_lists_what_to_add(self):
        novel = dict(STRENGTH_TEST, bodyRegion="Thumb", movement="Opposition")
        missing = unmapped_tests([STRENGTH_TEST, novel, novel])
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["bodyRegion"], "Thumb")

    def test_garbage_never_raises(self):
        warnings = []
        out = transform_tests(["not an object", None, {}, {"testCategory": "x"}],
                              warnings)
        self.assertEqual(out["dynamo"], [])
        self.assertTrue(warnings)

    def test_empty_batch_returns_none(self):
        self.assertIsNone(build_objective_measures([]))

    def test_zero_force_reps_are_dropped(self):
        """ROM tests carry maxForceNewtons of 0 · that is not a force reading."""
        out = transform_tests([ROM_TEST])
        self.assertEqual(out["dynamo"], [])


class TestFullAssembly(unittest.TestCase):

    def test_builds_a_block_the_generator_accepts(self):
        payload = build_objective_measures(
            [STRENGTH_TEST, SHOULDER_TEST, ROM_TEST],
            previous_tests=[dict(STRENGTH_TEST, id="prev-1",
                                 startTimeUTC="2026-04-12T05:01:48Z")],
            bodyweight_lb=185)
        self.assertIn("current", payload)
        self.assertIn("previous", payload)
        validate_payload({"objective_measures": payload})

        objective = parse_objective_measures(payload)
        self.assertTrue(objective.has_data())
        self.assertTrue(objective.has_previous())
        self.assertEqual(objective.current.bodyweight_lb, 185)

    def test_session_date_comes_from_the_latest_test(self):
        payload = build_objective_measures([STRENGTH_TEST, SHOULDER_TEST])
        self.assertEqual(payload["current"]["date"], "2026-06-14")

    def test_end_to_end_produces_a_plan(self):
        from tests.test_objective_measures import build, make_assessment
        payload = build_objective_measures(
            [SHOULDER_TEST, ROM_TEST, IMTP_TEST], bodyweight_lb=185)
        program = build(make_assessment(objective_measures=payload))
        self.assertTrue(program.objective["measure_table"])
        self.assertIn("vald_api", program.objective["measure_table"][0]["source"])


class TestTransformEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = app_module.app.test_client()

    def test_transform_returns_a_valid_block(self):
        resp = self.client.post("/api/vald/transform", json={
            "current": [STRENGTH_TEST, SHOULDER_TEST, ROM_TEST],
            "bodyweight_lb": 185,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["valid"])
        self.assertIn("current", body["objective_measures"])

    def test_transform_reports_unmapped_without_failing(self):
        novel = dict(STRENGTH_TEST, bodyRegion="Thumb", movement="Opposition")
        resp = self.client.post("/api/vald/transform",
                                json={"current": [STRENGTH_TEST, novel]})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["valid"])
        self.assertEqual(body["unmapped"][0]["bodyRegion"], "Thumb")

    def test_transform_of_nothing_is_not_an_error(self):
        resp = self.client.post("/api/vald/transform", json={"current": []})
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()["objective_measures"])

    def test_transform_output_feeds_generate(self):
        """The two endpoints have to actually compose."""
        t = self.client.post("/api/vald/transform", json={
            "current": [STRENGTH_TEST, SHOULDER_TEST, ROM_TEST],
            "bodyweight_lb": 185}).get_json()
        resp = self.client.post("/api/generate", json={
            "client_name": "VALD Client",
            "age_range": "late 40s",
            "sex": "M",
            "strength_days": 3,
            "pdf_mode": "full",
            "fra_priorities": ["Hip IR L+R"],
            "mobility_map": [{"joint": "hip", "direction": "IR", "side": "L",
                              "rating": "yellow"}],
            "objective_measures": t["objective_measures"],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
