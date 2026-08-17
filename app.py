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
# app.py is at the repo ROOT, so parent = repo root
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "generator"))

from generator import (
    Assessment, MobilityRating, Generator, parse_fra_priority
)
from plan_pdf import generate_plan_pdf
from ims_contract import CONTRACT_VERSION, GENERATOR_VERSION, PROTOCOL_VERSION
from validation import PayloadError, validate_payload
from force_load import ImplausibleLoadError
from objective_measures import parse_objective_measures


app = Flask(__name__, static_folder=None)


# ── Static file serving ────────────────────────────────────

@app.route('/')
def index():
    try:
        resp = send_from_directory(str(ROOT / "web"), "index.html")
        # Don't cache the HTML · prevents stale UI sticking after a deploy.
        # Static assets (JS/CSS) are still fine to cache · they're served from
        # the catch-all route below.
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        return Response(f"Home page failed to load: {e}", status=500)


@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    """Handle favicon requests cleanly · return 204 No Content rather than crashing."""
    return Response('', status=204)


@app.route('/<path:filename>')
def static_files(filename):
    """Serve anything else from /web (if present) or /assets.

    Wrapped in try/except · on Vercel's read-only filesystem certain path
    operations can raise, and we don't want that to bubble up as a 500.
    """
    try:
        web_path = ROOT / "web" / filename
        if web_path.exists() and web_path.is_file():
            return send_from_directory(str(ROOT / "web"), filename)
        assets_path = ROOT / "assets" / filename
        if assets_path.exists() and assets_path.is_file():
            return send_from_directory(str(ROOT / "assets"), filename)
    except Exception:
        pass
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

def build_program_pdf(form_data, out_warnings=None):
    """Generate the plan PDF. Returns (pdf_bytes, client_name).

    ``out_warnings`` · optional list the validator's non-blocking warnings are
    appended to. The return signature is unchanged on purpose · several call
    sites and tests unpack a 2-tuple, and a new feature is not a reason to
    break them.
    """
    # ── Validate BEFORE coercing ──────────────────────
    # The parsing below is deliberately forgiving · it has to be, because a
    # half-filled assessment is a normal thing for a coach to submit mid-session.
    # But forgiving parsing on an UNVALIDATED payload means a typo'd field name
    # silently produces a plan missing that input, and nobody finds out. So the
    # strict pass runs first and fails loudly; the forgiving pass runs second on
    # data already known to be structurally sound.
    validation = validate_payload(form_data)
    if out_warnings is not None:
        out_warnings.extend(validation.get('warnings', []))

    if not isinstance(form_data, dict):
        raise ValueError(f"Expected form_data to be a dict, got {type(form_data).__name__}")

    # FRA priorities · must be list of strings
    raw_priorities = form_data.get('fra_priorities', []) or []
    if not isinstance(raw_priorities, list):
        raw_priorities = []
    fra = []
    for p in raw_priorities:
        if isinstance(p, str) and p.strip():
            fra.append(parse_fra_priority(p))
        elif isinstance(p, dict) and p.get('description'):
            # In case someone sends pre-parsed priorities
            fra.append(parse_fra_priority(p['description']))

    # Mobility map · must be list of dicts
    raw_mobility = form_data.get('mobility_map', []) or []
    if not isinstance(raw_mobility, list):
        raw_mobility = []
    mob = []
    for m in raw_mobility:
        if not isinstance(m, dict):
            continue
        try:
            mob.append(MobilityRating(
                joint=str(m.get('joint', '')),
                direction=str(m.get('direction', '')),
                side=str(m.get('side', '')),
                rating=str(m.get('rating', ''))
            ))
        except Exception:
            continue

    # Body comp · must be dict (or empty)
    raw_bc = form_data.get('body_comp', {})
    if not isinstance(raw_bc, dict):
        raw_bc = {}
    body_comp = dict(raw_bc) if raw_bc else {}

    if body_comp and body_comp.get('weight'):
        try:
            activity = float(form_data.get('activity_factor', 1.45) or 1.45)
        except (TypeError, ValueError):
            activity = 1.45
        strategy = form_data.get('nutrition_strategy', 'maintenance') or 'maintenance'
        body_comp = calculate_nutrition(body_comp, activity, strategy)
    else:
        body_comp = {}

    # Guard · strip any leftover 'AUTO' placeholders so PDF renderer doesn't
    # try to call .get() on them. This happens if calculate_nutrition was
    # skipped or bailed early (e.g. lean_mass not a valid number).
    for key in ('rmr_katch_mcardle', 'tdee_estimated', 'nutrition_targets'):
        if body_comp.get(key) == 'AUTO':
            del body_comp[key]

    # Constraints · must be list of strings
    raw_constraints = form_data.get('constraints', []) or []
    constraints = [str(c) for c in raw_constraints if c] if isinstance(raw_constraints, list) else []

    # NEW · Structured constraint data (side, status, pain level, notes)
    raw_constraints_rich = form_data.get('constraints_rich', []) or []
    constraints_rich = []
    if isinstance(raw_constraints_rich, list):
        for cr in raw_constraints_rich:
            if not isinstance(cr, dict):
                continue
            constraints_rich.append({
                'key': str(cr.get('key') or '').strip(),
                'display_name': str(cr.get('display_name') or '').strip(),
                'side': (str(cr.get('side') or '').strip() or None),
                'status': (str(cr.get('status') or '').strip() or None),
                'pain_level': (int(cr.get('pain_level'))
                               if isinstance(cr.get('pain_level'), (int, float))
                                  and 0 <= cr.get('pain_level') <= 10
                               else None),
                'avoid_notes': (str(cr.get('avoid_notes') or '').strip() or None),
                'allowed_notes': (str(cr.get('allowed_notes') or '').strip() or None),
                'coach_notes': (str(cr.get('coach_notes') or '').strip() or None),
            })

    # Status-aware filtering · drop CLEARED constraints from the flat list used
    # by the picker. Coach kept the checkbox to track history, but cleared
    # constraints shouldn't actively filter exercises.
    cleared_keys = {cr['key'] for cr in constraints_rich
                     if (cr.get('status') or '').lower() == 'cleared'}
    if cleared_keys:
        constraints = [c for c in constraints if c not in cleared_keys]

    # NEW · Client concerns · joint flags + free-text notes
    raw_concerns = form_data.get('concerns', []) or []
    concerns = [str(c) for c in raw_concerns if c] if isinstance(raw_concerns, list) else []
    concern_notes = str(form_data.get('concern_notes', '') or '')

    # NEW · Cardio Capacity & Machine Tolerance profile
    try:
        from cardio_profile import parse_cardio_profile
        cardio_profile = parse_cardio_profile(form_data.get('cardio_profile'))
    except Exception:
        cardio_profile = None

    # NEW · accessory categories (Strength C block)
    raw_acc_cats = form_data.get('accessory_categories', []) or []
    accessory_categories = ([str(c) for c in raw_acc_cats if c]
                              if isinstance(raw_acc_cats, list) else [])

    # Strength markers + results
    raw_markers = form_data.get('strength_markers', []) or []
    markers = [str(m) for m in raw_markers if m] if isinstance(raw_markers, list) else []

    raw_results = form_data.get('strength_marker_results', {}) or {}
    if not isinstance(raw_results, dict):
        raw_results = {}
    marker_results = {
        k: (v if isinstance(v, str) else str(v))
        for k, v in raw_results.items()
        if not str(k).endswith('__display')
    }

    # NEW · richer strength test data (optional · empty list means use legacy results only)
    raw_tests = form_data.get('strength_marker_tests', []) or []
    try:
        from strength_testing import parse_strength_tests
        strength_tests = parse_strength_tests(raw_tests)
    except Exception:
        # If parsing fails for any reason, don't crash · just skip the new data
        strength_tests = []

    # Training frequency · parse strength_days + cardio_days separately
    # (fall back to training_frequency if the new fields aren't present)
    try:
        strength_days = int(form_data.get('strength_days', 0) or 0)
    except (TypeError, ValueError):
        strength_days = 0
    try:
        cardio_days = int(form_data.get('cardio_days', 0) or 0)
    except (TypeError, ValueError):
        cardio_days = 0

    if strength_days == 0 and cardio_days == 0:
        # Legacy · single training_frequency field
        try:
            freq = int(form_data.get('training_frequency', 3) or 3)
        except (TypeError, ValueError):
            freq = 3
        # Map old frequency to defaults · 2x = 2 strength / 0 cardio, 3x = 3s/0c, 4x = 3s/1c
        if freq <= 2:
            strength_days, cardio_days = 2, 0
        elif freq == 3:
            strength_days, cardio_days = 3, 0
        else:
            strength_days, cardio_days = 3, 1

    freq = strength_days + cardio_days  # total days (for Assessment back-compat)

    # PDF mode · "client" / "coach" / "full" · default to client if missing
    pdf_mode = str(form_data.get('pdf_mode', 'client') or 'client').lower().strip()
    if pdf_mode not in ('client', 'coach', 'full'):
        pdf_mode = 'client'

    # NEW · optional instrumented assessment (DynaMo / VOLTRA / passive ROM).
    # Absent for most clients. Absent must cost nothing.
    objective_measures = parse_objective_measures(form_data.get('objective_measures'))

    # NEW · Phase 2 individualization inputs. Both optional; both degrade to
    # the legacy ladder when missing.
    training_age_years = form_data.get('training_age_years')
    if training_age_years in ('', None):
        training_age_years = None
    else:
        try:
            training_age_years = float(training_age_years)
        except (TypeError, ValueError):
            training_age_years = None

    assessment = Assessment(
        name=str(form_data.get('client_name', 'Client') or 'Client'),
        age_range=str(form_data.get('age_range', '') or ''),
        sex=str(form_data.get('sex', '') or ''),
        background=str(form_data.get('background', '') or ''),
        training_frequency=freq,
        strength_days=strength_days,
        cardio_days=cardio_days,
        primary_goal=str(form_data.get('primary_goal', '') or ''),
        fra_priorities=fra,
        strength_markers=markers,
        constraints=constraints,
        mobility_map=mob,
        body_comp=body_comp,
        # progression_mode is resolved by the generator from the client's
        # ProgressionProfile · it is no longer a constant, and it is no longer
        # the word "autoregulated", which described something this system does
        # not do.
        strength_marker_results=marker_results,
        strength_marker_tests=strength_tests,
        concerns=concerns,
        concern_notes=concern_notes,
        constraints_rich=constraints_rich,
        pdf_mode=pdf_mode,
        cardio_profile=cardio_profile,
        accessory_categories=accessory_categories,
        # ── Coach OS integration fields ──
        sleep_quality=str(form_data.get('sleep_quality', '') or ''),
        sleep_hours=str(form_data.get('sleep_hours', '') or ''),
        stress_level=str(form_data.get('stress_level', '') or ''),
        desk_hours=str(form_data.get('desk_hours', '') or ''),
        resting_hr=str(form_data.get('resting_hr', '') or ''),
        posture=form_data.get('posture', {}) if isinstance(form_data.get('posture'), dict) else {},
        pain_map=form_data.get('pain_map', {}) if isinstance(form_data.get('pain_map'), dict) else {},
        rom_degrees=form_data.get('rom_degrees', {}) if isinstance(form_data.get('rom_degrees'), dict) else {},
        red_flags=str(form_data.get('red_flags', '') or ''),
        coach_notes=str(form_data.get('coach_notes', '') or ''),
        # ── v2.0 ──
        objective_measures=objective_measures,
        assessment_date=str(form_data.get('assessment_date', '') or ''),
        training_age_years=training_age_years,
        conditioning_level=str(form_data.get('conditioning_level', '') or ''),
    )

    generator = Generator(libraries_path=str(ROOT / "libraries"))
    program = generator.build_program(assessment, block_number=1)

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = str(Path(tmpdir) / "program.json")
        pdf_path = str(Path(tmpdir) / "plan.pdf")
        program.to_json(json_path)
        generate_plan_pdf(program_json=json_path, output_pdf=pdf_path, pdf_mode=pdf_mode)
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
    except Exception as e:
        return jsonify({'error': 'invalid_json', 'errors': [str(e)]}), 400

    warnings = []
    try:
        pdf_bytes, client_name = build_program_pdf(form_data, out_warnings=warnings)
    except PayloadError as e:
        # Structural problem with the payload · nothing was generated. Every
        # error is returned at once so the caller fixes them in one pass.
        return jsonify(e.to_dict()), 400
    except ImplausibleLoadError as e:
        # A computed load was not physically sensible for the equipment. This
        # is deliberately a failure and not a printed number · see force_load.
        return jsonify({
            'error': 'implausible_load',
            'detail': str(e),
            'hint': ('Check the force measurement, the exercise equipment '
                     'tagging, and load_from_force in '
                     'config/objective_thresholds.json.'),
            'contract_version': CONTRACT_VERSION,
        }), 422
    except Exception as e:
        return jsonify({
            'error': str(e),
            'contract_version': CONTRACT_VERSION,
            'trace': traceback.format_exc()
        }), 500

    safe_name = (client_name or 'client').lower().replace(' ', '_')
    safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')

    headers = {
        'Content-Disposition': f'attachment; filename="{safe_name}_plan.pdf"',
        'Access-Control-Allow-Origin': '*',
        'X-IMS-Generator-Version': GENERATOR_VERSION,
        'X-IMS-Contract-Version': CONTRACT_VERSION,
        'X-IMS-Protocol-Version': PROTOCOL_VERSION,
    }
    if warnings:
        # Warnings must not be silent, but they must not block a plan either.
        headers['X-IMS-Warnings'] = ' | '.join(warnings)[:900]
    return Response(pdf_bytes, mimetype='application/pdf', headers=headers)


@app.route('/api/validate', methods=['POST', 'OPTIONS'])
def validate_only():
    """Dry-run the validator without generating a PDF.

    Coach OS can call this on save to surface field problems while the coach is
    still in front of the client, instead of at generate time.
    """
    if request.method == 'OPTIONS':
        return Response('', status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        })
    try:
        form_data = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'invalid_json', 'errors': [str(e)]}), 400
    try:
        result = validate_payload(form_data)
    except PayloadError as e:
        return jsonify(e.to_dict()), 400
    return jsonify({
        'ok': True,
        'contract_version': CONTRACT_VERSION,
        'generator_version': GENERATOR_VERSION,
        'protocol_version': PROTOCOL_VERSION,
        'warnings': result.get('warnings', []),
    }), 200


@app.route('/api/vald/transform', methods=['POST', 'OPTIONS'])
def vald_transform():
    """Turn raw VALD DynaMo test objects into an objective_measures block.

    Coach OS owns the VALD integration · OAuth, the modifiedFromUtc cursor,
    athlete-to-client identity, storage. All of that is stateful and this
    service is not.

    What this endpoint owns is the VOCABULARY. The canonical test ids belong to
    the generator, and a mapping table maintained in two places drifts. So
    Coach OS POSTs the raw tests it pulled and gets back a block it can hand
    straight to /api/generate.

    Body ·
      {"current": [ ...VALD test objects... ],
       "previous": [ ... ],            // optional
       "bodyweight_lb": 185}           // optional

    Unmapped tests are SKIPPED and listed in `warnings`, never fatal · one
    novel movement type must not fail a whole assessment sync.
    """
    if request.method == 'OPTIONS':
        return Response('', status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        })
    try:
        body = request.get_json(force=True)
    except Exception as e:
        return jsonify({'error': 'invalid_json', 'errors': [str(e)]}), 400
    if not isinstance(body, dict):
        return jsonify({'error': 'invalid_payload',
                        'errors': ['body must be an object']}), 400

    from vald_mapping import build_objective_measures, unmapped_tests

    current = body.get('current') or body.get('tests') or []
    previous = body.get('previous') or []
    if not isinstance(current, list) or not isinstance(previous, list):
        return jsonify({'error': 'invalid_payload',
                        'errors': ["'current' and 'previous' must be lists"]}), 400

    warnings = []
    objective = build_objective_measures(
        current, previous, bodyweight_lb=body.get('bodyweight_lb'),
        warnings=warnings)

    result = {
        'objective_measures': objective,
        'warnings': warnings,
        'unmapped': unmapped_tests(list(current) + list(previous)),
        'contract_version': CONTRACT_VERSION,
    }

    # Run the same validation /api/generate would, so a sync problem surfaces
    # here rather than at plan time.
    if objective is not None:
        try:
            validate_payload({'objective_measures': objective})
            result['valid'] = True
        except PayloadError as e:
            result['valid'] = False
            result['errors'] = e.errors
            return jsonify(result), 422
    else:
        result['valid'] = True
    return jsonify(result), 200


@app.route('/api/version', methods=['GET'])
def version():
    """What this deployment is running · useful when a deploy half-lands."""
    return jsonify({
        'generator_version': GENERATOR_VERSION,
        'contract_version': CONTRACT_VERSION,
        'protocol_version': PROTOCOL_VERSION,
    })


# ── Local dev runner ───────────────────────────────────────
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
