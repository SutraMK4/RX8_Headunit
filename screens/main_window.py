"""
screens/main_window.py
-----------------------
Root window. Contains the bottom navigation bar and a QStackedWidget
that holds all screens. This is the only window — screens swap in/out.
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget, QLabel
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from core import theme
from screens.home_screen import HomeScreen
from screens.gauge_screen import GaugeScreen
from screens.navigation_screen import NavigationScreen
from screens.audio_screen import AudioScreen
from screens.settings_screen import SettingsScreen


class MainWindow(QMainWindow):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setWindowTitle("RX-8 Head Unit")
        self.setStyleSheet(theme.GLOBAL_STYLESHEET)

        # ── Root layout ────────────────────────────────────────────
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Screen stack ───────────────────────────────────────────
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        # ── Bottom nav bar ─────────────────────────────────────────
        self.nav_bar = NavBar(self)
        layout.addWidget(self.nav_bar)

        # ── Screens ────────────────────────────────────────────────
        self.screens = {}
        self._add_screen("home",       HomeScreen(state, self))
        self._add_screen("gauges",     GaugeScreen(state, self))
        self._add_screen("navigation", NavigationScreen(state, self))
        self._add_screen("audio",      AudioScreen(state, self))
        self._add_screen("settings",   SettingsScreen(state, self))

        # ── Boot to configured default screen ──────────────────────
        start = state.config.get("startup", {}).get("default_screen", "home")
        self.switch_screen(start)

        # ── Clock timer (used by nav bar) ──────────────────────────
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self.nav_bar.update_clock)
        self._clock_timer.start()

    def _add_screen(self, name, widget):
        self.screens[name] = widget
        self.stack.addWidget(widget)

    def switch_screen(self, name):
        if name in self.screens:
            self.stack.setCurrentWidget(self.screens[name])
            self.state.current_screen = name
            self.nav_bar.set_active(name)

    # ── Keyboard shortcuts ─────────────────────────────────────────
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.switch_screen("home")
        elif key == Qt.Key_F:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif key == Qt.Key_1:
            self.switch_screen("home")
        elif key == Qt.Key_2:
            self.switch_screen("gauges")
        elif key == Qt.Key_3:
            self.switch_screen("navigation")
        elif key == Qt.Key_4:
            self.switch_screen("audio")
        elif key == Qt.Key_5:
            self.switch_screen("settings")
        super().keyPressEvent(event)


# ──────────────────────────────────────────────────────────────────
#  Navigation bar
# ──────────────────────────────────────────────────────────────────
class NavBar(QWidget):
    NAV_ITEMS = [
        ("home",       "⌂  HOME"),
        ("gauges",     "◎  GAUGES"),
        ("navigation", "⊕  NAV"),
        ("audio",      "♪  AUDIO"),
        ("settings",   "⚙  SETTINGS"),
    ]

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setFixedHeight(theme.NAV_BAR_HEIGHT)
        self.setStyleSheet(f"background-color: {theme.BG_SECONDARY}; border-top: 1px solid {theme.BORDER};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self._buttons = {}
        for screen_name, label in self.NAV_ITEMS:
            btn = QPushButton(label)
            btn.setFixedHeight(theme.NAV_BAR_HEIGHT - 12)
            btn.setStyleSheet(theme.nav_button_style(active=False))
            btn.clicked.connect(lambda _, s=screen_name: main_window.switch_screen(s))
            layout.addWidget(btn)
            self._buttons[screen_name] = btn

        # Clock on the right
        layout.addStretch()
        self._clock_label = QLabel("")
        self._clock_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SM}pt;")
        layout.addWidget(self._clock_label)
        self.update_clock()

    def set_active(self, screen_name):
        for name, btn in self._buttons.items():
            btn.setStyleSheet(theme.nav_button_style(active=(name == screen_name)))

    def update_clock(self):
        from datetime import datetime
        self._clock_label.setText(datetime.now().strftime("%H:%M"))
