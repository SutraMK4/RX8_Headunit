"""
screens/home_screen.py
-----------------------
Home screen / dashboard overview.
Shows quick-status tiles: OBD connection, time, temp summary.
Tapping a tile navigates to the relevant screen.

TODO (your design pass):
- Replace placeholder tiles with styled cards
- Add background graphic / RX-8 silhouette
- Add startup animation
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from core import theme


class HomeScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

        # Refresh status tiles every 2 seconds
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 12)
        layout.setSpacing(16)

        # ── Title ──────────────────────────────────────────────────
        title = QLabel("RX-8 HEAD UNIT")
        title.setStyleSheet(f"""
            color: {theme.ACCENT};
            font-size: {theme.FONT_SIZE_XL}pt;
            font-weight: bold;
            letter-spacing: 4px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("2004 · 6-PORT · 238HP · 6MT")
        subtitle.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 3px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # ── Quick-launch tiles ─────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)

        tiles = [
            ("gauges",     "◎",  "GAUGES",     "RPM · TEMP · OBD"),
            ("navigation", "⊕",  "NAVIGATION", "Offline Maps · GPS"),
            ("audio",      "♪",  "AUDIO",      "Bose · Source"),
            ("settings",   "⚙",  "SETTINGS",   "Config · System"),
        ]

        for i, (screen, icon, label, sub) in enumerate(tiles):
            tile = QuickTile(icon, label, sub, lambda s=screen: self.main_window.switch_screen(s))
            grid.addWidget(tile, i // 2, i % 2)

        layout.addLayout(grid)

        # ── Status bar ─────────────────────────────────────────────
        self._status_bar = StatusBar(self.state)
        layout.addWidget(self._status_bar)

    def _refresh_status(self):
        self._status_bar.refresh()


# ──────────────────────────────────────────────────────────────────
#  Quick-launch tile
# ──────────────────────────────────────────────────────────────────
class QuickTile(QPushButton):
    def __init__(self, icon, label, subtitle, on_click):
        super().__init__()
        self.setFixedHeight(90)
        self.clicked.connect(on_click)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme.BG_CARD};
                border: 1px solid {theme.BORDER};
                border-radius: 8px;
                text-align: left;
                padding: 12px 16px;
            }}
            QPushButton:hover {{
                background-color: {theme.BG_HOVER};
                border: 1px solid {theme.ACCENT_DIM};
            }}
            QPushButton:pressed {{
                background-color: {theme.ACCENT_DIM};
            }}
        """)

        inner = QVBoxLayout(self)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(2)

        top = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color: {theme.ACCENT}; font-size: {theme.FONT_SIZE_LG}pt; background: transparent;")
        top.addWidget(icon_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"""
            color: {theme.TEXT_PRIMARY};
            font-size: {theme.FONT_SIZE_MD}pt;
            font-weight: bold;
            letter-spacing: 2px;
            background: transparent;
        """)
        top.addWidget(name_lbl)
        top.addStretch()
        inner.addLayout(top)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt; background: transparent;")
        inner.addWidget(sub_lbl)


# ──────────────────────────────────────────────────────────────────
#  Status bar
# ──────────────────────────────────────────────────────────────────
class StatusBar(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self._obd_lbl  = QLabel()
        self._temp_lbl = QLabel()

        for lbl in (self._obd_lbl, self._temp_lbl):
            lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
            layout.addWidget(lbl)

        layout.addStretch()
        self.refresh()

    def refresh(self):
        status = self.state.obd_status
        colours = {
            "connected":    theme.SUCCESS_GREEN,
            "connecting":   theme.WARN_ORANGE,
            "error":        theme.WARN_RED,
            "disconnected": theme.TEXT_DIM,
        }
        col = colours.get(status, theme.TEXT_DIM)
        self._obd_lbl.setText(f"OBD: <span style='color:{col}'>{status.upper()}</span>")
        self._obd_lbl.setTextFormat(Qt.RichText)

        # Pi CPU temp (Linux only)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp_c = int(f.read().strip()) / 1000
            self._temp_lbl.setText(f"PI: {temp_c:.0f}°C")
        except Exception:
            self._temp_lbl.setText("")
