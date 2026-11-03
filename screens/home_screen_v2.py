"""
screens/home_screen_v2.py
-------------------------
Home screen, layout v2 "Night drive" — implemented from Figma
(file CBKo9oyYbDV1pKuGCFEcy5, frame 2:2 "RX-8 · Night drive startup").

The Figma frame is 1440 × 960; the head unit is 1024 × 600. All Figma
coordinates in this file are the original values, scaled with
theme.v2px() / theme.v2text(), so the code can be compared 1:1 with the
design. Regions (Figma nodes):

    2:3  System header      logo, subtitle, status, clock
    2:4  Vehicle welcome    greeting, RX-8 hero, specs, rotary schematic
    2:5  Launch menu        four module tiles (2 × 2)
    2:6  System navigation  → screens/v2_widgets.NavBarV2 (shared bar)

Assets: assets/home_v2/*.svg (py tools/fetch_figma_assets.py home_v2)
"""

from datetime import datetime

from PyQt5.QtCore import Qt, QRectF, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QLabel, QAbstractButton

from core import theme, fonts
from core.theme import v2px, v2text
from screens.v2_widgets import Canvas, load_svg, paint_svg, label_style

ASSETS = "home_v2"
MEDIUM = 57          # QFont weight for IBM Plex Mono Medium


class HomeScreenV2(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {theme.V2_BG};")

        root = QVBoxLayout(self)
        # Figma: content spans x 40..1400; header starts at y 28
        root.setContentsMargins(v2px(40), v2px(20), v2px(40), v2px(10))
        root.setSpacing(0)

        self._header = Header()
        root.addWidget(self._header)
        root.addSpacing(v2px(18))
        root.addWidget(Welcome(state))
        root.addStretch(1)
        root.addWidget(LaunchMenu(main_window))

        self._clock = QTimer(self)
        self._clock.setInterval(10_000)
        self._clock.timeout.connect(self._header.update_clock)
        self._clock.start()


# ──────────────────────────────────────────────────────────────────
#  2:3 System header (1360 × 56)
# ──────────────────────────────────────────────────────────────────
class Header(Canvas):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(v2px(56))
        self.label("MAZDA", 0, 7, "display", 24, theme.V2_TEXT, QFont.Bold, small=False)
        self.rule(155, 10, 1, 25)
        self.label("ROTARY // DRIVER INTERFACE", 177, 15, "mono", 12, theme.V2_MUTED)
        self._online = self.label("●  SYSTEM ONLINE", 922, 15, "mono", 12, theme.V2_CYAN)
        self._time = self.label("00:00", 1238, 7, "heading", 24, theme.V2_TEXT, small=False)
        self.label("LOCAL", 1310, 17, "mono", 10, theme.V2_MUTED)
        self.update_clock()

    def update_clock(self):
        self._time.setText(datetime.now().strftime("%H:%M"))
        self._time.ensurePolished()
        self._time.adjustSize()

    def paintEvent(self, _event):
        # bottom hairline across, short yellow accent at the left (2:13, 2:14)
        p = QPainter(self)
        y = self.height() - 1
        p.fillRect(0, y, self.width(), 1, QColor(theme.V2_RULE))
        p.fillRect(0, y, v2px(74), max(2, v2px(2)), QColor(theme.V2_YELLOW))


# ──────────────────────────────────────────────────────────────────
#  2:4 Vehicle welcome (1360 × 370)
# ──────────────────────────────────────────────────────────────────
class Welcome(Canvas):
    SPECS = [("MODEL", "2004"), ("ENGINE", "6-PORT"), ("POWER", "238HP"), ("GEARBOX", "6MT")]

    def __init__(self, state):
        super().__init__()
        self.setFixedHeight(v2px(370))
        name = state.get("system", "driver_name", default="Roger")

        self.label("DRIVER IDENTIFIED   /   01", 0, 16, "mono", 12, theme.V2_CYAN)
        self.label(f"Ciao {name}!", 0, 49, "heading", 34, theme.V2_TEXT, small=False)
        self.label("RX-8", -4, 95, "display", 102, theme.V2_YELLOW, QFont.Bold,
                   spacing=-4.08 * theme.V2_SCALE, small=False)
        self.label("THE NIGHT IS YOURS.", 2, 224, "heading", 22, theme.V2_TEXT, small=False)
        self.label("All systems ready. Choose your next move.", 2, 256, "mono", 13, theme.V2_MUTED)

        for i, (key, value) in enumerate(self.SPECS):
            x = 132 * i
            self.label(key, x, 310, "mono", 10, theme.V2_MUTED)
            self.label(value, x, 330, "heading", 19, theme.V2_TEXT, small=False)
            if i:
                self.rule(x - 21, 313, 1, 36)

        # Rotary schematic (2:31) with its annotations
        self.svg(ASSETS, "rotary_schematic", 706, 0, 600, 370)
        self.label("RENESIS", 1154, 45, "mono", 12, theme.V2_CYAN, MEDIUM)
        self.label("13B-MSP", 1154, 64, "mono", 10, theme.V2_MUTED)
        self.label("ROTARY CORE", 1151, 286, "mono", 10, theme.V2_CYAN)
        self.label("2 × 654 cc", 1151, 303, "mono", 10, theme.V2_MUTED)
        self.label("POWERTRAIN / READY", 724, 300, "mono", 10, theme.V2_CYAN)
        self.label("SCHEMATIC   01 / 08", 914, 349, "mono", 10, theme.V2_MUTED)


# ──────────────────────────────────────────────────────────────────
#  2:5 Launch menu — header row + 2 × 2 module tiles (668 × 120 each)
# ──────────────────────────────────────────────────────────────────
MODULES = [
    # screen,      title,        line 1,               line 2,                         icon,                 primary
    ("gauges",     "GAUGES",     "RPM · TEMP · OBD",   "Live vehicle telemetry",       "icon_gauges_tile",   True),
    ("navigation", "NAVIGATION", "Offline Maps · GPS", "Find your next destination",   "icon_nav_tile",      False),
    ("audio",      "AUDIO",      "Bose · Source",      "Set the soundtrack",           "icon_audio_tile",    False),
    ("settings",   "SETTINGS",   "Config · System",    "Make it your machine",         "icon_settings_tile", False),
]


class LaunchMenu(QWidget):
    def __init__(self, main_window):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(v2px(18))

        top = QHBoxLayout()
        for text, align in (("01 / LAUNCH CONTROL", Qt.AlignLeft), ("SELECT A MODULE  ↗", Qt.AlignRight)):
            lbl = QLabel(text)
            lbl.setFont(fonts.font("mono", v2text(11)))
            lbl.setStyleSheet(label_style(theme.V2_MUTED, "mono"))
            top.addWidget(lbl, alignment=align)
        lay.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(v2px(24))
        grid.setVerticalSpacing(v2px(18))
        for i, (screen, title, l1, l2, icon, primary) in enumerate(MODULES):
            tile = ModuleTile(i + 1, title, l1, l2, icon, primary)
            tile.clicked.connect(lambda _=False, s=screen: main_window.switch_screen(s))
            grid.addWidget(tile, i // 2, i % 2)
        lay.addLayout(grid)


# The Figma frame (1440 × 960) is relatively taller than the screen
# (1024 × 600). Scaling by width leaves ~27 px too little height, so the
# tiles are drawn at 108 instead of 120 Figma px high; their contents are
# spread over the reduced height (TILE_Y).
TILE_H_FIGMA = 108
TILE_Y = TILE_H_FIGMA / 120


class ModuleTile(QAbstractButton):
    """One launch tile. The chamfered surface is the Figma SVG; text is drawn
    in code so it stays sharp and can change (e.g. live status later)."""

    def __init__(self, number, title, line1, line2, icon, primary=False):
        super().__init__()
        self.number, self.title, self.line1, self.line2 = number, title, line1, line2
        self.primary = primary
        self._surface = load_svg(ASSETS, "tile_surface_active" if primary else "tile_surface")
        self._icon = load_svg(ASSETS, icon)
        self._arrow = load_svg(ASSETS, "arrow_dark" if primary else "arrow_light")
        self.setFixedHeight(v2px(TILE_H_FIGMA))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect())

        if self._surface is not None:
            self._surface.render(p, r)          # stretch to tile, like the design
        else:                                   # asset missing: plain fallback
            p.fillRect(r, QColor(theme.V2_YELLOW if self.primary else theme.V2_SURFACE))

        title_c = theme.V2_ON_YELLOW if self.primary else theme.V2_TEXT
        sub_c = theme.V2_ON_YELLOW_2 if self.primary else theme.V2_MUTED

        def y(figma_y):
            return v2px(figma_y * TILE_Y)

        paint_svg(p, self._icon, QRectF(v2px(23), y(21), v2px(34), v2px(34)))
        p.setPen(QColor(title_c))
        p.setFont(fonts.font("heading", v2px(30)))
        p.drawText(QRectF(v2px(80), y(12), r.width(), v2px(40)), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(QColor(sub_c))
        p.setFont(fonts.font("mono", v2text(12)))
        p.drawText(QRectF(v2px(81), y(55), r.width(), v2px(18)), Qt.AlignLeft | Qt.AlignVCenter, self.line1)
        p.setFont(fonts.font("mono", v2text(11)))
        p.drawText(QRectF(v2px(81), y(88), r.width(), v2px(18)), Qt.AlignLeft | Qt.AlignVCenter, self.line2)
        # number and launch arrow, aligned to the right edge (Figma: 578 / 622 of 668)
        right = r.width()
        p.drawText(QRectF(right - v2px(90), y(20), v2px(30), v2px(20)),
                   Qt.AlignLeft | Qt.AlignVCenter, f"{self.number:02d}")
        paint_svg(p, self._arrow, QRectF(right - v2px(46), y(25), v2px(20), v2px(20)))

        if self.isDown():                       # touch feedback
            p.fillRect(r, QColor(255, 255, 255, 28))
