"""
screens/navigation_screen.py
-----------------------------
Navigation screen.
Placeholder skeleton — ready for map integration.

Integration path:
- Option A: Embed a Chromium/WebEngine view running a local tile server (e.g. Nominatim + Leaflet)
- Option B: Launch Navit as a subprocess and embed its window via QWindow.fromWinId()
- Option C: Use PyQt5 QWebEngineView with an offline OpenStreetMap tile cache

TODO:
- Integrate chosen map solution
- Wire GPS device (gpsd or direct serial read from /dev/ttyUSB0)
- Add search bar
- Add route controls
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt5.QtCore import Qt
from core import theme


class NavigationScreen(QWidget):
    def __init__(self, state, main_window):
        super().__init__()
        self.state = state
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top bar ────────────────────────────────────────────────
        top_bar = TopBar(self.state)
        layout.addWidget(top_bar)

        # ── Map area (placeholder) ─────────────────────────────────
        self._map_area = MapPlaceholder()
        layout.addWidget(self._map_area, stretch=1)

        # ── Bottom controls ────────────────────────────────────────
        bottom = BottomControls()
        layout.addWidget(bottom)


class TopBar(QWidget):
    def __init__(self, state):
        super().__init__()
        self.setFixedHeight(44)
        self.setStyleSheet(f"background-color: {theme.BG_SECONDARY}; border-bottom: 1px solid {theme.BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        # GPS status
        self._gps_label = QLabel("GPS: NO FIX")
        self._gps_label.setStyleSheet(f"color: {theme.WARN_ORANGE}; font-size: {theme.FONT_SIZE_SM}pt; letter-spacing: 2px;")
        layout.addWidget(self._gps_label)

        layout.addStretch()

        # Search bar placeholder
        search = QLabel("[ Search destination ]")
        search.setStyleSheet(f"""
            color: {theme.TEXT_DIM};
            font-size: {theme.FONT_SIZE_SM}pt;
            background-color: {theme.BG_CARD};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 4px 12px;
        """)
        layout.addWidget(search)

        layout.addStretch()

        # Speed display
        self._speed_label = QLabel("-- km/h")
        self._speed_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        layout.addWidget(self._speed_label)


class MapPlaceholder(QFrame):
    """
    Replace this widget with your actual map view.
    The frame gives you the correct geometry to work with.
    """
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: #0d1117; border: none;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("⊕")
        icon.setStyleSheet(f"color: {theme.ACCENT_DIM}; font-size: 48pt;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        msg = QLabel("MAP VIEW")
        msg.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_LG}pt; letter-spacing: 4px;")
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        sub = QLabel("Integrate Navit · OpenStreetMap · or QWebEngineView tile server here")
        sub.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: {theme.FONT_SIZE_SM}pt;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)


class BottomControls(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self.setStyleSheet(f"background-color: {theme.BG_SECONDARY}; border-top: 1px solid {theme.BORDER};")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        buttons = ["◂ BACK", "⌂ HOME", "RECALC", "▴ NORTH", "⊕ GPS"]
        for label in buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(36)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme.BG_CARD};
                    color: {theme.TEXT_SECONDARY};
                    border: 1px solid {theme.BORDER};
                    border-radius: 4px;
                    font-size: {theme.FONT_SIZE_SM}pt;
                    padding: 4px 10px;
                    letter-spacing: 1px;
                }}
                QPushButton:hover {{
                    background-color: {theme.BG_HOVER};
                    color: {theme.TEXT_PRIMARY};
                }}
            """)
            layout.addWidget(btn)

        layout.addStretch()
