"""
screens/v2_widgets.py
---------------------
Building blocks for layout v2 ("Night drive", from Figma).

    SvgView     draws an SVG from assets/<set>/<name>.svg, optional tint
    Canvas      a widget whose children are placed at Figma coordinates
                (scaled with theme.v2px) — used for static compositions
    NavBarV2    bottom navigation bar of layout v2 (all screens)
"""

import logging
import os

from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtGui import QPainter, QColor, QPixmap, QFont, QFontMetrics
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget, QLabel, QAbstractButton

from core import theme, fonts
from core.theme import v2px, v2text

log = logging.getLogger("rx8.ui")

ASSET_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_missing_logged = set()


def label_style(colour, role):
    """QLabel style for v2. The app-wide stylesheet sets font-family on every
    QLabel, which overrides setFont(); naming the family here wins."""
    return (f"color: {colour}; background: transparent; "
            f"font-family: '{fonts.family(role)}';")


def asset_path(asset_set, name):
    return os.path.join(ASSET_ROOT, asset_set, name + ".svg")


def load_svg(asset_set, name):
    """QSvgRenderer or None (logged once) if the file is missing/invalid."""
    path = asset_path(asset_set, name)
    if not os.path.isfile(path):
        if path not in _missing_logged:
            _missing_logged.add(path)
            log.warning("missing asset %s — run: py tools/fetch_figma_assets.py %s",
                        os.path.relpath(path, ASSET_ROOT), asset_set)
        return None
    r = QSvgRenderer(path)
    return r if r.isValid() else None


def paint_svg(painter, renderer, rect, tint=None):
    """Render an SVG into rect (keeps aspect ratio, centred). With tint, all
    opaque pixels take that colour (for single-colour icons)."""
    if renderer is None:
        return
    size = renderer.defaultSize()
    if size.isEmpty():
        target = QRectF(rect)
    else:
        s = min(rect.width() / size.width(), rect.height() / size.height())
        w, h = size.width() * s, size.height() * s
        target = QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h)
    if tint is None:
        renderer.render(painter, target)
        return
    dpr = painter.device().devicePixelRatioF() if hasattr(painter.device(), "devicePixelRatioF") else 1.0
    pm = QPixmap(int(target.width() * dpr) + 1, int(target.height() * dpr) + 1)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, target.width() * dpr, target.height() * dpr))
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), QColor(tint))
    p.end()
    pm.setDevicePixelRatio(dpr)
    painter.drawPixmap(target.topLeft(), pm)


class SvgView(QWidget):
    def __init__(self, asset_set, name, tint=None, parent=None):
        super().__init__(parent)
        self._renderer = load_svg(asset_set, name)
        self.tint = tint
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_tint(self, tint):
        self.tint = tint
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_svg(p, self._renderer, QRectF(self.rect()), self.tint)


class Canvas(QWidget):
    """Children placed at Figma coordinates (scaled). For static compositions
    where the design is a fixed arrangement, not a flowing layout."""

    def label(self, text, x, y, role, size, colour, weight=None, spacing=None, small=True):
        lbl = QLabel(text, self)
        px = v2text(size) if small else v2px(size)
        lbl.setFont(fonts.font(role, px, weight, spacing))
        lbl.setStyleSheet(label_style(colour, role))
        lbl.ensurePolished()
        lbl.adjustSize()
        dy = 0
        if role == "display" and weight == QFont.Bold:
            # Orbitron Bold is a separate (2009) file with smaller ascent than
            # the variable font Figma measures with; keep Figma's baseline.
            dy = (QFontMetrics(fonts.font(role, px)).ascent()
                  - QFontMetrics(fonts.font(role, px, weight)).ascent())
        lbl.move(v2px(x), v2px(y) + dy)
        return lbl

    def rule(self, x, y, w, h, colour=theme.V2_RULE):
        line = QWidget(self)
        line.setStyleSheet(f"background: {colour};")
        line.setGeometry(v2px(x), v2px(y), max(1, v2px(w)), max(1, v2px(h)))
        return line

    def svg(self, asset_set, name, x, y, w, h, tint=None):
        view = SvgView(asset_set, name, tint, self)
        view.setGeometry(v2px(x), v2px(y), v2px(w), v2px(h))
        return view


# ──────────────────────────────────────────────────────────────────
#  Bottom navigation (Figma node 2:6 "System navigation")
# ──────────────────────────────────────────────────────────────────
class _NavItem(QAbstractButton):
    def __init__(self, screen, label, icon, parent):
        super().__init__(parent)
        self.screen = screen
        self.text_ = label
        self._icon = load_svg("home_v2", icon)
        self.active = False
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        return QSize(v2px(174), v2px(76))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        colour = theme.V2_YELLOW if self.active else theme.V2_MUTED
        if self.isDown():
            p.fillRect(self.rect(), QColor(255, 255, 255, 18))
        # icon 22×22 at (10, 23); label at (46, 26) — Figma coordinates
        paint_svg(p, self._icon, QRectF(v2px(10), v2px(23), v2px(22), v2px(22)), colour)
        p.setPen(QColor(colour))
        p.setFont(fonts.font("mono", v2text(12), weight=57))   # IBM Plex Mono Medium
        p.drawText(QRectF(v2px(46), 0, self.width(), self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text_)


class NavBarV2(QWidget):
    ITEMS = [
        ("home",       "HOME",     "icon_home_nav"),
        ("gauges",     "GAUGES",   "icon_gauges_nav"),
        ("navigation", "NAV",      "icon_nav_nav"),
        ("audio",      "AUDIO",    "icon_audio_nav"),
        ("settings",   "SETTINGS", "icon_settings_nav"),
    ]
    HEIGHT_FIGMA = 76

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setFixedHeight(v2px(self.HEIGHT_FIGMA))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {theme.V2_BG};")
        self._items = {}
        self._active = "home"
        for i, (screen, label, icon) in enumerate(self.ITEMS):
            item = _NavItem(screen, label, icon, self)
            item.clicked.connect(lambda _=False, s=screen: main_window.switch_screen(s))
            self._items[screen] = item

        self._status = QLabel("DATA: —", self)
        self._status.setFont(fonts.font("mono", v2text(11)))
        self._status.setStyleSheet(label_style(theme.V2_CYAN, "mono"))
        self._status_sub = QLabel("", self)
        self._status_sub.setFont(fonts.font("mono", v2text(10)))
        self._status_sub.setStyleSheet(label_style(theme.V2_MUTED, "mono"))

        state = main_window.state
        if state.data is not None:
            state.data.status_changed.connect(self._on_data_status)

    # Figma: bar spans x 40..1400 of the 1440 frame; items every 174 px
    def resizeEvent(self, _event):
        left = v2px(40)
        for i, item in enumerate(self._items.values()):
            item.setGeometry(left + v2px(174) * i, 0, v2px(174), self.height())
        self._status.move(left + v2px(1086), v2px(19))
        self._status_sub.move(left + v2px(1086), v2px(41))
        self._status.resize(v2px(270), v2px(18))
        self._status_sub.resize(v2px(270), v2px(16))

    def paintEvent(self, _event):
        p = QPainter(self)
        left = v2px(40)
        width = self.width() - 2 * left
        p.fillRect(self.rect(), QColor(theme.V2_BG))
        p.fillRect(left, 0, width, 1, QColor("#2a3a43"))
        x = left + v2px(174) * [s for s, _, _ in self.ITEMS].index(self._active)
        p.fillRect(x, 0, v2px(146), max(2, v2px(3)), QColor(theme.V2_YELLOW))

    def set_active(self, screen_name):
        self._active = screen_name if screen_name in self._items else "home"
        for name, item in self._items.items():
            item.active = name == self._active
            item.update()
        self.update()

    def update_clock(self):
        pass   # v2 shows the clock in the screen header, not in the bar

    def _on_data_status(self, kind, status, detail):
        sub = {
            "simulated": "DEMO MODE / NO LIVE OBD",
            "replay":    "REPLAY / RECORDED DRIVE",
            "emulator":  "EMULATOR / NO CAR",
            "live":      "LIVE OBD",
        }
        if status == "running":
            self._status.setText(f"DATA: {kind.upper()}")
            self._status_sub.setText(sub.get(kind, ""))
            colour = theme.V2_CYAN
        elif status == "idle":
            self._status.setText("DATA: STOPPED")
            self._status_sub.setText("")
            colour = theme.V2_MUTED
        else:
            self._status.setText(f"DATA: {kind.upper()} {status.upper()}")
            self._status_sub.setText(detail[:40])
            colour = theme.V2_YELLOW if status == "connecting" else theme.WARN_RED
        self._status.setStyleSheet(label_style(colour, "mono"))
