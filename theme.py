"""
core/theme.py
-------------
Central theme constants.
Import this everywhere instead of hardcoding colours.
Swap this file out to change the entire UI look.
"""

# ── Colours ────────────────────────────────────────────────────────
BG_PRIMARY    = "#0a0a0f"
BG_SECONDARY  = "#14141e"
BG_CARD       = "#1a1a28"
BG_HOVER      = "#22223a"

ACCENT        = "#c0392b"   # Mazda red
ACCENT_DIM    = "#7a1f1a"
ACCENT_GLOW   = "rgba(192, 57, 43, 80)"

TEXT_PRIMARY  = "#f0f0f0"
TEXT_SECONDARY= "#888899"
TEXT_DIM      = "#444455"

WARN_ORANGE   = "#e67e22"
WARN_RED      = "#e74c3c"
SUCCESS_GREEN = "#27ae60"

BORDER        = "#2a2a40"
BORDER_ACTIVE = "#c0392b"

# ── Fonts ──────────────────────────────────────────────────────────
FONT_MAIN     = "Courier New"   # monospace — readable on 7" screen
FONT_SIZE_SM  = 9
FONT_SIZE_MD  = 11
FONT_SIZE_LG  = 14
FONT_SIZE_XL  = 18
FONT_SIZE_XXL = 24

# ── Dimensions ─────────────────────────────────────────────────────
NAV_BAR_HEIGHT = 56      # bottom navigation bar
SCREEN_W       = 800
SCREEN_H       = 480
CONTENT_H      = SCREEN_H - NAV_BAR_HEIGHT

# ── Stylesheet snippets ────────────────────────────────────────────
def nav_button_style(active=False):
    bg = ACCENT_DIM if active else "transparent"
    border = f"2px solid {ACCENT}" if active else "2px solid transparent"
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {TEXT_PRIMARY if active else TEXT_SECONDARY};
            border: {border};
            border-radius: 6px;
            padding: 6px 12px;
            font-family: {FONT_MAIN};
            font-size: {FONT_SIZE_SM}pt;
            font-weight: bold;
            letter-spacing: 2px;
        }}
        QPushButton:hover {{
            background-color: {BG_HOVER};
            color: {TEXT_PRIMARY};
        }}
    """

GLOBAL_STYLESHEET = f"""
    QWidget {{
        background-color: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        font-family: {FONT_MAIN};
    }}
    QLabel {{
        color: {TEXT_PRIMARY};
        font-family: {FONT_MAIN};
    }}
    QScrollBar:vertical {{
        background: {BG_SECONDARY};
        width: 6px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical {{
        background: {ACCENT_DIM};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
"""
