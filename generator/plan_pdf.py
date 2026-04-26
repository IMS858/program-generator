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


def sanitize_copy(text):
    """Final copy-cleanup pass for generated PDF text.

    Fixes common typos and awkward grammar that can come from user input
    or template substitution. Run this on any string that flows from the
    assessment into rendered PDF output.

    Rules ·
      - Common medical/anatomy spelling fixes (Mensicus → Meniscus, etc.)
      - "a early/an early" article agreement before vowels
      - "Level X,Y cars" → "Level X-Y CARs" (en-dash for ranges)
      - Double spaces collapsed
      - Awkward " · ." or " · ," cleaned
    """
    if not text or not isinstance(text, str):
        return text

    import re

    # 1 · Spelling fixes (medical terms commonly mistyped)
    SPELLING_FIXES = {
        r'\bMensicus\b': 'Meniscus',
        r'\bmensicus\b': 'meniscus',
        r'\bMenisci\b': 'Menisci',
        r'\bACL\b': 'ACL',  # canonicalize
        r'\bMCL\b': 'MCL',
        r'\bLCL\b': 'LCL',
        r'\bPCL\b': 'PCL',
        r'\bIliotibial\b': 'Iliotibial',
        r'\bAchilles\b': 'Achilles',
        r'\bAcheles\b': 'Achilles',
        r'\bRotater\b': 'Rotator',
        r'\brotater\b': 'rotator',
        r'\bSciatic\b': 'Sciatic',
        r'\bSiatic\b': 'Sciatic',
        r'\bsiatic\b': 'sciatic',
        r'\bPiriformis\b': 'Piriformis',
        r'\bpiriformis\b': 'Piriformis',
        r'\bPirformis\b': 'Piriformis',
        r'\bpirformis\b': 'Piriformis',
    }
    for pattern, replacement in SPELLING_FIXES.items():
        text = re.sub(pattern, replacement, text)

    # 2 · "Level X,Y cars" → "Level X-Y CARs"
    text = re.sub(r'\bLevel\s+(\d+)\s*,\s*(\d+)\s+cars\b', r'Level \1-\2 CARs', text)
    text = re.sub(r'\bLevel\s+(\d+)\s*,\s*(\d+)\s+CARs\b', r'Level \1-\2 CARs', text)
    text = re.sub(r'\bcars\b(?!\w)', 'CARs', text)
    text = re.sub(r'\bpails\b(?!\w)', 'PAILs', text)
    text = re.sub(r'\brails\b(?!\w)', 'RAILs', text)
    text = re.sub(r'\bprlo\b(?!\w)', 'PRLO', text, flags=re.IGNORECASE)
    text = re.sub(r'\berr\b(?!\w)', 'ERR', text)

    # 3 · Article agreement · "a early 30s" → "an early-30s", "a old" → "an old"
    text = re.sub(
        r'\b([Aa])\s+(early|old|active|active-sounding|older|aging|injured|adolescent|elderly|adult)\b',
        lambda m: ('A' if m.group(1) == 'A' else 'a') + 'n ' + m.group(2),
        text,
    )
    # "a 80-year" / "a 18-year" type phrasing
    text = re.sub(
        r'\b([Aa])\s+(8|11|18|80|85|88)\b',
        lambda m: ('A' if m.group(1) == 'A' else 'a') + 'n ' + m.group(2),
        text,
    )

    # 4 · "early 30s body" / "early 50s body" → "early-30s body" (compound modifier hyphen)
    text = re.sub(
        r'\b(early|mid|late)\s+(\d{2}s)\b\s+(?=body|frame|client|adult|athlete)',
        r'\1-\2 ',
        text,
    )

    # 5 · Collapse double spaces, fix awkward separator artifacts
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\s+·\s*\.', '.', text)
    text = re.sub(r'\s+·\s*,', ',', text)
    text = re.sub(r'\s+\.\s*\.', '.', text)

    return text.strip()


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
    """Shorten a name via known abbreviations · NO ellipses ever.
    If after abbreviation the name is still long, return it as-is and let
    the caller's wrap logic handle it."""
    replacements = [
        ("Front Foot Elevated", "FFE"), ("Single-Leg", "SL"), ("Single Leg", "SL"),
        ("Romanian Deadlift", "RDL"), ("Assisted", "Asst"),
        ("External Rotation", "ER"), ("Internal Rotation", "IR"),
        ("Dumbbell", "DB"), ("Kettlebell", "KB"),
        ("(Single or Double Arm)", ""), ("(Single Arm)", "(SA)"),
    ]
    s = name
    for long, abbr in replacements:
        s = s.replace(long, abbr)
    return s.strip().replace("  ", " ")


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

    # Sections
    y -= 56
    sections = [
        ("THE GOAL", assessment.get('primary_goal', '')),
        ("WHAT YOU'RE WORKING WITH", compose_working_with(assessment)),
        ("OUR APPROACH", compose_approach(assessment)),
        ("HOW WE MEASURE", compose_measures(assessment)),
    ]

    for label, content in sections:
        if not content:
            continue
        content = sanitize_copy(content)
        small_caps_label(c, label, MARGIN, y, color=SKY_BLUE, size=10)
        lw = c.stringWidth(label.upper(), SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 20
        y = draw_wrapped(c, content, MARGIN, y, CONTENT_W, SERIF, 11.5,
                         leading=16, color=CREAM)
        y -= 18


def compose_working_with(a):
    """Mirror back what the coach actually told us · concerns, priorities,
    mobility map highlights, constraints. This is the 'we listened' section.
    """
    parts = []

    # Concerns · the bad-knee-style flags
    concerns = a.get('concerns') or []
    concern_notes = (a.get('concern_notes') or '').strip()
    if concerns:
        labels = _humanize_concerns(concerns)
        if len(labels) == 1:
            parts.append(f"You came in with {labels[0]}.")
        else:
            parts.append(f"You came in with concerns about · {', '.join(labels)}.")
    if concern_notes:
        parts.append(f"Specifically · {concern_notes}")

    # FRA priorities · the joint-level work
    priorities = a.get('fra_priorities') or []
    if priorities:
        descs = []
        for p in priorities[:3]:
            if isinstance(p, dict):
                descs.append(p.get('description') or _priority_desc(p))
            else:
                descs.append(getattr(p, 'description', '') or _priority_desc(p))
        descs = [d for d in descs if d]
        if descs:
            parts.append(f"Your priority joints right now · {', '.join(descs)}.")

    # Red-flag mobility map entries (limited control)
    mob = a.get('mobility_map') or []
    red_entries = []
    for entry in mob:
        rating = (entry.get('rating') if isinstance(entry, dict)
                  else getattr(entry, 'rating', '')) or ''
        if rating.lower() in ('red', 'limited'):
            joint = (entry.get('joint') if isinstance(entry, dict)
                     else getattr(entry, 'joint', '')) or ''
            direction = (entry.get('direction') if isinstance(entry, dict)
                         else getattr(entry, 'direction', '')) or ''
            side = (entry.get('side') if isinstance(entry, dict)
                    else getattr(entry, 'side', '')) or ''
            label = f"{joint.title()} {direction.upper()}"
            if side and side.lower() not in ('bilateral', 'both', ''):
                label += f" ({side.upper()})"
            red_entries.append(label.strip())
    if red_entries:
        parts.append(f"Joints we're moving carefully · {', '.join(red_entries)}.")

    # Formal constraints (post-surgery, disc, etc.)
    constraints = a.get('constraints') or []
    if constraints:
        formal = [c.replace('_', ' ').replace('-', ' ').strip() for c in constraints]
        formal = [c for c in formal if c]
        if formal:
            parts.append(f"Medical considerations on file · {', '.join(formal)}.")

    if not parts:
        return "No specific concerns or constraints flagged. Clean training profile."

    return " ".join(parts)


def compose_approach(a):
    """Connect the dots · how the program is shaped by the things above."""
    bits = []

    # Lifestyle context · routed through cleanup so it shapes language without
    # being pasted verbatim
    bg = clean_lifestyle_context(a.get('background', ''))
    if bg:
        bits.append(bg)

    concerns = a.get('concerns') or []
    if concerns:
        joint_words = _humanize_concerns(concerns, short=True)
        if joint_words:
            bits.append(
                f"Heavy loading through your {', '.join(joint_words)} stays off the table "
                f"this block. We earn that load back through smarter patterns first."
            )

    priorities = a.get('fra_priorities') or []
    if priorities:
        bits.append(
            "Mobility prep targets your priority joints with progressive Lift-Offs and "
            "slow-control work · doses ramp week to week based on where each joint is right now."
        )

    # Strength tests on file
    tests = a.get('strength_marker_tests') or []
    if tests:
        bits.append(
            "Strength loads are calculated from the rep maxes you tested today · "
            "no guesswork, no generic %1RM math · weights ramp through the 4-week block."
        )
    else:
        bits.append(
            "Until we have tested rep maxes, loads are prescribed by RIR (reps in reserve) · "
            "you stop with 2-3 clean reps left in the tank."
        )

    age = (a.get('age_range') or '').strip()
    if age:
        bits.append(
            f"Block 1 is structured for sustainability, not punishment · "
            f"smart enough to fit a {age} body."
        )

    return " ".join(bits)


def clean_lifestyle_context(raw):
    """Copy cleanup engine for the Lifestyle / Work Context field.

    Takes the coach's rough notes ("software engineer, sits often, new to
    strength training") and returns a polished short sentence ready for client
    copy. Empty input returns empty string · field is optional.

    Rules ·
      - Strip extraneous punctuation, normalize whitespace
      - First letter capitalized
      - Detect common patterns and expand them with plain-English framing
      - Never paste verbatim · always reframe in coaching voice
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    # Normalize · collapse whitespace, strip surrounding punctuation
    import re
    s = re.sub(r'\s+', ' ', s)
    s = s.strip(' ·.,;:')

    s_lower = s.lower()

    # Pattern detection · build the framing sentence
    framings = []
    if any(k in s_lower for k in ('desk', 'office', 'sits', 'sitting', 'engineer',
                                    'developer', 'programmer', 'analyst', 'accountant')):
        framings.append("Your day involves long sitting · so we prioritize hip mobility, "
                        "thoracic extension, and posture-supporting strength work")
    if any(k in s_lower for k in ('new to', 'beginner', 'never lifted', 'just starting')):
        framings.append("Block 1 prioritizes patterns and tolerance over load · "
                        "your body learns the movement before it carries weight")
    if any(k in s_lower for k in ('runner', 'running', 'marathon', 'cyclist', 'cycling')):
        framings.append("Endurance background means we lean into strength as the gap · "
                        "shorter, denser sessions complement your aerobic base")
    if any(k in s_lower for k in ('parent', 'kids', 'children', 'busy', 'travel')):
        framings.append("Sessions are designed to fit into a real life · "
                        "every minute earns its place")
    if any(k in s_lower for k in ('experienced', 'years training', 'returning',
                                    'former athlete', 'ex-athlete')):
        framings.append("You've trained before · we respect that floor and build from it")

    if not framings:
        # Generic fallback · acknowledge without repeating their words
        return "Your context shapes the program · sessions, intensity, and recovery "\
               "all match your real life."

    return ". ".join(framings) + "."


def _humanize_concerns(concerns, short=False):
    """Map concern flags to natural-language labels."""
    mapping = {
        "bad_knee": ("a sensitive knee", "knee"),
        "knee": ("a sensitive knee", "knee"),
        "bad_shoulder": ("a sensitive shoulder", "shoulder"),
        "shoulder": ("a sensitive shoulder", "shoulder"),
        "lower_back": ("lower back sensitivity", "lower back"),
        "low_back": ("lower back sensitivity", "lower back"),
        "back": ("lower back sensitivity", "lower back"),
        "lumbar": ("lower back sensitivity", "lower back"),
        "hip": ("hip sensitivity", "hip"),
        "bad_hip": ("hip sensitivity", "hip"),
        "neck": ("neck sensitivity", "neck"),
        "wrist": ("wrist sensitivity", "wrist"),
        "elbow": ("elbow sensitivity", "elbow"),
        "ankle": ("ankle sensitivity", "ankle"),
    }
    out = []
    seen = set()
    for c in concerns:
        key = str(c).lower().replace(" ", "_").replace("-", "_")
        if key in mapping:
            long_label, short_label = mapping[key]
            label = short_label if short else long_label
            if label not in seen:
                out.append(label)
                seen.add(label)
    return out


def _priority_desc(p):
    """Build a description for an FRA priority dict that lacks one."""
    joints = p.get('joints') if isinstance(p, dict) else getattr(p, 'joints', None)
    directions = p.get('directions') if isinstance(p, dict) else getattr(p, 'directions', None)
    j = (joints or [None])[0] or ''
    d = (directions or [None])[0] or ''
    return f"{j.title()} {d.upper()}".strip()


def compose_measures(a):
    return ("Re-tested every 4 weeks · strength markers, full mobility re-screen, "
            "plus energy and recovery tracking. Progress shows up as stronger lifts, "
            "smoother movement, better sleep, fewer aches.")


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

    # Resolve actual session counts from the program rather than trusting form input
    actual_sessions = program['weeks'][0]['sessions']
    strength_count = sum(1 for s in actual_sessions
                          if s.get('day_type', '').startswith('strength'))
    cardio_count = sum(1 for s in actual_sessions
                        if s.get('day_type') == 'cardio')
    total_count = len(actual_sessions)

    # Meta row · block / weeks / strength sessions / cardio sessions / total
    y -= 60
    meta_items = [
        ("BLOCK", str(program['block_number'])),
        ("WEEKS", "1-4"),
        ("STRENGTH", f"{strength_count}/wk"),
        ("CARDIO", f"{cardio_count}/wk"),
        ("TOTAL", f"{total_count}/wk"),
    ]
    col_w = CONTENT_W / len(meta_items)
    for i, (label, val) in enumerate(meta_items):
        x = MARGIN + i * col_w
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 8.5)
        c.drawString(x, y, label)
        thin_divider(c, x, y - 6, x + col_w - 12, color=DIVIDER)
        c.setFillColor(CREAM)
        c.setFont(SERIF, 22)
        c.drawString(x, y - 32, val)

    # Schedule table · editorial style with serif body
    y -= 80
    small_caps_label(c, "WEEK 01  ·  DAY BY DAY", MARGIN, y, color=SKY_BLUE, size=10)
    thin_divider(c, MARGIN + 120, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 16

    days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    sessions = program['weeks'][0]['sessions']
    sd = assessment.get('strength_days', 0)
    cd = assessment.get('cardio_days', 0)
    # Build session→day_idx map handling ANY frequency 1-7
    # _spread_days_across_week returns {session_num : day_of_week(1-7 where 1=MON)}
    # We want day_idx for ["SUN","MON",...] · MON=1 so day_of_week IS day_idx
    spread = _spread_days_across_week(sd, cd, len(sessions))
    session_map = {sn: day_idx for sn, day_idx in spread.items()}
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
                # Trim at word boundary, no ellipsis
                cut = focus_short[:50].rsplit(" ", 1)[0]
                focus_short = cut

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

def draw_session_page(c, program, session_idx, day_num_in_week,
                      start_page_num=1, total_pages=1):
    """Detailed session page · one per training day.

    May consume 1 or 2 PDF pages depending on content density.
    Renders its own footers and showPage()s.
    Returns the number of pages actually consumed.
    """
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")

    session = program['weeks'][0]['sessions'][session_idx]
    pages_used = 1
    current_page = start_page_num

    page_header_bar(c, f"SECTION 07 · SESSION {session_idx + 1} DETAIL",
                    f"WEEK 01-04 · DAY {day_num_in_week}")

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
        # Word-boundary trim, no ellipsis
        focus_clean = focus_clean[:90].rsplit(" ", 1)[0]
    c.drawString(MARGIN, y, focus_clean)

    y -= 30

    def _needs_page_break(current_y, block):
        """Estimate vertical space a block needs."""
        if block['name'].startswith("Strength"):
            nex = len(block.get('exercises', []))
            needed = 40 + (nex * 13 + 50) * 2 + 20
            bottom_buffer = 50
        else:
            needed = 25 + len(block.get('exercises', [])) * 13 + 10
            bottom_buffer = 15  # Compact blocks can run closer to bottom margin
        return current_y - needed < MARGIN + bottom_buffer

    def _new_page():
        nonlocal y, pages_used, current_page
        page_footer(c, current_page, total_pages)
        c.showPage()
        current_page += 1
        pages_used += 1
        fill_page(c, NAVY)
        ghost_watermark(c, "ims")
        page_header_bar(c, f"SECTION 07 · SESSION {session_idx + 1} (continued)",
                        f"WEEK 01-04 · DAY {day_num_in_week}")
        y = PAGE_H - MARGIN - 100

    for block in session['blocks']:
        name = block['name']

        # Strength B gets its OWN page after Strength A · the split-table
        # layout needs the vertical room, and they shouldn't crush each other.
        if name.startswith("Strength B"):
            _new_page()
        # Otherwise break normally if the next block won't fit
        elif _needs_page_break(y, block) and y < PAGE_H - MARGIN - 150:
            _new_page()

        if name.startswith("Strength A") or name.startswith("Strength B"):
            y = render_strength_progression(c, program, session_idx, name, y)
        elif dt == "cardio" and (name.startswith("Week 1 ·") or "Zone 2" in name):
            # Cardio main block · render the full 4-week progression
            y = render_cardio_progression(c, program, session_idx, y)
        else:
            y = render_block_compact(c, block, y)
        y -= 8

    # Final footer + showPage for the last page of this session
    page_footer(c, current_page, total_pages)
    c.showPage()

    return pages_used


def render_cardio_progression(c, program, session_idx, y):
    """Render the cardio session's 4-week progression as a clean table.

    Walks program['weeks'][0..3]['sessions'][session_idx] and renders each
    week's machine + dose. Adds a joint-response rule at the bottom.
    """
    weeks = program.get('weeks', [])
    if len(weeks) < 1:
        return y

    # Find the conditioning block in each week's session
    week_data = []
    for wk_idx, week in enumerate(weeks[:4]):
        sess = week.get('sessions', [])[session_idx] if session_idx < len(week.get('sessions', [])) else None
        if not sess:
            continue
        cond_block = None
        for blk in sess.get('blocks', []):
            bname = blk.get('name', '')
            # The main conditioning block has "Week N ·" or "Zone 2" in its name
            if (bname.startswith(f"Week {wk_idx+1} ·") or
                "Zone 2" in bname or "Retest" in bname or "Foundation" in bname or
                "Build" in bname or "Sustain" in bname or "Pickups" in bname or
                "Interval Block" in bname or "Extended" in bname or "Sustained" in bname):
                cond_block = blk
                break
        if cond_block:
            machine = ""
            dose = ""
            if cond_block.get('exercises'):
                ex = cond_block['exercises'][0]
                machine = ex.get('name', '')
                dose = ex.get('dose', '')
            # Week label · short version (e.g., "Baseline" / "Build" / "Capacity" / "Retest")
            label_map = ["Baseline", "Build", "Capacity", "Retest"]
            short_label = label_map[wk_idx] if wk_idx < 4 else f"Week {wk_idx+1}"
            week_data.append({
                "wk_idx": wk_idx,
                "label": short_label,
                "focus": cond_block.get('name', ''),
                "machine": machine,
                "dose": dose,
            })

    # Section header
    small_caps_label(c, "CARDIO PRESCRIPTION · 4-WEEK PROGRESSION",
                     MARGIN, y, color=SKY_BLUE, size=9.5)
    lw = c.stringWidth("CARDIO PRESCRIPTION · 4-WEEK PROGRESSION", SANS_MEDIUM, 9.5)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
    y -= 18

    # Primary machine line (top of table) · pulled from week 1
    if week_data:
        c.setFillColor(CREAM)
        c.setFont(SERIF_ITALIC, 11)
        c.drawString(MARGIN, y, f"Primary machine · {week_data[0]['machine']}")
        y -= 16

    # Per-week rows
    for w in week_data:
        c.setFillColor(SKY_LIGHT)
        c.setFont(SANS_MEDIUM, 10)
        # Week label and badge
        c.drawString(MARGIN + 4, y, f"WEEK {w['wk_idx']+1}  ·  {w['label'].upper()}")
        y -= 13
        # Focus title
        c.setFillColor(CREAM)
        c.setFont(SERIF, 11)
        focus_short = w['focus']
        # Strip leading "Week N · " prefix
        if focus_short.startswith(f"Week {w['wk_idx']+1} · "):
            focus_short = focus_short.split(" · ", 1)[1] if " · " in focus_short else focus_short
        c.drawString(MARGIN + 14, y, focus_short[:70])
        y -= 13
        # Dose text · word-wrap
        dose_lines = _wrap_to_lines(c, w['dose'], CONTENT_W - 30, SERIF_ITALIC, 10, max_lines=3)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 10)
        for line in dose_lines:
            c.drawString(MARGIN + 14, y, line)
            y -= 12
        y -= 4

    # Joint response rule
    y -= 4
    c.setFillColor(SKY_BLUE)
    c.setFont(SANS_MEDIUM, 9)
    c.drawString(MARGIN, y, "JOINT RESPONSE RULE")
    y -= 12
    c.setFillColor(CREAM)
    c.setFont(SERIF_ITALIC, 10)
    c.drawString(MARGIN + 14, y,
                 "Stop or adjust if symptoms increase, mechanics change, or recovery drops.")
    y -= 14

    return y


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

        # Word-wrap long names · NO ellipses
        name_w = CONTENT_W * 0.55
        name_lines = _wrap_to_lines(c, name, name_w, SERIF, 11, max_lines=2)

        # Word-wrap long doses · NO ellipses
        dose_w = CONTENT_W * 0.38
        dose_lines = _wrap_to_lines(c, dose, dose_w, SANS_MEDIUM, 9, max_lines=2) if dose else [""]

        rows = max(len(name_lines), len(dose_lines))
        line_h = 12

        c.setFillColor(CREAM)
        c.setFont(SERIF, 11)
        for li, line in enumerate(name_lines):
            c.drawString(MARGIN + 12, y - li * line_h, line)

        c.setFillColor(SKY_LIGHT)
        c.setFont(SANS_MEDIUM, 9)
        for li, line in enumerate(dose_lines):
            c.drawRightString(PAGE_W - MARGIN, y - li * line_h, line)

        y -= rows * line_h

    return y


def render_strength_progression(c, program, session_idx, block_name, y):
    """Render a strength block as a 4-week progression table.

    Cell layout · 3 stacked lines per cell, centered ·
       3 × 12
       @ 55 lb /hand
       RPE 7
    Tempo (e.g. "3-sec eccentric") replaces RPE line on Week 2.

    Names wrap cleanly to up to 2 lines · NO ellipses ever.
    """
    weeks = program['weeks']

    blocks_per_week = []
    for wk in weeks:
        sess = wk['sessions'][session_idx]
        for b in sess['blocks']:
            if b['name'] == block_name:
                blocks_per_week.append(b)
                break

    if not blocks_per_week:
        return y
    if len(blocks_per_week) < 4:
        return render_block_compact(c, blocks_per_week[0], y)

    # ── BLOCK LABEL ──
    small_caps_label(c, block_name.upper(), MARGIN, y, color=SKY_BLUE, size=9.5)
    lw = c.stringWidth(block_name.upper(), SANS_MEDIUM, 9.5)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
    y -= 14

    # ── COLUMN GEOMETRY ──
    # 22% name (was 30%) · gives data cells more room for "@ 315 lb" etc.
    name_col_w = CONTENT_W * 0.22
    wk_col_w = (CONTENT_W - name_col_w) / 4

    wk1_exercises = blocks_per_week[0]['exercises']

    # ── HEADER ROW ──
    c.setFillColor(CREAM_DIM)
    c.setFont(SANS_MEDIUM, 7.5)
    c.drawString(MARGIN + 8, y, "EXERCISE")
    wk_labels = [
        "WK 1 · BASE",
        "WK 2 · TEMPO",
        "WK 3 · STRENGTH",
        "WK 4 · PEAK",
    ]
    for i, lbl in enumerate(wk_labels):
        x = MARGIN + name_col_w + i * wk_col_w + wk_col_w / 2
        c.drawCentredString(x, y, lbl)
    y -= 10
    thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 14

    # ── EXERCISE ROWS ──
    LINE_H = 9.5
    ROW_PAD = 8

    for ex_idx, ex in enumerate(wk1_exercises):
        name = ex.get('name', '')

        # Wrap name across up to 2 lines · NO ellipses
        name_lines = _wrap_to_lines(c, name, name_col_w - 12, SERIF, 10, max_lines=2)

        # Pre-compute cell content for all 4 weeks · max line count = row height
        cells = []
        for wk_idx in range(4):
            wk_block = blocks_per_week[wk_idx]
            if ex_idx < len(wk_block['exercises']):
                wk_ex = wk_block['exercises'][ex_idx]
                cells.append(_cell_lines_for_week(wk_ex, wk_idx + 1, wk_col_w - 8, c))
            else:
                cells.append([])

        max_lines = max([len(name_lines)] + [len(cl) for cl in cells]) or 1
        row_height = max_lines * LINE_H + ROW_PAD

        # ── DRAW NAME ──
        c.setFillColor(CREAM)
        c.setFont(SERIF, 10)
        for li, line in enumerate(name_lines):
            c.drawString(MARGIN + 8, y - li * LINE_H, line)

        # ── DRAW CELLS ──
        for wk_idx, cell_lines in enumerate(cells):
            x_center = MARGIN + name_col_w + wk_idx * wk_col_w + wk_col_w / 2
            # Color each line · header line cream, weight line sky-light, tail dim
            for li, line in enumerate(cell_lines):
                if li == 0:
                    c.setFillColor(CREAM)
                    c.setFont(SANS_MEDIUM, 9)
                elif li == 1 and len(cell_lines) > 1:
                    c.setFillColor(SKY_LIGHT if wk_idx > 0 else CREAM_DIM)
                    c.setFont(SANS_MEDIUM, 8.5)
                else:
                    c.setFillColor(CREAM_DIM)
                    c.setFont(SERIF_ITALIC, 8)
                c.drawCentredString(x_center, y - li * LINE_H, line)

        y -= row_height

    # ── LEGEND ──
    y -= 2
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 7.5)
    legend = "W1 base volume · W2 tempo control · W3 strength build · W4 performance · or retest 10RM W4"
    c.drawString(MARGIN + 8, y, legend)
    y -= 8

    return y


def _cell_lines_for_week(wk_ex, week_num, max_w, c):
    """Build the stacked lines for one week's cell.

    Layout (3 stacked lines) ·
      [line 0] sets × reps         (cream)
      [line 1] @ load               (sky)  OR  RIR 2-3 if no test data
      [line 2] tempo OR rpe         (dim italic)

    Returns list of strings · 1 to 3 lines.
    """
    wpx = wk_ex.get('week_prescriptions') or []
    wp = next((w for w in wpx if w.get('week') == week_num), None)

    # If no week_prescription matched, synthesize a minimal one from the
    # 4-week template so bodyweight clients still get RIR + RPE labels.
    if wp is None:
        wp = _synth_wp_from_dose(wk_ex.get('dose', ''), week_num)

    if wp is None:
        return [wk_ex.get('dose', '—')]

    lines = []

    sets = wp.get('sets')
    reps = wp.get('reps')
    if sets and reps:
        lines.append(f"{sets} × {reps}")
    elif wk_ex.get('dose'):
        lines.append(wk_ex.get('dose'))

    weight = wp.get('weight')
    if weight is not None:
        wt = int(weight) if weight == int(weight) else round(weight, 1)
        unit = wp.get('weight_unit') or ''
        note = wp.get('weight_note') or ''
        load_text = f"@ {wt}"
        if unit:
            load_text += f" {unit}"
        if note:
            load_text += f" {note}"
        lines.append(load_text)
    else:
        lines.append("RIR 2-3")

    tempo = wp.get('tempo_note')
    rpe = wp.get('rpe')
    if tempo:
        if tempo == "3-sec eccentric":
            tempo_short = "3-sec eccentric"
            if c.stringWidth(tempo_short, SERIF_ITALIC, 8) > max_w:
                tempo_short = "ecc · 3 sec"
            lines.append(tempo_short)
        else:
            lines.append(tempo)
    elif rpe:
        lines.append(f"RPE {rpe}")

    return lines


# Map week number → (sets, reps, rpe, tempo, intent) for the 4-week IMS block.
# Used as fallback when an exercise has no tested-load prescription.
_WEEK_4_TEMPLATE = {
    1: {"sets": 3, "reps": 12, "rpe": "7",   "tempo_note": "",                "intent_label": "Base Volume"},
    2: {"sets": 3, "reps": 10, "rpe": "7-8", "tempo_note": "3-sec eccentric", "intent_label": "Tempo Control"},
    3: {"sets": 4, "reps": 8,  "rpe": "8",   "tempo_note": "",                "intent_label": "Strength Build"},
    4: {"sets": 4, "reps": 6,  "rpe": "8-9", "tempo_note": "",                "intent_label": "Performance Week"},
}


def _synth_wp_from_dose(dose, week_num):
    """Synthesize a week_prescription dict from a dose string + week number.
    Used when an exercise has no tested-load prescription · gives bodyweight /
    no-test-data clients the same multi-line cell layout.
    """
    if week_num not in _WEEK_4_TEMPLATE:
        return None
    tpl = _WEEK_4_TEMPLATE[week_num].copy()
    tpl["weight"] = None
    tpl["weight_unit"] = ""
    tpl["weight_note"] = ""
    return tpl


def _wrap_to_lines(c, text, max_w, font, size, max_lines=2):
    """Wrap text into up to max_lines lines, NO ellipses ever."""
    if not text:
        return [""]
    if c.stringWidth(text, font, size) <= max_w:
        return [text]

    words = text.split()
    lines = []
    cur = ""
    for w in words:
        candidate = w if not cur else cur + " " + w
        if c.stringWidth(candidate, font, size) <= max_w:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
            if len(lines) >= max_lines - 1:
                # Build the final line · accept overflow rather than truncate
                idx = words.index(w)
                rest = " ".join(words[idx:])
                lines.append(rest)
                return lines[:max_lines]
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def compact_dose(dose):
    """Tighten a dose string aggressively for narrow table cells.

    Examples ·
      '3 × 12-10-8'                               → '3×12-10-8'
      '3 × 12-10-8  · tempo 3-sec eccentric'      → '3×12-10-8 ecc3'
      '3 × 12-10-8  · +5-10 lbs from Wk 1'        → '3×12-10-8 +5-10lb'
      '4 × 12-10-8-6  · same weight as Wk 3...'   → '4×12-10-8-6 +set'
      '4 × 12-10-8-6  · push top set heavy'       → '4×12-10-8-6 ↑heavy'
      '2 × 12-10 (deload) · ~60% of Wk 5 weight'  → '2×12-10 dld'
    """
    s = dose or ""

    # Tempo + iso shorthands (apply BEFORE x/× normalization so strings like
    # "3-sec eccentric" don't get touched by later substitutions)
    replacements = [
        ("tempo 3-sec eccentric", "ecc3"),
        ("3-sec eccentric", "ecc3"),
        ("2-sec eccentric", "ecc2"),
        ("3-sec iso at end range", "iso3"),
        ("2-sec iso at end range", "iso2"),
        ("3-sec iso hold", "iso3"),
        ("2-sec iso hold", "iso2"),
        # Generic trailing notes
        ("same weight as Wk 3, extra set", "+set"),
        ("same weight as Wk 3", ""),
        ("push top set heavy", "↑heavy"),
        ("push load", "↑load"),
        ("push top set", "↑top"),
        ("added set", "+set"),
        ("from Wk 1", ""),
        ("from Week 1", ""),
        ("~60% of Wk 5 weight", ""),
        ("(deload)", "dld"),
        ("deload", "dld"),
        (" lbs", "lb"),
        ("/side", "/s"),
    ]
    for before, after in replacements:
        s = s.replace(before, after)

    # Now safe to normalize 'x' in set-rep context · only where surrounded by digits
    import re
    s = re.sub(r'(\d)\s*x\s*(\d)', r'\1×\2', s)

    # Drop the middle dot separator and any bare parens
    s = s.replace(" · ", " ").replace("·", "")
    s = s.replace("(", "").replace(")", "")

    # Collapse spaces, then strip dangling punctuation
    while "  " in s:
        s = s.replace("  ", " ")
    s = s.strip().strip(",").strip()
    return s


# ==========================================================
# PAGE 12 · NUTRITION
# ==========================================================

# ==========================================================
# NUTRITION · 3-PAGE SPREAD (targets · pantry · day)
# ==========================================================

def draw_nutrition(c, program):
    """Page 1 of 3 · Daily targets + strategy."""
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 08 · NUTRITION · DAILY TARGETS", program['client_name'].upper())

    bc = program['assessment'].get('body_comp', {}) or {}
    targets = bc.get('nutrition_targets', {}) or {}
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

    # DAILY TARGETS
    y -= 60
    small_caps_label(c, "DAILY TARGETS · CALCULATED FROM YOUR LEAN MASS", MARGIN, y,
                     color=SKY_BLUE, size=9)
    lw = c.stringWidth("DAILY TARGETS · CALCULATED FROM YOUR LEAN MASS", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 26

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
        val_str = str(val)
        font_size = 22 if len(val_str) < 10 else 16
        c.setFillColor(CREAM)
        c.setFont(SERIF, font_size)
        c.drawString(x, y - 40, val_str)

    y -= 90

    # Water
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

    # RMR + TDEE context
    rmr = bc.get('rmr_katch_mcardle', '')
    tdee = bc.get('tdee_estimated', '')
    if rmr and tdee:
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 11)
        c.drawString(MARGIN, y,
                     f"RMR · {rmr}   ·   TDEE · {tdee}")
        y -= 18
        thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
        y -= 20

    # THE STRATEGY
    small_caps_label(c, "THE STRATEGY", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("THE STRATEGY", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    primary_goal = (program['assessment'].get('primary_goal') or '').lower()
    is_runner = 'run' in primary_goal or 'marathon' in primary_goal
    is_strength = 'strong' in primary_goal or 'strength' in primary_goal
    is_fat_loss = 'lose' in primary_goal or 'fat' in primary_goal or 'weight' in primary_goal

    if is_runner:
        strategy = ("Endurance-forward fueling. Carbs are prioritized to support running volume "
                    "and recovery. Protein at every meal protects lean mass. Hydration matters most "
                    "on run days — add 16 oz per hour of training. Whole-food sources only · your "
                    "gut and joints respond to food quality, not just macros.")
    elif is_strength:
        strategy = ("Strength-forward fueling. Protein is prioritized at ~1.0 g per lb of lean mass "
                    "to support adaptation. Carbs fuel training sessions. Fat fills the remainder for "
                    "hormone and joint health. Eat real food · grass-fed proteins, organic produce, "
                    "whole-food carbs. Skip the powders when possible.")
    elif is_fat_loss:
        strategy = ("Fat-loss fueling in a mild deficit (~300 cal below TDEE). Protein stays high to "
                    "protect lean mass while you lose fat. Carbs are lower but still support training. "
                    "Quality matters more than ever in a deficit · clean, whole, organic when possible. "
                    "Veggies on every plate for fiber and satiety.")
    else:
        strategy = ("Balanced fueling built around your lean mass — not your scale weight. Protein at "
                    "every meal protects muscle. Carbs fuel training. Fat rounds out hormone and joint "
                    "health. Real food first · the generator targets macros, but your body responds to "
                    "food QUALITY.")

    y = draw_wrapped(c, strategy, MARGIN, y, CONTENT_W, SERIF, 11.5, leading=16, color=CREAM)

    # FOOD QUALITY PRINCIPLES · 3-column teaser (detail on next page)
    y -= 30
    small_caps_label(c, "THE FOUR PRINCIPLES", MARGIN, y, color=SKY_BLUE, size=10)
    lw = c.stringWidth("THE FOUR PRINCIPLES", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 22

    principles = [
        ("01 · ORGANIC FIRST", "Cleaner hormones · less inflammation · better recovery."),
        ("02 · WHOLE FOOD", "If it comes in a box, question it. Real food is the starting point."),
        ("03 · LEAN MASS TARGETS", "Macros calculated from BOD POD · not a generic formula."),
        ("04 · TIMING MATTERS", "Pre-workout · post-workout · before bed. Turn the page."),
    ]
    for i, (label, note) in enumerate(principles):
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(MARGIN, y, label)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 10.5)
        c.drawString(MARGIN + 160, y, note)
        y -= 17

    # Footer
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 9)
    c.drawCentredString(PAGE_W / 2, MARGIN + 30,
                        "These targets are a starting point. We adjust based on energy, sleep, and performance.")


def draw_nutrition_pantry(c, program):
    """Page 2 of 3 · The Pantry · organic whole-food lists by category."""
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 08 · NUTRITION · THE PANTRY", program['client_name'].upper())

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "The")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "pantry list.")

    y -= 50
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 11)
    intro = ("Shop the outside of the store. Organic whenever possible · especially for proteins, "
             "leafy greens, and berries. Pastured, grass-fed, wild-caught · quality matters.")
    y = draw_wrapped(c, intro, MARGIN, y, CONTENT_W, SERIF_ITALIC, 11, leading=16, color=CREAM_DIM)
    y -= 20

    # Category grid · 2 columns
    categories = [
        {
            "name": "PROTEINS · PASTURED / WILD",
            "items": [
                "Grass-fed beef (ribeye, ground, steak)",
                "Pastured chicken (thigh, breast, whole)",
                "Wild salmon · sardines · mackerel",
                "Pastured eggs · organic cottage cheese",
                "Grass-fed Greek yogurt · kefir",
                "Bison · lamb · venison",
                "Organ meats (liver, heart · if you can)",
            ]
        },
        {
            "name": "CARBS · WHOLE-FOOD",
            "items": [
                "Sweet potato · white potato · yam",
                "Organic white rice · jasmine · basmati",
                "Steel-cut oats · rolled oats",
                "Quinoa · buckwheat · millet",
                "Sourdough bread (real, not supermarket)",
                "Plantains · bananas · dates",
                "Honey · maple syrup (real, limited)",
            ]
        },
        {
            "name": "FATS · COLD-PRESSED / PASTURED",
            "items": [
                "Extra virgin olive oil (cold-pressed)",
                "Avocado · avocado oil",
                "Grass-fed butter · ghee",
                "Coconut oil · MCT oil",
                "Raw nuts (almonds, walnuts, macadamia)",
                "Seeds (chia, flax, pumpkin, sunflower)",
                "Pastured tallow · lard for cooking",
            ]
        },
        {
            "name": "PRODUCE · ORGANIC WHEN POSSIBLE",
            "items": [
                "Leafy greens (spinach, arugula, kale)",
                "Cruciferous (broccoli, cauliflower, Brussels)",
                "Berries (blue, rasp, black) · organic!",
                "Peppers · tomatoes · cucumber",
                "Onions · garlic · herbs (fresh)",
                "Squash (butternut, acorn, spaghetti)",
                "Avocados · lemons · limes",
            ]
        },
    ]

    col_w = (CONTENT_W - 20) / 2
    col_x = [MARGIN, MARGIN + col_w + 20]
    col_y = [y, y]

    for i, cat in enumerate(categories):
        col = i % 2
        cx = col_x[col]
        cy = col_y[col]

        # Category label
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(cx, cy, cat["name"])
        cy -= 10
        thin_divider(c, cx, cy, cx + col_w - 8, color=DIVIDER, width=0.4)
        cy -= 14

        # Items
        c.setFillColor(CREAM)
        c.setFont(SERIF, 10.5)
        for item in cat["items"]:
            c.drawString(cx, cy, "·  " + item)
            cy -= 15

        col_y[col] = cy - 18

    # Avoid list at bottom
    y_bottom = min(col_y) - 10
    small_caps_label(c, "AVOID OR MINIMIZE", MARGIN, y_bottom, color=SKY_BLUE, size=9)
    lw = c.stringWidth("AVOID OR MINIMIZE", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y_bottom + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y_bottom -= 18

    avoids = "Seed oils (canola, soybean, corn) · ultra-processed packaged foods · industrial sugar · conventional CAFO meat when possible · artificial sweeteners"
    draw_wrapped(c, avoids, MARGIN, y_bottom, CONTENT_W, SERIF_ITALIC, 10.5, leading=15, color=CREAM_DIM)


def draw_nutrition_day(c, program):
    """Page 3 of 3 · Sample day + timing + supplements."""
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "SECTION 08 · NUTRITION · A DAY ON THE PLATE", program['client_name'].upper())

    bc = program['assessment'].get('body_comp', {}) or {}
    targets = bc.get('nutrition_targets', {}) or {}
    if not isinstance(targets, dict):
        targets = {}

    primary_goal = (program['assessment'].get('primary_goal') or '').lower()
    is_runner = 'run' in primary_goal or 'marathon' in primary_goal
    is_strength = 'strong' in primary_goal or 'strength' in primary_goal

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "A day on")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "the plate.")

    y -= 60
    small_caps_label(c, "SAMPLE DAY · WHOLE-FOOD MEALS · ORGANIC WHERE YOU CAN", MARGIN, y,
                     color=SKY_BLUE, size=9)
    lw = c.stringWidth("SAMPLE DAY · WHOLE-FOOD MEALS · ORGANIC WHERE YOU CAN", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 22

    # Build sample meals with timing
    meals = build_sample_meals(targets, is_runner, is_strength)
    # Scale meal portions so the sample day total lands within ±100 cal of target
    meals = scale_meals_to_target(meals, targets)
    for i, (meal_name, items, meal_cals) in enumerate(meals):
        # Extract time from meal_name if present
        c.setFillColor(CREAM)
        c.setFont(SERIF_ITALIC, 12)
        c.drawString(MARGIN, y, meal_name)
        c.setFillColor(SKY_LIGHT)
        c.setFont(SANS_MEDIUM, 9)
        c.drawRightString(PAGE_W - MARGIN, y, f"~{meal_cals} cal")
        y -= 13
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF, 10.5)
        # wrap items if long
        y = draw_wrapped(c, items, MARGIN + 14, y, CONTENT_W - 14, SERIF, 10.5, leading=14, color=CREAM_DIM)
        y -= 6
        thin_divider(c, MARGIN, y, PAGE_W - MARGIN, color=DIVIDER, width=0.3)
        y -= 10

    # TIMING
    y -= 6
    small_caps_label(c, "MEAL TIMING", MARGIN, y, color=SKY_BLUE, size=9)
    lw = c.stringWidth("MEAL TIMING", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 18

    if is_runner:
        timing = ("Eat a real breakfast within 90 min of waking. Snack 45-60 min before runs over 45 min · banana + honey or dates. Protein + carbs within 30 min of finishing. Final meal 2-3 hrs before bed.")
    elif is_strength:
        timing = ("Eat breakfast within 90 min of waking. Pre-training · protein + carbs 60-90 min before. Post-training · biggest meal of the day within 60 min. Protein before bed (cottage cheese, casein) helps overnight recovery.")
    else:
        timing = ("Eat within 90 min of waking to stabilize energy. Eat every 3-4 hrs. Pre-training · small carb snack if training fasted feels rough. Post-training · protein + carbs within an hour. Last meal 2-3 hrs before bed.")

    c.setFillColor(CREAM)
    c.setFont(SERIF, 11)
    y = draw_wrapped(c, timing, MARGIN, y, CONTENT_W, SERIF, 11, leading=15, color=CREAM)

    # SUPPLEMENTS
    y -= 18
    small_caps_label(c, "SUPPLEMENTS · BASELINE", MARGIN, y, color=SKY_BLUE, size=9)
    lw = c.stringWidth("SUPPLEMENTS · BASELINE", SANS_MEDIUM, 9)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.4)
    y -= 20

    supps = [
        ("VITAMIN D3 + K2", "5,000 IU D3 + 100 mcg K2  ·  with breakfast"),
        ("FISH OIL / OMEGA-3", "2-3 g EPA/DHA daily  ·  with meals  ·  smelly pills mean it went rancid"),
        ("MAGNESIUM GLYCINATE", "300-400 mg before bed  ·  sleep + recovery"),
        ("CREATINE MONOHYDRATE", "5 g daily, any time  ·  the only powder that's always worth it"),
        ("ELECTROLYTES", "sodium + potassium + magnesium on training days · LMNT or homemade"),
    ]
    for label, note in supps:
        c.setFillColor(SKY_BLUE)
        c.setFont(SANS_MEDIUM, 9)
        c.drawString(MARGIN, y, label)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 10.5)
        c.drawString(MARGIN + 160, y, note)
        y -= 16

    # Footer
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 9)
    c.drawCentredString(PAGE_W / 2, MARGIN + 30,
                        "Food first. Supplements fill gaps · they don't replace the plate.")


def scale_meals_to_target(meals, targets):
    """Scale every meal's calorie count proportionally so the daily total
    lands within ±100 cal of the target.

    If we can't read a target, return meals as-is.

    The meal item text remains generic but the per-meal calorie
    annotation reflects the scaled value.
    """
    if not meals or not targets:
        return meals

    # Try to extract numeric calorie target · "1959" or "1959 cal" or "~2,000"
    raw = targets.get('calories', None)
    if raw is None:
        return meals
    target_str = str(raw).replace(',', '').replace('cal', '').strip()
    # Pull the first integer from the string
    import re
    m = re.search(r'\d+', target_str)
    if not m:
        return meals
    target = int(m.group())
    if target <= 0:
        return meals

    current_total = sum(c for _, _, c in meals)
    if current_total <= 0:
        return meals

    # If we're already within ±100, no need to scale
    if abs(current_total - target) <= 100:
        return meals

    factor = target / current_total
    scaled = []
    running = 0
    for i, (name, items, cals) in enumerate(meals):
        if i == len(meals) - 1:
            # Last meal absorbs rounding so the total is exact
            new_cals = target - running
            new_cals = max(50, new_cals)  # don't let it go silly small
        else:
            new_cals = int(round(cals * factor / 10) * 10)  # round to nearest 10
            running += new_cals
        scaled.append((name, items, new_cals))
    return scaled


def build_sample_meals(targets, is_runner, is_strength):
    """Produce a sample day matched to the target profile · whole-food, organic-first.

    Returns list of (meal_name, items_string, calories).
    Every item is a specific quality source · grass-fed, pastured, wild, organic.
    """
    if is_runner:
        # Endurance-forward · carb-loaded around runs · all whole food
        return [
            ("7:00 AM · Breakfast",
             "Steel-cut oats w/ banana, pastured eggs over easy (2), Greek yogurt + wild blueberries, raw honey, coffee w/ grass-fed butter",
             620),
            ("10:30 AM · Mid-morning",
             "Organic apple + handful raw almonds + pinch of sea salt",
             240),
            ("1:00 PM · Lunch",
             "Grass-fed ground beef + jasmine rice bowl · sweet potato · avocado · mixed greens · EVOO + lemon",
             720),
            ("4:30 PM · Pre-run fuel (if running >45 min)",
             "Banana + raw honey + sourdough toast OR 4-5 medjool dates",
             220),
            ("7:30 PM · Dinner",
             "Wild salmon · quinoa + roasted beets · sautéed spinach w/ garlic · EVOO · dark leafy salad",
             620),
        ]
    elif is_strength:
        # Strength-forward · protein-heavy · all whole food
        return [
            ("7:00 AM · Breakfast",
             "4 pastured eggs + spinach + grass-fed cheddar · grass-fed Greek yogurt + wild blueberries + walnuts · coffee",
             560),
            ("12:00 PM · Lunch",
             "Pastured chicken thigh · jasmine rice · black beans · avocado · roasted peppers · EVOO",
             720),
            ("4:00 PM · Pre-training (60-90 min out)",
             "Grass-fed beef jerky + organic apple + handful raw cashews",
             320),
            ("7:00 PM · Post-training · biggest meal of day",
             "Grass-fed ribeye or bison · roasted sweet potato + grass-fed butter · broccoli · mixed greens",
             780),
            ("10:00 PM · Before bed",
             "Organic cottage cheese + raw walnuts + drizzle of raw honey",
             260),
        ]
    else:
        # Balanced / fat-loss / general · whole food, quality first
        return [
            ("7:30 AM · Breakfast",
             "3 pastured eggs scrambled w/ spinach + avocado · 1 cup berries · coffee w/ grass-fed butter (optional)",
             480),
            ("12:30 PM · Lunch",
             "Pastured chicken OR wild salmon · sweet potato · roasted veg · EVOO + lemon · dark leafy salad",
             640),
            ("3:30 PM · Snack",
             "Grass-fed Greek yogurt + wild blueberries + raw almonds + pinch of cinnamon",
             280),
            ("7:00 PM · Dinner",
             "Grass-fed beef OR wild fish · white rice OR potato · sautéed greens · avocado · herbs",
             620),
            ("9:30 PM · Optional (if hungry)",
             "Organic cottage cheese + walnuts · OR a small handful of macadamia nuts",
             200),
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
    sessions = program['weeks'][0]['sessions']
    a = program['assessment']
    sd = a.get('strength_days', 0)
    cd = a.get('cardio_days', 0)
    spread = _spread_days_across_week(sd, cd, len(sessions))
    session_map = {sn: day_idx for sn, day_idx in spread.items()}
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
    page_header_bar(c, "SECTION 10  ·  THE COACHING PROCESS",
                    program['client_name'].upper())

    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "How we")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "keep adapting.")

    y -= 64
    paras = [
        "This four-week block is a starting point, not a finish line. Real progress comes from the next block, and the one after that — each one tuned to what your body is actually responding to.",
        "At the end of the block, we look at three things together · how you've been feeling and recovering, what your body is telling us through the work, and what life looks like in the weeks ahead.",
        "From there we adjust. New loads. Different exercises. A new emphasis. The goal is never to chase a random workout — it's to build a system your body can keep adapting to.",
    ]
    for p in paras:
        y = draw_wrapped(c, p, MARGIN, y, CONTENT_W - 60, SERIF, 12.5,
                         leading=18, color=CREAM)
        y -= 10

    # ── HOW WE ADJUST ──
    y -= 14
    small_caps_label(c, "HOW WE ADJUST YOUR PLAN", MARGIN, y,
                     color=SKY_BLUE, size=10)
    lw = c.stringWidth("HOW WE ADJUST YOUR PLAN", SANS_MEDIUM, 10)
    thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER)
    y -= 26

    items = [
        ("Test results",
         "Where the numbers moved · where they didn't · what that's telling us."),
        ("Client feedback",
         "Soreness, recovery, schedule stress, and how training felt in your body."),
        ("What life looks like",
         "Travel, family, work load · we build the next block around your real schedule."),
        ("Coach observation",
         "What we saw in the room · movement quality, focus, the things data can't measure."),
    ]
    for label, sub in items:
        c.setFillColor(CREAM)
        c.setFont(SERIF, 13)
        c.drawString(MARGIN + 6, y, label)
        c.setFillColor(CREAM_DIM)
        c.setFont(SERIF_ITALIC, 10.5)
        # Wrap the sub-text if it's long
        sub_lines = wrap(c, sub, SERIF_ITALIC, 10.5, CONTENT_W - 180)
        for li, line in enumerate(sub_lines):
            c.drawString(MARGIN + 160, y - li * 13, line)
        # Move y down by the taller of label or sub
        rows_used = max(1, len(sub_lines))
        y -= 8 + rows_used * 13
        thin_divider(c, MARGIN, y + 4, PAGE_W - MARGIN, color=DIVIDER, width=0.3)
        y -= 10

    # ── CLOSING LINE ──
    y -= 12
    c.setFillColor(SKY_LIGHT)
    c.setFont(SERIF_ITALIC, 11.5)
    closing = "The work is the same every week. The strategy adapts."
    c.drawString(MARGIN, y, closing)


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

def _spread_days_across_week(strength_days, cardio_days, num_sessions):
    """Distribute training sessions across a 7-day week with reasonable spacing.

    Rules ·
      Strength days get priority placement (alternating with rest days)
      Cardio days fill in the remaining slots

    Returns · {session_index(1-based) : day_of_week(1-7)}
    """
    total = strength_days + cardio_days
    if total == 0 or num_sessions == 0:
        return {}

    # Pre-baked spreads · kept simple for readability
    spreads = {
        # strength + cardio total → day slots in order
        1: [1],
        2: [1, 4],
        3: [1, 3, 5],
        4: [1, 2, 4, 5],
        5: [1, 2, 4, 5, 6],
        6: [1, 2, 3, 4, 5, 6],
        7: [1, 2, 3, 4, 5, 6, 7],
    }
    slots = spreads.get(total, list(range(1, total + 1)))

    result = {}
    for i in range(num_sessions):
        if i < len(slots):
            result[i + 1] = slots[i]
        else:
            result[i + 1] = i + 1  # fallback
    return result


def draw_coach_appendix(c, program):
    """Render the coach-only page · math, flags, substitution rationale,
    constraint detail, and review notes. This is what the coach sees but
    the client doesn't.
    """
    fill_page(c, NAVY)
    ghost_watermark(c, "ims")
    page_header_bar(c, "COACH APPENDIX", program['client_name'].upper())

    # Editorial header
    y = PAGE_H - MARGIN - 150
    c.setFillColor(CREAM)
    c.setFont(SERIF, 42)
    c.drawString(MARGIN, y, "Behind the")
    y -= 50
    c.setFillColor(SKY_BLUE)
    c.setFont(SERIF_ITALIC, 42)
    c.drawString(MARGIN, y, "programming.")

    assessment = program.get('assessment', {})
    y -= 56

    # ── 1 · STRENGTH MATH ──────────────────────────────
    tests = assessment.get('strength_marker_tests') or []
    if tests:
        small_caps_label(c, "STRENGTH TESTING ANCHORS · MATH", MARGIN, y, color=SKY_BLUE, size=10)
        lw = c.stringWidth("STRENGTH TESTING ANCHORS · MATH", SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 20

        # Lower-bound sanity checks per movement category to flag entry errors.
        # If a tested weight is below this floor, we suspect a typo (e.g. 3 lb
        # for a Trap Bar Deadlift) and surface a flag in the appendix.
        SUSPICIOUS_FLOOR = {
            "deadlift": 45,        # an empty barbell
            "trap_bar": 95,
            "squat": 45,
            "bench": 45,
            "row": 30,
            "press": 20,
        }

        # Name normalization · catch common typos
        NAME_FIXES = {
            "pulllups": "Pull-ups",
            "pulllup": "Pull-up",
            "puplup": "Pull-up",
            "chinups": "Chin-ups",
            "rdls": "RDLs",
            "kbsswings": "KB Swings",
        }

        def _normalize_name(s):
            if not s:
                return "(unnamed)"
            key = s.strip().lower().replace("-", "").replace(" ", "")
            return NAME_FIXES.get(key, s.strip())

        def _form_label(s):
            if not s or s.strip() in ("?", ""):
                return "not recorded"
            return s.strip()

        for t in tests:  # show all anchors · spec requires no truncation
            name = _normalize_name(t.get('exercise_name'))
            cat = t.get('movement_category') or 'movement'
            cat_clean = cat.replace("_", " ") if cat != "movement" else cat
            form_q = _form_label(t.get('form_quality'))
            pain_notes = (t.get('pain_or_compensation_notes') or '').strip()
            coach_notes_t = (t.get('coach_notes') or '').strip()

            # Top tested rep / weight
            top = None
            for r in (3, 5, 6, 8, 10, 12):
                v = t.get(f'tested_{r}rm')
                if v:
                    top = (r, v)
                    break

            # Skip rows with no math AND no notes · they're incomplete
            if not top and not pain_notes and not coach_notes_t and form_q == "not recorded":
                continue

            line1 = f"{name}  ·  {cat_clean}  ·  form: {form_q}"
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 10)
            c.drawString(MARGIN, y, line1[:90])
            y -= 14

            if top:
                fq_mult = {"clean": 1.00, "moderate": 0.93, "poor": 0.85}.get(form_q, 1.00)
                pain_mult = 0.90 if pain_notes else 1.00
                try:
                    weight = float(top[1])
                except (TypeError, ValueError):
                    weight = 0
                est_1rm = weight * (1 + top[0] / 30.0)
                training_max = est_1rm * 0.85 * fq_mult * pain_mult
                math_str = (f"   {weight:.0f} × {top[0]}RM  →  est 1RM ≈ {est_1rm:.0f}  ·  "
                            f"TM (×0.85 ·  fq {fq_mult:.2f} ·  pain {pain_mult:.2f}) ≈ {training_max:.0f}")
                c.setFillColor(CREAM_DIM)
                c.setFont(SERIF_ITALIC, 9.5)
                c.drawString(MARGIN, y, math_str[:110])
                y -= 12

                # Suspiciously-low weight flag · catches data entry errors
                cat_lower = (cat or "").lower()
                floor = None
                for cat_key, floor_v in SUSPICIOUS_FLOOR.items():
                    if cat_key in cat_lower or cat_key in name.lower():
                        floor = floor_v
                        break
                if floor and weight > 0 and weight < floor:
                    c.setFillColor(LIMITED)
                    c.setFont(SERIF_ITALIC, 9)
                    c.drawString(MARGIN, y,
                                  f"   ⚠ {weight:.0f} lb is unusually light for {cat_clean} · likely data entry error")
                    y -= 11

            if pain_notes:
                # Truncated notes flagged · long notes get word-boundary trim
                if len(pain_notes) >= 90 and not pain_notes.rstrip().endswith(('.', '!', '?')):
                    note_text = pain_notes[:87].rsplit(" ", 1)[0] + " (truncated)"
                else:
                    note_text = pain_notes[:90]
                c.setFillColor(LIMITED)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN, y, f"   ⚠ {note_text}")
                y -= 11
            if coach_notes_t:
                c.setFillColor(SKY_BLUE)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN, y, f"   coach: {coach_notes_t[:90]}")
                y -= 11
            y -= 4
        y -= 8

    # ── 1b · USED / UNUSED STRENGTH ANCHORS ──────────────
    # Walk the actual programmed exercise objects from the JSON · they carry
    # week_prescriptions and the anchor_match_method we attached at build time.
    # This is the source of truth for what the renderer will actually display,
    # NOT a re-run of the resolver (which doesn't know about the renderer's
    # category-match weight-nulling, etc.).
    if tests:
        try:
            class _T:
                def __init__(self, d):
                    for k, v in (d or {}).items():
                        setattr(self, k, v)
            test_objs = [_T(t) for t in tests]

            # name → matched test name for quick lookup
            test_names = {getattr(t, 'exercise_name', None): t for t in test_objs
                          if getattr(t, 'exercise_name', None)}

            used = {}      # test_name -> {test, slots: [{exercise, method, has_wp, with_loads}]}
            for week in program.get('weeks', [])[:1]:
                for sess in week.get('sessions', []):
                    for blk in sess.get('blocks', []):
                        if not (blk.get('name', '').startswith("Strength")):
                            continue
                        for ex in blk.get('exercises', []):
                            method = ex.get('anchor_match_method')
                            source = ex.get('anchor_source_name')
                            if not method or not source:
                                continue
                            wp = ex.get('week_prescriptions') or []
                            has_wp = len(wp) > 0
                            with_loads = any(w.get('weight') is not None for w in wp)
                            slot_list = used.setdefault(source, {
                                "test": test_names.get(source),
                                "slots": [],
                            })["slots"]
                            slot_list.append({
                                "exercise": ex.get('name', ''),
                                "method": method,
                                "has_wp": has_wp,
                                "with_loads": with_loads,
                            })

            used_names = set(used.keys())
            unused_tests = [t for t in test_objs
                              if getattr(t, 'exercise_name', None) not in used_names]

            # USED ANCHORS section
            small_caps_label(c, "USED STRENGTH ANCHORS", MARGIN, y, color=SKY_BLUE, size=10)
            lw = c.stringWidth("USED STRENGTH ANCHORS", SANS_MEDIUM, 10)
            thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
            y -= 18

            if not used:
                c.setFillColor(CREAM_DIM)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN + 14, y, "(none of the anchors matched any programmed exercise)")
                y -= 14
            else:
                for source_name, payload in used.items():
                    slots = payload["slots"]
                    # Dedupe by (exercise, method) so we don't list the same exercise
                    # 4× when it shows up in week 1-4 sessions
                    seen = set()
                    unique_slots = []
                    for s in slots:
                        key = (s["exercise"], s["method"])
                        if key in seen:
                            continue
                        seen.add(key)
                        unique_slots.append(s)

                    c.setFillColor(OPTIMAL)
                    c.setFont(SANS_MEDIUM, 9)
                    c.drawString(MARGIN + 14, y, f"✓ {source_name}")
                    y -= 11
                    for s in unique_slots[:4]:
                        loads_label = "loads ✓" if s["with_loads"] else "loads ✗ (rep scheme only)"
                        wp_label = "wp ✓" if s["has_wp"] else "wp ✗"
                        line = (f"applied to: {s['exercise']}  ·  match: {s['method']}  ·  "
                                f"{wp_label}  ·  {loads_label}")
                        c.setFillColor(CREAM_DIM if s["with_loads"] else LIMITED)
                        c.setFont(SERIF_ITALIC, 9)
                        # Word-wrap the line
                        for chunk in _wrap_to_lines(c, line, CONTENT_W - 30, SERIF_ITALIC, 9, max_lines=2):
                            c.drawString(MARGIN + 28, y, chunk)
                            y -= 11
                    y -= 2
            y -= 4

            # UNUSED ANCHORS section
            if unused_tests:
                small_caps_label(c, "UNUSED STRENGTH ANCHORS", MARGIN, y, color=LIMITED, size=10)
                lw = c.stringWidth("UNUSED STRENGTH ANCHORS", SANS_MEDIUM, 10)
                thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
                y -= 18
                for t in unused_tests:
                    name = getattr(t, "exercise_name", "(unnamed)")
                    cat = getattr(t, "movement_category", None) or "uncategorized"
                    # Quick summary · top tested rep max
                    summary = ""
                    for r in (3, 5, 6, 8, 10, 12):
                        v = getattr(t, f"tested_{r}rm", None)
                        if v:
                            unit = getattr(t, "load_unit", "lb")
                            summary = f"{v:.0f} {unit} × {r}RM"
                            break
                    c.setFillColor(LIMITED)
                    c.setFont(SANS_MEDIUM, 9)
                    c.drawString(MARGIN + 14, y, f"⚠ {name}")
                    y -= 11
                    c.setFillColor(CREAM_DIM)
                    c.setFont(SERIF_ITALIC, 9)
                    detail = f"{cat}"
                    if summary:
                        detail += f" · {summary}"
                    detail += " · no matching programmed exercise"
                    c.drawString(MARGIN + 28, y, detail[:100])
                    y -= 13
                y -= 6
        except Exception:
            pass

    # ── 2 · STRUCTURED CONSTRAINTS ─────────────────────
    rich = assessment.get('constraints_rich') or []
    if rich:
        small_caps_label(c, "CONSTRAINTS · STRUCTURED DETAIL", MARGIN, y, color=SKY_BLUE, size=10)
        lw = c.stringWidth("CONSTRAINTS · STRUCTURED DETAIL", SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 20

        def _truncated(txt):
            """Return (clean_text, was_truncated) tuple."""
            txt = txt.strip()
            if len(txt) >= 90 and not txt.rstrip().endswith(('.', '!', '?')):
                # Likely truncated · trim at word boundary and flag
                return txt[:85].rsplit(" ", 1)[0] + " (truncated)", True
            return txt[:90], False

        for cr in rich[:6]:
            display = cr.get('display_name') or cr.get('key') or '?'
            side_raw = cr.get('side') or '—'
            # "bilateral side" reads weird · drop the redundant " side"
            side = "bilateral" if side_raw == "bilateral" else side_raw
            status = (cr.get('status') or '—').replace('_', ' ')
            pain = cr.get('pain_level')
            avoid = (cr.get('avoid_notes') or '').strip()
            allowed = (cr.get('allowed_notes') or '').strip()
            cnotes = (cr.get('coach_notes') or '').strip()

            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 10)
            side_part = f"  ·  {side}" if side and side != '—' else ""
            c.drawString(MARGIN, y,
                         f"{display}  ·  status: {status}{side_part}"
                         + (f"  ·  pain: {pain}/10" if pain is not None else ""))
            y -= 14
            if avoid:
                clean, was_trunc = _truncated(avoid)
                c.setFillColor(LIMITED)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN + 16, y, f"avoid: {clean}")
                y -= 11
            if allowed:
                clean, _ = _truncated(allowed)
                c.setFillColor(OPTIMAL)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN + 16, y, f"allowed: {clean}")
                y -= 11
            if cnotes:
                clean, _ = _truncated(cnotes)
                c.setFillColor(SKY_BLUE)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN + 16, y, f"coach: {clean}")
                y -= 11
            y -= 4
        y -= 8

    # ── 3 · CARDIO TEST DATA ────────────────────────────
    cp = assessment.get('cardio_profile')
    if isinstance(cp, dict):
        small_caps_label(c, "CARDIO · TEST DATA & PROGRESSION LOGIC", MARGIN, y, color=SKY_BLUE, size=10)
        lw = c.stringWidth("CARDIO · TEST DATA & PROGRESSION LOGIC", SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 18

        # Modality & limitations summary
        primary = (cp.get('primary_modality') or '').replace('_', ' ').title() or '—'
        secondaries = ", ".join(m.replace('_', ' ').title()
                                  for m in (cp.get('secondary_modalities') or [])) or '—'
        avoids = ", ".join(m.replace('_', ' ').title()
                            for m in (cp.get('avoid_modalities') or [])) or '—'
        limits = ", ".join(l.replace('_', ' ')
                            for l in (cp.get('limitations') or [])) or '—'

        c.setFillColor(CREAM)
        c.setFont(SANS_MEDIUM, 9.5)
        c.drawString(MARGIN, y, f"Primary: {primary}  ·  Alt: {secondaries}")
        y -= 12
        c.drawString(MARGIN, y, f"Avoid: {avoids}")
        y -= 12
        c.setFillColor(SKY_BLUE)
        c.drawString(MARGIN, y, f"Limitations: {limits}")
        y -= 14

        # Z2 baseline
        z2 = cp.get('z2_baseline') or {}
        if any(v is not None and v != "" for v in z2.values()):
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9)
            c.drawString(MARGIN, y, "Z2 BASELINE TEST")
            y -= 11
            parts = []
            if z2.get('machine'):
                parts.append(f"machine: {str(z2.get('machine')).replace('_', ' ').title()}")
            if z2.get('duration_minutes') is not None:
                parts.append(f"{z2.get('duration_minutes')} min")
            if z2.get('avg_hr'):
                parts.append(f"avg HR {z2.get('avg_hr')}")
            if z2.get('peak_hr'):
                parts.append(f"peak {z2.get('peak_hr')}")
            if z2.get('rpe') is not None:
                parts.append(f"RPE {z2.get('rpe')}")
            if z2.get('avg_watts'):
                parts.append(f"{z2.get('avg_watts')} W avg")
            if z2.get('distance'):
                parts.append(str(z2.get('distance')))
            if z2.get('calories'):
                parts.append(f"{z2.get('calories')} kcal")
            if z2.get('resistance_level'):
                parts.append(f"resist {z2.get('resistance_level')}")
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 9)
            c.drawString(MARGIN + 14, y, "  ·  ".join(parts)[:110])
            y -= 11
            if z2.get('notes'):
                c.drawString(MARGIN + 14, y, f"notes: {z2.get('notes')[:90]}")
                y -= 11
            if z2.get('joint_tolerance_notes'):
                c.setFillColor(LIMITED if 'pain' in z2.get('joint_tolerance_notes').lower()
                                or 'flare' in z2.get('joint_tolerance_notes').lower() else OPTIMAL)
                c.drawString(MARGIN + 14, y, f"joints: {z2.get('joint_tolerance_notes')[:90]}")
                y -= 11
            y -= 4

        # Interval test
        iv = cp.get('interval_test') or {}
        if any(v is not None and v != "" for v in iv.values()):
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9)
            c.drawString(MARGIN, y, "INTERVAL TEST")
            y -= 11
            parts = []
            if iv.get('machine'):
                parts.append(f"machine: {str(iv.get('machine')).replace('_', ' ').title()}")
            if iv.get('protocol'):
                parts.append(str(iv.get('protocol')))
            elif iv.get('work_seconds') and iv.get('rest_seconds') and iv.get('rounds'):
                parts.append(f"{iv.get('work_seconds')}s/{iv.get('rest_seconds')}s × {iv.get('rounds')}")
            if iv.get('peak_watts'):
                parts.append(f"peak {iv.get('peak_watts')} W")
            if iv.get('avg_watts'):
                parts.append(f"avg {iv.get('avg_watts')} W")
            if iv.get('peak_hr'):
                parts.append(f"peak HR {iv.get('peak_hr')}")
            if iv.get('ending_rpe') is not None:
                parts.append(f"end RPE {iv.get('ending_rpe')}")
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 9)
            c.drawString(MARGIN + 14, y, "  ·  ".join(parts)[:110])
            y -= 11
            if iv.get('joint_tolerance_notes'):
                c.drawString(MARGIN + 14, y, f"joints: {iv.get('joint_tolerance_notes')[:90]}")
                y -= 11
            if iv.get('recovery_notes'):
                c.drawString(MARGIN + 14, y, f"recovery: {iv.get('recovery_notes')[:90]}")
                y -= 11
            y -= 4

        # HR recovery
        hrr = cp.get('hr_recovery') or {}
        if any(v is not None for v in hrr.values()):
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9)
            c.drawString(MARGIN, y, "HR RECOVERY")
            y -= 11
            parts = []
            if hrr.get('end_hr'):
                parts.append(f"end {hrr.get('end_hr')}")
            if hrr.get('one_min_hr'):
                parts.append(f"1-min {hrr.get('one_min_hr')}")
            if hrr.get('drop_one_min') is not None:
                drop = hrr.get('drop_one_min')
                quality = "strong" if drop >= 18 else "normal" if drop >= 12 else "poor"
                parts.append(f"drop -{drop} bpm ({quality})")
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 9)
            c.drawString(MARGIN + 14, y, "  ·  ".join(parts)[:110])
            y -= 14

        # Coach flags from cardio_rules
        try:
            from cardio_rules import (
                normalize_cardio_profile,
                determine_interval_clearance,
                decide_machine_with_audit,
                detect_contradictions,
                generate_cardio_coach_flags,
                MODALITY_DISPLAY,
            )
            # Reconstruct a profile-like object for the rules engine
            class _Pseudo:
                pass
            pseudo = _Pseudo()
            pseudo.primary_modality = cp.get('primary_modality')
            pseudo.secondary_modalities = cp.get('secondary_modalities') or []
            pseudo.avoid_modalities = cp.get('avoid_modalities') or []
            pseudo.limitations = cp.get('limitations') or []
            pseudo.z2_baseline = cp.get('z2_baseline') or {}
            pseudo.interval_test = cp.get('interval_test') or {}
            pseudo.hr_recovery = cp.get('hr_recovery') or {}

            normalized = normalize_cardio_profile(
                pseudo,
                concerns=assessment.get('concerns'),
                constraints_rich=assessment.get('constraints_rich'),
            )
            machine_id, machine_rat, rejected = decide_machine_with_audit(normalized)
            clearance = determine_interval_clearance(normalized)
            contradictions = detect_contradictions(normalized)
            flags = generate_cardio_coach_flags(normalized)
            machine_label = MODALITY_DISPLAY.get(machine_id, machine_id)

            # ── DECISIONS section ──
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9)
            c.drawString(MARGIN, y, "DECISIONS")
            y -= 11
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 9)
            c.drawString(MARGIN + 14, y, f"machine selected: {machine_label}")
            y -= 11
            # Wrap rationale
            rat_text = f"reason: {machine_rat}"
            for line in _wrap_to_lines(c, rat_text, CONTENT_W - 30, SERIF_ITALIC, 9, max_lines=3):
                c.drawString(MARGIN + 14, y, line)
                y -= 11
            if rejected:
                c.setFillColor(LIMITED)
                c.setFont(SERIF_ITALIC, 9)
                c.drawString(MARGIN + 14, y, "alternatives rejected:")
                y -= 11
                for r in rejected[:5]:
                    rname = MODALITY_DISPLAY.get(r['machine'], r['machine'])
                    c.drawString(MARGIN + 28, y, f"· {rname} → {r['reason'][:75]}")
                    y -= 11
            y -= 4

            # ── CONTRADICTIONS RESOLVED section ──
            if contradictions:
                c.setFillColor(CREAM)
                c.setFont(SANS_MEDIUM, 9)
                c.drawString(MARGIN, y, "CONTRADICTIONS RESOLVED")
                y -= 11
                for ct in contradictions[:5]:
                    sev_color = (LIMITED if ct['severity'] == 'error'
                                  else (SKY_BLUE if ct['severity'] == 'warning' else CREAM_DIM))
                    c.setFillColor(sev_color)
                    c.setFont(SERIF_ITALIC, 9)
                    msg = f"[{ct['severity']}] {ct['message']}"
                    for line in _wrap_to_lines(c, msg, CONTENT_W - 30, SERIF_ITALIC, 9, max_lines=2):
                        c.drawString(MARGIN + 14, y, line)
                        y -= 11
                    c.setFillColor(CREAM_DIM)
                    res_text = f"  → {ct['resolution']}"
                    for line in _wrap_to_lines(c, res_text, CONTENT_W - 36, SERIF_ITALIC, 9, max_lines=2):
                        c.drawString(MARGIN + 20, y, line)
                        y -= 11
                y -= 4

            # ── INTERVAL CLEARANCE ──
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9)
            c.drawString(MARGIN, y, f"INTERVAL CLEARANCE · {clearance.upper()}")
            y -= 14

            # ── COACH FLAGS ──
            if flags:
                c.setFillColor(CREAM)
                c.setFont(SANS_MEDIUM, 9)
                c.drawString(MARGIN, y, "COACH FLAGS")
                y -= 11
                for flag in flags[:6]:
                    color = LIMITED if any(w in flag.lower()
                                             for w in ("not cleared", "blocked", "no intervals",
                                                        "active flare", "post-surgery", "poor"))\
                            else (OPTIMAL if "strong" in flag.lower() or "good hr" in flag.lower()
                                  else SKY_BLUE)
                    c.setFillColor(color)
                    c.setFont(SERIF_ITALIC, 9)
                    text = flag.strip()
                    while text:
                        chunk = text[:105]
                        if len(text) > 105:
                            sp = chunk.rfind(' ')
                            if sp > 60:
                                chunk = chunk[:sp]
                        c.drawString(MARGIN + 14, y, chunk)
                        y -= 11
                        text = text[len(chunk):].lstrip()
                y -= 4
        except Exception:
            pass

    # ── 4 · PICKER · SUBSTITUTION RATIONALE ────────────
    # Walk the program for any exercise with a non-null rationale
    sub_lines = []
    for week in program.get('weeks', [])[:1]:  # week 1 only
        for sess in week.get('sessions', [])[:6]:
            for blk in sess.get('blocks', []):
                for ex in blk.get('exercises', []):
                    rat = ex.get('rationale')
                    if rat and ('care' in rat.lower() or 'concern' in rat.lower()
                                or 'spine' in rat.lower() or 'flagged' in rat.lower()
                                or 'tested' in rat.lower()):
                        sub_lines.append((ex.get('name', '?'), rat))

    # Dedupe by exercise name
    seen = set()
    sub_lines_unique = []
    for n, r in sub_lines:
        if n not in seen:
            seen.add(n)
            sub_lines_unique.append((n, r))

    if sub_lines_unique:
        small_caps_label(c, "PICKER · SUBSTITUTION RATIONALE", MARGIN, y, color=SKY_BLUE, size=10)
        lw = c.stringWidth("PICKER · SUBSTITUTION RATIONALE", SANS_MEDIUM, 10)
        thin_divider(c, MARGIN + lw + 12, y + 3, PAGE_W - MARGIN, color=DIVIDER, width=0.5)
        y -= 18

        for name, rat in sub_lines_unique[:10]:
            c.setFillColor(CREAM)
            c.setFont(SANS_MEDIUM, 9.5)
            c.drawString(MARGIN, y, f"{name}")
            y -= 11
            c.setFillColor(CREAM_DIM)
            c.setFont(SERIF_ITALIC, 9)
            c.drawString(MARGIN + 14, y, f"{rat[:100]}")
            y -= 14

    # Bottom note
    y -= 12
    c.setFillColor(CREAM_DIM)
    c.setFont(SERIF_ITALIC, 9)
    c.drawString(MARGIN, y, "Coach-only · do not share with client.")


def generate_plan_pdf(program_json: str, output_pdf: str, pdf_mode: str = "client"):
    """Render the program PDF.

    pdf_mode controls what sections appear ·
      "client" · clean polished plan, no coach-only content
      "coach"  · coach-facing only · math, flags, substitution rationale
      "full"   · client content + coach appendix at the end
    """
    if pdf_mode not in ("client", "coach", "full"):
        pdf_mode = "client"

    with open(program_json) as f:
        program = json.load(f)

    # Stash mode on the program dict so individual draw_* functions can read it
    program['_pdf_mode'] = pdf_mode

    c = canvas.Canvas(output_pdf, pagesize=LETTER)
    title_suffix = {
        "client": "",
        "coach": " · Coach Plan",
        "full": " · Full Plan",
    }[pdf_mode]
    c.setTitle(f"IMS Body & Movement Plan · {program['client_name']}{title_suffix}")
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
        draw_nutrition_pantry,
        draw_nutrition_day,
        draw_weekly_map,
        draw_tracking,
        draw_stay_connected,
    ]

    # In coach mode, replace the client-facing flow entirely with the coach appendix.
    # In full mode, run client flow then append the coach appendix at the end.
    if pdf_mode == "coach":
        base_pages = [draw_cover, draw_coach_appendix]
        closing_pages = []

    # Session detail pages · may run to multiple pages each due to 8 blocks
    # Pre-render to count actual page usage
    assessment = program.get('assessment', {})
    sd = assessment.get('strength_days', 0) or 0
    cd = assessment.get('cardio_days', 0) or 0
    if sd == 0 and cd == 0:
        freq = assessment.get('training_frequency', 3)
        if freq <= 2:
            sd, cd = 2, 0
        elif freq == 3:
            sd, cd = 2, 1
        else:
            sd, cd = 3, 1

    day_map = _spread_days_across_week(sd, cd, num_sessions)

    # Rough estimate · strength sessions use 3 pages (intro+Strength A / Strength B+finishers)
    # due to forced page break between A and B. Cardio uses 1 page.
    est_session_pages = 0
    if pdf_mode != "coach":  # coach mode skips session pages entirely
        for i in range(num_sessions):
            sess = program['weeks'][0]['sessions'][i]
            if sess.get('day_type', '').startswith('strength'):
                est_session_pages += 3
            else:
                est_session_pages += 1

    # In full mode, the coach appendix adds one extra page at the end
    appendix_pages = 1 if pdf_mode == "full" else 0
    total = len(base_pages) + est_session_pages + len(closing_pages) + appendix_pages

    # Draw base pages with updated total
    page_num = 0
    for fn in base_pages:
        page_num += 1
        fn(c, program)
        if page_num > 1:
            page_footer(c, page_num, total)
        c.showPage()

    # Draw sessions · each may consume 1-2 pages (skipped in coach mode)
    if pdf_mode != "coach":
        for i in range(num_sessions):
            day_in_week = day_map.get(i + 1, i + 1)
            pages_used = draw_session_page(c, program, i, day_in_week,
                                           page_num + 1, total)
            page_num += pages_used

    # Draw closing
    for fn in closing_pages:
        page_num += 1
        fn(c, program)
        page_footer(c, page_num, total)
        c.showPage()

    # Append coach appendix in full mode
    if pdf_mode == "full":
        page_num += 1
        draw_coach_appendix(c, program)
        page_footer(c, page_num, total)
        c.showPage()

    c.save()
    print(f"PDF generated · mode={pdf_mode} · {output_pdf}  (~{total} pages, actual = {page_num})")


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
