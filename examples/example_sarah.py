"""
Test client · Sarah · validates the generator handles a completely
different client profile from Matt.

Differences from Matt ·
  - Younger female (early 30s vs Matt's late 40s)
  - Runner (not ex-military)
  - Knee pain focus (different FRA priorities)
  - NO spine constraints (axial loading OK)
  - 2x/week frequency (not 3x)
  - Different strength marker selection
"""
import sys
from pathlib import Path

# Repo-relative imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "generator"))

from generator import (
    Assessment, FRAPriority, MobilityRating, Generator,
    parse_fra_priority
)

sarah = Assessment(
    name="Sarah",
    age_range="early 30s",
    sex="F",
    background="recreational runner · marathon training",
    training_frequency=2,
    primary_goal="Eliminate knee pain during running · build strength foundation · protect for long-term running career",
    fra_priorities=[
        parse_fra_priority("Ankle Dorsiflexion L+R"),
        parse_fra_priority("Hip External Rotation Right"),
        parse_fra_priority("Thoracic Extension"),
    ],
    strength_markers=["goblet_squat", "sl_rdl", "dead_hang", "side_plank_hold"],
    constraints=[],  # No spine constraints · she can do axial loading
    mobility_map=[
        MobilityRating(joint="ankle", direction="dorsiflexion", side="L", rating="yellow"),
        MobilityRating(joint="ankle", direction="dorsiflexion", side="R", rating="red"),
        MobilityRating(joint="hip", direction="ER", side="R", rating="yellow"),
        MobilityRating(joint="hip", direction="IR", side="L", rating="green"),
        MobilityRating(joint="thoracic", direction="extension", side="bilateral", rating="yellow"),
        MobilityRating(joint="shoulder", direction="flexion", side="bilateral", rating="green"),
        MobilityRating(joint="knee", direction="flexion", side="bilateral", rating="yellow"),
    ],
    body_comp={
        "weight": "135 lbs",
        "body_fat": "22%",
        "lean_mass": "105.3 lbs",
        "fat_mass": "29.7 lbs",
        "method": "BOD POD (Siri Model)",
        "assessment_date": "Apr 15, 2026",
        "rmr_katch_mcardle": "1,402 cal/day",
        "tdee_estimated": "2,173 cal/day",
        "nutrition_targets": {
            "calories": "2,150 cal/day",
            "protein": "95 g",
            "carbs": "245 g",
            "fat": "90 g",
            "water": "95 oz (≈3 L) baseline · +16 oz per run hour"
        }
    },
    progression_mode="autoregulated",
    strength_marker_results={
        "goblet_squat": "30 lbs x 8",
        "sl_rdl": "20 lbs x 8 per side",
        "dead_hang": "45 sec",
        "side_plank_hold": "40 sec per side"
    }
)

generator = Generator()
program = generator.build_program(sarah, block_number=1)

out_path = str(REPO_ROOT / "examples" / "sarah_program.json")
program.to_json(out_path)

# Summary
print(f"\n{'='*70}")
print(f"GENERATED · {program.client_name} · Block {program.block_number}")
print(f"{'='*70}")
print(f"Frequency · {sarah.training_frequency}x/week")
print(f"Constraints · {sarah.constraints or 'None (axial loading OK)'}")
print(f"Priorities · {len(sarah.fra_priorities)} FRA items")

for week in program.weeks:
    print(f"\n--- Week {week.week_number} · {week.intent} ---")
    for session in week.sessions:
        print(f"  Day {session.day_number} · {session.focus}")
        for block in session.blocks:
            print(f"    [{block.name}]  · {len(block.exercises)} exercises")
            for ex in block.exercises[:3]:
                tempo = f"  [tempo · {ex.tempo}]" if ex.tempo else ""
                print(f"      · {ex.name} — {ex.dose}{tempo}")

print(f"\nProgram JSON · {out_path}")

# Generate Sarah's PDF plan
from plan_pdf import generate_plan_pdf
pdf_path = str(REPO_ROOT / "examples" / "sarah_plan.pdf")
generate_plan_pdf(program_json=out_path, output_pdf=pdf_path)
