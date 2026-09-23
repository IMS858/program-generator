"""Authenticated reviewed-PDF endpoint regression tests."""
import io
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import app as server


class RenderEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()
        self.secret = patch.dict(os.environ, {"PROGRAM_GENERATOR_SECRET": "unit-test-secret"})
        self.secret.start()

    def tearDown(self):
        self.secret.stop()

    def test_requires_bearer_auth(self):
        result = self.client.post("/api/render", json={"program": {}})
        self.assertEqual(result.status_code, 401)

    def test_rejects_incomplete_program(self):
        result = self.client.post("/api/render",
            headers={"Authorization": "Bearer unit-test-secret"},
            json={"program": {"client_name": "Client", "weeks": [{}], "assessment": {}}})
        self.assertEqual(result.status_code, 400)

    def test_renders_reviewed_program_and_disables_cache(self):
        plan = {"client_name": "Test Client", "weeks": [
            {"week_number": 1, "sessions": [{"day_number": 1, "blocks": [
                {"name": "Strength", "exercises": [{"name": "Goblet squat", "dose": "3x8"}]}]}]}],
            "assessment": {}}
        def fake_pdf(_source, destination, pdf_mode):
            self.assertEqual(pdf_mode, "client")
            Path(destination).write_bytes(b"%PDF-1.4\nreviewed")
        with patch.object(server, "generate_plan_pdf", side_effect=fake_pdf):
            result = self.client.post("/api/render",
                headers={"Authorization": "Bearer unit-test-secret"},
                json={"program": plan, "pdf_mode": "client"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["Cache-Control"], "private, no-store")
        import base64
        self.assertTrue(base64.b64decode(result.json["pdf_base64"]).startswith(b"%PDF-"))

if __name__ == "__main__":
    unittest.main()
