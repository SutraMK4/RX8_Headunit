"""
core/data_manager.py
--------------------
Owns the one active DataSource and re-broadcasts its signals, so screens
connect once to the manager and never care when the source is swapped.

    manager = DataManager(state)
    manager.values_updated.connect(gauge_screen.on_values)
    manager.start()                 # uses state.config["data"]["source"]
    manager.switch("emulator")      # stop current, start another

Which source and its options come from state.config:

    "data": {"source": "simulated" | "live" | "emulator" | "replay",
             "emulator_port": "socket://localhost:35000",
             "replay_file": "C:/.../idle.csv", "replay_speed": 1.0,
             "replay_loop": true}
    "obd":  {"port": "auto" | "COM5" | "/dev/serial/by-id/usb-...",
             "fast": false, "timeout": 30}
"""

import logging

from PyQt5.QtCore import QObject, pyqtSignal

from core.diagnostics import timed, record_error

from core.data_sources import (
    DEFAULT_KEYS, SOURCE_KINDS,
    SimulatedSource, LiveSource, EmulatorSource, ReplaySource,
    STATUS_RUNNING, STATUS_CONNECTING, STATUS_ERROR, STATUS_FINISHED,
)


log = logging.getLogger("rx8.data")


class DataManager(QObject):
    values_updated = pyqtSignal(dict)
    status_changed = pyqtSignal(str, str, str)   # (kind, status, detail)

    def __init__(self, state, keys=DEFAULT_KEYS, parent=None):
        super().__init__(parent)
        self.state = state
        self.keys = tuple(keys)
        self.source = None
        self.state.obd_status = "stopped"

    # ── public API ─────────────────────────────────────────────────
    @property
    def kind(self):
        return self.source.kind if self.source else None

    def start(self):
        self.switch(self.state.get("data", "source", default="simulated"))

    def switch(self, kind):
        if kind not in SOURCE_KINDS:
            log.warning("unknown source '%s', using simulated", kind)
            kind = "simulated"
        log.info("switching data source to '%s'", kind)
        self.stop()
        with timed(f"data.start.{kind}"):
            self.source = self._build(kind)
            self.source.values_updated.connect(self.values_updated)
            self.source.status_changed.connect(self._on_status)
            self.source.start()

    def restart(self):
        self.switch(self.kind or self.state.get("data", "source", default="simulated"))

    def stop(self):
        if self.source is None:
            return
        old = self.source
        self.source = None
        old.stop()
        old.status_changed.disconnect()
        old.values_updated.disconnect()
        old.deleteLater()
        self._publish(None, "idle", "stopped")

    def shutdown(self):
        """Connect to QApplication.aboutToQuit. Never blocks: a connect still
        in progress runs in a daemon thread and is simply abandoned."""
        self.stop()

    def supported_command_names(self):
        return self.source.supported_command_names() if self.source else []

    # ── internals ──────────────────────────────────────────────────
    def _build(self, kind):
        get = self.state.get
        if kind == "live":
            port = get("obd", "port", default="auto")
            return LiveSource(self.keys,
                              port=None if port in ("", "auto") else port,
                              fast=get("obd", "fast", default=False),
                              timeout=get("obd", "timeout", default=30))
        if kind == "emulator":
            return EmulatorSource(self.keys,
                                  port=get("data", "emulator_port",
                                           default="socket://localhost:35000"))
        if kind == "replay":
            return ReplaySource(self.keys,
                                path=get("data", "replay_file", default=""),
                                speed=get("data", "replay_speed", default=1.0),
                                loop=get("data", "replay_loop", default=True))
        return SimulatedSource(self.keys)

    def _on_status(self, status, detail):
        self._publish(self.kind, status, detail)
        if status == STATUS_ERROR:
            # Not an exception (python-obd reports problems as status), so
            # there is no stack; python-obd's own messages are in the log.
            record_error(f"data.{self.kind}", message=detail,
                         trace="Reported as a status, not an exception (no stack).\n"
                               "python-obd's own messages are in the LOG tab.",
                         level=logging.WARNING)
        else:
            log.info("%s: %s %s", self.kind, status, detail)

    def _publish(self, kind, status, detail):
        # Short summary for the home screen: what is feeding the gauges.
        if status == STATUS_RUNNING:
            self.state.obd_status = kind
        elif status in (STATUS_CONNECTING, STATUS_ERROR):
            self.state.obd_status = status
        elif status == STATUS_FINISHED:
            self.state.obd_status = "replay ended"
        else:
            self.state.obd_status = "stopped"
        self.status_changed.emit(kind or "", status, detail)
