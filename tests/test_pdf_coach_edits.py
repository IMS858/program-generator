"""Regression: coach-edited compact exercise fields must reach the generated PDF."""
import io
import unittest

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from generator.plan_pdf import render_block_compact


class PdfCoachEditsTests(unittest.TestCase):
    def test_compact_block_renders_edited_name_dose_tempo_and_progression(self):
        output = io.BytesIO()
        pdf = canvas.Canvas(output)
        render_block_compact(pdf, {
            "name": "Mobility Prep",
            "exercises": [{
                "name": "Edited hip CARs",
                "dose": "2 sets of 4",
                "tempo": "slow control",
                "progression_note": "Increase range when controlled",
            }],
        }, 700, program={"_pdf_mode": "client"})
        pdf.save()
        text = PdfReader(io.BytesIO(output.getvalue())).pages[0].extract_text()
        for expected in (
            "Edited hip CARs", "2 sets of 4", "tempo slow control",
            "Increase range when controlled",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
