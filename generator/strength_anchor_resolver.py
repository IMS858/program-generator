"""
Strength Anchor Resolver · matches tested-anchor data to programmed exercises.

Existing problem ·
  Coach types "3 Point Row 35 lb × 3RM"
  Picker selects "Single Arm Dumbbell Row" from the pool
  Old matcher uses 2-token overlap → ("3 point row" ∩ "single arm dumbbell row") = {row}
  Below threshold → no match → generic RIR appears in the table.

This module fixes that with a real alias system. Public API ·

    normalize_exercise_name(name)
        → lowercase, punctuation-stripped, abbreviation-expanded canonical form

    build_anchor_aliases()
        → dict[str, set[str]] · canonical group name → set of normalized aliases
        Includes ROW / BENCH / PRESS / HINGE / PULL-UP / SQUAT / HIP-THRUST etc.

    resolve_anchor_for_exercise(program_exercise_name, tests)
        → (matched_test, match_method) · method ∈ {"exact","alias","category","fuzzy",None}

    apply_anchor_to_program_exercise(exercise_obj, anchor)
        → mutates the Exercise object to attach 4-week calculated progression
        Honors load_style for display ("lb /hand" vs "lb" vs "stack" etc.)

The resolver is dependency-light · it imports only stdlib + strength_math
(for 4-week calculation). Safe to import from generator.py.
"""

from __future__ import annotations
import re
from typing import Optional


# ─── 1 · NAME NORMALIZATION ──────────────────────────────────

# Common abbreviation expansions. Applied as whole-word replacements
# AFTER lowercasing and punctuation stripping.
_ABBREVIATIONS = {
    "db":           "dumbbell",
    "dbs":          "dumbbells",
    "bb":           "barbell",
    "kb":           "kettlebell",
    "kbs":          "kettlebells",
    "sa":           "single arm",
    "sl":           "single leg",
    "rdl":          "romanian deadlift",
    "rdls":         "romanian deadlifts",
    "bw":           "bodyweight",
    "ohp":          "overhead press",
    "fsq":          "front squat",
    "bsq":          "back squat",
    "pulllups":     "pull ups",   # typo
    "pullup":       "pull up",
    "pullups":      "pull ups",
    "chinup":       "chin up",
    "chinups":      "chin ups",
    "trx":          "trx",        # keep trx as-is
}


def normalize_exercise_name(name: str) -> str:
    """Normalize an exercise name to a canonical form.

    Rules ·
      - lowercase
      - remove punctuation (- _ . , ' " ( ) [ ])
      - collapse whitespace
      - expand short abbreviations (db → dumbbell, sa → single arm, etc.)
      - strip simple trailing 's' on common words (thrusts → thrust,
        deadlifts → deadlift) to bridge user-typed plurals to alias entries

    Returns the normalized string. Empty input returns "".
    """
    if not name:
        return ""
    s = str(name).lower()
    # Strip punctuation we want to ignore (replace with space, then collapse)
    s = re.sub(r"[\-_/\\.,'\"()\[\]]+", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    # Whole-word abbreviation expansion
    tokens = s.split()
    out_tokens = []
    for tok in tokens:
        if tok in _ABBREVIATIONS:
            out_tokens.append(_ABBREVIATIONS[tok])
        else:
            # Strip trailing 's' on common compound-noun heads to bridge plural
            # user input to singular alias. Only strips when the de-pluralized
            # form is a recognized exercise term · prevents over-eager stripping.
            if tok.endswith("s") and len(tok) > 3:
                base = tok[:-1]
                if base in _SINGULAR_FORMS:
                    out_tokens.append(base)
                    continue
            out_tokens.append(tok)
    # Re-join + re-collapse (in case an expansion introduced multi-word like "single arm")
    return re.sub(r"\s+", " ", " ".join(out_tokens)).strip()


# Words where the singular form is the canonical alias term · trailing 's'
# gets stripped during normalization so "Hip Thrusts" → "hip thrust" matches.
_SINGULAR_FORMS = {
    "thrust", "deadlift", "squat", "lunge", "press", "row", "curl", "raise",
    "pulldown", "pullup", "chinup", "carry", "swing", "kick", "drag", "hop",
    "jump", "reach", "rotation", "extension", "flexion", "bridge", "march",
    "drill", "hold", "lift", "twist", "switch", "transition",
}


# ─── 2 · ALIAS SYSTEM ────────────────────────────────────────

# Canonical group name → list of variant phrases that all mean
# "this exercise belongs to this movement family." Each variant is
# normalized via normalize_exercise_name() before matching.
#
# Movement category mapping is also provided so we can fall back to
# category-only matching when neither exact nor alias hits.

_ALIAS_GROUPS_RAW = {
    # ── PULL HORIZONTAL · ROWS ──────────────────────────────
    "row": {
        "category": "pull_horizontal",
        "aliases": [
            "row", "rows",
            "db row", "db rows", "dumbbell row", "dumbbell rows",
            "single arm row", "single arm dumbbell row", "single arm db row",
            "3 point row", "three point row",
            "bench supported row", "chest supported row",
            "incline bench db row", "incline bench row",
            "cable row", "seated row", "seated cable row", "single arm cable row",
            "tbar row", "t bar row", "t-bar row",
            "machine row",
            "trx row", "ring row", "inverted row", "band row",
            "barbell row", "bb row", "pendlay row", "meadows row", "landmine row",
        ],
    },
    # ── PRESS HORIZONTAL · BENCH FAMILY ────────────────────
    "horizontal_press": {
        "category": "press_horizontal",
        "aliases": [
            "bench press", "barbell bench press",
            "db bench press", "dumbbell bench press",
            "flat bench press", "flat db press", "flat dumbbell press",
            "incline bench press", "incline db press", "incline dumbbell press",
            "incline db bench press",
            "decline bench press",
            "single arm db press", "single arm dumbbell press", "sa db press",
            "neutral grip db press", "neutral grip bench press",
            "pushup", "push up", "pushups", "push ups", "push-up",
            "floor press", "db floor press",
            "machine chest press",
        ],
    },
    # ── PRESS VERTICAL · OVERHEAD FAMILY ───────────────────
    "vertical_press": {
        "category": "press_vertical",
        "aliases": [
            "overhead press", "ohp", "military press",
            "shoulder press",
            "db shoulder press", "dumbbell shoulder press",
            "seated db press", "seated dumbbell press",
            "landmine press", "landmine single arm press",
            "single arm landmine press", "sa landmine press",
            "z press",
            "push press",
            "arnold press",
            "kettlebell press", "kb press",
        ],
    },
    # ── PULL VERTICAL · PULLUPS / PULLDOWNS ────────────────
    "vertical_pull": {
        "category": "pull_vertical",
        "aliases": [
            "pull up", "pull ups", "pullup", "pullups", "pull-up", "pull-ups",
            "chin up", "chin ups", "chinup", "chinups",
            "assisted pull up", "assisted pull ups", "assisted pullup",
            "assisted chin up", "band-assisted pull up", "band assisted pull up",
            "band pull up", "neutral grip pull up",
            "lat pulldown", "lat pull down", "pulldown", "pull down",
            "neutral grip pulldown", "neutral grip lat pulldown",
            "single arm lat pulldown",
            "cable pulldown", "machine pulldown",
            "cable pullover", "straight arm pulldown",
            "scap pull up", "dead hang", "active hang",
        ],
    },
    # ── HINGE · DEADLIFT FAMILY ────────────────────────────
    "hinge": {
        "category": "hinge",
        "aliases": [
            "deadlift", "conventional deadlift", "barbell deadlift", "bb deadlift",
            "trap bar deadlift", "trap bar dl", "hex bar deadlift",
            "trap bar deadlift high handles", "trap bar deadlift from blocks",
            "romanian deadlift", "rdl", "rdls",
            "db romanian deadlift", "barbell romanian deadlift",
            "kettlebell romanian deadlift", "kb romanian deadlift",
            "single leg rdl", "sl rdl",
            "bench supported rdl", "bench supported single leg rdl",
            "bench supported sl rdl",
            "kickstand rdl", "b-stance rdl", "b stance rdl",
            "kettlebell single leg rdl", "kb single leg rdl",
            "kettlebell sl rdl", "kb sl rdl",
            "trx single leg rdl", "trx sl rdl", "trx split stance hinge",
            "good morning",
            "stiff leg deadlift", "stiff legged deadlift",
            "sumo deadlift",
            "landmine rdl",
            "cable pull-through", "cable pull through",
            "kettlebell deadlift",
            "back extension", "45 degree back extension",
            "reverse hyper", "reverse hyperextension",
            "hamstring curl", "hamstring curl machine",
            "slider hamstring curl", "swiss ball hamstring curl",
            "nordic hamstring curl",
        ],
    },
    # ── HIP THRUST / BRIDGE FAMILY ─────────────────────────
    "hip_extension": {
        "category": "hinge",  # categorized under hinge for picker purposes
        "aliases": [
            "hip thrust", "hip thrusts",
            "barbell hip thrust", "bb hip thrust", "weighted hip thrust",
            "db hip thrust",
            "b-stance hip thrust", "b stance hip thrust",
            "single-leg hip thrust", "single leg hip thrust", "sl hip thrust",
            "glute bridge", "weighted glute bridge",
            "b-stance glute bridge", "b stance glute bridge",
            "single leg glute bridge", "sl glute bridge",
            "single-leg hip bridge", "single leg hip bridge",
            "foot-elevated hip bridge", "foot elevated hip bridge",
            "foot-elevated single-leg hip bridge",
            "dumbbell hip bridge", "db hip bridge", "banded hip bridge",
            "barbell hip bridge",
            "hamstring bridge",
            "long-lever bridge", "long lever bridge", "long-lever glute bridge",
            "bridge", "bridge single leg", "bridge single double leg",
            "bridge single & double leg", "bridge single and double leg",
            "frog pump",
        ],
    },
    # ── SQUAT FAMILY ───────────────────────────────────────
    "squat": {
        "category": "squat",
        "aliases": [
            "squat", "back squat", "front squat", "high bar squat", "low bar squat",
            "goblet squat",
            "box squat", "high box squat", "low box squat",
            "safety bar box squat",
            "landmine squat",
            "heels-elevated goblet squat", "heels elevated goblet squat",
            "counterbalance squat",
            "trx assisted squat", "trx squat",
            "trx split stance squat", "trx split-stance squat",
            "split squat", "rear foot elevated split squat", "rfe split squat",
            "rear-foot elevated split squat",
            "bulgarian split squat", "trx split squat", "supported split squat",
            "spanish squat", "spanish squat iso",
            "wall sit", "partial wall sit", "wall sit partial range",
            "step up", "step-up", "step ups", "step-ups",
            "step up low box", "step up high box", "lateral step up",
            "controlled step down", "reverse step down", "step down",
            "lunge", "reverse lunge", "alternating reverse lunge", "walking lunge",
            "lateral lunge", "around the world lunge", "cossack squat",
            "pistol squat", "shrimp squat",
            "zercher squat",
            "belt squat",
            "leg press", "leg press partial range",
            "hack squat", "hack squat partial range",
        ],
    },
    # ── LOADED CARRY ───────────────────────────────────────
    "carry": {
        "category": "carry",
        "aliases": [
            "farmer carry", "farmers carry", "farmers walk", "farmer's walk",
            "suitcase carry", "single arm carry",
            "overhead carry", "front rack carry", "offset carry", "marching carry",
            "bottoms-up carry", "bottoms up carry", "waiter carry",
        ],
    },
    # ── CORE / ANTI-EXTENSION ──────────────────────────────
    "core": {
        "category": "core",
        "aliases": [
            "dead bug", "deadbug",
            "deadbug training table", "weighted deadbug", "band-resisted deadbug",
            "heel tap deadbug", "kettlebell pullover deadbug",
            "bird dog", "bird dog row",
            "plank", "rkc plank", "stir the pot",
            "side plank", "side plank short lever", "side plank long lever",
            "copenhagen side plank", "copenhagen plank",
            "copenhagen plank short lever", "copenhagen plank long lever",
            "adductor side plank",
            "pallof press", "pallof hold", "pallof walkout",
            "cable chop", "cable lift", "half-kneeling chop", "half-kneeling lift",
            "ab wheel", "ab rollout",
            "hollow hold",
            "bear crawl", "bear crawl hold",
            "supine march", "glute bridge march",
            "turkish get-up partial",
            "reverse crunch",
        ],
    },
}


# Build: normalized-alias-string → canonical-group-name
def build_anchor_aliases() -> dict[str, str]:
    """Return a flat lookup · normalized alias string → canonical group name.

    For example ·
        build_anchor_aliases()["3 point row"] == "row"
        build_anchor_aliases()["dumbbell row"] == "row"
        build_anchor_aliases()["single arm dumbbell row"] == "row"
    """
    out = {}
    for group, payload in _ALIAS_GROUPS_RAW.items():
        for variant in payload["aliases"]:
            normalized = normalize_exercise_name(variant)
            if normalized:
                out[normalized] = group
    return out


def get_group_category(group: str) -> Optional[str]:
    """Return the canonical movement_category for an alias group, or None."""
    payload = _ALIAS_GROUPS_RAW.get(group)
    return payload.get("category") if payload else None


# Cached at module load
_ALIAS_TABLE: dict[str, str] = build_anchor_aliases()


# ─── 3 · RESOLVER ────────────────────────────────────────────

def _alias_group_for(name: str) -> Optional[str]:
    """Return the alias group for a given exercise name, or None."""
    norm = normalize_exercise_name(name)
    if not norm:
        return None
    # Direct hit
    if norm in _ALIAS_TABLE:
        return _ALIAS_TABLE[norm]
    # Substring containment (in either direction · catches "Single Arm DB Row"
    # vs "single arm dumbbell row" type mismatches that survive normalization)
    for alias_norm, group in _ALIAS_TABLE.items():
        if alias_norm == norm:
            return group
        # Whole-word containment: alias appears as a contiguous run in name, or vice versa
        if (f" {alias_norm} " in f" {norm} " or
                f" {norm} " in f" {alias_norm} "):
            return group
    return None


def _fuzzy_token_score(a: str, b: str) -> float:
    """Token-set similarity · |intersect| / |union| (Jaccard) on stop-stripped tokens.
    Returns 0.0 when either side is empty."""
    STOP = {"a", "the", "and", "or", "of", "with", "to", "for", "single", "double"}
    ta = set(normalize_exercise_name(a).split()) - STOP
    tb = set(normalize_exercise_name(b).split()) - STOP
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def resolve_anchor_for_exercise(program_exercise_name: str,
                                 strength_marker_tests: list,
                                 fuzzy_threshold: float = 0.50) -> tuple[Optional[object], str]:
    """Find the best matching anchor for a given programmed exercise name.

    Match priority (in order, returns first hit) ·
      A. EXACT  · normalized names match perfectly
      B. ALIAS  · both names map to the same alias group (e.g., "row")
      C. CATEGORY · anchor's movement_category matches the alias-group category
                    of the program exercise (e.g., user tested some pull_horizontal,
                    program picked a row variant we don't know about)
      D. FUZZY  · Jaccard token overlap above threshold
      E. UNUSED · no match

    Returns (matched_test_or_None, match_method).
    match_method is one of: "exact", "alias", "category", "fuzzy", None.
    """
    if not program_exercise_name or not strength_marker_tests:
        return (None, None)

    target_norm = normalize_exercise_name(program_exercise_name)
    target_group = _alias_group_for(program_exercise_name)
    target_category = get_group_category(target_group) if target_group else None

    # Pass A · EXACT normalized match
    for t in strength_marker_tests:
        tn = getattr(t, "exercise_name", None)
        if tn and normalize_exercise_name(tn) == target_norm:
            return (t, "exact")

    # Pass B · ALIAS group match
    if target_group:
        for t in strength_marker_tests:
            tn = getattr(t, "exercise_name", None)
            if tn and _alias_group_for(tn) == target_group:
                return (t, "alias")

    # Pass C · CATEGORY match · the test has a movement_category that matches
    # the program exercise's alias-group category
    if target_category:
        for t in strength_marker_tests:
            tcat = getattr(t, "movement_category", None)
            if tcat and tcat == target_category:
                return (t, "category")

    # Pass D · FUZZY Jaccard above threshold
    best_test, best_score = None, 0.0
    for t in strength_marker_tests:
        tn = getattr(t, "exercise_name", None)
        if not tn:
            continue
        s = _fuzzy_token_score(program_exercise_name, tn)
        if s > best_score:
            best_test, best_score = t, s
    if best_test and best_score >= fuzzy_threshold:
        return (best_test, "fuzzy")

    return (None, None)


# ─── 4 · APPLY · attach 4-week loading to a program Exercise ──

# Display per load_style
def _format_load(weight: Optional[float], load_style: Optional[str],
                  load_unit: str = "lb") -> str:
    if weight is None or weight <= 0:
        return ""
    style = (load_style or "total_load").lower()
    unit = load_unit or "lb"
    w_str = f"{weight:.0f}"
    if style == "per_hand":
        return f"{w_str} {unit}/hand"
    if style == "cable_stack":
        return f"stack {w_str}"
    if style == "machine_number":
        return f"machine {w_str}"
    if style == "bodyweight_added":
        return f"+{w_str} {unit}"
    if style == "bodyweight_assisted":
        return f"−{w_str} {unit} assist"
    # default total_load
    return f"{w_str} {unit}"


def apply_anchor_to_program_exercise(exercise, anchor) -> bool:
    """Attach a 4-week calculated progression to `exercise` based on `anchor`.

    Mutates `exercise` in place (sets .week_prescriptions to a list of 4 dicts,
    one per week, each shaped: {"week": N, "sets": int, "reps": int,
    "load_display": str, "intensity_note": str}).

    Returns True if a progression was attached, False if math couldn't run.
    """
    if exercise is None or anchor is None:
        return False

    # Use existing strength_math.generate_4_week_progression to compute weights.
    try:
        from strength_math import generate_4_week_progression
    except Exception:
        return False

    try:
        prog = generate_4_week_progression(anchor, exercise_name=exercise.name)
    except Exception:
        return False

    if not isinstance(prog, dict) or not prog:
        return False

    style = getattr(anchor, "load_style", None)
    unit = getattr(anchor, "load_unit", "lb")

    week_list = []
    for wk in (1, 2, 3, 4):
        entry = prog.get(wk) or prog.get(str(wk)) or {}
        # generate_4_week_progression keys: weight (rounded), reps, sets, intensity_note
        weight = entry.get("weight") or entry.get("load") or entry.get("working_weight")
        sets = entry.get("sets")
        reps = entry.get("reps") or entry.get("target_reps")
        intensity = entry.get("intensity_note") or entry.get("note") or entry.get("rpe") or ""

        load_display = _format_load(weight, style, unit) if weight else ""
        week_list.append({
            "week": wk,
            "sets": sets,
            "reps": reps,
            "load_display": load_display,
            "intensity_note": str(intensity)[:30] if intensity else "",
        })

    exercise.week_prescriptions = week_list
    return True


# ─── 5 · USAGE TRACKING (for coach appendix UNUSED list) ──────

class AnchorUsageTracker:
    """Tracks which anchors got matched + how, so the coach appendix can
    show USED vs UNUSED clearly."""

    def __init__(self, all_tests: list):
        # store id() of test objects so we can de-dup matches
        self._tests = list(all_tests or [])
        self._used: dict[int, dict] = {}  # id(test) -> {test, methods, exercises}
        self._method_history: list[dict] = []  # ordered audit log

    def record_match(self, test, exercise_name: str, method: str):
        if test is None or method is None:
            return
        key = id(test)
        slot = self._used.setdefault(key, {
            "test": test,
            "methods": set(),
            "exercises": [],
        })
        slot["methods"].add(method)
        if exercise_name and exercise_name not in slot["exercises"]:
            slot["exercises"].append(exercise_name)
        self._method_history.append({
            "test_name": getattr(test, "exercise_name", "(unnamed)"),
            "exercise_name": exercise_name,
            "method": method,
        })

    def used(self) -> list[dict]:
        out = []
        for slot in self._used.values():
            test = slot["test"]
            out.append({
                "test_name": getattr(test, "exercise_name", "(unnamed)"),
                "exercises": list(slot["exercises"]),
                "methods": sorted(slot["methods"]),
            })
        return out

    def unused(self) -> list[dict]:
        used_ids = set(self._used.keys())
        out = []
        for t in self._tests:
            if id(t) in used_ids:
                continue
            out.append({
                "test_name": getattr(t, "exercise_name", "(unnamed)"),
                "movement_category": getattr(t, "movement_category", None),
                "tested_summary": _summarize_test(t),
            })
        return out

    def all_methods(self) -> list[dict]:
        """Full audit log · who got matched and how, in order."""
        return list(self._method_history)


def _summarize_test(t) -> str:
    """Render a brief summary like '40 lb × 3RM' from a StrengthTest."""
    for r in (3, 5, 6, 8, 10, 12):
        v = getattr(t, f"tested_{r}rm", None)
        if v:
            unit = getattr(t, "load_unit", "lb")
            return f"{v} {unit} × {r}RM"
    return "no rep max recorded"
