"""
IMS · Vercel Python entrypoint

Flask app that ·
  - Serves web/index.html at /
  - Generates a PDF plan at POST /api/generate

Vercel's Python runtime auto-detects the `app` variable here.
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path
from flask import Flask, request, send_file, send_from_directory, jsonify, Response

# ── Make the generator importable ──────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generator"))

from generator import (
    Assessment, MobilityRating, Generator, parse_fra_priority
)
from plan_pdf import generate_plan_pdf


app = Flask(__name__, static_folder=None)


# ── Static file serving ────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(str(ROOT / "web"), "index.html")


@app.route('/<path:filename>')
def static_files(filename):
    """Serve anything else from /web (if present) or /assets."""
    web_path = ROOT / "web" / filename
    if web_path.exists() and web_path.is_file():
        return send_from_directory(str(ROOT / "web"), filename)
    assets_path = ROOT / "assets" / filename
    if assets_path.exists() and assets_path.is_file():
        return send_from_directory(str(ROOT / "assets"), filename)
    return ('Not found', 404)


# ── Nutrition calculation (Katch-McArdle) ──────────────────

def calculate_nutrition(body_comp, activity_factor, strategy):
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


# ── PDF generation endpoint ────────────────────────────────

def build_program_pdf(form_data):
    fra = [parse_fra_priority(p) for p in form_data.get('fra_priorities', []) if p.strip()]

    mob = [
        MobilityRating(
            joint=m['joint'], direction=m['direction'],
            side=m['side'], rating=m['rating']
        )
        for m in form_data.get('mobility_map', [])
    ]

    body_comp = form_data.get('body_comp', {}) or {}
    if body_comp and body_comp.get('weight'):
        body_comp = calculate_nutrition(
            dict(body_comp),
            form_data.get('activity_factor', 1.45),
            form_data.get('nutrition_strategy', 'maintenance')
        )
    else:
        body_comp = {}

    constraints = form_data.get('constraints', [])
    markers = form_data.get('strength_markers', [])
    marker_results = form_data.get('strength_marker_results', {})
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

    generator = Generator(libraries_path=str(ROOT / "libraries"))
    program = generator.build_program(assessment, block_number=1)

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = str(Path(tmpdir) / "program.json")
        pdf_path = str(Path(tmpdir) / "plan.pdf")
        program.to_json(json_path)
        generate_plan_pdf(program_json=json_path, output_pdf=pdf_path)
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
    return pdf_bytes, assessment.name


@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate():
    # CORS preflight
    if request.method == 'OPTIONS':
        return Response('', status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        })

    try:
        form_data = request.get_json(force=True)
        pdf_bytes, client_name = build_program_pdf(form_data)

        safe_name = (client_name or 'client').lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{safe_name}_plan.pdf"',
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        return jsonify({
            'error': str(e),
            'trace': traceback.format_exc()
        }), 500


# ── Local dev runner ───────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
