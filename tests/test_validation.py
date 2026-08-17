"""
IMS · server-side validation · test suite.

The point of this layer is that a malformed payload FAILS rather than quietly
producing a plan with a field missing. These tests assert the failure.
"""

import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "generator"))

from ims_contract import CONTRACT_VERSION  # noqa: E402
from validation import PayloadError, validate_payload  # noqa: E402


def minimal():
    return {
        "client_name": "Test Client",
        "age_range": "late 40s",
        "sex": "M",
        "strength_days": 3,
        "cardio_days": 0,
        "fra_priorities": ["Hip IR L+R"],
        "mobility_map": [{"joint": "hip", "direction": "IR", "side": "L",
                          "rating": "yellow"}],
    }


class TestHappyPath(unittest.TestCase):

    def test_minimal_payload_passes(self):
        self.assertEqual(validate_payload(minimal())["warnings"], [])

    def test_empty_object_passes_with_a_warning(self):
        result = validate_payload({})
        self.assertTrue(any("client_name" in w for w in result["warnings"]))

    def test_unknown_field_warns_but_does_not_block(self):
        """Coach OS ships ahead of the generator sometimes. A new field must
        not take the studio down mid-session."""
        payload = minimal()
        payload["some_future_field"] = "whatever"
        result = validate_payload(payload)
        self.assertTrue(any("some_future_field" in w for w in result["warnings"]))


class TestHardFailures(unittest.TestCase):

    def assertRejects(self, payload, needle):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(payload)
        joined = " ".join(ctx.exception.errors).lower()
        self.assertIn(needle.lower(), joined)

    def test_not_an_object(self):
        for bad in ("a string", [1, 2, 3], 42, None):
            with self.subTest(bad=bad):
                with self.assertRaises(PayloadError):
                    validate_payload(bad)

    def test_wrong_type_on_a_list_field(self):
        p = minimal()
        p["constraints"] = "SI_joint_sensitivity"
        self.assertRejects(p, "constraints must be a list")

    def test_wrong_type_on_a_dict_field(self):
        p = minimal()
        p["body_comp"] = ["185 lb"]
        self.assertRejects(p, "body_comp must be an object")

    def test_bad_enum(self):
        p = minimal()
        p["pdf_mode"] = "printer_friendly"
        self.assertRejects(p, "pdf_mode")

    def test_out_of_range_training_days(self):
        p = minimal()
        p["strength_days"] = 9
        self.assertRejects(p, "strength_days must be between")

    def test_more_than_seven_days_in_a_week(self):
        p = minimal()
        p["strength_days"], p["cardio_days"] = 5, 4
        self.assertRejects(p, "more than 7 days")

    def test_bad_mobility_rating(self):
        p = minimal()
        p["mobility_map"] = [{"joint": "hip", "direction": "IR", "side": "L",
                              "rating": "orange"}]
        self.assertRejects(p, "red, yellow or green")

    def test_bad_pain_level(self):
        p = minimal()
        p["constraints_rich"] = [{"key": "bad_knee", "pain_level": 42}]
        self.assertRejects(p, "pain_level must be 0")

    def test_every_error_is_reported_at_once(self):
        """One round trip, not five."""
        p = minimal()
        p["constraints"] = "nope"
        p["strength_days"] = 99
        p["pdf_mode"] = "wat"
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(p)
        self.assertGreaterEqual(len(ctx.exception.errors), 3)


class TestContractGate(unittest.TestCase):

    def test_current_contract_is_accepted(self):
        p = minimal()
        p["contract_version"] = CONTRACT_VERSION
        validate_payload(p)

    def test_previous_major_is_still_accepted(self):
        p = minimal()
        p["contract_version"] = "1.4.0"
        validate_payload(p)

    def test_unknown_major_is_refused(self):
        p = minimal()
        p["contract_version"] = "9.0.0"
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(p)
        self.assertIn("contract_version", ctx.exception.errors[0])


class TestObjectiveMeasureValidation(unittest.TestCase):

    def _with(self, om):
        p = minimal()
        p["objective_measures"] = om
        return p

    def test_valid_block_passes(self):
        validate_payload(self._with({
            "current": {
                "date": "2026-06-14", "bodyweight_lb": 185,
                "dynamo": [{"test": "knee_extension", "side": "L",
                            "value": 60, "unit": "lb"}],
                "rom": [{"joint": "hip", "motion": "ir", "side": "L",
                         "degrees": 22}],
            }}))

    def test_unknown_dynamo_test_is_rejected(self):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(self._with({"current": {
                "dynamo": [{"test": "vibe_check", "value": 40}]}}))
        self.assertIn("unknown test", " ".join(ctx.exception.errors))

    def test_missing_value_is_rejected(self):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(self._with({"current": {
                "dynamo": [{"test": "grip", "side": "L"}]}}))
        self.assertIn("numeric 'value'", " ".join(ctx.exception.errors))

    def test_bad_unit_is_rejected(self):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(self._with({"current": {
                "dynamo": [{"test": "grip", "value": 40, "unit": "stone"}]}}))
        self.assertIn("not lb, kg or N", " ".join(ctx.exception.errors))

    def test_impossible_rom_is_rejected(self):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(self._with({"current": {
                "rom": [{"joint": "hip", "motion": "ir", "degrees": 400}]}}))
        self.assertIn("out of range", " ".join(ctx.exception.errors))

    def test_voltra_needs_a_position(self):
        with self.assertRaises(PayloadError) as ctx:
            validate_payload(self._with({"current": {
                "voltra": [{"pattern": "trap_bar_deadlift", "value": 300}]}}))
        self.assertIn("mid_range or end_range", " ".join(ctx.exception.errors))

    def test_bodyweight_out_of_range_is_rejected(self):
        with self.assertRaises(PayloadError):
            validate_payload(self._with({"current": {
                "bodyweight_lb": 1850,
                "dynamo": [{"test": "grip", "value": 40}]}}))

    def test_previous_dated_after_current_warns(self):
        result = validate_payload(self._with({
            "current": {"date": "2026-01-01",
                        "dynamo": [{"test": "grip", "value": 90}]},
            "previous": {"date": "2026-06-14",
                         "dynamo": [{"test": "grip", "value": 88}]},
        }))
        self.assertTrue(any("dated after" in w for w in result["warnings"]))

    def test_objective_block_must_be_an_object(self):
        with self.assertRaises(PayloadError):
            validate_payload(self._with([{"test": "grip"}]))


class TestApiSurface(unittest.TestCase):
    """The endpoints, exercised through Flask's test client."""

    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.client = app_module.app.test_client()

    def test_version_endpoint(self):
        resp = self.client.get("/api/version")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["contract_version"], CONTRACT_VERSION)

    def test_validate_endpoint_accepts_good_payload(self):
        resp = self.client.post("/api/validate", json=minimal())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["ok"])

    def test_validate_endpoint_rejects_bad_payload(self):
        bad = minimal()
        bad["strength_days"] = 99
        resp = self.client.post("/api/validate", json=bad)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "invalid_payload")

    def test_generate_rejects_bad_payload_with_400_not_500(self):
        """A malformed payload is the caller's problem and must say so.

        Before validation existed this produced either a 500 with a stack
        trace or, worse, a 200 with a plan silently missing an input.
        """
        bad = minimal()
        bad["mobility_map"] = [{"joint": "hip", "rating": "chartreuse",
                                "side": "L", "direction": "IR"}]
        resp = self.client.post("/api/generate", json=bad)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("errors", resp.get_json())

    def test_generate_returns_a_pdf_and_version_headers(self):
        resp = self.client.post("/api/generate", json=minimal())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/pdf")
        self.assertEqual(resp.headers["X-IMS-Contract-Version"], CONTRACT_VERSION)
        self.assertTrue(resp.data.startswith(b"%PDF"))

    def test_generate_with_objective_measures_end_to_end(self):
        payload = minimal()
        payload["pdf_mode"] = "full"
        payload["objective_measures"] = {
            "current": {
                "date": "2026-06-14", "bodyweight_lb": 185,
                "dynamo": [
                    {"test": "knee_extension", "side": "L", "value": 60},
                    {"test": "knee_extension", "side": "R", "value": 95},
                    {"test": "shoulder_er", "side": "L", "value": 14},
                    {"test": "shoulder_er", "side": "R", "value": 24},
                    {"test": "grip", "side": "L", "value": 95},
                    {"test": "grip", "side": "R", "value": 98},
                ],
                "rom": [{"joint": "hip", "motion": "ir", "side": "L",
                         "degrees": 18}],
            },
            "previous": {
                "date": "2026-04-12",
                "dynamo": [{"test": "knee_extension", "side": "L", "value": 50}],
            },
        }
        resp = self.client.post("/api/generate", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestFormServerDrift(unittest.TestCase):
    """The capture form and the server must agree on the vocabulary.

    The server rejects an unknown DynaMo test id with a 400 rather than
    dropping it silently. That is the right behaviour, and it makes drift
    between the form's dropdown and the server's list a hard outage instead
    of a quiet data loss · so it gets a test.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (REPO_ROOT / "web" / "index.html").read_text()

    def _js_list(self, const_name):
        import re
        m = re.search(const_name + r"\s*=\s*\[(.*?)\n\];", self.html, re.S)
        self.assertIsNotNone(m, f"{const_name} not found in the form")
        return re.findall(r"\['([a-z_|]+)',", m.group(1))

    def test_form_dynamo_tests_are_all_known_to_the_server(self):
        from objective_measures import DYNAMO_TESTS
        for test_id in self._js_list("const DYNAMO_TESTS"):
            with self.subTest(test=test_id):
                self.assertIn(test_id, DYNAMO_TESTS,
                              f"form offers '{test_id}', server would 400 on it")

    def test_form_rom_joints_are_canonical(self):
        from objective_measures import canonical_joint
        for pair in self._js_list("const ROM_JOINTS"):
            joint = pair.split("|")[0]
            with self.subTest(joint=joint):
                self.assertIsNotNone(canonical_joint(joint))

    def test_form_rom_motions_have_norms_in_config(self):
        """A ROM reading with no norm in the config can never fire a quadrant.

        Not fatal · it still shows on the measure table. But if the form
        invites a coach to measure something the config cannot classify, that
        is worth knowing about deliberately rather than discovering later.
        """
        from ims_contract import load_thresholds
        norms = load_thresholds()["rom_norms"]
        missing = [p for p in self._js_list("const ROM_JOINTS")
                   if p.replace("|", "_") not in norms]
        self.assertEqual(missing, [],
                         f"form offers ROM measurements with no norm: {missing}")
