#!/usr/bin/env python3
"""
RX-8 Head Unit — Main Launcher
-------------------------------
Entry point. Boots the main window with tab navigation.
Run from the project root:  python3 main.py   (Windows: py main.py)

Options:
  --debug     verbose logging and open the debug panel at start
"""

import argparse
import logging
import sys

from PyQt5.QtWidgets import QApplication


def main():
    ap = argparse.ArgumentParser(description="RX-8 head unit")
    ap.add_argument("--debug", action="store_true",
                    help="verbose logging, open the debug panel at start")
    ap.add_argument("--layout", choices=["v1", "v2"],
                    help="UI layout for this run (overrides the saved setting)")
    args, qt_args = ap.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("RX-8 Head Unit")

    # Diagnostics first, so everything after this is logged and timed
    from core import diagnostics as diag
    from core.app_state import AppState
    state = AppState()
    diag.install(verbose=args.debug or state.get("debug", "verbose", default=False),
                 stall_ms=state.get("debug", "stall_ms", default=diag.STALL_MS),
                 args=" ".join(sys.argv[1:]))
    log = logging.getLogger("rx8")
    if args.layout:
        state.set("display", "layout", args.layout)

    from core import fonts
    with diag.timed("startup.fonts", slow_ms=None):
        fonts.load()

    with diag.timed("startup.total", slow_ms=None):
        from core import theme
        from core.data_manager import DataManager
        from screens.main_window import MainWindow
        from screens.gauge_screen import GAUGE_KEYS

        # Data pipeline: one active source (simulated / live / emulator / replay)
        state.data = DataManager(state, keys=GAUGE_KEYS)
        app.aboutToQuit.connect(state.data.shutdown)
        app.aboutToQuit.connect(diag.shutdown)      # last: stores metrics, marks clean exit

        with diag.timed("startup.main_window", slow_ms=None):
            window = MainWindow(state)

        # Fullscreen on real hardware; windowed in dev
        if state.config.get("startup", {}).get("fullscreen", False):
            window.showFullScreen()
        else:
            window.resize(theme.SCREEN_W, theme.SCREEN_H)
            window.show()

        # Start after the UI exists so the first status reaches every screen
        state.data.start()

    log.info("startup done in %.0f ms", diag.METRICS.snapshot()["startup.total"]["last"])
    if args.debug:
        window.open_debug_panel()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
