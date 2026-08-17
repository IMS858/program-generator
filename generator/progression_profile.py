"""
IMS · progression profile (Phase 2).

The finding that mattered most in the audit had nothing to do with force data ·
a 68-year-old deconditioned client and a 28-year-old athlete received the same
3×12 → 3×10 → 4×8 → 4×6. That is a larger individualization gap than any
instrument closes, it needs no measured data to fix, and it is a safety issue
before it is a product issue.

This module is the ONE place the ladder is decided. Before it existed the same
fixed ladder was hard-coded in three places ·

    generator._strength_dose
    plan_pdf._WEEK_4_TEMPLATE
    strength_math.WEEK_TEMPLATES

all three now resolve through here, so an individualized plan stays
individualized all the way to the printed cell.

Inputs · age, training age, conditioning level, recovery factor, surgical
history. All optional; every one of them degrades to the legacy ladder when
absent, so a client with a sparse intake gets exactly what they got before.

Ladders and the scoring that selects them live in
config/objective_thresholds.json under "progression".
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from ims_contract import load_thresholds


WEEK_INTENTS = ["Base Volume", "Tempo Control", "Strength Build", "Performance Week"]
WEEK_TEMPO = ["", "3-sec eccentric", "", ""]

# Conservative ladders rename week 4 · there is no peak week for a client who
# should not be peaking.
CONSERVATIVE_WEEK_INTENTS = ["Base Volume", "Tempo Control", "Consolidate", "Consolidate"]


@dataclass
class ProgressionProfile:
    """The resolved individualization decision for one client."""
    ladder_id: str = "_default"
    age: Optional[int] = None
    age_band: Optional[str] = None
    training_age_years: Optional[float] = None
    training_age_band: Optional[str] = None
    conditioning: Optional[str] = None
    score: int = 0
    recovery: float = 1.0
    reasons: list = field(default_factory=list)
    ladders: dict = field(default_factory=dict)   # {"compound": [[s,r],...], ...}
    rpe: list = field(default_factory=list)

    @property
    def progression_mode(self) -> str:
        """A label that is TRUE.

        The old default was "autoregulated", which described a fixed calendar
        with no performance input. It is not autoregulated and calling it that
        on a client-facing document was wrong. These names describe what the
        program actually is.
        """
        if self.ladder_id == "_default":
            return "fixed_4week_block"
        return f"individualized_4week_block · {self.ladder_id}"

    def week_templates(self, exercise_type: str = "compound") -> list:
        """[{week, sets, reps, rpe, tempo, intent}, ...] · 4 entries."""
        rows = self.ladders.get(exercise_type) or self.ladders.get("compound") or []
        intents = (CONSERVATIVE_WEEK_INTENTS if self.ladder_id == "conservative"
                   else WEEK_INTENTS)
        out = []
        for i, pair in enumerate(rows[:4]):
            sets, reps = pair
            out.append({
                "week": i + 1,
                "sets": int(sets),
                "reps": int(reps),
                "rpe": self.rpe[i] if i < len(self.rpe) else "",
                "tempo": WEEK_TEMPO[i] if i < len(WEEK_TEMPO) else "",
                "intent": intents[i] if i < len(intents) else "",
            })
        return out

    def dose(self, week: int, exercise_type: str = "compound") -> tuple:
        """(sets, reps) for one week. Falls back to the legacy pair."""
        for tpl in self.week_templates(exercise_type):
            if tpl["week"] == week:
                return tpl["sets"], tpl["reps"]
        return (3, 10)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["progression_mode"] = self.progression_mode
        return d


# ── input parsing ──────────────────────────────────────────

_AGE_WORDS = {
    "early": 2, "mid": 5, "late": 7,
}


def parse_age(age_range) -> Optional[int]:
    """Turn coach shorthand into a usable number.

    Handles · "47", "late 40s", "mid-50s", "60-65", "68 years", "early 30's".
    Returns None when nothing sensible comes out · the profile then simply
    does not use age.
    """
    if age_range is None:
        return None
    if isinstance(age_range, (int, float)) and not isinstance(age_range, bool):
        a = int(age_range)
        return a if 10 <= a <= 100 else None
    s = str(age_range).strip().lower().replace("'", "")
    if not s:
        return None

    # "60-65" or "60 to 65" · take the midpoint
    span = re.search(r"(\d{2})\s*(?:-|–|to)\s*(\d{2})", s)
    if span:
        a, b = int(span.group(1)), int(span.group(2))
        mid = (a + b) // 2
        return mid if 10 <= mid <= 100 else None

    decade = re.search(r"(\d0)s", s)
    if decade:
        base = int(decade.group(1))
        offset = 5
        for word, off in _AGE_WORDS.items():
            if word in s:
                offset = off
                break
        age = base + offset
        return age if 10 <= age <= 100 else None

    plain = re.search(r"\b(\d{1,3})\b", s)
    if plain:
        a = int(plain.group(1))
        return a if 10 <= a <= 100 else None
    return None


def parse_training_age(assessment) -> Optional[float]:
    """Years of consistent training.

    Prefers the explicit field. Falls back to phrases in the background text ·
    "ex-military", "former college athlete", "lifted for 15 years", "new to
    lifting". Inference is coarse on purpose; it only shifts the score by a
    point.
    """
    explicit = getattr(assessment, "training_age_years", None)
    if explicit not in (None, ""):
        try:
            v = float(explicit)
            if 0 <= v <= 70:
                return v
        except (TypeError, ValueError):
            pass

    text = " ".join(str(getattr(assessment, f, "") or "")
                    for f in ("background", "primary_goal")).lower()
    if not text.strip():
        return None

    yrs = re.search(r"(\d{1,2})\s*(?:\+)?\s*(?:years?|yrs?)", text)
    if yrs:
        v = float(yrs.group(1))
        if 0 <= v <= 70:
            return v

    if any(k in text for k in ("never trained", "new to lifting", "beginner",
                               "first time", "no training history",
                               "hasn't trained", "has not trained")):
        return 0.5
    if any(k in text for k in ("ex-military", "former athlete", "college athlete",
                               "collegiate", "competed", "d1", "athlete",
                               "lifelong lifter", "powerlifter")):
        return 8.0
    if any(k in text for k in ("returning", "getting back", "used to train",
                               "off for", "took time off")):
        return 3.0
    return None


_CONDITIONING_WORDS = {
    "deconditioned": ("deconditioned", "sedentary", "very low", "detrained",
                      "unconditioned", "poor"),
    "well_conditioned": ("well conditioned", "well-conditioned", "high",
                         "athletic", "very active", "excellent"),
    "moderate": ("moderate", "average", "fair", "recreational", "active"),
}


def parse_conditioning(assessment) -> Optional[str]:
    """deconditioned | moderate | well_conditioned, or None.

    Prefers the explicit field, then the cardio profile's own capacity signal,
    then resting HR as a last resort.
    """
    explicit = str(getattr(assessment, "conditioning_level", "") or "").strip().lower()
    if explicit:
        explicit = explicit.replace(" ", "_").replace("-", "_")
        if explicit in ("deconditioned", "moderate", "well_conditioned"):
            return explicit
        for level, words in _CONDITIONING_WORDS.items():
            if any(w.replace(" ", "_") in explicit for w in words):
                return level

    cp = getattr(assessment, "cardio_profile", None)
    for attr in ("conditioning_level", "capacity_level", "fitness_level"):
        val = getattr(cp, attr, None) if cp is not None else None
        if val:
            s = str(val).strip().lower()
            for level, words in _CONDITIONING_WORDS.items():
                if any(w in s for w in words):
                    return level

    rhr = str(getattr(assessment, "resting_hr", "") or "").strip()
    if rhr:
        try:
            hr = int(re.sub(r"[^\d]", "", rhr) or 0)
        except ValueError:
            hr = 0
        if 30 < hr <= 58:
            return "well_conditioned"
        if 58 < hr <= 74:
            return "moderate"
        if hr > 82:
            return "deconditioned"
    return None


def _band(value, bands, key, default=None):
    if value is None:
        return default
    for b in bands:
        if float(value) <= float(b[key]):
            return b["id"]
    return bands[-1]["id"] if bands else default


def _recent_surgery(assessment, months: int) -> bool:
    """post_surgery status in constraints_rich, or surgery language in notes."""
    for cr in (getattr(assessment, "constraints_rich", None) or []):
        if not isinstance(cr, dict):
            continue
        if str(cr.get("status") or "").lower() == "post_surgery":
            return True
    text = " ".join(str(getattr(assessment, f, "") or "")
                    for f in ("concern_notes", "red_flags", "coach_notes")).lower()
    return bool(re.search(r"(post[- ]?op|surgery|replacement|repair)\b", text)) and \
        bool(re.search(r"(recent|weeks ago|month|months ago|202\d)", text))


# ── resolution ─────────────────────────────────────────────

def derive_profile(assessment, recovery: float = 1.0,
                   cfg: dict = None) -> ProgressionProfile:
    """Resolve one client's ladder. Never raises."""
    try:
        cfg = cfg or load_thresholds()
    except Exception:
        cfg = {}
    pcfg = (cfg.get("progression") or {})
    ladders = pcfg.get("ladders") or {}
    sel = pcfg.get("ladder_selection") or {}

    profile = ProgressionProfile(recovery=float(recovery or 1.0))

    age = parse_age(getattr(assessment, "age_range", None))
    tage = parse_training_age(assessment)
    cond = parse_conditioning(assessment)

    profile.age = age
    profile.training_age_years = tage
    profile.conditioning = cond
    profile.age_band = _band(age, pcfg.get("age_bands") or [], "max_age")
    profile.training_age_band = _band(tage, pcfg.get("training_age_bands") or [],
                                      "max_years")

    unknown = int(sel.get("unknown_points", 0))
    score = 0
    score += int((sel.get("age_points") or {}).get(profile.age_band, unknown))
    score += int((sel.get("training_age_points") or {}).get(profile.training_age_band, unknown))
    score += int((sel.get("conditioning_points") or {}).get(cond, unknown))
    profile.score = score

    thresholds = sel.get("thresholds") or {}
    cons_at = int(thresholds.get("conservative_at_or_below", -1))
    aggr_at = int(thresholds.get("aggressive_at_or_above", 4))

    if score <= cons_at:
        ladder_id = "conservative"
    elif score >= aggr_at:
        ladder_id = "aggressive"
    else:
        ladder_id = "moderate"

    if age is not None:
        profile.reasons.append(f"age {age}")
    if tage is not None:
        profile.reasons.append(f"training age ~{tage:g}y")
    if cond:
        profile.reasons.append(f"conditioning {cond.replace('_', ' ')}")

    # ── hard downshifts · non-negotiable, regardless of score ──
    hard = pcfg.get("hard_conservative_rules") or {}
    age_gate = hard.get("age_at_or_above")
    if age_gate is not None and age is not None and age >= int(age_gate):
        if ladder_id != "conservative":
            profile.reasons.append(f"age {age} forces the conservative ladder")
        ladder_id = "conservative"
    if cond in (hard.get("conditioning") or []):
        if ladder_id != "conservative":
            profile.reasons.append("deconditioned forces the conservative ladder")
        ladder_id = "conservative"
    surg_months = hard.get("post_surgery_within_months")
    if surg_months and _recent_surgery(assessment, int(surg_months)):
        if ladder_id != "conservative":
            profile.reasons.append("post-surgical status forces the conservative ladder")
        ladder_id = "conservative"

    # ── recovery downshift · sleep / stress / resting HR ──
    downshift_below = float(pcfg.get("recovery_downshift_below", 0.85))
    if profile.recovery < downshift_below:
        order = ["conservative", "moderate", "aggressive"]
        if ladder_id in order and order.index(ladder_id) > 0:
            ladder_id = order[order.index(ladder_id) - 1]
            profile.reasons.append(
                f"recovery factor {profile.recovery:.2f} · one step more conservative")

    # Nothing known about this client · keep the legacy ladder exactly, so a
    # sparse intake produces byte-identical output to the previous build.
    if age is None and tage is None and cond is None and profile.recovery >= downshift_below:
        ladder_id = "_default"
        profile.reasons.append("no age, training age or conditioning on file · legacy ladder")

    chosen = ladders.get(ladder_id) or ladders.get("_default") or {}
    profile.ladder_id = ladder_id if chosen else "_default"
    profile.ladders = {
        "compound": chosen.get("compound") or [[3, 12], [3, 10], [4, 8], [4, 6]],
        "accessory": chosen.get("accessory") or [[3, 12], [3, 10], [4, 10], [4, 8]],
        "corrective": chosen.get("corrective") or [[3, 12], [3, 12], [3, 12], [3, 12]],
    }
    profile.rpe = chosen.get("rpe") or ["7", "7-8", "8", "8-9"]
    return profile


def legacy_profile(cfg: dict = None) -> ProgressionProfile:
    """The pre-Phase-2 ladder, for callers with no assessment in hand."""
    try:
        cfg = cfg or load_thresholds()
        chosen = ((cfg.get("progression") or {}).get("ladders") or {}).get("_default") or {}
    except Exception:
        chosen = {}
    p = ProgressionProfile(ladder_id="_default")
    p.ladders = {
        "compound": chosen.get("compound") or [[3, 12], [3, 10], [4, 8], [4, 6]],
        "accessory": chosen.get("accessory") or [[3, 12], [3, 10], [4, 10], [4, 8]],
        "corrective": chosen.get("corrective") or [[3, 12], [3, 12], [3, 12], [3, 12]],
    }
    p.rpe = chosen.get("rpe") or ["7", "7-8", "8", "8-9"]
    return p
