"""
IMS · weakest-link emphasis.

Rank normalized force across the tested joints. The lowest one or two bias
exercise selection toward that joint's patterns.

Normalization, in descending order of preference ·

  1. force / bodyweight, compared against the per-test ratio in the threshold
     config. Gives a cross-joint comparable score where 1.0 == the "normal"
     cutoff for that test, so a grip reading and a knee-extension reading can
     be ranked against each other honestly.
  2. force / strongest tested force, when no bodyweight is on file. Ranking
     still works; the absolute claim does not, so it is marked low confidence.

Selection bias only. This never vetoes and never unblocks · it reorders
candidate lists that the contraindication router has already approved. Joint
tagging comes from joint_taxonomy, which is the router's own taxonomy.
"""

from dataclasses import dataclass, asdict
from typing import Optional

from ims_contract import load_thresholds
from joint_taxonomy import joints_loaded_by


@dataclass
class JointScore:
    joint: str
    score: float                 # 1.0 == the "normal" cutoff for that test
    side: str
    test: str
    value_lb: float
    basis: str                   # "bodyweight" | "relative"
    confidence: str              # "high" | "low"
    measured_on: Optional[str] = None

    def evidence(self) -> str:
        side = f" {self.side}" if self.side in ("L", "R") else ""
        d = f", {self.measured_on}" if self.measured_on else ""
        return (f"{self.test.replace('_', ' ')}{side} "
                f"{int(round(self.value_lb))} lb · index {self.score:.2f}{d}")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = self.evidence()
        return d


def rank_joints(objective, cfg: dict = None) -> list:
    """Return JointScore list, weakest first. Empty when not enough data."""
    if objective is None or not objective.has_data():
        return []
    cfg = cfg or load_thresholds()
    current = objective.current
    dynamo = [f for f in current.forces if f.device == "dynamo" and f.joint]
    if not dynamo:
        return []

    wl_cfg = cfg.get("weakest_link", {})
    norms = cfg.get("force_norms", {})
    bw = current.bodyweight_lb

    # Per joint, keep the WEAKEST side · the weak link is a side, not an average.
    per_joint = {}
    for f in dynamo:
        norm = norms.get(f.test) or norms.get("_default", {})
        if bw and norm:
            cutoff = float(norm.get("normal_at_or_above_bw_ratio") or 0) or None
            if not cutoff:
                continue
            score = (f.value_lb / bw) / cutoff
            basis, confidence = "bodyweight", "high"
        else:
            score = None
            basis, confidence = "relative", "low"
        entry = per_joint.get(f.joint)
        candidate = JointScore(
            joint=f.joint, score=score if score is not None else 0.0,
            side=f.side, test=f.test, value_lb=f.value_lb,
            basis=basis, confidence=confidence, measured_on=f.measured_on,
        )
        if score is None:
            candidate.score = f.value_lb  # provisional · rescaled below
        if entry is None or candidate.score < entry.score:
            per_joint[f.joint] = candidate

    scores = list(per_joint.values())
    if not scores:
        return []

    if all(s.basis == "relative" for s in scores):
        strongest = max(s.score for s in scores) or 1.0
        for s in scores:
            s.score = s.score / strongest

    if len(scores) < int(wl_cfg.get("min_tested_joints", 3)):
        # Too few joints to call anything "the weak link" honestly.
        return []

    scores.sort(key=lambda s: s.score)
    return scores


def weak_joints(objective, cfg: dict = None) -> list:
    """The joint names to bias selection toward · weakest first."""
    cfg = cfg or load_thresholds()
    n = int(cfg.get("weakest_link", {}).get("joints_to_emphasize", 2))
    return [s.joint for s in rank_joints(objective, cfg)[:n]]


def bias_candidates(candidates, find_entry, weak, avoid=None) -> list:
    """Reorder an ALREADY-APPROVED candidate list toward the weak joints.

    ``candidates``  · list of exercise names, in the order the picker built them
    ``find_entry``  · callable name -> library entry dict (or None)
    ``weak``        · joint names, weakest first
    ``avoid``       · joints an advisory route says to unload · these sink

    Stable: candidates that score equally keep their original order, so with no
    objective data the list comes back untouched and output is unchanged.
    """
    if not candidates or (not weak and not avoid):
        return list(candidates)

    weak = list(weak or [])
    avoid = set(avoid or [])
    weight = {j: (len(weak) - i) for i, j in enumerate(weak)}

    def rank(item):
        name, idx = item
        entry = find_entry(name)
        joints = joints_loaded_by(entry) if entry else set()
        boost = sum(weight.get(j, 0) for j in joints)
        penalty = 100 if (joints & avoid) else 0
        return (penalty - boost, idx)

    ordered = sorted([(n, i) for i, n in enumerate(candidates)], key=rank)
    return [n for n, _ in ordered]


def emphasis_notes(objective, cfg: dict = None) -> list:
    """Coach-output lines explaining the emphasis, with the measurement."""
    cfg = cfg or load_thresholds()
    n = int(cfg.get("weakest_link", {}).get("joints_to_emphasize", 2))
    out = []
    for s in rank_joints(objective, cfg)[:n]:
        out.append({
            "joint": s.joint,
            "text": (f"{s.joint.title()} is the weakest tested link · "
                     f"exercise selection biased toward {s.joint} patterns."),
            "evidence": s.evidence(),
            "confidence": s.confidence,
            "measured_on": s.measured_on,
        })
    return out


def asymmetries(objective, cfg: dict = None) -> list:
    """Side-to-side gaps above the configured flag threshold."""
    if objective is None or not objective.has_data():
        return []
    cfg = cfg or load_thresholds()
    gate = float(cfg.get("asymmetry", {}).get("flag_pct", 10.0))
    sig = float(cfg.get("asymmetry", {}).get("significant_pct", 15.0))
    current = objective.current

    seen = set()
    out = []
    for f in current.forces:
        if f.device != "dynamo" or f.side not in ("L", "R"):
            continue
        if f.test in seen:
            continue
        other = "R" if f.side == "L" else "L"
        contra = current.force(f.test, other)
        if not contra or not contra.value_lb:
            continue
        seen.add(f.test)
        stronger = max(f.value_lb, contra.value_lb)
        weaker_side = f.side if f.value_lb < contra.value_lb else other
        gap = abs(f.value_lb - contra.value_lb) / stronger * 100.0
        if gap < gate:
            continue
        out.append({
            "test": f.test,
            "joint": f.joint,
            "weak_side": weaker_side,
            "gap_pct": round(gap, 1),
            "significant": gap >= sig,
            "evidence": (f"{f.test.replace('_', ' ')} "
                         f"L {int(round(f.value_lb if f.side == 'L' else contra.value_lb))} lb / "
                         f"R {int(round(f.value_lb if f.side == 'R' else contra.value_lb))} lb"),
            "measured_on": f.measured_on,
        })
    out.sort(key=lambda a: -a["gap_pct"])
    return out
