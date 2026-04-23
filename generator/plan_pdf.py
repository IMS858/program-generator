"""
IMS BODY & MOVEMENT PLAN PDF v3.0
===================================
Aesthetic matches imsmethod.com ·
  - Deep navy canvas (#0B1E31)
  - Sky blue accents (#3477BB)
  - Cream body text (#EBEEF4)
  - Lora serif display with italic blue emphasis
  - Poppins sans-serif for labels (small caps)
  - Editorial, sophisticated, dark
  - 15 pages · adds 3 program session pages (one per training day, Week 1)
"""

import json
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def _find_font(filenames):
    """Search common font locations + the repo's fonts/ folder."""
    repo_fonts = Path(__file__).resolve().parent.parent / "fonts"
    search_paths = [
        repo_fonts,
        Path("/usr/share/fonts/truetype/google-fonts"),
        Path("/usr/share/fonts/truetype"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
        Path("C:/Windows/Fonts"),
    ]
    for base in search_paths:
        if not base.exists():
            continue
        for fname in filenames:
            # Direct match
            direct = base / fname
            if direct.exists():
                return str(direct)
            # Recursive search (limited depth)
            try:
                for path in base.rglob(fname):
                    return str(path)
            except (PermissionError, OSError):
                continue
    return None


# Register Lora + Poppins with fallbacks
_lora = _find_font(["Lora-Variable.ttf", "Lora-Regular.ttf", "Lora-VariableFont_wght.ttf"])
_lora_italic = _find_font(["Lora-Italic-Variable.ttf", "Lora-Italic.ttf", "Lora-Italic-VariableFont_wght.ttf"])

if _lora and _lora_italic:
    try:
        pdfmetrics.registerFont(TTFont('Lora', _lora))
        pdfmetrics.registerFont(TTFont('Lora-Italic', _lora_italic))
        SERIF = "Lora"
        SERIF_ITALIC = "Lora-Italic"
    except Exception:
        SERIF = "Times-Roman"
        SERIF_ITALIC = "Times-Italic"
else:
    SERIF = "Times-Roman"
    SERIF_ITALIC = "Times-Italic"

_poppins = _find_font(["Poppins-Regular.ttf"])
_poppins_bold = _find_font(["Poppins-Bold.ttf"])
_poppins_light = _find_font(["Poppins-Light.ttf"])
_poppins_medium = _find_font(["Poppins-Medium.ttf"])

if _poppins and _poppins_bold and _poppins_light and _poppins_medium:
    try:
        pdfmetrics.registerFont(TTFont('Poppins', _poppins))
        pdfmetrics.registerFont(TTFont('Poppins-Bold', _poppins_bold))
        pdfmetrics.registerFont(TTFont('Poppins-Light', _poppins_light))
        pdfmetrics.registerFont(TTFont('Poppins-Medium', _poppins_medium))
        SANS = "Poppins"
        SANS_BOLD = "Poppins-Bold"
        SANS_LIGHT = "Poppins-Light"
        SANS_MEDIUM = "Poppins-Medium"
    except Exception:
        SANS = "Helvetica"
        SANS_BOLD = "Helvetica-Bold"
        SANS_LIGHT = "Helvetica"
        SANS_MEDIUM = "Helvetica-Bold"
else:
    SANS = "Helvetica"
    SANS_BOLD = "Helvetica-Bold"
    SANS_LIGHT = "Helvetica"
    SANS_MEDIUM = "Helvetica-Bold"

# ==========================================================
# PAGE + PALETTE
# ==========================================================

PAGE_W, PAGE_H = LETTER
MARGIN = 0.5 * inch
CONTENT_W = PAGE_W - 2 * MARGIN

# Exact palette from imsmethod.com
NAVY = HexColor("#0B1E31")           # canvas
NAVY_DEEP = HexColor("#060D18")      # darker sections
NAVY_SOFT = HexColor("#16304D")      # slightly lifted
SKY_BLUE = HexColor("#3477BB")       # accent blue (italic emphasis, buttons)
SKY_LIGHT = HexColor("#5F9BD5")      # lighter accent
CREAM = HexColor("#EBEEF4")          # primary text
CREAM_DIM = HexColor("#A8B2C4")      # secondary text, dim label
GHOST = HexColor("#1A2F4A")          # watermark layer
DIVIDER = HexColor("#2A4468")        # thin rule lines

# Traffic light colors (mobility map) — kept distinct
LIMITED = HexColor("#E25C45")        # muted red-orange (harmonizes with navy)
MODERATE = HexColor("#D4A836")       # muted amber
OPTIMAL = HexColor("#4CA98A")        # muted green

# Assets
ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO_FULL = str(ASSETS / "ims_logo_tight.png")
LOGO_WHITE = str(ASSETS / "ims_logo_white.png")


# ==========================================================
# HELPERS
# ==========================================================

def draw_logo(c, x_center, y, width, variant="white"):
    path = LOGO_WHITE if variant == "white" else LOGO_FULL
    try:
        img = ImageReader(path)
        iw, ih = img.getSize()
        h = width * (ih / iw)
        c.drawImage(img, x_center - width / 2, y, width=width, height=h, mask='auto')
    except Exception:
        c.setFillColor(SKY_BLUE)
        c.setFont(SERIF, 26)
        c.drawCentredString(x_center, y, "iMS")


def wrap(c, text, font, size, max_w):
    words = text.split()
    lines, curr = [], ""
    for w in words:
        test = f"{curr} {w}".strip()
        if c.stringWidth(test, font, size) <= max_w:
            curr = test
        else:
            if curr:
                lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines


def draw_wrapped(c, text, x, y, w, font, size, leading=None, color=None):
    leading = leading or size * 1.4
    if color:
        c.setFillColor(color)
    c.setFont(font, size)
    for line in wrap(c, text, font, size, w):
        c.drawString(x, y, line)
        y -= leading
    return y


def shorten(name, max_chars=22):
    replacements = [
        ("Front Foot Elevated", "FFE"), ("Single-Leg", "SL"), ("Single Leg", "SL"),
        ("Romanian Deadlift", "RDL"), ("Assisted", "Asst"),
        ("External Rotation", "ER"), ("Internal Rotation", "IR"),
        ("Dumbbell", "DB"), ("Kettlebell", "KB"),
    ]
    s = name
    for long, abbr in replacements:
        s = s.replace(long, abbr)
    if len(s) <= max_chars:
        return s
    t = s[:max_chars - 1]
    last = t.rfind(" ")
    if last > max_chars // 2:
        t = t[:last]
    return t + "…"


def fill_page(c, color=None):
    """Default fills the page NAVY."""
    c.setFillColor(color or NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def ghost_watermark(c, letters="ims"):
    """Ghost 'ims' letters in background, like the website."""
    c.saveState()
    c.setFillColor(GHOST)
    c.setFont(f"{SERIF_ITALIC}", 280)
    c.drawString(PAGE_W - 340, 140, letters)
    c.restoreState()


def page_header_bar(c, vol_label, right_label="EST. 2020"):
    """Top bar · VOL. 01 · LOCATION — — EST. 2020"""
    y = PAGE_H - MARGIN - 4
    # Small caps label left
    c.setFillColor(SKY_BLUE)
    c.setFont(SANS_MEDIUM, 9)
    c.drawString(MARGIN, y, vol_label.upper())
    # Right label
    c.setFillColor(CREAM_DIM)
    c.drawRightString(PAGE_W - MARGIN, y, right_label)
    # Thin divider in middle
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.6)
    left_w = c.stringWidth(vol_label.upper(), SANS_MEDIUM, 9)
    right_w = c.stringWidth(right_label, SANS_MEDIUM, 9)
    line_start = MARGIN + left_w + 20
    line_end = PAGE_W - MARGIN - right_w - 20
    c.line(line_start + (line_end - line_start) * 0.4, y + 3,
           line_start + (line_end - line_start) * 0.6, y + 3)


def small_caps_label(c, text, x, y, color=None, size=9, font=None):
    """Small-caps sans label."""
    c.setFillColor(color or SKY_BLUE)
    c.setFont(font or SANS_MEDIUM, size)
    c.drawString(x, y, text.upper())


def editorial_header(c, h1, h1_italic=None, h2=None):
    """Serif display header block (like Move better / Get stronger / Stay active)."""
    y = PAGE_H - MARGIN - 140
    c.setFillColor(CREAM)
    c.setFont(SERIF, 52)
    c.drawString(MARGIN, y, h1)
    y -= 58
    if h1_italic:
        c.setFillColor(SKY_BLUE)
        c.setFont(SERIF_ITALIC, 52)
        c.drawString(MARGIN + 30, y, h1_italic)
        y -= 58
    if h2:
        c.setFillColor(CREAM)
        c.setFont(SERIF, 52)
        c.drawString(MARGIN, y, h2)
    return y


def pill_button(c, text, x, y, width=260, height=38, filled=True, arrow=False):
    """Flat blue button or outlined button · like BOOK A FREE ASSESSMENT."""
    if filled:
        c.setFillColor(SKY_BLUE)
        c.rect(x, y, width, height, fill=1, stroke=0)
        text_color = CREAM
    else:
        c.setStrokeColor(CREAM)
        c.setLineWidth(1.2)
        c.rect(x, y, width, height, fill=0, stroke=1)
        text_color = CREAM
    c.setFillColor(text_color)
    c.setFont(SANS_MEDIUM, 10)
    # Spaced letters feel
    label = text.upper()
    text_w = c.stringWidth(label, SANS_MEDIUM, 10)
    arrow_w = c.stringWidth("  →", SANS_MEDIUM, 10) if arrow else 0
    c.drawString(x + (width - text_w - arrow_w) / 2, y + height / 2 - 4, label)
    if arrow:
        c.drawString(x + (width + text_w) / 2, y + height / 2 - 4, "  →")


def thin_divider(c, x1, y, x2, color=None, width=0.8):
    c.setStrokeColor(color or DIVIDER)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)


def card(c, x, y, w, h, fill=None, border=None, border_w=1):
    """Dark card for content — subtle lift from the navy bg."""
    if fill is None:
        fill = NAVY_SOFT
    c.setFillColor(fill)
    c.rect(x, y, w, h, fill=1, stroke=0)
    if border:
        c.setStrokeColor(border)
        c.setLineWidth(border_w)
        c.rect(x, y, w, h, fill=0, stroke=1)


def page_footer(c, page_num, total):
    """Editorial footer · small-caps pagination + subtle logo."""
    y = MARGIN - 2
    c.setFillColor(CREAM_DIM)
    c.setFont(SANS_MEDIUM, 8)
    c.drawString(MARGIN, y, f"PG. {page_num:02d} / {total:02d}")
    c.drawRightString(PAGE_W - MARGIN, y, "imsmethod.com".upper())
    # Mini logo center
    draw_logo(c, PAGE_W / 2, y - 4, 30, variant="white")


# ==========================================================
# PAGE 1 · COVER
# ==========================================================

def draw_cover(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")

    # Top bar · VOL number, location, est
    page_header_bar(c, f"VOL. 01  ·  SCRIPPS RANCH, CA", "EST. 2020")

    # Logo top-left (white variant, small · fits between top bar and small-caps label)
    draw_logo(c, MARGIN + 40, PAGE_H - MARGIN - 80, 70, variant="white")

    # Small-caps meta line mid-upper
    small_caps_label(c, f"BLOCK {program['block_number']}  ·  FOR {program['client_name'].upper()}",
                     MARGIN, PAGE_H - MARGIN - 140, color=SKY_BLUE, size=10)

    # Hero serif display — three lines with italic blue middle line
    y = PAGE_H / 2 + 100
    c.setFillColor(CREAM)
    c.setFont(SERIF, 62)
    c.drawString(MARGIN, y, "Body &")
    y -= 72
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 62)
    c.drawString(MARGIN + 40, y, "Movement")
    y -= 72
    c.setFillColor(CREAM)
    c.setFont(SERIF, 62)
    c.drawString(MARGIN, y, "Plan.")

    # Italic serif subheading
    y -= 90
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 16)
    intro = ("A personalized training blueprint built around how you move, "
             "what you need, and where you're going.")
    draw_wrapped(c, intro, MARGIN, y, CONTENT_W * 0.75,
                 SERIF_ITALIC, 16, leading=22, color=CREAM_DIM)

    # CTA-style buttons bottom
    btn_y = MARGIN + 90
    pill_button(c, "Your Plan Begins Here", MARGIN, btn_y, width=260, height=42,
                filled=True, arrow=True)
    pill_button(c, f"Block {program['block_number']}  ·  Weeks 1-4", MARGIN + 280, btn_y,
                width=200, height=42, filled=False)

    # Footer thin line + signature
    thin_divider(c, MARGIN, MARGIN + 40, PAGE_W - MARGIN)
    c.setFillColor(CREAM_DIM)
    c.setFont(SANS_MEDIUM, 8)
    c.drawString(MARGIN, MARGIN + 22, "INNOVATIVE MOVEMENT SOLUTIONS")
    c.drawRightString(PAGE_W - MARGIN, MARGIN + 22, "(619) 937-1434")


# ==========================================================
# PAGE 2 · QUOTE / OPENING
# ==========================================================

QUOTES = {
    "starting": ("Start where you are.", "Use what you have.", "Do what you can.", "— Arthur Ashe"),
    "mid": ("Discipline is choosing", "between what you want now", "and what you want most.", "— Abraham Lincoln"),
}


def draw_quote(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "EPIGRAPH  ·  AT THE START", f"BLOCK {program['block_number']}")

    phase = "starting" if program['block_number'] == 1 else "mid"
    l1, l2, l3, attrib = QUOTES[phase]

    # Logo top-left

    # Big serif quote · three lines, italic emphasis middle
    y = PAGE_H / 2 + 100
    # Opening quote mark
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF, 100)
    c.drawString(MARGIN, y + 40, '"')

    y = PAGE_H / 2 + 80
    c.setFillColor(CREAM)
    c.setFont(SERIF, 46)
    c.drawString(MARGIN + 50, y, l1)
    y -= 56
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 46)
    c.drawString(MARGIN + 50, y, l2)
    y -= 56
    c.setFillColor(CREAM)
    c.setFont(SERIF, 46)
    c.drawString(MARGIN + 50, y, l3)

    # Attribution with thin rule
    y -= 60
    thin_divider(c, MARGIN + 50, y + 8, MARGIN + 100, color=SKY_BLUE, width=1.5)
    c.setFillColor(CREAM_DIM)
    c.setFont(SANS_MEDIUM, 10)
    c.drawString(MARGIN + 120, y + 4, attrib.replace("— ", "").upper())


# ==========================================================
# PAGE 3 · WELCOME
# ==========================================================

def draw_welcome(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 01  ·  WELCOME", program['client_name'].upper())


    # Editorial header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 48)
    c.drawString(MARGIN, y, "Welcome,")
    y -= 56
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 48)
    c.drawString(MARGIN, y, f"{program['client_name']}.")

    # Italic serif body paragraphs
    y -= 70
    paras = [
        ("What you're holding isn't a fitness plan. It's a blueprint for how we'll help "
         "you feel stronger, move better, and live more fully."),
        ("This plan was created specifically for you — based on how your body moves, your "
         "health data, and most importantly, your goals. Every section connects."),
        ("This isn't about perfection. It's about progress, consistency, and learning to "
         "trust your body again.")
    ]
    for p in paras:
        y = draw_wrapped(c, p, MARGIN, y, CONTENT_W - 80, SERIF_ITALIC, 15,
                         leading=22, color=CREAM)
        y -= 10

    # Thin divider then signature line
    y -= 20
    thin_divider(c, MARGIN, y, MARGIN + 80, color=SKY_BLUE, width=1.5)
    y -= 20
    c.setFillColor(SKY_BLUE)
    c.setFont(SANS_MEDIUM, 11)
    c.drawString(MARGIN, y, "LET'S GET TO WORK.")


# ==========================================================
# PAGE 4 · THE GOALS
# ==========================================================

def draw_goals(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 02  ·  THE GOALS", program['client_name'].upper())

    # Editorial header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "What we're")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "building together.")

    assessment = program['assessment']

    # Three section blocks — dark cards with small caps label + serif body
    y -= 70
    sections = [
        ("THE GOAL", assessment.get('primary_goal', '')),
        ("WHY IT MATTERS", compose_why(assessment)),
        ("HOW WE MEASURE", compose_measures(assessment)),
    ]

    for label, content in sections:
        small_caps_label(c, label, MARGIN, y, color=SKY_BLUE, size=10)
        # Rule under label
        lw = c.stringWidth(label.upper(), SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 22
        # Content
        y = draw_wrapped(c, content, MARGIN, y, CONTENT_W, SERIF, 12.5,
                         leading=18, color=CREAM)
        y -= 28


def compose_why(a):
    age = a.get('age_range', 'your age').strip()
    bg = a.get('background', 'an active adult')
    return (f"At {age}, your body needs a smarter approach. These goals aren't about cosmetic "
            f"changes — they're about protecting your movement capacity for the long game. "
            f"Your background as {bg} means you've earned the right to train in a way that "
            f"respects what your body's already done and prepares it for what's coming.")


def compose_measures(a):
    names = {
        "inverted_rows": "Inverted Rows", "incline_pushups": "Incline Pushups",
        "lat_pulldown": "Lat Pulldown", "landmine_sa_press": "Landmine SA Press",
        "goblet_squat": "Goblet Squat", "sl_rdl": "Single-Leg RDL",
        "dead_hang": "Dead Hang", "side_plank_hold": "Side Plank Hold",
    }
    markers = a.get('strength_markers', [])
    display = [names.get(m, m.replace("_", " ").title()) for m in markers[:4]]
    return (f"Re-tested every 4 weeks · {', '.join(display)}. Plus a full mobility "
            f"re-screen, plus energy and sleep tracking. Progress shows up in many forms — "
            f"stronger lifts, smoother movement, better sleep, fewer aches.")


# ==========================================================
# PAGE 5 · BODY COMP
# ==========================================================

def draw_body_comp(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 03  ·  BODY COMPOSITION", program['client_name'].upper())

    # Header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "What the")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "numbers say.")

    bc = program['assessment'].get('body_comp', {}) or {}

    # Stats grid · 3 x 2 · BOD POD measurements (row 1) + derived metabolic (row 2)
    y -= 80
    stats = [
        ("WEIGHT", bc.get('weight', '—')),
        ("BODY FAT", bc.get('body_fat', '—')),
        ("LEAN MASS", bc.get('lean_mass', '—')),
        ("FAT MASS", bc.get('fat_mass', '—')),
        ("RMR (KATCH-McARDLE)", bc.get('rmr_katch_mcardle', '—')),
        ("TDEE ESTIMATED", bc.get('tdee_estimated', '—')),
    ]
    cell_w = CONTENT_W / 3
    cell_h = 90
    for i, (label, val) in enumerate(stats):
        row = i // 3
        col = i % 3
        x = MARGIN + col * cell_w
        cy = y - row * cell_h
        # Small caps label top
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 8)
        c.drawString(x, cy, label)
        # Divider
        thin_divider(c, x, cy - 6, x + cell_w - 20, color=DIVIDER)
        # Serif value
        c.setFillColor(CREAM)
        # Scale font size if value is long
        val_str = str(val)
        font_size = 26 if len(val_str) < 12 else 20 if len(val_str) < 16 else 16
        c.setFont(SERIF, font_size)
        c.drawString(x, cy - 40, val_str)

    # Method badge
    y -= 220
    method = bc.get('method', '')
    if method:
        c.setFillColor(CREAM_DIM)
        c.setFont(SANS_MEDIUM, 8)
        c.drawString(MARGIN, y, f"MEASUREMENT METHOD  ·  {method.upper()}")
        y -= 18

    # Insights
    small_caps_label(c, "THE INSIGHTS", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("THE INSIGHTS", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
    y -= 22
    insights = ("Your body comp gives us a baseline to track real change — not weight "
                "swings, but lean mass and body fat as you progress. The RMR uses the "
                "Katch-McArdle formula (driven by lean mass), which is more accurate than "
                "weight-only estimators. We'll re-test at Week 12.") if bc else \
               "Body comp testing is scheduled. Insights will be filled in after your first assessment."
    draw_wrapped(c, insights, MARGIN, y, CONTENT_W, SERIF, 12, leading=18, color=CREAM)

    # Assessment date footer
    if bc.get('assessment_date'):
        c.setFillColor(CREAM_DIM)
        c.setFont(SANS_MEDIUM, 8)
        c.drawRightString(PAGE_W - MARGIN, MARGIN + 60,
                          f"ASSESSED  ·  {bc['assessment_date'].upper()}")


# ==========================================================
# PAGE 6 · MOBILITY ASSESSMENT
# ==========================================================

def draw_mobility_assessment(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 04  ·  MOBILITY ASSESSMENT", program['client_name'].upper())

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Your joints,")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "mapped.")

    priorities = program['assessment'].get('fra_priorities', [])

    # THE FINDINGS
    y -= 70
    small_caps_label(c, "THE FINDINGS", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("THE FINDINGS", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 12)
    c.drawString(MARGIN, y, "Priority joints requiring focused work ·")
    y -= 24

    c.setFont(SERIF, 13)
    for p in priorities[:5]:
        desc = p.get('description', '') if isinstance(p, dict) else str(p)
        # Numbered
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 10)
        idx = priorities.index(p) + 1 if isinstance(p, dict) else 1
        c.drawString(MARGIN, y, f"0{idx}")
        c.setFillColor(CREAM)
        c.setFont(SERIF, 13)
        c.drawString(MARGIN + 32, y, desc)
        y -= 22

    # WHAT IT MEANS
    y -= 16
    small_caps_label(c, "WHAT IT MEANS", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("WHAT IT MEANS", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22
    means = ("These aren't arbitrary. They're the joint-level gaps with the biggest "
             "downstream impact on your daily movement. Fix these and everything else "
             "gets easier — walking, sitting, reaching, lifting.")
    y = draw_wrapped(c, means, MARGIN, y, CONTENT_W, SERIF, 12.5, leading=18, color=CREAM)

    # DAILY MOBILITY ROUTINE
    y -= 20
    small_caps_label(c, "YOUR DAILY MOBILITY ROUTINE", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("YOUR DAILY MOBILITY ROUTINE", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    items = [
        "Passive stretch · 2 min at priority joint",
        "RAILs-based Lift-Offs for each priority · 2×6/side",
        "One slow-control drill (Hover or ERR) · 1-2×/side",
        "CARs finisher on cool-down · integrate the day's focus",
    ]
    for item in items:
        c.setFillColor(SKY_BLUE)
        c.circle(MARGIN + 4, y + 4, 2, fill=1, stroke=0)
        c.setFillColor(CREAM)
        c.setFont(SERIF, 12)
        c.drawString(MARGIN + 18, y, item)
        y -= 20


# ==========================================================
# PAGE 7 · MOBILITY MAP
# ==========================================================

def draw_mobility_map(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 05  ·  MOBILITY MAP", program['client_name'].upper())

    # Header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Every joint,")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "accounted for.")

    # Two columns · legend left, findings right
    y -= 50
    col_w = (CONTENT_W - 40) / 2

    # LEFT · Joint Legend
    small_caps_label(c, "JOINT LEGEND", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("JOINT LEGEND", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, MARGIN + col_w, color=DIVIDER)
    ty = y - 22

    sections = [
        ("UPPER BODY", ["01 Shoulder", "02 Acromioclavicular", "03 Sternoclavicular",
                        "04 Elbow", "05 Radiocarpal", "06 Carpometacarpal"]),
        ("SPINE", ["07 Sacroiliac", "08 Zygapophyseal"]),
        ("LOWER BODY", ["09 Hip", "10 Knee", "11 Ankle", "12 Subtalar", "13 Transverse Tarsal"]),
    ]
    for sec, items in sections:
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(MARGIN, ty, sec)
        ty -= 15
        c.setFillColor(CREAM)
        c.setFont(SERIF, 10.5)
        for it in items:
            c.drawString(MARGIN + 8, ty, it)
            ty -= 13
        ty -= 4

    # Traffic light legend beneath
    ty -= 10
    tl_items = [
        (LIMITED, "Limited Control", "needs focused work"),
        (MODERATE, "Moderate Control", "maintain & improve"),
        (OPTIMAL, "Optimal Control", "strong, usable range"),
    ]
    for color, title, sub in tl_items:
        c.setFillColor(color)
        c.circle(MARGIN + 6, ty + 4, 5, fill=1, stroke=0)
        c.setFillColor(CREAM)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(MARGIN + 18, ty + 2, title)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 9)
        c.drawString(MARGIN + 18, ty - 10, sub)
        ty -= 22

    # RIGHT · Client findings
    rx = MARGIN + col_w + 40
    small_caps_label(c, "YOUR STATUS", rx, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("YOUR STATUS", SANS_MEDIUM, 10)
    thin_divider(c, rx + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    ty = y - 22

    mobility = program['assessment'].get('mobility_map', [])
    for entry in mobility[:10]:
        rating = entry.get('rating', 'green') if isinstance(entry, dict) else 'green'
        joint = entry.get('joint', '') if isinstance(entry, dict) else ''
        side = entry.get('side', '') if isinstance(entry, dict) else ''
        direction = entry.get('direction', '') if isinstance(entry, dict) else ''
        color = {"red": LIMITED, "yellow": MODERATE, "green": OPTIMAL}.get(rating, OPTIMAL)
        c.setFillColor(color)
        c.circle(rx + 6, ty + 4, 5, fill=1, stroke=0)
        c.setFillColor(CREAM)
        c.setFont(SERIF, 11)
        label = f"{joint.title()} {direction.upper()}"
        if side and side != "bilateral":
            label += f"  ({side})"
        elif side == "bilateral":
            label += "  (bilateral)"
        c.drawString(rx + 18, ty + 2, label)
        ty -= 18


# ==========================================================
# PAGE 8 · STRENGTH & MOBILITY PLAN (weekly overview)
# ==========================================================

def draw_strength_plan(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 06  ·  STRENGTH & MOBILITY", program['client_name'].upper())

    # Header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Your weekly")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "structure.")

    assessment = program['assessment']

    # Meta row · block / week / frequency
    y -= 60
    meta_items = [
        ("BLOCK", str(program['block_number'])),
        ("WEEKS", "1-4"),
        ("FREQUENCY", f"{assessment.get('training_frequency', 3)}×/wk"),
    ]
    col_w = CONTENT_W / 3
    for i, (label, val) in enumerate(meta_items):
        x = MARGIN + i * col_w
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(x, y, label)
        thin_divider(c, x, y - 6, x + col_w - 20, color=DIVIDER)
        c.setFillColor(CREAM)
        c.setFont(SERIF, 28)
        c.drawString(x, y - 36, val)

    # Schedule table · editorial style with serif body
    y -= 80
    small_caps_label(c, "WEEK 01  ·  DAY BY DAY", MARGIN, y, color=SKY_BLUE, size=10)
    thin_divider(c, MARGIN + 120, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 16

    days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    freq = assessment.get('training_frequency', 3)
    session_map = ({1: 1, 2: 3, 3: 5} if freq == 3 else
                   {1: 1, 2: 4} if freq == 2 else
                   {1: 1, 2: 2, 3: 4, 4: 5})
    sessions = program['weeks'][0]['sessions']
    row_h = 44

    for day_idx, label in enumerate(days):
        ry = y - (day_idx + 1) * row_h
        # Subtle row separator
        thin_divider(c, MARGIN, ry, PAGE_W - MARGIN, color=DIVIDER, width=0.4)

        session_num = next((sn for sn, d in session_map.items() if d == day_idx), None)

        # Day label · small caps sans
        c.setFillColor(SKY_BLUE if session_num else CREAM_DIM)
        c.setFont(SANS_MEDIUM, 11)
        c.drawString(MARGIN, ry + 16, label)

        if session_num and session_num <= len(sessions):
            sess = sessions[session_num - 1]
            dt = sess.get('day_type', '')
            focus = sess.get('focus', '')
            focus_short = focus.replace("Lower Body Strength", "Lower Body").replace(
                "Upper Body Strength", "Upper Body").replace(
                "Cardio & Recovery Conditioning", "Cardio + Recovery")
            if len(focus_short) > 50:
                focus_short = focus_short[:49] + "…"

            # Focus line · serif italic
            c.setFillColor(CREAM)
            c.setFont(SERIF_ITALIC, 13)
            c.drawString(MARGIN + 80, ry + 22, focus_short)

            # Mini detail line beneath · sans small
            if dt == "cardio":
                detail = "Zone 2 or intervals · FRC reset finish"
            elif dt == "integration":
                detail = "Integration · extended PAIL/RAIL"
            else:
                sb = next((b for b in sess['blocks'] if b['name'].startswith('Strength A')), None)
                mb = next((b for b in sess['blocks'] if b['name'].startswith('Mobility Prep')), None)
                strength = shorten(sb['exercises'][0]['name'], 30) if sb and sb['exercises'] else "—"
                mob_count = len(mb['exercises']) if mb else 0
                detail = f"Strength · {strength}  ·  {mob_count} RAILs drills"
            c.setFillColor(CREAM_DIM)
            c.setFont(SANS, 9)
            c.drawString(MARGIN + 80, ry + 6, detail)

            # Right mark · small sky blue dot
            c.setFillColor(SKY_BLUE)
            c.circle(PAGE_W - MARGIN - 8, ry + row_h / 2, 3, fill=1, stroke=0)
        else:
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 12)
            c.drawString(MARGIN + 80, ry + 16, "Rest · active recovery")

    # Bottom rule
    final_y = y - 7 * row_h
    thin_divider(c, MARGIN, final_y, PAGE_W - MARGIN, color=DIVIDER, width=0.4)


# ==========================================================
# PAGES 9-11 · SESSION DETAIL PAGES (NEW · one per training day)
# ==========================================================

def draw_session_page(c, program, session_idx, day_num_in_week):
    """Detailed session page · one per training day. Mobility/cooldown blocks show
    Week 1 doses (they stay constant across weeks). Strength A/B show all 4 weeks
    in a progression table so the client sees the whole block at a glance.
    """
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")

    session = program['weeks'][0]['sessions'][session_idx]

    page_header_bar(c, f"SECTION 07  ·  SESSION {session_idx + 1} DETAIL",
                    f"WEEK 01-04  ·  DAY {day_num_in_week}")

    # Session title
    y = PAGE_H - MARGIN - 140
    dt = session.get('day_type', '')

    if dt == "cardio":
        h1 = f"Day {day_num_in_week}."
        h1_italic = "Cardio & recovery."
    elif dt == "integration":
        h1 = f"Day {day_num_in_week}."
        h1_italic = "Integration."
    else:
        day_label = "Lower body" if dt == "strength_lb" else "Upper body"
        h1 = f"Day {day_num_in_week}."
        h1_italic = f"{day_label} strength."

    c.setFillColor(CREAM)
    c.setFont(SERIF, 36)
    c.drawString(MARGIN, y, h1)
    y -= 42
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 36)
    c.drawString(MARGIN, y, h1_italic)

    # Focus line
    y -= 24
    focus = session.get('focus', '')
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 12)
    focus_clean = focus.replace("Lower Body Strength + ", "Focus · ").replace(
        "Upper Body Strength + ", "Focus · ").replace(" Focus", "")
    if len(focus_clean) > 90:
        focus_clean = focus_clean[:89] + "…"
    c.drawString(MARGIN, y, focus_clean)

    # Render blocks
    # Strategy:
    #   - Passive stretch, Mobility Prep, Cool Down · render compact (1-col, Wk 1 only)
    #   - Strength A, Strength B · render as 4-week progression table
    #   - Cardio session has different blocks (Warm-Up, Conditioning, Reset) — render compact
    y -= 30

    block_names = [b['name'] for b in session['blocks']]

    for block in session['blocks']:
        name = block['name']
        if name.startswith("Strength A") or name.startswith("Strength B"):
            y = render_strength_progression(c, program, session_idx, name, y)
        else:
            y = render_block_compact(c, block, y)
        y -= 8
        if y < MARGIN + 70:
            break


def render_block_compact(c, block, y):
    """Compact block renderer · for mobility, cool-down, cardio · Week 1 doses only
    since these stay constant across weeks."""
    block_name = block.get('name', '')
    exercises = block.get('exercises', [])

    # Block label · small caps sans + thin rule
    small_caps_label(c, block_name.upper(), MARGIN, y, color=SKY_BLUE, size=9.5)
    lw = c.stringWidth(block_name.upper(), SANS_MEDIUM, 9.5)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
    y -= 15

    for ex in exercises:
        name = ex.get('name', '')
        dose = ex.get('dose', '')

        # Truncate long names
        if c.stringWidth(name, SERIF, 11) > CONTENT_W * 0.55:
            while c.stringWidth(name + "…", SERIF, 11) > CONTENT_W * 0.55 and len(name) > 10:
                name = name[:-1]
            name = name + "…"

        # Truncate long doses
        if dose and c.stringWidth(dose, SANS_MEDIUM, 9) > CONTENT_W * 0.38:
            while c.stringWidth(dose + "…", SANS_MEDIUM, 9) > CONTENT_W * 0.38 and len(dose) > 10:
                dose = dose[:-1]
            dose = dose + "…"

        c.setFillColor(CREAM)
        c.setFont(SERIF, 11)
        c.drawString(MARGIN + 12, y, name)
        c.setFillColor(SKY_LIGHT)
        c.setFont(SANS_MEDIUM, 9)
        c.drawRightString(PAGE_W - MARGIN, y, dose)
        y -= 12

    return y


def render_strength_progression(c, program, session_idx, block_name, y):
    """Render a strength block as a 4-week progression table.
    Rows · exercises  ·  Columns · WK 1 / WK 2 / WK 3 / WK 4 doses
    """
    # Pull the same block from each of the 4 weeks
    weeks = program['weeks']
    if len(weeks) < 4:
        # Fallback · render compact
        for b in weeks[0]['sessions'][session_idx]['blocks']:
            if b['name'] == block_name:
                return render_block_compact(c, b, y)

    blocks_per_week = []
    for wk in weeks:
        sess = wk['sessions'][session_idx]
        for b in sess['blocks']:
            if b['name'] == block_name:
                blocks_per_week.append(b)
                break

    # Safety
    if len(blocks_per_week) < 4:
        return render_block_compact(c, blocks_per_week[0] if blocks_per_week else {"name": block_name, "exercises": []}, y)

    # Block label
    small_caps_label(c, block_name.upper(), MARGIN, y, color=SKY_BLUE, size=9.5)
    lw = c.stringWidth(block_name.upper(), SANS_MEDIUM, 9.5)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
    y -= 14

    # Sub-header · WK 1 / WK 2 / WK 3 / WK 4
    name_col_w = CONTENT_W * 0.30
    wk_col_w = (CONTENT_W - name_col_w) / 4

    # Week header row
    c.setFillColor(CREAM_DIM)
    c.setFont(SANS_MEDIUM, 8)
    c.drawString(MARGIN + 12, y, "EXERCISE")
    for i in range(4):
        x = MARGIN + name_col_w + i * wk_col_w + wk_col_w / 2
        c.drawCentredString(x, y, f"WK {i + 1}")
    y -= 10
    thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 10

    # For each exercise (using Week 1 as the source of truth for names)
    wk1_exercises = blocks_per_week[0]['exercises']
    for ex_idx, ex in enumerate(wk1_exercises):
        name = ex.get('name', '')

        # Truncate name to fit column
        orig_name = name
        while c.stringWidth(name, SERIF, 10.5) > name_col_w - 14 and len(name) > 8:
            name = name[:-1]
        if name != orig_name:
            name = name + "…"

        c.setFillColor(CREAM)
        c.setFont(SERIF, 10.5)
        c.drawString(MARGIN + 12, y, name)

        # Render the dose for each of the 4 weeks
        for wk_idx in range(4):
            wk_block = blocks_per_week[wk_idx]
            # Match by exercise index (generator preserves order week to week)
            if ex_idx < len(wk_block['exercises']):
                wk_ex = wk_block['exercises'][ex_idx]
                dose = wk_ex.get('dose', '—')

                # Compact the dose for the narrow cell
                dose_compact = compact_dose(dose)

                # Color-code by week · Wk 1 cream, Wk 2-3 sky blue, Wk 4 dim (deload)
                if wk_idx == 0:
                    c.setFillColor(CREAM_DIM)
                elif wk_idx == 3:
                    c.setFillColor(CREAM_DIM)
                else:
                    c.setFillColor(SKY_LIGHT)
                c.setFont(SANS_MEDIUM, 8.5)

                x = MARGIN + name_col_w + wk_idx * wk_col_w + wk_col_w / 2
                c.drawCentredString(x, y, dose_compact)
        y -= 14

    # Small progression legend row
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 8)
    legend = "WK 1 · establish  ·  WK 2-3 · push one lever  ·  WK 4 · deload + re-test"
    c.drawString(MARGIN + 12, y, legend)
    y -= 6

    return y


def compact_dose(dose):
    """Tighten a dose string aggressively for narrow table cells.
    '3x8/side  +5 lbs from Wk 1' → '3×8/s +5lb'
    '3x8/side  +10 lbs from Wk 1  (tempo · 3-sec eccentric)' → '3×8/s +10lb ecc3'
    '3x12  (with 2-sec iso hold at hardest point)' → '3×12 iso2'
    """
    s = dose
    # Normalize
    s = s.replace("x", "×")
    s = s.replace(" from Wk 1", "")
    # Tempo markers · shorten
    s = s.replace("(tempo · 3-sec eccentric)", "ecc3")
    s = s.replace("(tempo · 2-sec eccentric)", "ecc2")
    s = s.replace("(with 2-sec iso hold at hardest point)", "iso2")
    s = s.replace("(with 3-sec iso hold)", "iso3")
    s = s.replace("(with 2-sec iso hold)", "iso2")
    s = s.replace("3-sec eccentric", "ecc3")
    s = s.replace("2-sec iso", "iso2")
    s = s.replace("3-sec iso", "iso3")
    # Units + side
    s = s.replace(" lbs", "lb")
    s = s.replace("/side", "/s")
    # Deload/slow shorthand
    s = s.replace("(deload)", "dld")
    s = s.replace("(slow tempo)", "slow")
    s = s.replace("(slow)", "slow")
    # Remove remaining parens if short enough
    s = s.replace("(", "").replace(")", "")
    # Collapse multiple spaces
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


# ==========================================================
# PAGE 12 · NUTRITION
# ==========================================================

def draw_nutrition(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 08  ·  NUTRITION", program['client_name'].upper())

    bc = program['assessment'].get('body_comp', {}) or {}
    targets = bc.get('nutrition_targets', {}) or {}
    # Guard against non-dict values (e.g. leftover "AUTO" string from form intake)
    if not isinstance(targets, dict):
        targets = {}
    has_real_targets = bool(targets)

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Fuel for")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "the work.")

    # DAILY TARGETS · show calculated values if we have them
    y -= 60
    small_caps_label(c, "DAILY TARGETS  ·  CALCULATED FROM YOUR LEAN MASS", MARGIN, y,
                     color=SKY_BLUE, size=9)
    lw = c.stringWidth("DAILY TARGETS  ·  CALCULATED FROM YOUR LEAN MASS", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 26

    # Macro cards · 4 across with serif numbers
    macros = [
        ("CALORIES", targets.get('calories', '—'), "/ day"),
        ("PROTEIN", targets.get('protein', '—'), "/ day"),
        ("CARBS", targets.get('carbs', '—'), "/ day"),
        ("FAT", targets.get('fat', '—'), "/ day"),
    ]
    col_w = CONTENT_W / 4
    for i, (label, val, suffix) in enumerate(macros):
        x = MARGIN + i * col_w
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 8)
        c.drawString(x, y, label)
        thin_divider(c, x, y - 6, x + col_w - 16, color=DIVIDER)
        # Big serif number
        val_str = str(val)
        # Split off the unit if present (e.g. "2,150 cal/day" → "2,150" + " cal/day")
        font_size = 22 if len(val_str) < 10 else 16
        c.setFillColor(CREAM)
        c.setFont(SERIF, font_size)
        c.drawString(x, y - 40, val_str)

    y -= 90

    # Water + rationale
    water = targets.get('water', '—')
    c.setFillColor(SKY_BLUE)
    c.setFont(SANS_MEDIUM, 9)
    c.drawString(MARGIN, y, "WATER")
    c.setFillColor(CREAM)
    c.setFont(SERIF, 13)
    c.drawString(MARGIN + 60, y, water)
    y -= 18
    thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 20

    # THE FOCUS / RATIONALE
    small_caps_label(c, "THE STRATEGY", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("THE STRATEGY", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    # Personalize strategy based on client
    primary_goal = (program['assessment'].get('primary_goal') or '').lower()
    is_runner = 'run' in primary_goal or 'marathon' in primary_goal
    is_strength = 'strong' in primary_goal or 'strength' in primary_goal

    if is_runner:
        strategy = ("Endurance-forward fueling. Carbs are prioritized to support running "
                    "volume and recovery. Protein at every meal protects lean mass. "
                    "Hydration matters most on run days.")
    elif is_strength:
        strategy = ("Strength-forward fueling. Protein is prioritized at ~0.9 g per lb of "
                    "lean mass to support adaptation. Carbs fuel training sessions. Fat "
                    "fills the remainder for hormone and joint health.")
    else:
        strategy = ("Balanced fueling built around your lean mass — not your scale weight. "
                    "Protein at every meal protects muscle. Carbs fuel training. Fat rounds "
                    "out hormone and joint health.")

    y = draw_wrapped(c, strategy, MARGIN, y, CONTENT_W, SERIF, 11.5, leading=16, color=CREAM)

    # SAMPLE DAY · with real food examples matched to Sarah/Matt
    y -= 22
    small_caps_label(c, "A SAMPLE DAY", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("A SAMPLE DAY", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 20

    # Build sample meals that roughly hit the targets
    meals = build_sample_meals(targets, is_runner, is_strength)
    for meal_name, items, meal_cals in meals:
        c.setFillColor(CREAM)
        c.setFont(SERIF_ITALIC, 11.5)
        c.drawString(MARGIN, y, meal_name)
        c.setFillColor(SKY_LIGHT)
        c.setFont(SANS_MEDIUM, 9)
        c.drawRightString(PAGE_W - MARGIN, y, f"~{meal_cals} cal")
        y -= 13
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF, 10.5)
        c.drawString(MARGIN + 14, y, items)
        y -= 14
        thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.3)
        y -= 10

    # Footer note
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 9)
    c.drawCentredString(PAGE_W / 2, MARGIN + 30,
                        "These targets are a starting point. We adjust based on energy, "
                        "sleep, and performance.")


def build_sample_meals(targets, is_runner, is_strength):
    """Produce a sample day matched to the target profile.
    Returns list of (meal_name, items_string, calories)."""
    cal_str = targets.get('calories', '')
    # Parse calories as integer
    try:
        total_cal = int(''.join(ch for ch in cal_str if ch.isdigit()))
    except (ValueError, TypeError):
        total_cal = 2100

    if is_runner:
        # Runner · carb-forward
        return [
            ("Breakfast", "Overnight oats · Greek yogurt · banana · peanut butter · chia seeds", 550),
            ("Mid-morning", "Apple + handful of almonds", 220),
            ("Lunch", "Chicken + rice bowl · sweet potato · avocado · mixed greens", 650),
            ("Pre-run snack", "Banana + honey toast OR energy chew (if running >45 min)", 180),
            ("Dinner", "Salmon · quinoa · roasted veg · olive oil · dark leafy salad", 550),
        ]
    elif is_strength:
        # Strength · protein-forward
        return [
            ("Breakfast", "4 egg omelet + spinach · Greek yogurt + berries · coffee", 500),
            ("Lunch", "Chicken thigh · rice · black beans · avocado · peppers", 700),
            ("Pre-training", "Protein shake + banana (45-60 min before)", 300),
            ("Post-training", "Grilled steak or chicken · sweet potato · broccoli", 650),
            ("Evening", "Cottage cheese + walnuts + honey", 250),
        ]
    else:
        return [
            ("Breakfast", "Eggs · whole-grain toast · avocado · fruit", 450),
            ("Lunch", "Lean protein · mixed grains · vegetables · olive oil", 600),
            ("Snack", "Greek yogurt + fruit + nuts", 250),
            ("Dinner", "Fish or chicken · sweet potato · salad · dressing", 550),
            ("Optional", "Cottage cheese or protein shake", 200),
        ]


# ==========================================================
# PAGE 13 · WEEKLY ROUTINE MAP
# ==========================================================

def draw_weekly_map(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 09  ·  WEEKLY ROUTINE", program['client_name'].upper())

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Everything,")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "integrated.")

    # Intro line
    y -= 36
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 12)
    c.drawString(MARGIN, y, "Strength, mobility, nutrition, recovery — all together on one page.")

    # Table headers
    y -= 40
    col_widths = [CONTENT_W * 0.13, CONTENT_W * 0.25, CONTENT_W * 0.22, CONTENT_W * 0.22, CONTENT_W * 0.18]
    col_starts = [MARGIN]
    for w in col_widths[:-1]:
        col_starts.append(col_starts[-1] + w)

    headers = ["DAY", "STRENGTH", "MOBILITY", "NUTRITION", "RECOVERY"]
    for i, h in enumerate(headers):
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(col_starts[i], y, h)
    thin_divider(c, MARGIN, y - 8, PAGE_W - MARGIN, color=DIVIDER)

    # Rows
    days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    freq = program['assessment'].get('training_frequency', 3)
    session_map = ({1: 1, 2: 3, 3: 5} if freq == 3 else
                   {1: 1, 2: 4} if freq == 2 else
                   {1: 1, 2: 2, 3: 4, 4: 5})
    sessions = program['weeks'][0]['sessions']
    row_h = 42

    for day_idx, day in enumerate(days):
        ry = y - 36 - day_idx * row_h

        session_num = next((sn for sn, d in session_map.items() if d == day_idx), None)

        # Day label
        c.setFillColor(SKY_BLUE if session_num else CREAM_DIM)
        c.setFont(SANS_MEDIUM, 10)
        c.drawString(col_starts[0], ry + 8, day)

        if session_num and session_num <= len(sessions):
            sess = sessions[session_num - 1]
            dt = sess.get('day_type', '')
            if dt == "cardio":
                vals = ["—", "Cardio + FRC reset", "Hydration focus", "Zone 2 / intervals"]
            elif dt == "integration":
                vals = ["Integration", "PAIL/RAIL extended", "Whole food", "Breathwork"]
            else:
                sb = next((b for b in sess['blocks'] if b['name'].startswith('Strength A')), None)
                mb = next((b for b in sess['blocks'] if b['name'].startswith('Mobility Prep')), None)
                strength = shorten(sb['exercises'][0]['name'], 22) if sb and sb['exercises'] else "—"
                mobility = f"{len(mb['exercises'])} RAILs drills" if mb else "—"
                vals = [strength, mobility, "Pre/post protein", "CARs + stretch"]

            c.setFillColor(CREAM)
            c.setFont(SERIF, 10.5)
            for i, v in enumerate(vals):
                c.drawString(col_starts[i + 1], ry + 8, v)
        else:
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 10)
            c.drawString(col_starts[1], ry + 8, "Rest · active recovery")

        # Thin divider between rows
        thin_divider(c, MARGIN, ry, PAGE_W - MARGIN, color=DIVIDER, width=0.3)


# ==========================================================
# PAGE 14 · TRACKING
# ==========================================================

def draw_tracking(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 10  ·  TRACKING", program['client_name'].upper())

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Notice,")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "adjust, grow.")

    y -= 70
    paras = [
        "Tracking isn't about chasing perfection — it's about noticing patterns, celebrating wins, and learning what your body responds to over time.",
        "Some weeks will show clear progress. Others will reveal what needs adjusting. Both are valuable.",
        "Progress can show up as better sleep, fewer aches, or lifting a little heavier. The more we notice, the more we can build on what's working.",
    ]
    for p in paras:
        y = draw_wrapped(c, p, MARGIN, y, CONTENT_W - 60, SERIF, 12.5, leading=18, color=CREAM)
        y -= 10

    # What you track monthly
    y -= 20
    small_caps_label(c, "WHAT YOU TRACK", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("WHAT YOU TRACK", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 28

    items = [
        ("Energy", "scale 1-10"),
        ("Sleep", "quality + duration"),
        ("Weight", "once per week"),
        ("Training Wins", "anything that felt good"),
    ]
    for label, sub in items:
        c.setFillColor(CREAM)
        c.setFont(SERIF, 13)
        c.drawString(MARGIN + 10, y, label)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 11)
        c.drawString(MARGIN + 110, y, f"· {sub}")
        y -= 12
        thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.3)
        y -= 18


# ==========================================================
# PAGE 15 · STAY CONNECTED
# ==========================================================

def draw_stay_connected(c, program):
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 11  ·  STAY CONNECTED", program['client_name'].upper())

    priorities = program['assessment'].get('fra_priorities', [])

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "The road")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "ahead.")

    # What's Next
    y -= 70
    small_caps_label(c, "WHAT'S NEXT  ·  WEEKS 5-8", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("WHAT'S NEXT  ·  WEEKS 5-8", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    top_priority = priorities[0].get('description', 'your priorities') if priorities else 'your priorities'
    next_text = (f"After your Week 4 re-test we launch Block 2. Expect progressions on "
                 f"{top_priority}, plus PAIL/RAIL Level 2 work at cleared joints. Strength "
                 f"moves forward using your current markers as baseline.")
    y = draw_wrapped(c, next_text, MARGIN, y, CONTENT_W, SERIF, 12.5, leading=18, color=CREAM)

    # 90-day vision
    y -= 30
    small_caps_label(c, "YOUR 90-DAY VISION", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("YOUR 90-DAY VISION", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    vision = ("Three completed blocks. Measurable mobility gains at every priority joint. "
              "Strength markers improved by 15-20%. A body that moves better than it did at 30.")
    y = draw_wrapped(c, vision, MARGIN, y, CONTENT_W, SERIF_ITALIC, 13, leading=19, color=CREAM)

    # Check-ins
    y -= 30
    small_caps_label(c, "CHECK-IN TIMELINE", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("CHECK-IN TIMELINE", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 28

    checkins = [("Next Body Comp", "Week 12"),
                ("Next FRA Test", "Week 4"),
                ("Next Strength Test", "Week 4")]
    for label, date in checkins:
        c.setFillColor(CREAM)
        c.setFont(SERIF, 13)
        c.drawString(MARGIN + 10, y, label)
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 11)
        c.drawRightString(PAGE_W - MARGIN - 10, y, date.upper())
        y -= 10
        thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.3)
        y -= 16

    # Closing · centered logo + tagline
    draw_logo(c, PAGE_W / 2, MARGIN + 80, 120, variant="white")
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 11)
    c.drawCentredString(PAGE_W / 2, MARGIN + 50,
                        "Move better. Get stronger. Stay active for life.")


# ==========================================================
# MAIN
# ==========================================================

def generate_plan_pdf(program_json: str, output_pdf: str):
    with open(program_json) as f:
        program = json.load(f)

    c = canvas.Canvas(output_pdf, pagesize=LETTER)
    c.setTitle(f"IMS Body & Movement Plan · {program['client_name']}")
    c.setAuthor("Innovative Movement Solutions")

    # Base pages
    base_pages = [
        draw_cover,               # 1
        draw_quote,               # 2
        draw_welcome,             # 3
        draw_goals,               # 4
        draw_body_comp,           # 5
        draw_mobility_assessment, # 6
        draw_mobility_map,        # 7
        draw_strength_plan,       # 8
    ]

    # Session detail pages · one per training session
    num_sessions = len(program['weeks'][0]['sessions'])

    # Footer pages
    closing_pages = [
        draw_nutrition,
        draw_weekly_map,
        draw_tracking,
        draw_stay_connected,
    ]

    total = len(base_pages) + num_sessions + len(closing_pages)

    # Draw base
    page_num = 0
    for fn in base_pages:
        page_num += 1
        fn(c, program)
        if page_num > 1:
            page_footer(c, page_num, total)
        c.showPage()

    # Draw session detail pages (NEW)
    freq = program['assessment'].get('training_frequency', 3)
    day_map = ({1: 1, 2: 3, 3: 5} if freq == 3 else
               {1: 1, 2: 4} if freq == 2 else
               {1: 1, 2: 2, 3: 4, 4: 5})
    for i in range(num_sessions):
        page_num += 1
        day_in_week = day_map.get(i + 1, i + 1)
        draw_session_page(c, program, i, day_in_week)
        page_footer(c, page_num, total)
        c.showPage()

    # Draw closing
    for fn in closing_pages:
        page_num += 1
        fn(c, program)
        page_footer(c, page_num, total)
        c.showPage()

    c.save()
    print(f"PDF v3 generated · {output_pdf}  ({total} pages)")


if __name__ == "__main__":
    import sys
    from pathlib import Path as _P
    repo_root = _P(__file__).resolve().parent.parent
    default_json = repo_root / "examples" / "matt_program.json"
    default_pdf = repo_root / "examples" / "matt_plan.pdf"
    generate_plan_pdf(
        program_json=str(sys.argv[1]) if len(sys.argv) > 1 else str(default_json),
        output_pdf=str(sys.argv[2]) if len(sys.argv) > 2 else str(default_pdf)
    )
