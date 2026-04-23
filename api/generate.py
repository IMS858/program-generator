"""
IMS plan generator · Vercel serverless function

Receives POST JSON from the web form, builds the program, renders the PDF,
and returns it as a downloadable attachment.
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Make the generator importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from generator import (
    Assessment, MobilityRating, Generator, parse_fra_priority
)
from plan_pdf import generate_plan_pdf


def calculate_nutrition(body_comp, activity_factor, strategy):
    """Katch-McArdle RMR + TDEE + macros."""
    lean_str = body_comp.get('lean_mass', '')
    weight_str = body_comp.get('weight', '')
    try:
        lean_lb = float(''.join(c for c in lean_str if c.isdigit() or c == '.'))
        weight_lb = float(''.join(c for c in weight_str if c.isdigit() or c == '.'))
    except (ValueError, TypeError):
        return body_comp

    lean_kg = lean_lb / 2.2046
    weight_kg = weight_lb / 2.2046
    rmr = 370 + (21.6 * lean_kg)
    tdee = rmr * activity_factor

    if strategy == "fat_loss":
        target_cal, protein_g, carbs_g = tdee - 300, round(lean_lb * 1.0), round(weight_kg * 2.2)
    elif strategy == "endurance":
        target_cal, protein_g, carbs_g = tdee, round(lean_lb * 0.9), round(weight_kg * 4.0)
    elif strategy == "strength":
        target_cal, protein_g, carbs_g = tdee + 200, round(lean_lb * 1.0), round(weight_kg * 3.0)
    else:
        target_cal, protein_g, carbs_g = tdee, round(lean_lb * 0.9), round(weight_kg * 3.0)

    fat_cal = target_cal - (protein_g * 4) - (carbs_g * 4)
    fat_g = max(round(fat_cal / 9), round(weight_lb * 0.3))
    water_oz = round(weight_lb * 0.7)
    water_suffix = "+ 16 oz per run hour" if strategy == "endurance" else "+ 16 oz per training hour"

    body_comp['rmr_katch_mcardle'] = f"{rmr:,.0f} cal/day"
    body_comp['tdee_estimated'] = f"{tdee:,.0f} cal/day"
    body_comp['nutrition_targets'] = {
        "calories": f"{target_cal:,.0f} cal/day",
        "protein": f"{protein_g} g",
        "carbs": f"{carbs_g} g",
        "fat": f"{fat_g} g",
        "water": f"{water_oz} oz baseline · {water_suffix}"
    }
    return body_comp


def build_program_pdf(form_data):
    """Take form JSON, build the program, render a PDF. Returns PDF bytes."""
    # Map the web form data to Assessment
    fra = [parse_fra_priority(p) for p in form_data.get('fra_priorities', []) if p.strip()]

    mob = [
        MobilityRating(
            joint=m['joint'], direction=m['direction'],
            side=m['side'], rating=m['rating']
        )
        for m in form_data.get('mobility_map', [])
    ]

    # Body comp with auto-nutrition
    body_comp = form_data.get('body_comp', {}) or {}
    if body_comp and body_comp.get('weight'):
        body_comp = calculate_nutrition(
            dict(body_comp),
            form_data.get('activity_factor', 1.45),
            form_data.get('nutrition_strategy', 'maintenance')
        )
    else:
        body_comp = {}

    # Constraints + Markers
    constraints = form_data.get('constraints', [])
    markers = form_data.get('strength_markers', [])
    marker_results = form_data.get('strength_marker_results', {})
    # Strip any __display helper keys
    marker_results = {k: v for k, v in marker_results.items() if not k.endswith('__display')}

    assessment = Assessment(
        name=form_data.get('client_name', 'Client'),
        age_range=form_data.get('age_range', ''),
        sex=form_data.get('sex', ''),
        background=form_data.get('background', ''),
        training_frequency=form_data.get('training_frequency', 3),
        primary_goal=form_data.get('primary_goal', ''),
        fra_priorities=fra,
        strength_markers=markers,
        constraints=constraints,
        mobility_map=mob,
        body_comp=body_comp,
        progression_mode="autoregulated",
        strength_marker_results=marker_results
    )

    # Build program
    generator = Generator(libraries_path=str(ROOT / "libraries"))
    program = generator.build_program(assessment, block_number=1)

    # Render PDF to a temp file, read bytes, return
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = str(Path(tmpdir) / "program.json")
        pdf_path = str(Path(tmpdir) / "plan.pdf")

        program.to_json(json_path)
        generate_plan_pdf(program_json=json_path, output_pdf=pdf_path)

        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()

    return pdf_bytes, assessment.name


# ───────────────────────────────────────────────────────────
# VERCEL ENTRY POINT
# ───────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_len)
            form_data = json.loads(raw_body.decode('utf-8'))

            pdf_bytes, client_name = build_program_pdf(form_data)

            safe_name = (client_name or 'client').lower().replace(' ', '_')
            safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')

            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition',
                             f'attachment; filename="{safe_name}_plan.pdf"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)

        except Exception as e:
            err_body = json.dumps({
                'error': str(e),
                'trace': traceback.format_exc()
            }).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
