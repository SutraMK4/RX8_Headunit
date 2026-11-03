"""
core/obd_manager.py
--------------------
Manages the OBD-II connection in a background thread.
Emits Qt signals so the UI can react without blocking.

Usage:
    manager = OBDManager(state)
    manager.status_changed.connect(my_slot)
    manager.start()
"""

import obd
from PyQt5.QtCore import QThread, pyqtSignal


class OBDManager(QThread):
    status_changed = pyqtSignal(str)          # 'disconnected' | 'connecting' | 'connected' | 'error'
    connection_ready = pyqtSignal(object)     # emits the obd.Async connection object

    def __init__(self, state):
        super().__init__()
        self.state = state
        self._connection = None
        self._running = False

    def run(self):
        self._running = True
        self.status_changed.emit("connecting")
        self.state.obd_status = "connecting"

        port = self.state.get("obd", "port")
        if port == "auto":
            port = None   # python-obd will scan automatically

        try:
            self._connection = obd.Async(
                portstr=port,
                fast=False,       # more reliable on RX-8
                timeout=30,
            )

            if self._connection.status() == obd.OBDStatus.CAR_CONNECTED:
                self.state.obd_connection = self._connection
                self.state.obd_status = "connected"
                self.status_changed.emit("connected")
                self.connection_ready.emit(self._connection)
            else:
                self.state.obd_status = "error"
                self.status_changed.emit("error")

        except Exception as e:
            print(f"[OBDManager] Connection failed: {e}")
            self.state.obd_status = "error"
            self.status_changed.emit("error")

    def disconnect(self):
        if self._connection:
            self._connection.close()
            self._connection = None
        self.state.obd_connection = None
        self.state.obd_status = "disconnected"
        self.status_changed.emit("disconnected")

    def scan_ports(self):
        """Returns list of available serial ports for settings screen."""
        return obd.scan_serial()
