#!/usr/bin/env python3
"""
RX-8 Head Unit — Main Launcher
-------------------------------
Entry point. Boots the main window with tab navigation.
Run: python3 main.py
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from core.app_state import AppState
from screens.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RX-8 Head Unit")

    # Global application state — shared across all screens
    state = AppState()

    window = MainWindow(state)

    # Fullscreen on real hardware; windowed in dev
    if state.config.get("startup", {}).get("fullscreen", False):
        window.showFullScreen()
    else:
        window.resize(800, 480)   # Waveshare 7" native resolution
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
